"""reversement effectif : reference_virement, date_reversement, reverse_par (§18)

Revision ID: a7b3e9c1d2f4
Revises: f1a2c3d4e5b6
Create Date: 2026-08-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b3e9c1d2f4'
down_revision: Union[str, Sequence[str], None] = 'f1a2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reversement effectif à la compagnie (PATCH .../reverser, statut `reverse`) : référence du
    virement, date de reversement et auteur. Colonnes nullables (renseignées au reversement)."""
    op.add_column("bordereau_reversement", sa.Column("reference_virement", sa.String(length=100), nullable=True))
    op.add_column("bordereau_reversement", sa.Column("date_reversement", sa.Date(), nullable=True))
    op.add_column("bordereau_reversement", sa.Column("reverse_par", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_bordereau_reversement_reverse_par", "bordereau_reversement", "utilisateur",
        ["reverse_par"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_bordereau_reversement_reverse_par", "bordereau_reversement", type_="foreignkey")
    op.drop_column("bordereau_reversement", "reverse_par")
    op.drop_column("bordereau_reversement", "date_reversement")
    op.drop_column("bordereau_reversement", "reference_virement")
