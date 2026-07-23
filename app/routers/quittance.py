"""
Module Quittance (POL) — le détail financier d'un avenant.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_quittance
from ..auth import get_current_user

router = APIRouter(prefix="/quittances", tags=["Quittance"])


@router.post("", response_model=schemas.QuittanceRead)
def create_quittance(payload: schemas.QuittanceCreate, db: Session = Depends(get_db),
                      user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_quittance"] = generer_numero_quittance(db)
    return crud.create(db, models.Quittance, data)


@router.get("", response_model=list[schemas.QuittanceRead])
def list_quittances(police_id: int | None = None, statut: models.StatutQuittance | None = None,
                     db: Session = Depends(get_db)):
    quittances = crud.list_all(db, models.Quittance)
    if police_id is not None:
        quittances = [q for q in quittances if q.police_id == police_id]
    if statut is not None:
        quittances = [q for q in quittances if q.statut == statut]
    return quittances


@router.get("/{quittance_id}", response_model=schemas.QuittanceRead)
def get_quittance(quittance_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Quittance, quittance_id)
