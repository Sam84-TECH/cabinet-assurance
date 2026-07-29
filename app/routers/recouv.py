"""
Module Recouvrement (RECOUV).
Un dossier de recouvrement s'ouvre sur une quittance impayée (statut != reglee)
au-delà du délai convenu, avec un historique de relances (amiable puis mise en demeure).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..recouvrement import calculer_balance_agee, basculer_quittances_en_recouvrement

router = APIRouter(prefix="/recouv", tags=["Recouvrement"])


@router.get("/balance-agee", response_model=schemas.BalanceAgee)
def balance_agee(db: Session = Depends(get_db),
                 user: models.Utilisateur = Depends(get_current_user)):
    """Balance âgée des créances client impayées (RF-RECOUV-01) : reste dû ventilé par
    ancienneté (0-30, 30-60, 60-90, +90 jours depuis l'exigibilité de la prime). Le reste dû
    exclut les chèques rejetés. Calculée à la demande depuis les quittances (pas de table dédiée)."""
    return calculer_balance_agee(db)


@router.post("/basculer-echus")
def basculer_echus(db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    """Déclenche à la demande la bascule en recouvrement des quittances impayées au-delà du
    délai réglementaire (RF-ECH-04) : même traitement que la tâche planifiée quotidienne
    (app/scheduler.py), utile pour la recette et l'exploitation. Ouvre un dossier par quittance
    échue sans dossier en cours ; renvoie le nombre de dossiers ouverts."""
    return {"dossiers_ouverts": basculer_quittances_en_recouvrement(db)}


@router.post("/dossiers", response_model=schemas.DossierRecouvrementRead)
def ouvrir_dossier(payload: schemas.DossierRecouvrementCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    quittance = crud.get_or_404(db, models.Quittance, payload.quittance_id)
    if quittance.statut == models.StatutQuittance.reglee:
        raise HTTPException(400, "Cette quittance est déjà réglée, pas besoin de recouvrement.")
    return crud.create(db, models.DossierRecouvrement, payload.model_dump())


@router.get("/dossiers", response_model=list[schemas.DossierRecouvrementRead])
def list_dossiers(statut: models.StatutDossierRecouv | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.DossierRecouvrement, skip, limit, statut=statut)


@router.get("/dossiers/{dossier_id}", response_model=schemas.DossierRecouvrementRead)
def get_dossier(dossier_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.DossierRecouvrement, dossier_id)


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
    crud.get_or_404(db, models.DossierRecouvrement, dossier_id)  # 404 si dossier inexistant
    data = payload.model_dump()
    data["dossier_recouvrement_id"] = dossier_id
    relance = crud.create(db, models.Relance, data)

    # La première relance fait passer le dossier en "en_relance" automatiquement
    dossier = crud.get_or_404(db, models.DossierRecouvrement, dossier_id)
    if dossier.statut == models.StatutDossierRecouv.ouvert:
        dossier.statut = models.StatutDossierRecouv.en_relance
        db.commit()

    return relance


@router.get("/dossiers/{dossier_id}/relances", response_model=list[schemas.RelanceRead])
def list_relances(dossier_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Relance, skip, limit, dossier_recouvrement_id=dossier_id)
