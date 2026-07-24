"""
Module Référentiel — compagnie, produit, garantie, barème de commission, pièces justificatives.
C'est le catalogue produit générique/paramétrable (principe clé du CDCF :
ajouter un produit ou une garantie ne demande aucun code, juste des données).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/referentiel", tags=["Référentiel"])


# ----- Compagnie -----
# Le cabinet est agent général d'une seule compagnie (Sanlam), créée par le seed :
# pas de création ni de suppression, seulement lecture et mise à jour des coordonnées.
# La table et les compagnie_id restent en place — le modèle demeure multi-compagnie.

@router.get("/compagnies", response_model=list[schemas.CompagnieRead])
def list_compagnies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Compagnie, skip, limit)


@router.patch("/compagnies/{compagnie_id}", response_model=schemas.CompagnieRead)
def update_compagnie(compagnie_id: int, payload: schemas.CompagnieCreate, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    """Met à jour les coordonnées de la compagnie. Pas de création ni de suppression :
    le cabinet n'a qu'une compagnie (Sanlam), créée par le seed."""
    return crud.update(db, models.Compagnie, compagnie_id, payload.model_dump(exclude_unset=True))


# ----- Produit -----

@router.post("/produits", response_model=schemas.ProduitRead)
def create_produit(payload: schemas.ProduitCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Produit, payload.model_dump())


@router.get("/produits", response_model=list[schemas.ProduitRead])
def list_produits(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Produit, skip, limit)


@router.get("/produits/{produit_id}", response_model=schemas.ProduitRead)
def get_produit(produit_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Produit, produit_id)


# ----- Garantie -----

@router.post("/garanties", response_model=schemas.GarantieRead)
def create_garantie(payload: schemas.GarantieCreate, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Garantie, payload.model_dump())


@router.get("/garanties", response_model=list[schemas.GarantieRead])
def list_garanties(produit_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Garantie, skip, limit, produit_id=produit_id)


# ----- Barème de commission (RF-REV-03) -----

@router.post("/baremes", response_model=schemas.BaremeCommissionRead)
def create_bareme(payload: schemas.BaremeCommissionCreate, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    """Crée un barème de commission (RF-REV-03). Un barème avec produit_id renseigné
    est prioritaire ; un barème à produit_id NULL sert de barème général de la compagnie."""
    return crud.create(db, models.BaremeCommission, payload.model_dump())


@router.get("/baremes", response_model=list[schemas.BaremeCommissionRead])
def list_baremes(compagnie_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.BaremeCommission, skip, limit, compagnie_id=compagnie_id)


@router.get("/baremes/{bareme_id}", response_model=schemas.BaremeCommissionRead)
def get_bareme(bareme_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.BaremeCommission, bareme_id)


@router.patch("/baremes/{bareme_id}", response_model=schemas.BaremeCommissionRead)
def update_bareme(bareme_id: int, payload: schemas.BaremeCommissionCreate, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.BaremeCommission, bareme_id, payload.model_dump(exclude_unset=True))


@router.delete("/baremes/{bareme_id}", status_code=204)
def delete_bareme(bareme_id: int, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    crud.delete(db, models.BaremeCommission, bareme_id)


# ----- Pièce justificative requise -----

@router.post("/pieces-justificatives", response_model=schemas.PieceJustificativeRequiseRead)
def create_piece(payload: schemas.PieceJustificativeRequiseCreate, db: Session = Depends(get_db),
                 user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.PieceJustificativeRequise, payload.model_dump())


@router.get("/pieces-justificatives", response_model=list[schemas.PieceJustificativeRequiseRead])
def list_pieces(produit_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.PieceJustificativeRequise, skip, limit, produit_id=produit_id)


@router.get("/pieces-justificatives/{piece_id}", response_model=schemas.PieceJustificativeRequiseRead)
def get_piece(piece_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.PieceJustificativeRequise, piece_id)


@router.patch("/pieces-justificatives/{piece_id}", response_model=schemas.PieceJustificativeRequiseRead)
def update_piece(piece_id: int, payload: schemas.PieceJustificativeRequiseCreate, db: Session = Depends(get_db),
                 user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.PieceJustificativeRequise, piece_id, payload.model_dump(exclude_unset=True))


@router.delete("/pieces-justificatives/{piece_id}", status_code=204)
def delete_piece(piece_id: int, db: Session = Depends(get_db),
                 user: models.Utilisateur = Depends(get_current_user)):
    crud.delete(db, models.PieceJustificativeRequise, piece_id)
