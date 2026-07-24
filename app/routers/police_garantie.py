"""
Module Police-Garantie (SOUS) — rattachement des garanties (et de leur prime)
à une police, éventuellement ciblées sur un risque précis (véhicule).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/police-garanties", tags=["Police garantie"])


@router.post("", response_model=schemas.PoliceGarantieRead)
def create_police_garantie(payload: schemas.PoliceGarantieCreate, db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.PoliceGarantie, payload.model_dump())


@router.get("", response_model=list[schemas.PoliceGarantieRead])
def list_police_garanties(police_id: int | None = None, risque_id: int | None = None,
                          skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.PoliceGarantie, skip, limit,
                         police_id=police_id, risque_id=risque_id)


@router.get("/{police_garantie_id}", response_model=schemas.PoliceGarantieRead)
def get_police_garantie(police_garantie_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.PoliceGarantie, police_garantie_id)


@router.patch("/{police_garantie_id}", response_model=schemas.PoliceGarantieRead)
def update_police_garantie(police_garantie_id: int, payload: schemas.PoliceGarantieCreate,
                           db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.PoliceGarantie, police_garantie_id, payload.model_dump(exclude_unset=True))


@router.delete("/{police_garantie_id}", status_code=204)
def delete_police_garantie(police_garantie_id: int, db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    crud.delete(db, models.PoliceGarantie, police_garantie_id)
