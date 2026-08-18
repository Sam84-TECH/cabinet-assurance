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
from .recouvrement import basculer_quittances_en_recouvrement, progresser_dossiers_echus

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()


def _tache_synchronisation_polices():
    db = SessionLocal()
    try:
        synchroniser_statuts_polices(db)
        logger.info("Synchronisation automatique des statuts de polices exécutée.")
    finally:
        db.close()


def _tache_bascule_recouvrement():
    db = SessionLocal()
    try:
        nombre = basculer_quittances_en_recouvrement(db)
        logger.info("Bascule automatique en recouvrement : %d dossier(s) ouvert(s).", nombre)
    finally:
        db.close()


def _tache_progression_recouvrement():
    db = SessionLocal()
    try:
        transitions = progresser_dossiers_echus(db)
        logger.info("Progression automatique des dossiers de recouvrement : %d transition(s).",
                    len(transitions))
    finally:
        db.close()


def demarrer_scheduler():
    # Tournent chaque jour peu après minuit, plus une fois immédiatement au démarrage
    # du serveur (pour rattraper la période où le serveur était éteint) : d'abord la
    # synchronisation des statuts de polices, puis la bascule des quittances échues en
    # recouvrement (RF-ECH-04), puis la progression des dossiers de recouvrement d'une
    # étape de relance à la suivante après le délai (RF-RECOUV-02) — chaque étape s'appuyant
    # sur des données à jour.
    scheduler.add_job(_tache_synchronisation_polices, CronTrigger(hour=0, minute=5))
    scheduler.add_job(_tache_bascule_recouvrement, CronTrigger(hour=0, minute=10))
    scheduler.add_job(_tache_progression_recouvrement, CronTrigger(hour=0, minute=15))
    scheduler.start()
    _tache_synchronisation_polices()
    _tache_bascule_recouvrement()
    _tache_progression_recouvrement()


def arreter_scheduler():
    scheduler.shutdown(wait=False)
