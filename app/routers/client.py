"""
Module Client (CRM minimal) — une seule table, particulier + entreprise (option A validée).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/clients", tags=["Client"])


@router.post("", response_model=schemas.ClientRead)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Client, payload.model_dump())


@router.get("", response_model=list[schemas.ClientRead])
def list_clients(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Client, skip, limit)


@router.get("/{client_id}", response_model=schemas.ClientRead)
def get_client(client_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Client, client_id)


@router.patch("/{client_id}", response_model=schemas.ClientRead)
def update_client(client_id: int, payload: schemas.ClientCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.Client, client_id, payload.model_dump(exclude_unset=True))


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    """Suppression refusée si le client est référencé ailleurs — police, encaissement,
    lien familial… — via le contrôle générique de `crud.delete` (règles 14 et 15)."""
    crud.delete(db, models.Client, client_id)
