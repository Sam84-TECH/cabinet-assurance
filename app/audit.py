"""
Journal d'audit — historisation automatique (CDCF §6, traçabilité transversale).

Des listeners SQLAlchemy interceptent les créations, modifications et suppressions sur
toutes les tables métier et écrivent une ligne dans `journal_audit` (auteur, date,
ancienne et nouvelle valeur).

L'auteur est déduit de l'utilisateur connecté : la dépendance `get_current_user` dépose
son id dans `session.info["auteur_id"]`, que les listeners relisent au moment du flush
(la session étant partagée par référence, c'est fiable même en exécution multi-thread).

Les écritures d'audit passent par la Connection (Core), jamais par la Session : elles ne
redéclenchent donc pas les listeners ORM — aucune récursion. La table `journal_audit`
elle-même est exclue de l'audit.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Mapper, object_session

from .models import JournalAudit

CLE_AUTEUR = "auteur_id"

# Colonnes jamais recopiées dans le journal (secret d'authentification, etc.).
COLONNES_SENSIBLES = {"mot_de_passe_hash"}


def _json_safe(valeur):
    """Rend une valeur de colonne sérialisable en JSON(B) (Decimal, date, enum…).
    Les types déjà JSON-safe (dict/list JSONB, str, int, float, bool, None) passent tels
    quels ; tout autre type est converti en str par sécurité, pour qu'une colonne d'un type
    inattendu ne fasse jamais échouer l'écriture d'audit (et donc la mutation métier)."""
    if isinstance(valeur, Enum):
        return valeur.value
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if valeur is None or isinstance(valeur, (dict, list, str, int, float, bool)):
        return valeur
    return str(valeur)


def _snapshot(obj) -> dict:
    """Valeurs des colonnes chargées de l'objet, sans déclencher de lazy load
    (colonnes à défaut serveur non chargées, ex. date_creation, ignorées ; colonnes
    sensibles, ex. mot_de_passe_hash, jamais recopiées)."""
    etat = sa_inspect(obj)
    return {
        attr.key: _json_safe(getattr(obj, attr.key))
        for attr in etat.mapper.column_attrs
        if attr.key not in etat.unloaded and attr.key not in COLONNES_SENSIBLES
    }


def _auteur(target):
    """Id de l'utilisateur à l'origine de l'opération, déposé dans session.info."""
    session = object_session(target)
    return session.info.get(CLE_AUTEUR) if session is not None else None


def _ecrire(connection, target, action, ancienne, nouvelle):
    connection.execute(
        JournalAudit.__table__.insert().values(
            table_cible=target.__tablename__,
            enregistrement_id=target.id,
            action=action,
            auteur_id=_auteur(target),
            ancienne_valeur=ancienne,
            nouvelle_valeur=nouvelle,
        )
    )


def _audit_insert(mapper, connection, target):
    if isinstance(target, JournalAudit):
        return
    _ecrire(connection, target, "creation", None, _snapshot(target))


def _audit_update(mapper, connection, target):
    if isinstance(target, JournalAudit):
        return
    etat = sa_inspect(target)
    ancienne, nouvelle = {}, {}
    for attr in etat.mapper.column_attrs:
        if attr.key in COLONNES_SENSIBLES:
            continue
        histo = etat.attrs[attr.key].history
        if histo.has_changes():
            ancienne[attr.key] = _json_safe(histo.deleted[0]) if histo.deleted else None
            nouvelle[attr.key] = _json_safe(histo.added[0]) if histo.added else None
    if nouvelle:  # au moins une colonne a réellement changé
        _ecrire(connection, target, "modification", ancienne, nouvelle)


def _audit_delete(mapper, connection, target):
    if isinstance(target, JournalAudit):
        return
    _ecrire(connection, target, "suppression", _snapshot(target), None)


def configurer_audit():
    """Enregistre les listeners sur tous les mappers. Idempotent : un second appel (double
    import, rechargement en tests) ne réenregistre pas les listeners — évite les doublons
    de lignes d'audit."""
    for evenement, gestionnaire in (
        ("after_insert", _audit_insert),
        ("before_update", _audit_update),
        ("before_delete", _audit_delete),
    ):
        if not event.contains(Mapper, evenement, gestionnaire):
            event.listen(Mapper, evenement, gestionnaire)
