"""
Génération automatique de la quittance à la validation d'un avenant (RF-SOUS-07).

À la validation d'un avenant d'affaire nouvelle ou de renouvellement, la quittance est
calculée à partir des garanties rattachées à la police (fini la saisie manuelle) :

    prime_nette = somme des primes des garanties de la police
    taxes       = prime_nette * TAUX_TAXE / 100
    prime_ttc   = prime_nette + taxes + timbres + accessoires        (règle métier n°4)

La commission (part de l'agence, qui NE s'ajoute PAS au TTC) est calculée via le barème
compagnie/produit. Les paramètres fiscaux (taux de taxe, droit de timbre) sont lus dans
l'environnement pour ne pas figer une fiscalité en dur — défauts branche auto Maroc, à
ajuster selon la réglementation en vigueur.
"""

import os
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from sqlalchemy.orm import Session

from . import models
from .numerotation import generer_numero_quittance


def _param_decimal(nom: str, defaut: str) -> Decimal:
    """Lit un paramètre décimal dans l'environnement, avec un message clair si la valeur est
    mal formée (ex. séparateur virgule `14,00`) plutôt qu'un InvalidOperation opaque au démarrage."""
    brut = os.environ.get(nom, defaut)
    try:
        return Decimal(brut)
    except InvalidOperation:
        raise RuntimeError(
            f"Variable d'environnement {nom}={brut!r} invalide : nombre décimal attendu "
            f"(point décimal, ex. « 14.00 »)."
        )


# Paramètres fiscaux, surchargeables via l'environnement (voir .env.example).
TAUX_TAXE = _param_decimal("TAUX_TAXE_ASSURANCE", "14.00")   # % sur la prime nette
DROIT_TIMBRE = _param_decimal("DROIT_TIMBRE", "0.00")        # timbre fixe par quittance

# Seuls ces avenants donnent lieu à une quittance de prime pleine calculée depuis les
# garanties. Modification, suspension et résiliation relèvent d'un traitement dédié
# (avenant complémentaire, avoir, remboursement) hors périmètre RF-SOUS-07.
TYPES_AVEC_QUITTANCE = {
    models.TypeAvenant.affaire_nouvelle,
    models.TypeAvenant.renouvellement,
}


def _centimes(montant: Decimal) -> Decimal:
    return montant.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _taux_commission(db: Session, compagnie_id: int, produit_id: int) -> Decimal:
    """Taux du barème applicable : priorité compagnie+produit, sinon barème général de la
    compagnie (produit_id NULL), sinon 0 — la commission ne bloque pas l'émission."""
    bareme = (
        db.query(models.BaremeCommission)
        .filter_by(compagnie_id=compagnie_id, produit_id=produit_id)
        .first()
        or db.query(models.BaremeCommission)
        .filter_by(compagnie_id=compagnie_id, produit_id=None)
        .first()
    )
    return bareme.taux_commission if bareme else Decimal("0")


def generer_quittance_pour_avenant(db: Session, avenant: models.Avenant) -> models.Quittance | None:
    """Crée et renvoie la quittance de l'avenant, ou None si son type n'en génère pas.

    Idempotent : si l'avenant a déjà une quittance, la renvoie sans en créer une seconde.
    L'objet est ajouté et flushé (id attribué) mais PAS committé — le commit revient à
    l'appelant (valider_avenant), pour rester atomique avec la validation.
    """
    if avenant.type_avenant not in TYPES_AVEC_QUITTANCE:
        return None

    existante = db.query(models.Quittance).filter_by(avenant_id=avenant.id).first()
    if existante is not None:
        return existante

    police = db.get(models.Police, avenant.police_id)
    produit = db.get(models.Produit, police.produit_id)

    # prime_nette = somme des primes des garanties rattachées à la police
    lignes = db.query(models.PoliceGarantie).filter_by(police_id=police.id).all()
    prime_nette = _centimes(sum((ligne.montant_prime or Decimal("0") for ligne in lignes), Decimal("0")))

    taxes = _centimes(prime_nette * TAUX_TAXE / Decimal("100"))
    timbres = _centimes(DROIT_TIMBRE)
    accessoires = Decimal("0.00")
    prime_ttc = _centimes(prime_nette + taxes + timbres + accessoires)  # règle métier n°4

    taux = _taux_commission(db, produit.compagnie_id, police.produit_id)
    commission = _centimes(prime_nette * taux / Decimal("100"))

    quittance = models.Quittance(
        numero_quittance=generer_numero_quittance(db),
        police_id=police.id,
        avenant_id=avenant.id,
        periode_debut=avenant.date_effet,
        periode_fin=police.date_echeance,
        prime_nette=prime_nette,
        taxes=taxes,
        timbres=timbres,
        commission=commission,
        accessoires=accessoires,
        prime_ttc=prime_ttc,
        statut=models.StatutQuittance.emise,
    )
    db.add(quittance)
    db.flush()  # attribue l'id ; le commit est fait par l'appelant
    return quittance
