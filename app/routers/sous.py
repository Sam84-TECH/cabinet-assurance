"""
Module Souscription (SOUS) — police et avenant.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_police
from ..sync import synchroniser_statuts_polices
from ..auth import get_current_user

router = APIRouter(prefix="/sous", tags=["Souscription"])


# ----- Police -----

@router.post("/polices", response_model=schemas.PoliceRead)
def create_police(payload: schemas.PoliceCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_police"] = generer_numero_police(db)
    return crud.create(db, models.Police, data)


@router.get("/polices", response_model=list[schemas.PoliceRead])
def list_polices(client_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    synchroniser_statuts_polices(db)
    polices = crud.list_all(db, models.Police, skip, limit)
    if client_id is not None:
        polices = [p for p in polices if p.client_id == client_id]
    return polices


@router.get("/polices/{police_id}", response_model=schemas.PoliceRead)
def get_police(police_id: int, db: Session = Depends(get_db)):
    synchroniser_statuts_polices(db)
    return crud.get_or_404(db, models.Police, police_id)


# ----- Avenant -----

@router.post("/avenants", response_model=schemas.AvenantRead)
def create_avenant(payload: schemas.AvenantCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Avenant, payload.model_dump())


@router.get("/avenants", response_model=list[schemas.AvenantRead])
def list_avenants(police_id: int | None = None, db: Session = Depends(get_db)):
    avenants = crud.list_all(db, models.Avenant)
    if police_id is not None:
        avenants = [a for a in avenants if a.police_id == police_id]
    return avenants


@router.patch("/avenants/{avenant_id}/valider", response_model=schemas.AvenantRead)
def valider_avenant(avenant_id: int, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    """Valide un avenant (règle CDCF : un avenant brouillon doit être validé pour prendre effet).
    L'auteur de la validation est déduit automatiquement du jeton de connexion."""
    from ..models import StatutAvenant
    return crud.update(db, models.Avenant, avenant_id, {
        "statut": StatutAvenant.valide,
        "valide_par": user.id,
        "date_validation": datetime.now(),
    })
