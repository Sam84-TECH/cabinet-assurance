"""table piece justificative fournie

Revision ID: 95cf2a5ed450
Revises: b52e97576a8a
Create Date: 2026-07-28 11:25:44.909233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95cf2a5ed450'
down_revision: Union[str, Sequence[str], None] = 'b52e97576a8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Table des pièces justificatives fournies par dossier (police), support du RF-SOUS-04.
    Une pièce requise n'est fournie qu'une fois par police (contrainte unique)."""
    op.create_table(
        "piece_justificative_fournie",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("police_id", sa.Integer(), nullable=False),
        sa.Column("piece_requise_id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("date_fourniture", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.ForeignKeyConstraint(["police_id"], ["police.id"]),
        sa.ForeignKeyConstraint(["piece_requise_id"], ["piece_justificative_requise.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("police_id", "piece_requise_id", name="uq_piece_fournie_police_requise"),
    )


def downgrade() -> None:
    op.drop_table("piece_justificative_fournie")
