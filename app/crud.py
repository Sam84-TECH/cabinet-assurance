"""
Fonctions CRUD génériques (Create/Read/Update/Delete).
Évite de réécrire les mêmes 4 opérations pour chacune des 23 tables.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException


def create(db: Session, model, data: dict):
    obj = model(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_or_404(db: Session, model, id: int):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {id} introuvable")
    return obj


def list_all(db: Session, model, skip: int = 0, limit: int = 100, **filtres):
    """Liste paginée. Les `filtres` (champ=valeur) sont appliqués en SQL (clause WHERE) ;
    ceux dont la valeur vaut None sont ignorés (aucun critère ajouté). Le filtrage se fait
    ainsi en base, avant skip/limit — jamais en Python après coup."""
    stmt = select(model)
    for champ, valeur in filtres.items():
        if valeur is not None:
            stmt = stmt.where(getattr(model, champ) == valeur)
    return db.execute(stmt.offset(skip).limit(limit)).scalars().all()


def update(db: Session, model, id: int, data: dict):
    obj = get_or_404(db, model, id)
    for key, value in data.items():
        if value is not None:
            setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, model, id: int):
    obj = get_or_404(db, model, id)
    db.delete(obj)
    db.commit()
