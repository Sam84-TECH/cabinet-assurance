"""
Synchronisation automatique du statut des polices selon la date du jour.
Appelée à chaque lecture (liste, détail, tableau de bord, reporting) pour que
le statut reflète toujours la réalité, sans tâche planifiée séparée (niveau 1
"à la demande" — suffisant tant que l'appli est consultée quotidiennement).
"""

from datetime import date
from sqlalchemy.orm import Session

from . import models


def synchroniser_statuts_polices(db: Session) -> None:
    """
    Toute police encore 'en_attente_effet' dont la date d'effet est arrivée
    passe automatiquement à 'en_vigueur'.
    """
    aujourdhui = date.today()
    a_activer = db.query(models.Police).filter(
        models.Police.statut == models.StatutPolice.en_attente_effet,
        models.Police.date_effet <= aujourdhui,
    ).all()
    for police in a_activer:
        police.statut = models.StatutPolice.en_vigueur
    if a_activer:
        db.commit()
