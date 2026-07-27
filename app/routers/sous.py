"""
Module Souscription (SOUS) — police et avenant.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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
    return crud.list_all(db, models.Police, skip, limit, client_id=client_id)


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
def list_avenants(police_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Avenant, skip, limit, police_id=police_id)


@router.patch("/avenants/{avenant_id}/valider", response_model=schemas.AvenantRead)
def valider_avenant(avenant_id: int, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    """Valide un avenant brouillon (règle CDCF : un avenant doit être validé pour prendre
    effet). Répercute l'effet sur la police via la synchronisation : un avenant de résiliation
    ou de suspension bascule la police en 'resilie' / 'suspendu' — immédiatement si sa date
    d'effet est atteinte, sinon à cette date. L'auteur est déduit du jeton de connexion."""
    avenant = crud.get_or_404(db, models.Avenant, avenant_id)
    if avenant.statut != models.StatutAvenant.brouillon:
        raise HTTPException(400, "Seul un avenant en brouillon peut être validé.")
    avenant.statut = models.StatutAvenant.valide
    avenant.valide_par = user.id
    avenant.date_validation = datetime.now()
    db.commit()
    synchroniser_statuts_polices(db)  # applique l'effet sur le statut de la police
    db.refresh(avenant)
    return avenant
