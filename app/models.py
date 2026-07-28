"""
Modèles SQLAlchemy — Application de gestion cabinet d'assurance
Périmètre : Assurance Automobile uniquement
Flux couvert : SOUS -> POL -> ENC -> BANQ -> REV -> RECOUV
Correspond exactement à schema.sql
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    ForeignKey, String, Text, Boolean, Numeric, Date, DateTime,
    UniqueConstraint, CheckConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PgEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ------------------------------------------------------------
# Types énumérés (Python) — reflètent les ENUM PostgreSQL
# ------------------------------------------------------------

class TypeClient(str, PyEnum):
    particulier = "particulier"
    entreprise = "entreprise"


class StatutClient(str, PyEnum):
    actif = "actif"
    prospect = "prospect"
    vip = "vip"


class RoleUtilisateur(str, PyEnum):
    utilisateur = "utilisateur"
    super_administrateur = "super_administrateur"


class StatutPolice(str, PyEnum):
    en_attente_effet = "en_attente_effet"
    en_vigueur = "en_vigueur"
    suspendu = "suspendu"
    resilie = "resilie"


class TypeAvenant(str, PyEnum):
    affaire_nouvelle = "affaire_nouvelle"
    renouvellement = "renouvellement"
    modification = "modification"
    suspension = "suspension"
    resiliation = "resiliation"


class StatutAvenant(str, PyEnum):
    brouillon = "brouillon"
    valide = "valide"
    annule = "annule"


class StatutQuittance(str, PyEnum):
    emise = "emise"
    reglee_partiellement = "reglee_partiellement"
    reglee = "reglee"
    annulee = "annulee"


class ModePaiement(str, PyEnum):
    especes = "especes"
    cheque = "cheque"
    virement = "virement"


class StatutEncaissement(str, PyEnum):
    enregistre = "enregistre"
    rapproche_banque = "rapproche_banque"
    rejete = "rejete"


class StatutBordereauVersement(str, PyEnum):
    brouillon = "brouillon"
    genere = "genere"
    verse = "verse"


class StatutBordereauReversement(str, PyEnum):
    brouillon = "brouillon"
    valide = "valide"
    reverse = "reverse"


class StatutDossierRecouv(str, PyEnum):
    ouvert = "ouvert"
    en_relance = "en_relance"
    mise_en_demeure = "mise_en_demeure"
    suspendu = "suspendu"
    resilie = "resilie"
    regularise = "regularise"


class TypeRelance(str, PyEnum):
    amiable = "amiable"
    mise_en_demeure = "mise_en_demeure"


# ------------------------------------------------------------
# Utilisateurs
# ------------------------------------------------------------

class Utilisateur(Base):
    __tablename__ = "utilisateur"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(100))
    prenom: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    keycloak_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    mot_de_passe_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[RoleUtilisateur] = mapped_column(
        PgEnum(RoleUtilisateur, name="role_utilisateur"),
        default=RoleUtilisateur.utilisateur,
    )
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# BLOC 1 — Référentiel / paramétrage
# ============================================================

class Compagnie(Base):
    __tablename__ = "compagnie"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)

    produits: Mapped[list["Produit"]] = relationship(back_populates="compagnie")


class Produit(Base):
    __tablename__ = "produit"

    id: Mapped[int] = mapped_column(primary_key=True)
    compagnie_id: Mapped[int] = mapped_column(ForeignKey("compagnie.id"))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    nom: Mapped[str] = mapped_column(String(150))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)

    compagnie: Mapped["Compagnie"] = relationship(back_populates="produits")
    garanties: Mapped[list["Garantie"]] = relationship(back_populates="produit")
    pieces_requises: Mapped[list["PieceJustificativeRequise"]] = relationship(back_populates="produit")


class Garantie(Base):
    __tablename__ = "garantie"
    __table_args__ = (UniqueConstraint("produit_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    produit_id: Mapped[int] = mapped_column(ForeignKey("produit.id"))
    code: Mapped[str] = mapped_column(String(30))
    nom: Mapped[str] = mapped_column(String(150))
    parametres: Mapped[dict] = mapped_column(JSONB, default=dict)

    produit: Mapped["Produit"] = relationship(back_populates="garanties")


class PieceJustificativeRequise(Base):
    __tablename__ = "piece_justificative_requise"

    id: Mapped[int] = mapped_column(primary_key=True)
    produit_id: Mapped[int] = mapped_column(ForeignKey("produit.id"))
    nom: Mapped[str] = mapped_column(String(150))
    obligatoire: Mapped[bool] = mapped_column(Boolean, default=True)

    produit: Mapped["Produit"] = relationship(back_populates="pieces_requises")


class BaremeCommission(Base):
    __tablename__ = "bareme_commission"

    id: Mapped[int] = mapped_column(primary_key=True)
    compagnie_id: Mapped[int] = mapped_column(ForeignKey("compagnie.id"))
    produit_id: Mapped[int | None] = mapped_column(ForeignKey("produit.id"))
    taux_commission: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date)


# ============================================================
# BLOC 2 — Client (option A : une seule table)
# ============================================================

class Client(Base):
    __tablename__ = "client"
    __table_args__ = (
        CheckConstraint(
            "type != 'particulier' OR (cin IS NOT NULL AND nom IS NOT NULL AND prenom IS NOT NULL)",
            name="chk_client_particulier",
        ),
        CheckConstraint(
            "type != 'entreprise' OR (raison_sociale IS NOT NULL AND ice IS NOT NULL)",
            name="chk_client_entreprise",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TypeClient] = mapped_column(PgEnum(TypeClient, name="type_client"))
    telephone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    adresse: Mapped[str | None] = mapped_column(Text)
    ville: Mapped[str | None] = mapped_column(String(100))
    pays: Mapped[str | None] = mapped_column(String(100))
    statut: Mapped[StatutClient] = mapped_column(
        PgEnum(StatutClient, name="statut_client"), default=StatutClient.prospect
    )
    charge_de_compte_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # champs particulier
    cin: Mapped[str | None] = mapped_column(String(20))
    nom: Mapped[str | None] = mapped_column(String(150))
    prenom: Mapped[str | None] = mapped_column(String(150))
    date_naissance: Mapped[date | None] = mapped_column(Date)
    sexe: Mapped[str | None] = mapped_column(String(10))
    profession: Mapped[str | None] = mapped_column(String(150))

    # champs entreprise
    raison_sociale: Mapped[str | None] = mapped_column(String(255))
    ice: Mapped[str | None] = mapped_column(String(30))
    responsable: Mapped[str | None] = mapped_column(String(150))
    banque_principale: Mapped[str | None] = mapped_column(String(150))
    rib: Mapped[str | None] = mapped_column(String(34))

    polices: Mapped[list["Police"]] = relationship(back_populates="client")


class LienFamilial(Base):
    __tablename__ = "lien_familial"
    __table_args__ = (UniqueConstraint("souscripteur_id", "membre_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    souscripteur_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    membre_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    lien_parente: Mapped[str] = mapped_column(String(50))


# ============================================================
# BLOC 3 — Souscription (module SOUS)
# ============================================================

class Police(Base):
    __tablename__ = "police"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_police: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    produit_id: Mapped[int] = mapped_column(ForeignKey("produit.id"))
    statut: Mapped[StatutPolice] = mapped_column(
        PgEnum(StatutPolice, name="statut_police"), default=StatutPolice.en_attente_effet
    )
    date_effet: Mapped[date] = mapped_column(Date)
    date_echeance: Mapped[date] = mapped_column(Date)
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="polices")
    risques: Mapped[list["Risque"]] = relationship(back_populates="police")
    avenants: Mapped[list["Avenant"]] = relationship(back_populates="police")


class Risque(Base):
    __tablename__ = "risque"

    id: Mapped[int] = mapped_column(primary_key=True)
    police_id: Mapped[int] = mapped_column(ForeignKey("police.id"))
    type_risque: Mapped[str] = mapped_column(String(50), default="vehicule")
    attributs: Mapped[dict] = mapped_column(JSONB, default=dict)

    police: Mapped["Police"] = relationship(back_populates="risques")


class Avenant(Base):
    __tablename__ = "avenant"

    id: Mapped[int] = mapped_column(primary_key=True)
    police_id: Mapped[int] = mapped_column(ForeignKey("police.id"))
    type_avenant: Mapped[TypeAvenant] = mapped_column(PgEnum(TypeAvenant, name="type_avenant"))
    motif: Mapped[str | None] = mapped_column(String(255))
    date_effet: Mapped[date] = mapped_column(Date)
    statut: Mapped[StatutAvenant] = mapped_column(
        PgEnum(StatutAvenant, name="statut_avenant"), default=StatutAvenant.brouillon
    )
    valide_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    date_validation: Mapped[datetime | None] = mapped_column(DateTime)

    police: Mapped["Police"] = relationship(back_populates="avenants")


class PoliceGarantie(Base):
    __tablename__ = "police_garantie"
    __table_args__ = (UniqueConstraint("police_id", "risque_id", "garantie_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    police_id: Mapped[int] = mapped_column(ForeignKey("police.id"))
    risque_id: Mapped[int | None] = mapped_column(ForeignKey("risque.id"))
    garantie_id: Mapped[int] = mapped_column(ForeignKey("garantie.id"))
    montant_prime: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class PieceJustificativeFournie(Base):
    """Pièce justificative effectivement fournie pour une police (dossier de souscription).
    Support du contrôle RF-SOUS-04 : émission bloquée tant qu'une pièce obligatoire manque."""
    __tablename__ = "piece_justificative_fournie"
    __table_args__ = (
        UniqueConstraint("police_id", "piece_requise_id", name="uq_piece_fournie_police_requise"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    police_id: Mapped[int] = mapped_column(ForeignKey("police.id"))
    piece_requise_id: Mapped[int] = mapped_column(ForeignKey("piece_justificative_requise.id"))
    reference: Mapped[str | None] = mapped_column(String(255))
    date_fourniture: Mapped[date] = mapped_column(Date, server_default=func.current_date())


# ============================================================
# BLOC 4 — Quittance (module POL)
# ============================================================

class Quittance(Base):
    __tablename__ = "quittance"
    __table_args__ = (UniqueConstraint("avenant_id", name="uq_quittance_avenant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_quittance: Mapped[str] = mapped_column(String(30), unique=True)
    police_id: Mapped[int] = mapped_column(ForeignKey("police.id"))
    avenant_id: Mapped[int] = mapped_column(ForeignKey("avenant.id"))
    periode_debut: Mapped[date] = mapped_column(Date)
    periode_fin: Mapped[date] = mapped_column(Date)
    prime_nette: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    taxes: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    timbres: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    commission: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    accessoires: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    prime_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    statut: Mapped[StatutQuittance] = mapped_column(
        PgEnum(StatutQuittance, name="statut_quittance"), default=StatutQuittance.emise
    )
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# BLOC 5 — Encaissement (module ENC)
# ============================================================

class Encaissement(Base):
    __tablename__ = "encaissement"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    mode_paiement: Mapped[ModePaiement] = mapped_column(PgEnum(ModePaiement, name="mode_paiement"))
    montant: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    date_encaissement: Mapped[date] = mapped_column(Date)
    statut: Mapped[StatutEncaissement] = mapped_column(
        PgEnum(StatutEncaissement, name="statut_encaissement"), default=StatutEncaissement.enregistre
    )

    # chèque
    cheque_banque: Mapped[str | None] = mapped_column(String(150))
    cheque_numero: Mapped[str | None] = mapped_column(String(50))
    cheque_echeance: Mapped[date | None] = mapped_column(Date)

    # virement
    virement_banque: Mapped[str | None] = mapped_column(String(150))
    virement_rib: Mapped[str | None] = mapped_column(String(34))
    virement_reference: Mapped[str | None] = mapped_column(String(100))

    enregistre_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EncaissementQuittance(Base):
    __tablename__ = "encaissement_quittance"
    __table_args__ = (UniqueConstraint("encaissement_id", "quittance_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    encaissement_id: Mapped[int] = mapped_column(ForeignKey("encaissement.id"))
    quittance_id: Mapped[int] = mapped_column(ForeignKey("quittance.id"))
    montant_affecte: Mapped[Decimal] = mapped_column(Numeric(12, 2))


# ============================================================
# BLOC 6 — Versement bancaire (module BANQ)
# ============================================================

class BanqueAgence(Base):
    __tablename__ = "banque_agence"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(150))
    rib: Mapped[str | None] = mapped_column(String(34))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class BordereauVersement(Base):
    __tablename__ = "bordereau_versement"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_bordereau: Mapped[str] = mapped_column(String(30), unique=True)
    banque_agence_id: Mapped[int] = mapped_column(ForeignKey("banque_agence.id"))
    date_bordereau: Mapped[date] = mapped_column(Date)
    statut: Mapped[StatutBordereauVersement] = mapped_column(
        PgEnum(StatutBordereauVersement, name="statut_bordereau_versement"),
        default=StatutBordereauVersement.brouillon,
    )
    date_creation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BordereauVersementLigne(Base):
    __tablename__ = "bordereau_versement_ligne"
    __table_args__ = (UniqueConstraint("bordereau_versement_id", "encaissement_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bordereau_versement_id: Mapped[int] = mapped_column(ForeignKey("bordereau_versement.id"))
    encaissement_id: Mapped[int] = mapped_column(ForeignKey("encaissement.id"))
    montant: Mapped[Decimal] = mapped_column(Numeric(12, 2))


# ============================================================
# BLOC 7 — Reversement compagnie (module REV)
# ============================================================

class BordereauReversement(Base):
    __tablename__ = "bordereau_reversement"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_bordereau: Mapped[str] = mapped_column(String(30), unique=True)
    compagnie_id: Mapped[int] = mapped_column(ForeignKey("compagnie.id"))
    periode_debut: Mapped[date] = mapped_column(Date)
    periode_fin: Mapped[date] = mapped_column(Date)
    montant_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    commission_totale: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    statut: Mapped[StatutBordereauReversement] = mapped_column(
        PgEnum(StatutBordereauReversement, name="statut_bordereau_reversement"),
        default=StatutBordereauReversement.brouillon,
    )
    date_generation: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valide_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    date_validation: Mapped[datetime | None] = mapped_column(DateTime)
    # Règle CDCF : un bordereau validé ne peut plus être modifié ;
    # toute correction = nouveau bordereau rectificatif (géré au niveau applicatif, pas en DB)


class BordereauReversementLigne(Base):
    __tablename__ = "bordereau_reversement_ligne"
    __table_args__ = (UniqueConstraint("bordereau_reversement_id", "quittance_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bordereau_reversement_id: Mapped[int] = mapped_column(ForeignKey("bordereau_reversement.id"))
    quittance_id: Mapped[int] = mapped_column(ForeignKey("quittance.id"))
    prime_nette_reversee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission_calculee: Mapped[Decimal] = mapped_column(Numeric(12, 2))


# ============================================================
# BLOC 8 — Recouvrement (module RECOUV)
# ============================================================

class DossierRecouvrement(Base):
    __tablename__ = "dossier_recouvrement"

    id: Mapped[int] = mapped_column(primary_key=True)
    quittance_id: Mapped[int] = mapped_column(ForeignKey("quittance.id"))
    statut: Mapped[StatutDossierRecouv] = mapped_column(
        PgEnum(StatutDossierRecouv, name="statut_dossier_recouv"), default=StatutDossierRecouv.ouvert
    )
    date_ouverture: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    date_cloture: Mapped[date | None] = mapped_column(Date)

    relances: Mapped[list["Relance"]] = relationship(back_populates="dossier")


class Relance(Base):
    __tablename__ = "relance"

    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_recouvrement_id: Mapped[int] = mapped_column(ForeignKey("dossier_recouvrement.id"))
    type_relance: Mapped[TypeRelance] = mapped_column(PgEnum(TypeRelance, name="type_relance"))
    date_relance: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    contenu: Mapped[str | None] = mapped_column(Text)
    resultat: Mapped[str | None] = mapped_column(String(255))

    dossier: Mapped["DossierRecouvrement"] = relationship(back_populates="relances")


# ============================================================
# Traçabilité transversale (exigence CDCF §6)
# ============================================================

class JournalAudit(Base):
    __tablename__ = "journal_audit"
    __table_args__ = (Index("idx_journal_audit_cible", "table_cible", "enregistrement_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_cible: Mapped[str] = mapped_column(String(100))
    enregistrement_id: Mapped[int]
    action: Mapped[str] = mapped_column(String(20))
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    date_action: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ancienne_valeur: Mapped[dict | None] = mapped_column(JSONB)
    nouvelle_valeur: Mapped[dict | None] = mapped_column(JSONB)
