"""
Module Encaissement (ENC) — règlement client, son affectation à une ou plusieurs quittances,
l'édition du reçu (RF-ENC-04) et le rejet de chèque impayé (remise en impayé + traçage).
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..reglement import montant_regle, recalculer_statut_quittance

router = APIRouter(prefix="/encaissements", tags=["Encaissement"])


@router.post("", response_model=schemas.EncaissementRead)
def create_encaissement(payload: schemas.EncaissementCreate, db: Session = Depends(get_db),
                         user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["enregistre_par"] = user.id  # déduit automatiquement, plus besoin de le fournir
    return crud.create(db, models.Encaissement, data)


@router.get("", response_model=list[schemas.EncaissementRead])
def list_encaissements(client_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.Encaissement, skip, limit, client_id=client_id)


@router.get("/{encaissement_id}", response_model=schemas.EncaissementRead)
def get_encaissement(encaissement_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.Encaissement, encaissement_id)


@router.post("/{encaissement_id}/affecter/{quittance_id}", response_model=schemas.EncaissementQuittanceRead)
def affecter_a_quittance(encaissement_id: int, quittance_id: int, payload: schemas.AffectationCreate,
                          db: Session = Depends(get_db),
                          user: models.Utilisateur = Depends(get_current_user)):
    """
    Affecte tout ou partie d'un encaissement à une quittance (montant dans le corps).
    Garde-fous : montant strictement positif, encaissement non rejeté, encaissement et quittance
    du même client, sans dépasser le reste disponible de l'encaissement ni le reste dû de la
    quittance, et quittance non annulée. Met ensuite à jour le statut de la quittance (réglée /
    réglée partiellement) selon le total réglé. Le reste dû exclut les affectations
    d'encaissements rejetés (cf. app/reglement.py).
    """
    montant = payload.montant_affecte
    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    quittance = crud.get_or_404(db, models.Quittance, quittance_id)

    if montant <= 0:
        raise HTTPException(400, "Le montant à affecter doit être strictement positif.")
    if encaissement.statut == models.StatutEncaissement.rejete:
        raise HTTPException(400, "Cet encaissement a été rejeté : aucune affectation n'est possible.")
    if quittance.statut == models.StatutQuittance.annulee:
        raise HTTPException(400, "Cette quittance est annulée : aucune affectation n'est possible.")

    # Cohérence client : le règlement d'un client ne peut solder la quittance d'un autre.
    police = crud.get_or_404(db, models.Police, quittance.police_id)
    if police.client_id != encaissement.client_id:
        raise HTTPException(
            400, "L'encaissement et la quittance ne concernent pas le même client : affectation refusée.")

    # Reste disponible sur l'encaissement = montant total - ce qui est déjà affecté ailleurs.
    lignes_encaissement = db.query(models.EncaissementQuittance).filter_by(encaissement_id=encaissement_id).all()
    reste_encaissement = encaissement.montant - sum((l.montant_affecte for l in lignes_encaissement), Decimal("0"))
    if montant > reste_encaissement:
        raise HTTPException(400, f"Le montant dépasse le reste disponible sur l'encaissement ({reste_encaissement}).")

    # Reste dû sur la quittance = prime TTC - ce qui a déjà été réglé (hors chèques rejetés).
    reste_quittance = quittance.prime_ttc - montant_regle(db, quittance_id)
    if montant > reste_quittance:
        raise HTTPException(400, f"Le montant dépasse le reste dû sur la quittance ({reste_quittance}).")

    lien = crud.create(db, models.EncaissementQuittance, {
        "encaissement_id": encaissement_id,
        "quittance_id": quittance_id,
        "montant_affecte": montant,
    })

    # Recalcule le statut de la quittance à partir du total réglé effectif.
    recalculer_statut_quittance(db, quittance)
    db.commit()

    return lien


@router.get("/{encaissement_id}/recu", response_model=schemas.RecuEncaissement)
def recu_encaissement(encaissement_id: int, db: Session = Depends(get_db),
                       user: models.Utilisateur = Depends(get_current_user)):
    """
    Reçu d'encaissement (RF-ENC-04) : atteste le règlement reçu du client. Récapitule le
    montant, le mode de paiement, les quittances réglées et l'éventuel reliquat non affecté.
    Un encaissement rejeté n'atteste aucun paiement : son reçu est refusé (400).
    Le numéro de reçu est dérivé de l'encaissement (déterministe, sans écriture en base).
    """
    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    if encaissement.statut == models.StatutEncaissement.rejete:
        raise HTTPException(400, "Encaissement rejeté : aucun reçu ne peut être édité.")

    client = crud.get_or_404(db, models.Client, encaissement.client_id)
    liens = db.query(models.EncaissementQuittance).filter_by(encaissement_id=encaissement_id).all()
    lignes = []
    for lien in liens:
        quittance = db.get(models.Quittance, lien.quittance_id)
        lignes.append({
            "quittance_id": quittance.id,
            "numero_quittance": quittance.numero_quittance,
            "montant_affecte": lien.montant_affecte,
        })

    montant_affecte = sum((lien.montant_affecte for lien in liens), Decimal("0"))
    agent = db.get(models.Utilisateur, encaissement.enregistre_par) if encaissement.enregistre_par else None

    return {
        "numero_recu": f"REC-{encaissement.date_encaissement.year}-{encaissement.id:06d}",
        "date_edition": date.today(),
        "encaissement": encaissement,
        "client": client,
        "montant_affecte": montant_affecte,
        "montant_non_affecte": encaissement.montant - montant_affecte,
        "quittances_reglees": lignes,
        "enregistre_par": agent,
    }


@router.post("/{encaissement_id}/rejeter", response_model=schemas.EncaissementRead)
def rejeter_cheque(encaissement_id: int, payload: schemas.RejetChequeCreate, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    """
    Rejet d'un chèque impayé : passe l'encaissement au statut `rejete`, trace l'incident
    (motif + date de rejet, auteur via le journal d'audit) et remet chaque quittance qu'il
    réglait en impayé (son montant réglé effectif retombe, cf. app/reglement.py). Seul un
    encaissement par chèque, non déjà rejeté et non encore rapproché en banque, peut être
    rejeté par cet endpoint.
    """
    encaissement = crud.get_or_404(db, models.Encaissement, encaissement_id)
    if encaissement.mode_paiement != models.ModePaiement.cheque:
        raise HTTPException(400, "Seul un encaissement par chèque peut faire l'objet d'un rejet.")
    if encaissement.statut == models.StatutEncaissement.rejete:
        raise HTTPException(400, "Cet encaissement est déjà marqué comme rejeté.")
    if encaissement.statut == models.StatutEncaissement.rapproche_banque:
        # Chèque déjà déposé et rapproché (bordereau de versement validé) : la règle 7 interdit
        # de modifier en silence un bordereau validé. Un retour impayé après dépôt se corrige
        # par un bordereau rectificatif tracé, pas par un simple changement de statut ici.
        raise HTTPException(
            409, "Cet encaissement est déjà rapproché en banque (bordereau de versement validé) : "
                 "un chèque revenu impayé après dépôt se corrige par un bordereau rectificatif tracé.")

    # Quittances actuellement réglées (en tout ou partie) par cet encaissement, à recalculer.
    quittance_ids = [
        lien.quittance_id
        for lien in db.query(models.EncaissementQuittance).filter_by(encaissement_id=encaissement_id).all()
    ]

    encaissement.statut = models.StatutEncaissement.rejete
    encaissement.motif_rejet = payload.motif
    encaissement.date_rejet = payload.date_rejet or date.today()
    db.flush()  # rend le statut `rejete` visible aux recalculs (autoflush désactivé)

    for quittance_id in quittance_ids:
        quittance = db.get(models.Quittance, quittance_id)
        if quittance is not None:
            recalculer_statut_quittance(db, quittance)

    db.commit()
    db.refresh(encaissement)
    return encaissement
