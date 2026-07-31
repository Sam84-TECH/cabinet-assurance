"""archivage des éditions PDF : table document_archive + enum type_document (RF-POL-04)

Revision ID: e4c1f7a9b0d2
Revises: d8e2b6a1c9f4
Create Date: 2026-07-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e4c1f7a9b0d2'
down_revision: Union[str, Sequence[str], None] = 'd8e2b6a1c9f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Trace horodatée des documents PDF générés côté serveur (RF-POL-04)."""
    valeurs = ("quittance", "attestation", "police", "bordereau_versement", "bordereau_reversement")
    postgresql.ENUM(*valeurs, name="type_document").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "document_archive",
        sa.Column("id", sa.Integer(), nullable=False),
        # create_type=False : l'enum vient d'être créé ci-dessus, ne pas le recréer ici.
        sa.Column("type_document", postgresql.ENUM(*valeurs, name="type_document", create_type=False), nullable=False),
        sa.Column("entite_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=50), nullable=True),
        sa.Column("nom_fichier", sa.String(length=255), nullable=False),
        sa.Column("chemin_fichier", sa.Text(), nullable=False),
        sa.Column("genere_par", sa.Integer(), nullable=True),
        sa.Column("date_generation", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["genere_par"], ["utilisateur.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_document_archive_cible", "document_archive", ["type_document", "entite_id"])


def downgrade() -> None:
    op.drop_index("idx_document_archive_cible", table_name="document_archive")
    op.drop_table("document_archive")
    postgresql.ENUM(name="type_document").drop(op.get_bind(), checkfirst=True)
