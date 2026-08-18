"""recouvrement : etapes de relance (date_derniere_etape), historique, echeancier negocie (RF-RECOUV-02..05)

Revision ID: c3f1a2b4d5e6
Revises: b2d4f6a8c1e3
Create Date: 2026-08-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3f1a2b4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Étape courante du dossier (RF-RECOUV-02) : date d'entrée dans l'étape, base du délai.
    op.add_column(
        "dossier_recouvrement",
        sa.Column("date_derniere_etape", sa.Date(), server_default=sa.func.current_date(), nullable=False),
    )
    # Backfill : les dossiers existants entrent « dans leur étape » à leur date d'ouverture.
    op.execute("UPDATE dossier_recouvrement SET date_derniere_etape = date_ouverture")

    # 2) Historique tracé du dossier (RF-RECOUV-05).
    op.create_table(
        "evenement_recouvrement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_recouvrement_id", sa.Integer(), nullable=False),
        sa.Column("type_evenement", sa.String(length=40), nullable=False),
        sa.Column("ancien_statut", sa.String(length=30), nullable=True),
        sa.Column("nouveau_statut", sa.String(length=30), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("auteur_id", sa.Integer(), nullable=True),
        sa.Column("date_evenement", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dossier_recouvrement_id"], ["dossier_recouvrement.id"]),
        sa.ForeignKeyConstraint(["auteur_id"], ["utilisateur.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_evenement_recouv_dossier", "evenement_recouvrement", ["dossier_recouvrement_id"])

    # 3) Échéancier négocié (RF-RECOUV-04) : entête + versements.
    op.create_table(
        "echeancier_recouvrement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_recouvrement_id", sa.Integer(), nullable=False),
        sa.Column("montant_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("nombre_versements", sa.Integer(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dossier_recouvrement_id"], ["dossier_recouvrement.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dossier_recouvrement_id", name="uq_echeancier_dossier"),
    )

    valeurs = ("prevu", "regle", "manque")
    postgresql.ENUM(*valeurs, name="statut_versement_echeancier").create(op.get_bind(), checkfirst=True)
    op.create_table(
        "versement_echeancier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("echeancier_id", sa.Integer(), nullable=False),
        sa.Column("numero_ordre", sa.Integer(), nullable=False),
        sa.Column("date_prevue", sa.Date(), nullable=False),
        sa.Column("montant", sa.Numeric(precision=12, scale=2), nullable=False),
        # create_type=False : l'enum vient d'être créé ci-dessus.
        sa.Column("statut", postgresql.ENUM(*valeurs, name="statut_versement_echeancier", create_type=False),
                  server_default="prevu", nullable=False),
        sa.ForeignKeyConstraint(["echeancier_id"], ["echeancier_recouvrement.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("echeancier_id", "numero_ordre"),
    )


def downgrade() -> None:
    op.drop_table("versement_echeancier")
    postgresql.ENUM(name="statut_versement_echeancier").drop(op.get_bind(), checkfirst=True)
    op.drop_table("echeancier_recouvrement")
    op.drop_index("idx_evenement_recouv_dossier", table_name="evenement_recouvrement")
    op.drop_table("evenement_recouvrement")
    op.drop_column("dossier_recouvrement", "date_derniere_etape")
