"""
Module Client (CRM minimal) — une seule table, particulier + entreprise (option A validée).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..reglement import enrichir_quittance
from ..auth import get_current_user

router = APIRouter(prefix="/clients", tags=["Client"])


@router.post("", response_model=schemas.ClientRead)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    return crud.create(db, models.Client, payload.model_dump())


@router.get("", response_model=list[schemas.ClientRead])
def list_clients(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Client, skip, limit)


@router.get("/{client_id}", response_model=schemas.ClientRead)
def get_client(client_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Client, client_id)


@router.patch("/{client_id}", response_model=schemas.ClientRead)
def update_client(client_id: int, payload: schemas.ClientUpdate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.Client, client_id, payload.model_dump(exclude_unset=True))


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    """Suppression refusée si le client est référencé ailleurs — police, encaissement,
    lien familial… — via le contrôle générique de `crud.delete` (règles 14 et 15)."""
    crud.delete(db, models.Client, client_id)


@router.get("/{client_id}/vue-360", response_model=schemas.Vue360Client)
def vue_360(client_id: int, db: Session = Depends(get_db),
            user: models.Utilisateur = Depends(get_current_user)):
    """Vue 360 du client (RF-CRM-06, RF-ENC-05) : ses polices, ses quittances, son solde
    (total dû sur quittances non annulées, total encaissé hors chèques rejetés, reste dû)
    et l'historique de ses encaissements."""
    client = crud.get_or_404(db, models.Client, client_id)
    polices = db.query(models.Police).filter_by(client_id=client_id).all()
    quittances = (
        db.query(models.Quittance).join(models.Police)
        .filter(models.Police.client_id == client_id).all()
    )
    # §30 (même cause que §27) : chaque quittance de la fiche client expose son reste dû réel
    # (prime_ttc - réglé hors chèques rejetés), pas seulement son TTC total.
    for q in quittances:
        enrichir_quittance(db, q)
    encaissements = db.query(models.Encaissement).filter_by(client_id=client_id).all()

    total_du = sum(
        (q.prime_ttc for q in quittances if q.statut != models.StatutQuittance.annulee),
        Decimal("0"),
    )
    total_encaisse = sum(
        (e.montant for e in encaissements if e.statut != models.StatutEncaissement.rejete),
        Decimal("0"),
    )
    return {
        "client": client,
        "polices": polices,
        "quittances": quittances,
        "solde": {
            "total_du": total_du,
            "total_encaisse": total_encaisse,
            "reste_du": total_du - total_encaisse,
        },
        "encaissements": encaissements,
    }
