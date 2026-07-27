"""
Consultation du journal d'audit (CDCF §6) — lecture seule, réservée au super administrateur.
Le journal est alimenté automatiquement par les listeners SQLAlchemy (voir app/audit.py) ;
il n'est jamais écrit via l'API, d'où l'absence de POST/PATCH/DELETE.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import exiger_role

router = APIRouter(prefix="/audit", tags=["Journal d'audit"])


@router.get("", response_model=list[schemas.JournalAuditRead])
def list_audit(table_cible: str | None = None, enregistrement_id: int | None = None,
               auteur_id: int | None = None, action: str | None = None,
               skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """Liste les entrées du journal d'audit (auteur, date, ancienne/nouvelle valeur),
    filtrable par table, enregistrement, auteur ou action (creation/modification/suppression).
    Réservé au super administrateur. Ordre chronologique (id croissant)."""
    return crud.list_all(db, models.JournalAudit, skip, limit,
                         table_cible=table_cible, enregistrement_id=enregistrement_id,
                         auteur_id=auteur_id, action=action)
