"""
Génération des numéros métier (police, quittance...).
Convention actuelle simple : PREFIXE-ANNEE-COMPTEUR.
À affiner plus tard selon la convention définitive du cabinet
(ex: incorporer un code produit ou agence) — ce n'est pas figé côté schéma,
juste ce format de génération qu'on pourra changer sans toucher la DB.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from . import models


def generer_numero_police(db: Session) -> str:
    annee = datetime.now().year
    compteur = db.query(models.Police).count() + 1
    return f"POL-{annee}-{compteur:06d}"


def generer_numero_quittance(db: Session) -> str:
    annee = datetime.now().year
    compteur = db.query(models.Quittance).count() + 1
    return f"QUI-{annee}-{compteur:06d}"


def generer_numero_bordereau_versement(db: Session) -> str:
    annee = datetime.now().year
    compteur = db.query(models.BordereauVersement).count() + 1
    return f"BVER-{annee}-{compteur:06d}"


def generer_numero_bordereau_reversement(db: Session) -> str:
    annee = datetime.now().year
    compteur = db.query(models.BordereauReversement).count() + 1
    return f"BREV-{annee}-{compteur:06d}"
