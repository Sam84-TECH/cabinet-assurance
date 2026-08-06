"""annulation de quittance : motif_annulation, date_annulation, annule_par (§11)

Revision ID: b2d4f6a8c1e3
Revises: a7b3e9c1d2f4
Create Date: 2026-08-05 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c1e3'
down_revision: Union[str, Sequence[str], None] = 'a7b3e9c1d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Annulation d'une quittance (statut `annulee`, réservé super admin) : motif obligatoire,
    date et auteur. Colonnes nullables (renseignées à l'annulation)."""
    op.add_column("quittance", sa.Column("motif_annulation", sa.String(length=255), nullable=True))
    op.add_column("quittance", sa.Column("date_annulation", sa.Date(), nullable=True))
    op.add_column("quittance", sa.Column("annule_par", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_quittance_annule_par", "quittance", "utilisateur", ["annule_par"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_quittance_annule_par", "quittance", type_="foreignkey")
    op.drop_column("quittance", "annule_par")
    op.drop_column("quittance", "date_annulation")
    op.drop_column("quittance", "motif_annulation")
