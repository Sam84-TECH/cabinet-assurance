"""
Module Risque (SOUS) — véhicules (risques) rattachés à une police.
Le détail du véhicule (immatriculation, marque, usage…) est stocké dans
`attributs` (JSONB) pour rester générique et accueillir d'autres branches plus tard.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/risques", tags=["Risque"])


@router.post("", response_model=schemas.RisqueRead)
def create_risque(payload: schemas.RisqueCreate, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Risque, payload.model_dump())


@router.get("", response_model=list[schemas.RisqueRead])
def list_risques(police_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Risque, skip, limit, police_id=police_id)


@router.get("/{risque_id}", response_model=schemas.RisqueRead)
def get_risque(risque_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Risque, risque_id)


@router.patch("/{risque_id}", response_model=schemas.RisqueRead)
def update_risque(risque_id: int, payload: schemas.RisqueUpdate, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.Risque, risque_id, payload.model_dump(exclude_unset=True))


@router.delete("/{risque_id}", status_code=204)
def delete_risque(risque_id: int, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    """Suppression autorisée tant qu'aucun avenant n'est validé sur la police (règle 13).
    Une fois la police engagée, retirer un véhicule passe par un avenant, pas un DELETE."""
    risque = crud.get_or_404(db, models.Risque, risque_id)
    if db.query(models.Avenant).filter_by(
        police_id=risque.police_id, statut=models.StatutAvenant.valide
    ).first():
        raise HTTPException(
            400,
            "Un avenant est validé sur cette police : le retrait d'un véhicule doit "
            "passer par un avenant, pas par une suppression.",
        )
    crud.delete(db, models.Risque, risque_id)
