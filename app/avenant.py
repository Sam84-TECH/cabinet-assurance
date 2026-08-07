"""
Sémantique de l'avenant de modification (module SOUS).

Un avenant `modification` est l'enveloppe tracée sous laquelle on ajuste la composition
d'une police **déjà engagée** — changement de véhicule, ajout ou retrait de garantie
(règle 13 du CLAUDE.md : « le retrait passe par un avenant »). Tant qu'il est en
`brouillon`, la composition (risques, police_garanties) redevient modifiable ; sa
validation reverrouille la police en traçant l'auteur et la date, **sans générer de
quittance**.

Volet financier (ajustement de prime au prorata temporis, avoir/remboursement) : hors
périmètre de cette phase — cf. QUESTIONS_ENCADRANT.md (Q2). Voir aussi app/facturation.py.
"""

from sqlalchemy.orm import Session

from . import models


def composition_verrouillee(db: Session, police_id: int) -> bool:
    """La composition de la police est-elle verrouillée pour suppression directe (règle 13) ?

    - Aucun avenant validé : la police n'est pas encore engagée -> composition libre (False).
    - Un avenant validé existe : verrouillée (True), **sauf** si un avenant de modification est
      actuellement en `brouillon` sur la police -> il rouvre la composition, ce qui matérialise
      précisément le « passer par un avenant » attendu par la règle 13 (False).
    """
    engagee = (
        db.query(models.Avenant)
        .filter_by(police_id=police_id, statut=models.StatutAvenant.valide)
        .first()
        is not None
    )
    if not engagee:
        return False
    modification_ouverte = (
        db.query(models.Avenant)
        .filter_by(
            police_id=police_id,
            type_avenant=models.TypeAvenant.modification,
            statut=models.StatutAvenant.brouillon,
        )
        .first()
        is not None
    )
    return not modification_ouverte
