"""
Module Encaissement (ENC) — règlement client, et son affectation à une ou plusieurs quittances.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/encaissements", tags=["Encaissement"])


@router.post("", response_model=schemas.EncaissementRead)
def create_encaissement(payload: schemas.EncaissementCreate, db: Session = Depends(get_db),
                         user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["enregistre_par"] = user.id  # déduit automatiquement, plus besoin de le fournir
    return crud.create(db, models.Encaissement, data)


@router.get("", response_model=list[schemas.EncaissementRead])
def list_encaissements(client_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Encaissement, skip, limit, client_id=client_id)


@router.get("/{encaissement_id}", response_model=schemas.EncaissementRead)
def get_encaissement(encaissement_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Encaissement, encaissement_id)


@router.post("/{encaissement_id}/affecter/{quittance_id}", response_model=schemas.EncaissementQuittanceRead)
def affecter_a_quittance(encaissement_id: int, quittance_id: int, payload: schemas.AffectationCreate,
                          db: Session = Depends(get_db),
                          user: models.Utilisateur = Depends(get_current_user)):
    """
    Affecte tout ou partie d'un encaissement à une quittance (montant dans le corps).
    Garde-fous : montant strictement positif, sans dépasser le reste disponible de
    l'encaissement ni le reste dû de la quittance, et quittance non annulée. Met ensuite
    à jour le statut de la quittance (réglée / réglée partiellement) selon le total affecté.
    """
    montant = payload.montant_affecte
    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    quittance = crud.get_or_404(db, models.Quittance, quittance_id)

    if montant <= 0:
        raise HTTPException(400, "Le montant à affecter doit être strictement positif.")
    if quittance.statut == models.StatutQuittance.annulee:
        raise HTTPException(400, "Cette quittance est annulée : aucune affectation n'est possible.")

    # Reste disponible sur l'encaissement = montant total - ce qui est déjà affecté ailleurs.
    lignes_encaissement = db.query(models.EncaissementQuittance).filter_by(encaissement_id=encaissement_id).all()
    reste_encaissement = encaissement.montant - sum((l.montant_affecte for l in lignes_encaissement), Decimal("0"))
    if montant > reste_encaissement:
        raise HTTPException(400, f"Le montant dépasse le reste disponible sur l'encaissement ({reste_encaissement}).")

    # Reste dû sur la quittance = prime TTC - ce qui a déjà été réglé.
    lignes_quittance = db.query(models.EncaissementQuittance).filter_by(quittance_id=quittance_id).all()
    total_regle = sum((l.montant_affecte for l in lignes_quittance), Decimal("0"))
    reste_quittance = quittance.prime_ttc - total_regle
    if montant > reste_quittance:
        raise HTTPException(400, f"Le montant dépasse le reste dû sur la quittance ({reste_quittance}).")

    lien = crud.create(db, models.EncaissementQuittance, {
        "encaissement_id": encaissement_id,
        "quittance_id": quittance_id,
        "montant_affecte": montant,
    })

    # Mise à jour du statut de la quittance selon le nouveau total réglé.
    nouveau_total = total_regle + montant
    if nouveau_total >= quittance.prime_ttc:
        quittance.statut = models.StatutQuittance.reglee
    elif nouveau_total > 0:
        quittance.statut = models.StatutQuittance.reglee_partiellement
    db.commit()

    return lien
