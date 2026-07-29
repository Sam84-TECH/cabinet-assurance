"""
Module Lien familial (gestion familiale) — rattache un client « membre » à un client
« souscripteur » avec un type de lien (conjoint, enfant, parent…). Paramétrage relationnel,
non comptable : il expose donc un DELETE (règles 11 et 12). Même style que client.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

MESSAGE_DOUBLON = "Ce lien familial existe déjà entre ces deux clients."

router = APIRouter(prefix="/liens-familiaux", tags=["Lien familial"])


def _valider_lien(db: Session, souscripteur_id: int, membre_id: int, lien_id: int | None = None):
    """Garde-fous serveur : un client ne peut être son propre membre, et un même couple
    (souscripteur, membre) ne peut être enregistré deux fois (409 au lieu de laisser remonter
    l'IntegrityError de la contrainte unique). `lien_id` exclut le lien courant lors d'un PATCH."""
    if souscripteur_id == membre_id:
        raise HTTPException(400, "Un client ne peut pas être son propre membre de famille.")
    existant = db.query(models.LienFamilial).filter_by(
        souscripteur_id=souscripteur_id, membre_id=membre_id
    ).first()
    if existant is not None and existant.id != lien_id:
        raise HTTPException(409, MESSAGE_DOUBLON)


@router.post("", response_model=schemas.LienFamilialRead)
def create_lien(payload: schemas.LienFamilialCreate, db: Session = Depends(get_db),
                user: models.Utilisateur = Depends(get_current_user)):
    """Crée un lien familial. Les clients souscripteur et membre doivent exister (404 sinon,
    via le contrôle générique des clés étrangères de crud.create)."""
    _valider_lien(db, payload.souscripteur_id, payload.membre_id)
    # Le doublon concurrent (course sur la contrainte unique) est rattrapé génériquement par
    # crud.create (filet IntegrityError -> 409), sans code local dédié ici.
    return crud.create(db, models.LienFamilial, payload.model_dump())


@router.get("", response_model=list[schemas.LienFamilialRead])
def list_liens(souscripteur_id: int | None = None, membre_id: int | None = None,
               skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Liste les liens familiaux, filtrables par souscripteur et/ou par membre (WHERE SQL)."""
    return crud.list_all(db, models.LienFamilial, skip, limit,
                         souscripteur_id=souscripteur_id, membre_id=membre_id)


@router.get("/{lien_id}", response_model=schemas.LienFamilialRead)
def get_lien(lien_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.LienFamilial, lien_id)


@router.patch("/{lien_id}", response_model=schemas.LienFamilialRead)
def update_lien(lien_id: int, payload: schemas.LienFamilialCreate, db: Session = Depends(get_db),
                user: models.Utilisateur = Depends(get_current_user)):
    """Met à jour un lien (type de lien, ou réaffectation souscripteur/membre). Revalide
    l'absence d'auto-lien et de doublon sur le couple résultant."""
    lien = crud.get_or_404(db, models.LienFamilial, lien_id)
    data = payload.model_dump(exclude_unset=True)
    souscripteur_id = data.get("souscripteur_id", lien.souscripteur_id)
    membre_id = data.get("membre_id", lien.membre_id)
    _valider_lien(db, souscripteur_id, membre_id, lien_id=lien_id)
    return crud.update(db, models.LienFamilial, lien_id, data)


@router.delete("/{lien_id}", status_code=204)
def delete_lien(lien_id: int, db: Session = Depends(get_db),
                user: models.Utilisateur = Depends(get_current_user)):
    """Supprime un lien familial (entité non comptable — suppression autorisée). Le refus de
    supprimer un client encore référencé par un lien reste géré côté client (règles 14 et 15)."""
    crud.delete(db, models.LienFamilial, lien_id)
