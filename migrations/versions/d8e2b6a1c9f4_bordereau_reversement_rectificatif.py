"""bordereau de reversement rectificatif : colonne rectifie_bordereau_id (self-FK)

Revision ID: d8e2b6a1c9f4
Revises: c7f4a1e9b2d3
Create Date: 2026-07-29 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e2b6a1c9f4'
down_revision: Union[str, Sequence[str], None] = 'c7f4a1e9b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Traçabilité du bordereau rectificatif (règle CDCF n°7) : un bordereau qui en corrige
    un autre (déjà validé) référence l'original via rectifie_bordereau_id. Auto-référence
    nullable (NULL pour un bordereau initial)."""
    op.add_column(
        "bordereau_reversement",
        sa.Column("rectifie_bordereau_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bordereau_reversement_rectifie",
        "bordereau_reversement",
        "bordereau_reversement",
        ["rectifie_bordereau_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_bordereau_reversement_rectifie", "bordereau_reversement", type_="foreignkey")
    op.drop_column("bordereau_reversement", "rectifie_bordereau_id")
