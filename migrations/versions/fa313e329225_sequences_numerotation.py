"""sequences_numerotation

Revision ID: fa313e329225
Revises: 32e34f5cc6bd
Create Date: 2026-07-24 17:19:29.534645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa313e329225'
down_revision: Union[str, Sequence[str], None] = '32e34f5cc6bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Séquences à créer : (nom de séquence, table, colonne "numéro").
# La colonne sert à positionner la séquence après le plus grand compteur déjà attribué.
_SEQUENCES = [
    ("seq_numero_police", "police", "numero_police"),
    ("seq_numero_quittance", "quittance", "numero_quittance"),
    ("seq_numero_bordereau_versement", "bordereau_versement", "numero_bordereau"),
    ("seq_numero_bordereau_reversement", "bordereau_reversement", "numero_bordereau"),
]


def upgrade() -> None:
    """Crée une séquence PostgreSQL par type de numéro métier, en remplacement du
    count()+1 (qui collisionnait après suppression et en accès concurrent).

    Chaque séquence est positionnée juste après le plus grand compteur déjà attribué
    (dernier segment du numéro « PREFIXE-ANNEE-COMPTEUR ») afin de ne jamais régénérer
    un numéro existant. is_called=false => le prochain nextval renvoie cette valeur ;
    sur une base vide, la séquence démarre donc à 1."""
    for sequence, table, colonne in _SEQUENCES:
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {sequence}")
        op.execute(
            f"SELECT setval('{sequence}', "
            f"COALESCE((SELECT MAX(split_part({colonne}, '-', 3)::bigint) FROM {table}), 0) + 1, "
            f"false)"
        )


def downgrade() -> None:
    """Supprime les séquences de numérotation."""
    for sequence, _table, _colonne in _SEQUENCES:
        op.execute(f"DROP SEQUENCE IF EXISTS {sequence}")
