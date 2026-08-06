"""
Module Reporting.
Fournit les données agrégées par période, pour les catégories listées dans
DIAM (Module 13) : Production, Paiements, Versements, Reversements, Clients,
Commissions, Chiffre d'affaires, Renouvellements, Échéances.

IMPORTANT — périmètre actuel : ces endpoints renvoient les données en JSON.
La génération de fichiers exportables (Word/PDF/Excel, prévue dans DIAM) n'est
PAS encore implémentée — ce sera une étape suivante, une fois le frontend en
place pour définir le format d'affichage attendu.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..sync import synchroniser_statuts_polices

router = APIRouter(prefix="/reporting", tags=["Reporting"])


@router.get("/production")
def production(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    polices = db.query(models.Police).filter(
        models.Police.date_creation >= date_debut, models.Police.date_creation <= date_fin
    ).all()
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_polices": len(polices),
    }


@router.get("/paiements")
def paiements(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    encaissements = db.query(models.Encaissement).filter(
        models.Encaissement.date_encaissement >= date_debut,
        models.Encaissement.date_encaissement <= date_fin,
    ).all()
    total = sum((e.montant for e in encaissements), 0)
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_encaissements": len(encaissements),
        "montant_total": total,
        "par_mode_paiement": {
            mode.value: sum((e.montant for e in encaissements if e.mode_paiement == mode), 0)
            for mode in models.ModePaiement
        },
    }


@router.get("/versements")
def versements(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    bordereaux = db.query(models.BordereauVersement).filter(
        models.BordereauVersement.date_bordereau >= date_debut,
        models.BordereauVersement.date_bordereau <= date_fin,
    ).all()
    lignes_total = 0
    for b in bordereaux:
        lignes = db.query(models.BordereauVersementLigne).filter_by(bordereau_versement_id=b.id).all()
        lignes_total += sum((l.montant for l in lignes), 0)
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_bordereaux": len(bordereaux),
        "montant_total_verse": lignes_total,
    }


@router.get("/reversements")
def reversements(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    bordereaux = db.query(models.BordereauReversement).filter(
        models.BordereauReversement.periode_debut >= date_debut,
        models.BordereauReversement.periode_fin <= date_fin,
    ).all()
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_bordereaux": len(bordereaux),
        "montant_total_reverse": sum((b.montant_total for b in bordereaux), 0),
        "commission_totale": sum((b.commission_totale for b in bordereaux), 0),
    }


@router.get("/commissions")
def commissions(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    bordereaux = db.query(models.BordereauReversement).filter(
        models.BordereauReversement.date_generation >= date_debut,
        models.BordereauReversement.date_generation <= date_fin,
    ).all()
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "commission_totale": sum((b.commission_totale for b in bordereaux), 0),
    }


@router.get("/chiffre-affaires")
def chiffre_affaires(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    quittances = db.query(models.Quittance).filter(
        models.Quittance.date_creation >= date_debut, models.Quittance.date_creation <= date_fin,
        models.Quittance.statut != models.StatutQuittance.annulee,  # une quittance annulée ne compte pas
    ).all()
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_quittances": len(quittances),
        "prime_nette_totale": sum((q.prime_nette for q in quittances), 0),
        "prime_ttc_totale": sum((q.prime_ttc for q in quittances), 0),
    }


@router.get("/renouvellements")
def renouvellements(date_debut: date, date_fin: date, db: Session = Depends(get_db)):
    avenants = db.query(models.Avenant).filter(
        models.Avenant.type_avenant == models.TypeAvenant.renouvellement,
        models.Avenant.date_effet >= date_debut,
        models.Avenant.date_effet <= date_fin,
    ).all()
    return {
        "periode": {"debut": date_debut, "fin": date_fin},
        "nombre_renouvellements": len(avenants),
    }


@router.get("/echeances")
def echeances(jours: int = Query(30, description="Contrats arrivant à échéance dans N jours"),
              db: Session = Depends(get_db)):
    from datetime import timedelta
    synchroniser_statuts_polices(db)
    aujourdhui = date.today()
    limite = aujourdhui + timedelta(days=jours)
    polices = db.query(models.Police).filter(
        models.Police.statut == models.StatutPolice.en_vigueur,
        models.Police.date_echeance >= aujourdhui,
        models.Police.date_echeance <= limite,
    ).all()
    return {
        "horizon_jours": jours,
        "nombre_contrats": len(polices),
        "polices": [{"id": p.id, "numero_police": p.numero_police, "date_echeance": p.date_echeance} for p in polices],
    }
