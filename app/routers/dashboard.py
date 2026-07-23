"""
Module Tableau de bord.
Photo instantanée de l'activité, calculée à la demande (pas de table dédiée —
tout est dérivé des données existantes). Reprend les indicateurs du Module 1
observés dans DIAM.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..sync import synchroniser_statuts_polices

router = APIRouter(prefix="/dashboard", tags=["Tableau de bord"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db)):
    synchroniser_statuts_polices(db)
    aujourdhui = date.today()
    dans_30_jours = aujourdhui + timedelta(days=30)

    contrats_actifs = db.query(models.Police).filter(
        models.Police.statut == models.StatutPolice.en_vigueur
    ).count()

    contrats_expirant_bientot = db.query(models.Police).filter(
        models.Police.statut == models.StatutPolice.en_vigueur,
        models.Police.date_echeance >= aujourdhui,
        models.Police.date_echeance <= dans_30_jours,
    ).count()

    contrats_renouveles_aujourdhui = db.query(models.Avenant).filter(
        models.Avenant.type_avenant == models.TypeAvenant.renouvellement,
        models.Avenant.date_effet == aujourdhui,
    ).count()

    paiements_en_attente = db.query(models.Quittance).filter(
        models.Quittance.statut.in_([
            models.StatutQuittance.emise,
            models.StatutQuittance.reglee_partiellement,
        ])
    ).count()

    cheques_non_encaisses = db.query(models.Encaissement).filter(
        models.Encaissement.mode_paiement == models.ModePaiement.cheque,
        models.Encaissement.statut != models.StatutEncaissement.rapproche_banque,
    ).count()

    dossiers_recouvrement_ouverts = db.query(models.DossierRecouvrement).filter(
        models.DossierRecouvrement.statut.in_([
            models.StatutDossierRecouv.ouvert,
            models.StatutDossierRecouv.en_relance,
            models.StatutDossierRecouv.mise_en_demeure,
        ])
    ).count()

    nombre_clients = db.query(models.Client).count()

    return {
        "contrats_actifs": contrats_actifs,
        "contrats_expirant_sous_30_jours": contrats_expirant_bientot,
        "contrats_renouveles_aujourdhui": contrats_renouveles_aujourdhui,
        "paiements_en_attente": paiements_en_attente,
        "cheques_non_encaisses": cheques_non_encaisses,
        "dossiers_recouvrement_ouverts": dossiers_recouvrement_ouverts,
        "nombre_clients": nombre_clients,
        # sinistres_ouverts volontairement absent : module SIN hors périmètre de cette phase
    }
