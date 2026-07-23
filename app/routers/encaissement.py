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
def list_encaissements(client_id: int | None = None, db: Session = Depends(get_db)):
    encaissements = crud.list_all(db, models.Encaissement)
    if client_id is not None:
        encaissements = [e for e in encaissements if e.client_id == client_id]
    return encaissements


@router.get("/{encaissement_id}", response_model=schemas.EncaissementRead)
def get_encaissement(encaissement_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Encaissement, encaissement_id)


@router.post("/{encaissement_id}/affecter/{quittance_id}", response_model=schemas.EncaissementQuittanceRead)
def affecter_a_quittance(encaissement_id: int, quittance_id: int, montant_affecte: Decimal,
                          db: Session = Depends(get_db),
                          user: models.Utilisateur = Depends(get_current_user)):
    """
    Affecte tout ou partie d'un encaissement à une quittance.
    Met à jour automatiquement le statut de la quittance (réglée / réglée partiellement)
    selon le total déjà affecté par rapport à la prime TTC due — logique observée en ENC.
    """
    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    quittance = crud.get_or_404(db, models.Quittance, quittance_id)

    lien = crud.create(db, models.EncaissementQuittance, {
        "encaissement_id": encaissement_id,
        "quittance_id": quittance_id,
        "montant_affecte": montant_affecte,
    })

    total_affecte = db.query(models.EncaissementQuittance).filter_by(quittance_id=quittance_id).all()
    total = sum((l.montant_affecte for l in total_affecte), Decimal("0"))

    if total >= quittance.prime_ttc:
        quittance.statut = models.StatutQuittance.reglee
    elif total > 0:
        quittance.statut = models.StatutQuittance.reglee_partiellement
    db.commit()

    return lien
