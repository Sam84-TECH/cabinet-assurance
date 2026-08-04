"""
Module Souscription (SOUS) — police et avenant.
"""

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_police
from ..sync import synchroniser_statuts_polices
from ..facturation import generer_quittance_pour_avenant
from ..auth import get_current_user

router = APIRouter(prefix="/sous", tags=["Souscription"])


# ----- Police -----

@router.post("/polices", response_model=schemas.PoliceRead)
def create_police(payload: schemas.PoliceCreate, db: Session = Depends(get_db),
                   user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_police"] = generer_numero_police(db)
    data["statut"] = models.StatutPolice.en_attente_effet  # forcé serveur (anti-contournement)
    return crud.create(db, models.Police, data)


@router.get("/polices", response_model=list[schemas.PoliceRead])
def list_polices(client_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    synchroniser_statuts_polices(db)
    return crud.list_all(db, models.Police, skip, limit, client_id=client_id)


@router.get("/polices/{police_id}", response_model=schemas.PoliceRead)
def get_police(police_id: int, db: Session = Depends(get_db)):
    synchroniser_statuts_polices(db)
    return crud.get_or_404(db, models.Police, police_id)


# ----- Avenant -----

@router.post("/avenants", response_model=schemas.AvenantRead)
def create_avenant(payload: schemas.AvenantCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["statut"] = models.StatutAvenant.brouillon  # forcé serveur : validation via PATCH .../valider
    return crud.create(db, models.Avenant, data)


@router.get("/avenants", response_model=list[schemas.AvenantRead])
def list_avenants(police_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Avenant, skip, limit, police_id=police_id)


def _pieces_obligatoires_manquantes(db: Session, police: models.Police) -> list[str]:
    """Noms des pièces justificatives obligatoires du produit non encore fournies pour la
    police (RF-SOUS-04)."""
    requises = db.query(models.PieceJustificativeRequise).filter_by(
        produit_id=police.produit_id, obligatoire=True
    ).all()
    fournies = {
        pf.piece_requise_id
        for pf in db.query(models.PieceJustificativeFournie).filter_by(police_id=police.id).all()
    }
    return [r.nom for r in requises if r.id not in fournies]


@router.patch("/avenants/{avenant_id}/valider", response_model=schemas.AvenantRead)
def valider_avenant(avenant_id: int, db: Session = Depends(get_db),
                     user: models.Utilisateur = Depends(get_current_user)):
    """Valide un avenant brouillon (règle CDCF : un avenant doit être validé pour prendre
    effet). Répercute l'effet sur la police via la synchronisation : un avenant de résiliation
    ou de suspension bascule la police en 'resilie' / 'suspendu' — immédiatement si sa date
    d'effet est atteinte, sinon à cette date. Génère aussi automatiquement la quittance à
    partir des garanties de la police (RF-SOUS-07), après avoir vérifié que les pièces
    justificatives obligatoires sont fournies (RF-SOUS-04). L'auteur vient du jeton de connexion."""
    avenant = crud.get_or_404(db, models.Avenant, avenant_id)
    if avenant.statut != models.StatutAvenant.brouillon:
        raise HTTPException(400, "Seul un avenant en brouillon peut être validé.")
    # RF-SOUS-04 : à l'émission (affaire nouvelle), toutes les pièces obligatoires du produit
    # doivent être fournies pour le dossier avant de valider.
    if avenant.type_avenant == models.TypeAvenant.affaire_nouvelle:
        police = crud.get_or_404(db, models.Police, avenant.police_id)
        manquantes = _pieces_obligatoires_manquantes(db, police)
        if manquantes:
            raise HTTPException(
                400, "Pièces justificatives obligatoires manquantes : " + ", ".join(manquantes) + ".")
    avenant.statut = models.StatutAvenant.valide
    avenant.valide_par = user.id
    avenant.date_validation = datetime.now()
    generer_quittance_pour_avenant(db, avenant)  # RF-SOUS-07 : quittance auto depuis les garanties
    try:
        db.commit()
    except IntegrityError:
        # Course concurrente : un autre appel a déjà validé cet avenant et créé sa quittance
        # (contrainte uq_quittance_avenant_id). On renvoie un 409 propre plutôt qu'un 500.
        db.rollback()
        raise HTTPException(409, "Cet avenant vient d'être validé par une autre opération.")
    synchroniser_statuts_polices(db)  # applique l'effet sur le statut de la police
    db.refresh(avenant)
    return avenant


def _plus_un_an(d: date) -> date:
    """Ajoute un an à une date, en ramenant le 29 février au 28 (année non bissextile)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


@router.post("/polices/{police_id}/renouveler", response_model=schemas.QuittanceRead)
def renouveler_police(police_id: int, db: Session = Depends(get_db),
                      user: models.Utilisateur = Depends(get_current_user)):
    """Renouvellement en un geste (Module 5) : crée et valide un avenant de renouvellement,
    décale la période de garantie d'un an, et génère la quittance correspondante (RF-SOUS-07).
    Renvoie la quittance générée. L'auteur est déduit du jeton de connexion."""
    police = crud.get_or_404(db, models.Police, police_id)
    if police.statut != models.StatutPolice.en_vigueur:
        raise HTTPException(400, "Seule une police en vigueur peut être renouvelée.")
    # Garde anti-double-renouvellement : un avenant de renouvellement à effet futur existe déjà
    # -> la police a déjà été renouvelée (évite un double avenant et une double quittance).
    if db.query(models.Avenant).filter(
        models.Avenant.police_id == police.id,
        models.Avenant.type_avenant == models.TypeAvenant.renouvellement,
        models.Avenant.date_effet > date.today(),
    ).first() is not None:
        raise HTTPException(409, "Cette police a déjà un renouvellement enregistré à effet futur.")
    police.date_effet = _plus_un_an(police.date_effet)
    police.date_echeance = _plus_un_an(police.date_echeance)
    avenant = models.Avenant(
        police_id=police.id,
        type_avenant=models.TypeAvenant.renouvellement,
        motif="Renouvellement annuel",
        date_effet=police.date_effet,
        statut=models.StatutAvenant.valide,
        valide_par=user.id,
        date_validation=datetime.now(),
    )
    db.add(avenant)
    db.flush()  # attribue l'id de l'avenant avant de générer la quittance
    quittance = generer_quittance_pour_avenant(db, avenant)
    db.commit()
    db.refresh(quittance)
    return quittance
