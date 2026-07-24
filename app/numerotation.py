"""
Génération des numéros métier (police, quittance, bordereaux).
Convention : PREFIXE-ANNEE-COMPTEUR (compteur sur 6 chiffres).

Le compteur provient d'une SÉQUENCE PostgreSQL dédiée par type de document
(`nextval`, atomique et monotone). Contrairement à l'ancien `count() + 1`, il ne
recule jamais après une suppression et ne collisionne pas en accès concurrent
(deux requêtes simultanées obtiennent deux valeurs distinctes).

Le compteur est global : il ne redémarre pas à chaque année (comportement
identique à l'ancienne implémentation). Les séquences sont créées par la
migration Alembic `..._sequences_numerotation.py`.

Le format de génération, lui, reste libre : on peut le changer (code produit,
agence…) sans toucher au schéma.
"""

from datetime import datetime

from sqlalchemy import Sequence, select
from sqlalchemy.orm import Session

# Séquences PostgreSQL (créées et positionnées par la migration Alembic).
SEQ_POLICE = Sequence("seq_numero_police")
SEQ_QUITTANCE = Sequence("seq_numero_quittance")
SEQ_BORDEREAU_VERSEMENT = Sequence("seq_numero_bordereau_versement")
SEQ_BORDEREAU_REVERSEMENT = Sequence("seq_numero_bordereau_reversement")


def _prochain(db: Session, sequence: Sequence) -> int:
    """Renvoie la prochaine valeur de la séquence (nextval, atomique et sans collision)."""
    return db.execute(select(sequence.next_value())).scalar()


def generer_numero_police(db: Session) -> str:
    return f"POL-{datetime.now().year}-{_prochain(db, SEQ_POLICE):06d}"


def generer_numero_quittance(db: Session) -> str:
    return f"QUI-{datetime.now().year}-{_prochain(db, SEQ_QUITTANCE):06d}"


def generer_numero_bordereau_versement(db: Session) -> str:
    return f"BVER-{datetime.now().year}-{_prochain(db, SEQ_BORDEREAU_VERSEMENT):06d}"


def generer_numero_bordereau_reversement(db: Session) -> str:
    return f"BREV-{datetime.now().year}-{_prochain(db, SEQ_BORDEREAU_REVERSEMENT):06d}"
