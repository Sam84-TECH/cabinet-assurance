"""
Recouvrement — balance âgée des impayés (RF-RECOUV-01) et bascule automatique en
recouvrement des quittances échues (RF-ECH-04).

RF-RECOUV-01 : les créances client impayées sont ventilées par ancienneté
(0-30, 30-60, 60-90 et +90 jours), calculées à la demande depuis les quittances —
pas de table dédiée. Le reste dû exclut les encaissements rejetés (cf. app/reglement.py).

RF-ECH-04 : au-delà du délai réglementaire, une quittance impayée bascule
automatiquement en recouvrement (ouverture d'un dossier). Déclenché par le
planificateur (app/scheduler.py) et disponible à la demande via un endpoint.

L'ancienneté se compte depuis `periode_debut` (date d'exigibilité de la prime),
bornée à 0 pour une prime pas encore échue.
"""

import os
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from . import models
from .reglement import montant_regle

# Délai (jours) au-delà duquel une quittance impayée bascule en recouvrement (RF-ECH-04).
# Surchargé par l'environnement pour ne pas figer une règle qui varie selon l'agence.
DELAI_RECOUVREMENT_JOURS = int(os.environ.get("DELAI_RECOUVREMENT_JOURS", "30"))

# Un dossier dans l'un de ces statuts est clos : il n'empêche pas d'en rouvrir un nouveau.
STATUTS_DOSSIER_CLOS = (
    models.StatutDossierRecouv.regularise,
    models.StatutDossierRecouv.resilie,
)


def _nom_client(client: models.Client | None) -> str:
    """Libellé d'affichage du client : raison sociale (entreprise) ou nom + prénom (particulier)."""
    if client is None:
        return ""
    if client.raison_sociale:
        return client.raison_sociale
    return " ".join(part for part in (client.nom, client.prenom) if part)


def _tranche(jours: int) -> str:
    """Range une ancienneté en jours dans l'une des quatre tranches de la balance âgée."""
    if jours <= 30:
        return "0_30"
    if jours <= 60:
        return "30_60"
    if jours <= 90:
        return "60_90"
    return "90_plus"


def _quittances_impayees(db: Session):
    """(quittance, reste_du, jours_retard) pour chaque quittance non annulée dont le reste dû
    est strictement positif. Le reste dû exclut les chèques rejetés ; on ne se fie pas au seul
    statut stocké (self-correcting : une quittance marquée `reglee` mais dont le chèque a été
    rejeté réapparaît si son reste dû redevient positif)."""
    aujourdhui = date.today()
    resultats = []
    quittances = db.query(models.Quittance).filter(
        models.Quittance.statut != models.StatutQuittance.annulee
    ).all()
    for quittance in quittances:
        reste = quittance.prime_ttc - montant_regle(db, quittance.id)
        if reste <= 0:
            continue
        jours = max((aujourdhui - quittance.periode_debut).days, 0)
        resultats.append((quittance, reste, jours))
    return resultats


def calculer_balance_agee(db: Session) -> dict:
    """Balance âgée des impayés (RF-RECOUV-01) : totaux par tranche + détail ligne à ligne,
    trié du plus ancien au plus récent."""
    tranches = {
        cle: {"nombre": 0, "montant": Decimal("0")}
        for cle in ("0_30", "30_60", "60_90", "90_plus")
    }
    lignes = []
    total = Decimal("0")

    for quittance, reste, jours in _quittances_impayees(db):
        cle = _tranche(jours)
        tranches[cle]["nombre"] += 1
        tranches[cle]["montant"] += reste
        total += reste

        police = db.get(models.Police, quittance.police_id)
        client = db.get(models.Client, police.client_id) if police else None
        lignes.append({
            "quittance_id": quittance.id,
            "numero_quittance": quittance.numero_quittance,
            "police_id": quittance.police_id,
            "numero_police": police.numero_police if police else None,  # écart §14
            "client_id": police.client_id if police else None,
            "client": _nom_client(client),
            "periode_debut": quittance.periode_debut,
            "reste_du": reste,
            "jours_retard": jours,
            "tranche": cle,
        })

    lignes.sort(key=lambda ligne: ligne["jours_retard"], reverse=True)
    return {
        "date_reference": date.today(),
        "tranche_0_30": tranches["0_30"],
        "tranche_30_60": tranches["30_60"],
        "tranche_60_90": tranches["60_90"],
        "tranche_90_plus": tranches["90_plus"],
        "total_impaye": total,
        "nombre_quittances": len(lignes),
        "lignes": lignes,
    }


def basculer_quittances_en_recouvrement(db: Session) -> int:
    """RF-ECH-04 : ouvre un dossier de recouvrement pour chaque quittance impayée dont le
    retard dépasse le délai réglementaire (DELAI_RECOUVREMENT_JOURS), sauf si un dossier
    non clôturé existe déjà pour cette quittance. Idempotent — renvoie le nombre de dossiers
    créés (0 si rien à faire), ce qui rend l'exécution rejouable sans doublon."""
    crees = 0
    for quittance, _reste, jours in _quittances_impayees(db):
        if jours <= DELAI_RECOUVREMENT_JOURS:
            continue
        deja_ouvert = db.query(models.DossierRecouvrement).filter(
            models.DossierRecouvrement.quittance_id == quittance.id,
            models.DossierRecouvrement.statut.not_in(STATUTS_DOSSIER_CLOS),
        ).first()
        if deja_ouvert is not None:
            continue
        db.add(models.DossierRecouvrement(
            quittance_id=quittance.id,
            statut=models.StatutDossierRecouv.ouvert,
        ))
        crees += 1
    if crees:
        db.commit()
    return crees
