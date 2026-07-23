"""
Planificateur de tâches en arrière-plan.
Tourne à l'intérieur du processus FastAPI (pas de conteneur séparé) : tant que
le serveur est allumé, la synchronisation des statuts de polices s'exécute
automatiquement, sans dépendre d'une consultation par un utilisateur.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .database import SessionLocal
from .sync import synchroniser_statuts_polices

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()


def _tache_synchronisation_polices():
    db = SessionLocal()
    try:
        synchroniser_statuts_polices(db)
        logger.info("Synchronisation automatique des statuts de polices exécutée.")
    finally:
        db.close()


def demarrer_scheduler():
    # Tourne chaque jour à 00h05, plus une fois immédiatement au démarrage
    # du serveur (pour rattraper les polices en attente pendant les périodes
    # où le serveur était éteint).
    scheduler.add_job(_tache_synchronisation_polices, CronTrigger(hour=0, minute=5))
    scheduler.start()
    _tache_synchronisation_polices()


def arreter_scheduler():
    scheduler.shutdown(wait=False)
