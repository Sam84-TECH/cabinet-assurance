"""unique quittance avenant_id

Revision ID: b52e97576a8a
Revises: fa313e329225
Create Date: 2026-07-27 17:19:06.549971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b52e97576a8a'
down_revision: Union[str, Sequence[str], None] = 'fa313e329225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Une quittance par avenant (RF-SOUS-07) : contrainte UNIQUE sur quittance.avenant_id,
    dernier rempart contre un doublon (POST manuel verrouillé + génération idempotente).
    Échoue si des doublons existent déjà en base : les résoudre (annulation) au préalable."""
    op.create_unique_constraint("uq_quittance_avenant_id", "quittance", ["avenant_id"])


def downgrade() -> None:
    op.drop_constraint("uq_quittance_avenant_id", "quittance", type_="unique")
