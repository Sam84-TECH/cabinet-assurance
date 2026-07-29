"""
Règlement des quittances — montant effectivement réglé, et recalcul du statut.

Règle clé : un encaissement rejeté (chèque impayé) ne compte plus dans le règlement
d'une quittance. Le montant réglé effectif ne retient donc QUE les affectations dont
l'encaissement n'est pas au statut `rejete`. Centralisé ici pour que l'affectation
(encaissement.py), le rejet de chèque (encaissement.py) et la balance âgée
(recouvrement.py) appliquent tous exactement la même règle — jamais dupliquée.
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def montant_regle(db: Session, quittance_id: int) -> Decimal:
    """Somme des montants affectés à la quittance, hors encaissements rejetés.
    Renvoie 0 si la quittance n'a aucune affectation valide."""
    total = (
        db.query(func.coalesce(func.sum(models.EncaissementQuittance.montant_affecte), 0))
        .join(
            models.Encaissement,
            models.Encaissement.id == models.EncaissementQuittance.encaissement_id,
        )
        .filter(
            models.EncaissementQuittance.quittance_id == quittance_id,
            models.Encaissement.statut != models.StatutEncaissement.rejete,
        )
        .scalar()
    )
    return Decimal(total)


def recalculer_statut_quittance(db: Session, quittance: models.Quittance) -> None:
    """Aligne le statut de la quittance sur son montant réglé effectif :
      - >= prime_ttc  -> `reglee`
      - > 0           -> `reglee_partiellement`
      - 0             -> `emise` (impayé)
    Une quittance `annulee` n'est jamais touchée. Ne committe pas (l'appelant décide) :
    utilisé aussi bien à l'affectation d'un règlement qu'au rejet d'un chèque (qui remet
    la quittance en impayé)."""
    if quittance.statut == models.StatutQuittance.annulee:
        return
    regle = montant_regle(db, quittance.id)
    if regle >= quittance.prime_ttc:
        quittance.statut = models.StatutQuittance.reglee
    elif regle > 0:
        quittance.statut = models.StatutQuittance.reglee_partiellement
    else:
        quittance.statut = models.StatutQuittance.emise
