"""
Module Versement bancaire (BANQ).
Règle clé (CDCF RF-BANQ-02) : un encaissement n'est considéré comme
définitivement traité qu'une fois rapproché avec un mouvement bancaire —
c'est-à-dire inclus dans un bordereau de versement validé.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_bordereau_versement
from ..auth import exiger_role, get_current_user

router = APIRouter(prefix="/banq", tags=["Versement bancaire"])


def _montant_total(db: Session, bordereau_id: int) -> Decimal:
    """Somme des lignes (encaissements déposés) d'un bordereau de versement."""
    total = db.query(func.coalesce(func.sum(models.BordereauVersementLigne.montant), 0)).filter_by(
        bordereau_versement_id=bordereau_id).scalar()
    return Decimal(total)


# ----- Comptes bancaires du cabinet -----

@router.post("/comptes", response_model=schemas.BanqueAgenceRead)
def create_compte(payload: schemas.BanqueAgenceCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.BanqueAgence, payload.model_dump())


@router.get("/comptes", response_model=list[schemas.BanqueAgenceRead])
def list_comptes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.BanqueAgence, skip, limit)


# ----- Bordereau de versement -----

@router.post("/bordereaux", response_model=schemas.BordereauVersementRead)
def create_bordereau(payload: schemas.BordereauVersementCreate, db: Session = Depends(get_db),
                      user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_bordereau"] = generer_numero_bordereau_versement(db)
    data["statut"] = models.StatutBordereauVersement.brouillon  # forcé serveur (anti-contournement)
    return crud.create(db, models.BordereauVersement, data)


@router.get("/bordereaux", response_model=list[schemas.BordereauVersementRead])
def list_bordereaux(statut: models.StatutBordereauVersement | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Liste des bordereaux de versement, chacun enrichi de son montant total (somme des
    encaissements déposés) pour l'écran « Liste des bordereaux »."""
    bordereaux = crud.list_all(db, models.BordereauVersement, skip, limit, statut=statut)
    # Un seul GROUP BY pour tous les bordereaux de la page (pas de requête par ligne : évite le N+1).
    ids = [b.id for b in bordereaux]
    sommes = dict(
        db.query(
            models.BordereauVersementLigne.bordereau_versement_id,
            func.coalesce(func.sum(models.BordereauVersementLigne.montant), 0),
        )
        .filter(models.BordereauVersementLigne.bordereau_versement_id.in_(ids))
        .group_by(models.BordereauVersementLigne.bordereau_versement_id)
        .all()
    )
    for b in bordereaux:
        b.montant_total = Decimal(sommes.get(b.id, 0))
    return bordereaux


@router.get("/bordereaux/{bordereau_id}", response_model=schemas.BordereauVersementDetailRead)
def get_bordereau(bordereau_id: int, db: Session = Depends(get_db)):
    """Détail d'un bordereau de versement : entête (avec montant total) + ses lignes enrichies
    du client et du mode de paiement de chaque encaissement déposé."""
    bordereau = crud.get_or_404(db, models.BordereauVersement, bordereau_id)
    bordereau.montant_total = _montant_total(db, bordereau_id)
    lignes = []
    for ligne in db.query(models.BordereauVersementLigne).filter_by(bordereau_versement_id=bordereau_id):
        enc = db.get(models.Encaissement, ligne.encaissement_id)
        reference = None
        if enc and enc.mode_paiement == models.ModePaiement.cheque:
            reference = " · ".join(x for x in (enc.cheque_numero, enc.cheque_banque) if x) or None
        lignes.append(schemas.BordereauVersementLigneDetailRead(
            id=ligne.id,
            bordereau_versement_id=ligne.bordereau_versement_id,
            encaissement_id=ligne.encaissement_id,
            montant=ligne.montant,
            client_id=enc.client_id if enc else None,
            mode_paiement=enc.mode_paiement.value if enc else None,
            reference=reference,
        ))
    return schemas.BordereauVersementDetailRead(
        **schemas.BordereauVersementRead.model_validate(bordereau).model_dump(),
        lignes=lignes,
    )


@router.post("/bordereaux/{bordereau_id}/ajouter/{encaissement_id}",
             response_model=schemas.BordereauVersementLigneRead)
def ajouter_encaissement(bordereau_id: int, encaissement_id: int, db: Session = Depends(get_db),
                          user: models.Utilisateur = Depends(get_current_user)):
    """
    Ajoute un encaissement (espèces ou chèque) à un bordereau de versement brouillon.
    Le montant repris est celui de l'encaissement lui-même (RF-BANQ-01).
    """
    bordereau = crud.get_or_404(db, models.BordereauVersement, bordereau_id)
    if bordereau.statut != models.StatutBordereauVersement.brouillon:
        raise HTTPException(400, "Ce bordereau n'est plus modifiable (déjà généré ou versé).")

    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    if encaissement.mode_paiement == models.ModePaiement.virement:
        raise HTTPException(400, "Un virement ne transite pas par un dépôt bancaire physique.")

    return crud.create(db, models.BordereauVersementLigne, {
        "bordereau_versement_id": bordereau_id,
        "encaissement_id": encaissement_id,
        "montant": encaissement.montant,
    })


@router.patch("/bordereaux/{bordereau_id}/valider", response_model=schemas.BordereauVersementRead)
def valider_bordereau(bordereau_id: int, db: Session = Depends(get_db),
                       _admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """
    Validation du versement (rôle Super Administrateur — CDCF §7).
    Marque le bordereau comme "verse" et rapproche chaque encaissement inclus
    (RF-BANQ-02) : un encaissement n'est définitivement traité qu'à ce moment-là.
    """
    bordereau = crud.get_or_404(db, models.BordereauVersement, bordereau_id)
    if bordereau.statut != models.StatutBordereauVersement.brouillon:
        raise HTTPException(400, "Ce bordereau a déjà été validé.")

    lignes = db.query(models.BordereauVersementLigne).filter_by(bordereau_versement_id=bordereau_id).all()
    if not lignes:
        raise HTTPException(400, "Impossible de valider un bordereau vide.")

    for ligne in lignes:
        encaissement = crud.get_or_404(db, models.Encaissement, ligne.encaissement_id)
        encaissement.statut = models.StatutEncaissement.rapproche_banque

    bordereau.statut = models.StatutBordereauVersement.verse
    db.commit()
    db.refresh(bordereau)
    return bordereau
