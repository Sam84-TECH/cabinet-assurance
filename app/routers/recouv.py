"""
Module Recouvrement (RECOUV).
Un dossier de recouvrement s'ouvre sur une quittance impayée (statut != reglee)
au-delà du délai convenu, avec un historique de relances (amiable puis mise en demeure).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user, exiger_role
from ..recouvrement import (
    calculer_balance_agee, basculer_quittances_en_recouvrement_detaille,
    progresser_dossier, creer_echeancier, _journaliser,
)

router = APIRouter(prefix="/recouv", tags=["Recouvrement"])


@router.get("/balance-agee", response_model=schemas.BalanceAgee)
def balance_agee(db: Session = Depends(get_db),
                 user: models.Utilisateur = Depends(get_current_user)):
    """Balance âgée des créances client impayées (RF-RECOUV-01) : reste dû ventilé par
    ancienneté (0-30, 30-60, 60-90, +90 jours depuis l'exigibilité de la prime). Le reste dû
    exclut les chèques rejetés. Calculée à la demande depuis les quittances (pas de table dédiée)."""
    return calculer_balance_agee(db)


@router.post("/basculer-echus", response_model=schemas.ResultatBasculeRecouv)
def basculer_echus(db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    """Déclenche à la demande la bascule en recouvrement des quittances impayées au-delà du
    délai réglementaire (RF-ECH-04) : même traitement que la tâche planifiée quotidienne
    (app/scheduler.py), utile pour la recette et l'exploitation. Ouvre un dossier par quittance
    échue sans dossier en cours et renvoie un résumé (quittances vérifiées, échues, dossiers
    ouverts, déjà en cours, détail des ouvertures)."""
    return basculer_quittances_en_recouvrement_detaille(db)


@router.post("/dossiers", response_model=schemas.DossierRecouvrementRead)
def ouvrir_dossier(payload: schemas.DossierRecouvrementCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    quittance = crud.get_or_404(db, models.Quittance, payload.quittance_id)
    if quittance.statut == models.StatutQuittance.reglee:
        raise HTTPException(400, "Cette quittance est déjà réglée, pas besoin de recouvrement.")
    data = payload.model_dump()
    data["statut"] = models.StatutDossierRecouv.ouvert  # forcé serveur (anti-contournement)
    return crud.create(db, models.DossierRecouvrement, data)


@router.get("/dossiers", response_model=list[schemas.DossierRecouvrementRead])
def list_dossiers(statut: models.StatutDossierRecouv | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.DossierRecouvrement, skip, limit, statut=statut)


@router.get("/dossiers/{dossier_id}", response_model=schemas.DossierRecouvrementDetailRead)
def get_dossier(dossier_id: int, db: Session = Depends(get_db)):
    """Détail d'un dossier : le dossier + son historique tracé (RF-RECOUV-05), ses relances et
    son éventuel échéancier négocié (RF-RECOUV-04)."""
    return crud.get_or_404(db, models.DossierRecouvrement, dossier_id)


@router.get("/dossiers/{dossier_id}/historique", response_model=list[schemas.EvenementRecouvrementRead])
def historique_dossier(dossier_id: int, db: Session = Depends(get_db)):
    """Historique tracé du dossier (RF-RECOUV-05) : chaque changement d'étape, relance générée,
    échéancier et suspension automatique, du plus ancien au plus récent."""
    crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    return crud.list_all(db, models.EvenementRecouvrement, 0, 1000, dossier_recouvrement_id=dossier_id)


@router.patch("/dossiers/{dossier_id}/progresser", response_model=schemas.DossierRecouvrementDetailRead)
def progresser(dossier_id: int, db: Session = Depends(get_db),
               admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """Fait progresser manuellement le dossier d'une étape de relance à la suivante (RF-RECOUV-02) :
    ouvert -> relance amiable -> mise en demeure -> suspension automatique du contrat. Génère la
    relance datée (RF-RECOUV-03), trace l'historique (RF-RECOUV-05). Réservé au super administrateur
    (l'action peut suspendre un contrat). 400 si le dossier est déjà à une étape terminale."""
    dossier = crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    try:
        progresser_dossier(db, dossier, auteur_id=admin.id)
    except ValueError as erreur:
        raise HTTPException(400, str(erreur))
    db.commit()
    db.refresh(dossier)
    return dossier


@router.post("/dossiers/{dossier_id}/echeancier", response_model=schemas.EcheancierRecouvrementRead)
def creer_echeancier_dossier(dossier_id: int, payload: schemas.EcheancierRecouvrementCreate,
                             db: Session = Depends(get_db),
                             user: models.Utilisateur = Depends(get_current_user)):
    """Crée l'échéancier de paiement négocié du dossier (RF-RECOUV-04) : `nombre_versements`
    versements de montant égal (dernier arrondi), espacés de `intervalle_jours`. Un seul
    échéancier par dossier (409 sinon)."""
    dossier = crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    try:
        echeancier = creer_echeancier(
            db, dossier, montant_total=payload.montant_total,
            nombre_versements=payload.nombre_versements,
            date_premier_versement=payload.date_premier_versement,
            intervalle_jours=payload.intervalle_jours, auteur_id=user.id,
        )
    except ValueError as erreur:
        raise HTTPException(409, str(erreur))
    db.commit()
    db.refresh(echeancier)
    return echeancier


@router.get("/dossiers/{dossier_id}/echeancier", response_model=schemas.EcheancierRecouvrementRead)
def get_echeancier(dossier_id: int, db: Session = Depends(get_db)):
    crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    echeancier = db.query(models.EcheancierRecouvrement).filter_by(
        dossier_recouvrement_id=dossier_id).first()
    if echeancier is None:
        raise HTTPException(404, "Aucun échéancier pour ce dossier.")
    return echeancier


@router.patch("/versements/{versement_id}", response_model=schemas.VersementEcheancierRead)
def modifier_versement(versement_id: int, payload: schemas.VersementEcheancierUpdate,
                       db: Session = Depends(get_db),
                       user: models.Utilisateur = Depends(get_current_user)):
    """Met à jour le statut d'un versement d'échéancier (RF-RECOUV-04) : prévu -> réglé / manqué.
    L'opération est tracée dans l'historique du dossier (RF-RECOUV-05)."""
    versement = crud.get_or_404(db, models.VersementEcheancier, versement_id)
    ancien = versement.statut
    versement.statut = payload.statut
    echeancier = db.get(models.EcheancierRecouvrement, versement.echeancier_id)
    dossier = db.get(models.DossierRecouvrement, echeancier.dossier_recouvrement_id)
    _journaliser(
        db, dossier, "versement",
        f"Versement n°{versement.numero_ordre} ({versement.montant}) : {ancien.value} -> {payload.statut.value}.",
        auteur_id=user.id,
    )
    db.commit()
    db.refresh(versement)
    return versement


@router.patch("/dossiers/{dossier_id}/statut", response_model=schemas.DossierRecouvrementRead)
def changer_statut(dossier_id: int, statut: models.StatutDossierRecouv, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    from datetime import date
    data = {"statut": statut}
    if statut in (models.StatutDossierRecouv.regularise, models.StatutDossierRecouv.resilie):
        data["date_cloture"] = date.today()
    return crud.update(db, models.DossierRecouvrement, dossier_id, data)


@router.post("/dossiers/{dossier_id}/relances", response_model=schemas.RelanceRead)
def ajouter_relance(dossier_id: int, payload: schemas.RelanceCreate, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    from datetime import date

    dossier = crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    data = payload.model_dump()
    data["dossier_recouvrement_id"] = dossier_id
    relance = crud.create(db, models.Relance, data)

    # Trace la relance manuelle dans l'historique (RF-RECOUV-05).
    _journaliser(db, dossier, "relance",
                 f"Relance {relance.type_relance.value} saisie manuellement.", auteur_id=user.id)
    # La première relance fait passer le dossier en « en_relance » et réarme l'horloge d'étape
    # (date_derniere_etape), pour rester cohérent avec la progression planifiée (RF-RECOUV-02).
    if dossier.statut == models.StatutDossierRecouv.ouvert:
        ancien = dossier.statut
        dossier.statut = models.StatutDossierRecouv.en_relance
        dossier.date_derniere_etape = date.today()
        _journaliser(db, dossier, "progression",
                     f"Passage de l'étape « {ancien.value} » à « en_relance » (relance manuelle).",
                     ancien=ancien, nouveau=models.StatutDossierRecouv.en_relance, auteur_id=user.id)
    db.commit()
    db.refresh(relance)
    return relance


@router.get("/dossiers/{dossier_id}/relances", response_model=list[schemas.RelanceRead])
def list_relances(dossier_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Relance, skip, limit, dossier_recouvrement_id=dossier_id)
