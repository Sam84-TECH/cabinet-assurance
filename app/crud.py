"""
Fonctions CRUD génériques (Create/Read/Update/Delete).
Évite de réécrire les mêmes 4 opérations pour chacune des 23 tables.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, inspect as sa_inspect
from fastapi import HTTPException


def _valider_cles_etrangeres(db: Session, model, data: dict):
    """Vérifie que chaque clé étrangère fournie dans `data` référence une ligne existante,
    et lève un 404 explicite (« Produit 12 introuvable ») au lieu de laisser remonter une
    IntegrityError SQL (500). Centralisé : appelé par create() et update(), donc actif sur
    tous les endpoints sans avoir à le répéter un par un. Les valeurs None sont ignorées
    (colonne FK laissée vide, ex. produit_id d'un barème général)."""
    mappers = list(model.registry.mappers)
    for colonne in sa_inspect(model).columns:
        if not colonne.foreign_keys or colonne.key not in data:
            continue
        valeur = data[colonne.key]
        if valeur is None:
            continue
        table_cible = next(iter(colonne.foreign_keys)).column.table
        cible = next((m.class_ for m in mappers if m.local_table is table_cible), None)
        if cible is not None and db.get(cible, valeur) is None:
            raise HTTPException(status_code=404, detail=f"{cible.__name__} {valeur} introuvable")


def create(db: Session, model, data: dict):
    _valider_cles_etrangeres(db, model, data)
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
    """Liste paginée et triée. Les `filtres` (champ=valeur) sont appliqués en SQL (clause
    WHERE) ; ceux dont la valeur vaut None sont ignorés. Le filtrage se fait en base, avant
    skip/limit — jamais en Python après coup.

    `skip`/`limit` sont bornés à >= 0 (une valeur négative donnerait un OFFSET/LIMIT invalide
    -> 500). Le tri par `id` garantit un ordre de page stable d'un appel à l'autre, qu'un
    offset/limit sans ORDER BY ne garantit pas."""
    skip = max(skip, 0)
    limit = max(limit, 0)
    stmt = select(model)
    for champ, valeur in filtres.items():
        if valeur is not None:
            stmt = stmt.where(getattr(model, champ) == valeur)
    stmt = stmt.order_by(model.id).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def update(db: Session, model, id: int, data: dict):
    obj = get_or_404(db, model, id)
    _valider_cles_etrangeres(db, model, data)
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
