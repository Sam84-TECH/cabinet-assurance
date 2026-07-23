"""
Module Référentiel — compagnie, produit, garantie, barème de commission.
C'est le catalogue produit générique/paramétrable (principe clé du CDCF :
ajouter un produit ou une garantie ne demande aucun code, juste des données).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/referentiel", tags=["Référentiel"])


# ----- Compagnie (lecture seule pour l'instant : une seule ligne, Sanlam) -----

@router.get("/compagnies", response_model=list[schemas.CompagnieRead])
def list_compagnies(db: Session = Depends(get_db)):
    return crud.list_all(db, models.Compagnie)


# ----- Produit -----

@router.post("/produits", response_model=schemas.ProduitRead)
def create_produit(payload: schemas.ProduitCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Produit, payload.model_dump())


@router.get("/produits", response_model=list[schemas.ProduitRead])
def list_produits(db: Session = Depends(get_db)):
    return crud.list_all(db, models.Produit)


@router.get("/produits/{produit_id}", response_model=schemas.ProduitRead)
def get_produit(produit_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Produit, produit_id)


# ----- Garantie -----

@router.post("/garanties", response_model=schemas.GarantieRead)
def create_garantie(payload: schemas.GarantieCreate, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Garantie, payload.model_dump())


@router.get("/garanties", response_model=list[schemas.GarantieRead])
def list_garanties(produit_id: int | None = None, db: Session = Depends(get_db)):
    garanties = crud.list_all(db, models.Garantie)
    if produit_id is not None:
        garanties = [g for g in garanties if g.produit_id == produit_id]
    return garanties


# ----- Barème de commission (RF-REV-03) -----

@router.post("/baremes", response_model=schemas.BaremeCommissionRead)
def create_bareme(payload: schemas.BaremeCommissionCreate, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    """Crée un barème de commission (RF-REV-03). Un barème avec produit_id renseigné
    est prioritaire ; un barème à produit_id NULL sert de barème général de la compagnie."""
    return crud.create(db, models.BaremeCommission, payload.model_dump())


@router.get("/baremes", response_model=list[schemas.BaremeCommissionRead])
def list_baremes(compagnie_id: int | None = None, db: Session = Depends(get_db)):
    baremes = crud.list_all(db, models.BaremeCommission)
    if compagnie_id is not None:
        baremes = [b for b in baremes if b.compagnie_id == compagnie_id]
    return baremes


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
