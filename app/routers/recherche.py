"""
Recherche multicritère (Module 5) — GET /recherche?q= cherche simultanément sur le nom, la
raison sociale, la CIN et l'ICE d'un client, le numéro de police, le numéro de quittance et
l'immatriculation d'un véhicule (risque), et renvoie des résultats typés (regroupés par entité).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/recherche", tags=["Recherche"])

LIMITE_PAR_TYPE = 50


@router.get("", response_model=schemas.RechercheResultats)
def recherche(q: str, db: Session = Depends(get_db),
              user: models.Utilisateur = Depends(get_current_user)):
    """Recherche insensible à la casse (ILIKE, correspondance partielle) sur plusieurs
    entités à la fois, résultats regroupés par type (50 max par type)."""
    terme = q.strip()
    if not terme:
        return {"clients": [], "polices": [], "quittances": [], "risques": []}
    motif = f"%{terme}%"

    # Ordre imposé (écart §13) : clients d'abord, puis polices (qui dépendent des clients
    # trouvés), puis quittances (qui dépendent des polices trouvées).
    clients = db.query(models.Client).filter(or_(
        models.Client.nom.ilike(motif),
        models.Client.raison_sociale.ilike(motif),
        models.Client.cin.ilike(motif),
        models.Client.ice.ilike(motif),
    )).limit(LIMITE_PAR_TYPE).all()

    # Polices : recherche directe par numéro ET polices liées à un client déjà trouvé (§13).
    ids_clients = [c.id for c in clients]
    polices = db.query(models.Police).filter(or_(
        models.Police.numero_police.ilike(motif),
        models.Police.client_id.in_(ids_clients),
    )).limit(LIMITE_PAR_TYPE).all()

    # Quittances : recherche directe par numéro ET quittances liées à une police déjà trouvée (§13).
    ids_polices = [p.id for p in polices]
    quittances = db.query(models.Quittance).filter(or_(
        models.Quittance.numero_quittance.ilike(motif),
        models.Quittance.police_id.in_(ids_polices),
    )).limit(LIMITE_PAR_TYPE).all()

    # immatriculation du véhicule : stockée dans le JSONB `attributs` du risque.
    risques = db.query(models.Risque).filter(
        models.Risque.attributs["immatriculation"].astext.ilike(motif)
    ).limit(LIMITE_PAR_TYPE).all()

    return {"clients": clients, "polices": polices, "quittances": quittances, "risques": risques}
