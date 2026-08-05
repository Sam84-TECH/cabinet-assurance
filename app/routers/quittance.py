"""
Module Quittance (POL) — le détail financier d'un avenant.
Les quittances sont générées automatiquement à la validation d'un avenant (RF-SOUS-07,
voir app/facturation.py) ; la création manuelle est verrouillée. La table reste en
lecture seule via l'API (consultation), sans DELETE (règle métier n°12).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..reglement import enrichir_quittance

router = APIRouter(prefix="/quittances", tags=["Quittance"])


@router.post("", deprecated=True)
def create_quittance():
    """Verrouillé : la quittance est générée automatiquement à la validation d'un avenant
    (RF-SOUS-07). La création manuelle est désactivée pour éviter les doublons."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Création manuelle de quittance désactivée : elle est générée automatiquement "
               "à la validation de l'avenant (RF-SOUS-07).",
    )


@router.get("", response_model=list[schemas.QuittanceRead])
def list_quittances(police_id: int | None = None, statut: models.StatutQuittance | None = None,
                     skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    quittances = crud.list_all(db, models.Quittance, skip, limit, police_id=police_id, statut=statut)
    return [enrichir_quittance(db, q) for q in quittances]  # + montant_regle / reste_du (§27)


@router.get("/{quittance_id}", response_model=schemas.QuittanceRead)
def get_quittance(quittance_id: int, db: Session = Depends(get_db)):
    return enrichir_quittance(db, crud.get_or_404(db, models.Quittance, quittance_id))  # + reste_du (§27)
