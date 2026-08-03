"""tarification par garantie : colonne police_garantie.capital_assure (RF-SOUS-02)

Revision ID: f1a2c3d4e5b6
Revises: e4c1f7a9b0d2
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2c3d4e5b6'
down_revision: Union[str, Sequence[str], None] = 'e4c1f7a9b0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Capital assuré d'une ligne police-garantie : base de la tarification proportionnelle
    (mode « taux »). Nullable — inutile pour une garantie au forfait."""
    op.add_column("police_garantie", sa.Column("capital_assure", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("police_garantie", "capital_assure")
