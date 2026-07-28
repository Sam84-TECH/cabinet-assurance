"""
Module Pièce justificative fournie (SOUS) — pièces effectivement fournies pour une police
(dossier de souscription). Support du contrôle RF-SOUS-04 : une police n'est émise
(validation de l'avenant d'affaire nouvelle) que si toutes les pièces obligatoires de son
produit sont fournies.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/pieces-fournies", tags=["Pièce justificative fournie"])


@router.post("", response_model=schemas.PieceJustificativeFournieRead)
def create_piece_fournie(payload: schemas.PieceJustificativeFournieCreate, db: Session = Depends(get_db),
                         user: models.Utilisateur = Depends(get_current_user)):
    """Marque une pièce comme fournie pour une police. Idempotent : re-marquer une pièce déjà
    fournie renvoie l'existante (pas de doublon ni de 500 sur uq_piece_fournie_police_requise)."""
    data = payload.model_dump()
    filtre = {"police_id": data["police_id"], "piece_requise_id": data["piece_requise_id"]}
    existante = db.query(models.PieceJustificativeFournie).filter_by(**filtre).first()
    if existante is not None:
        return existante
    try:
        return crud.create(db, models.PieceJustificativeFournie, data)
    except IntegrityError:
        # Course concurrente : un autre appel vient de marquer cette pièce → renvoie l'existante.
        db.rollback()
        return db.query(models.PieceJustificativeFournie).filter_by(**filtre).first()


@router.get("", response_model=list[schemas.PieceJustificativeFournieRead])
def list_pieces_fournies(police_id: int | None = None, skip: int = 0, limit: int = 100,
                         db: Session = Depends(get_db)):
    return crud.list_all(db, models.PieceJustificativeFournie, skip, limit, police_id=police_id)


@router.get("/{piece_fournie_id}", response_model=schemas.PieceJustificativeFournieRead)
def get_piece_fournie(piece_fournie_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.PieceJustificativeFournie, piece_fournie_id)


@router.delete("/{piece_fournie_id}", status_code=204)
def delete_piece_fournie(piece_fournie_id: int, db: Session = Depends(get_db),
                         user: models.Utilisateur = Depends(get_current_user)):
    crud.delete(db, models.PieceJustificativeFournie, piece_fournie_id)
