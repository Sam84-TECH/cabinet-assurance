"""add mot_de_passe_hash to utilisateur

Revision ID: 32e34f5cc6bd
Revises: 112a861157aa
Create Date: 2026-07-16 14:31:20.990842

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32e34f5cc6bd'
down_revision: Union[str, Sequence[str], None] = '112a861157aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('utilisateur', sa.Column('mot_de_passe_hash', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('utilisateur', 'mot_de_passe_hash')
