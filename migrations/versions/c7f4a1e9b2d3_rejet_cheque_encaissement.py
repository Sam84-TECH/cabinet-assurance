"""rejet cheque : colonnes motif_rejet et date_rejet sur encaissement

Revision ID: c7f4a1e9b2d3
Revises: 95cf2a5ed450
Create Date: 2026-07-28 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f4a1e9b2d3'
down_revision: Union[str, Sequence[str], None] = '95cf2a5ed450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Traçage du rejet de chèque : motif de l'incident et date de rejet.
    Colonnes nullables (renseignées uniquement quand l'encaissement passe au statut `rejete`)."""
    op.add_column("encaissement", sa.Column("motif_rejet", sa.String(length=255), nullable=True))
    op.add_column("encaissement", sa.Column("date_rejet", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("encaissement", "date_rejet")
    op.drop_column("encaissement", "motif_rejet")
