"""
Schémas Pydantic — validation des données entrantes/sortantes de l'API.
Un schéma "Create" (ce qu'on envoie pour créer) et un schéma "Read" (ce que l'API renvoie,
incluant l'id généré) par entité.
"""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict

from app.models import (
    TypeClient, StatutClient, RoleUtilisateur, StatutPolice, TypeAvenant,
    StatutAvenant, StatutQuittance, ModePaiement, StatutEncaissement,
    StatutBordereauVersement, StatutBordereauReversement,
    StatutDossierRecouv, TypeRelance,
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------
# Utilisateur
# ------------------------------------------------------------

class UtilisateurCreate(BaseModel):
    nom: str
    prenom: str
    email: str
    mot_de_passe: str
    role: RoleUtilisateur = RoleUtilisateur.utilisateur
    actif: bool = True


class UtilisateurRead(ORMBase):
    id: int
    nom: str
    prenom: str
    email: str
    role: RoleUtilisateur
    actif: bool
    date_creation: datetime


# ============================================================
# BLOC 1 — Référentiel
# ============================================================

class CompagnieCreate(BaseModel):
    nom: str
    code: str | None = None
    actif: bool = True


class CompagnieRead(ORMBase):
    id: int
    nom: str
    code: str | None
    actif: bool


class ProduitCreate(BaseModel):
    compagnie_id: int
    code: str
    nom: str
    actif: bool = True


class ProduitRead(ORMBase):
    id: int
    compagnie_id: int
    code: str
    nom: str
    actif: bool


class GarantieCreate(BaseModel):
    produit_id: int
    code: str
    nom: str
    parametres: dict = {}


class GarantieRead(ORMBase):
    id: int
    produit_id: int
    code: str
    nom: str
    parametres: dict


class PieceJustificativeRequiseCreate(BaseModel):
    produit_id: int
    nom: str
    obligatoire: bool = True


class PieceJustificativeRequiseRead(ORMBase):
    id: int
    produit_id: int
    nom: str
    obligatoire: bool


class BaremeCommissionCreate(BaseModel):
    compagnie_id: int
    produit_id: int | None = None
    taux_commission: Decimal
    date_debut: date
    date_fin: date | None = None


class BaremeCommissionRead(ORMBase):
    id: int
    compagnie_id: int
    produit_id: int | None
    taux_commission: Decimal
    date_debut: date
    date_fin: date | None


# ============================================================
# BLOC 2 — Client
# ============================================================

class ClientCreate(BaseModel):
    type: TypeClient
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None
    ville: str | None = None
    pays: str | None = None
    statut: StatutClient = StatutClient.prospect
    charge_de_compte_id: int | None = None

    # particulier
    cin: str | None = None
    nom: str | None = None
    prenom: str | None = None
    date_naissance: date | None = None
    sexe: str | None = None
    profession: str | None = None

    # entreprise
    raison_sociale: str | None = None
    ice: str | None = None
    responsable: str | None = None
    banque_principale: str | None = None
    rib: str | None = None


class ClientRead(ORMBase):
    id: int
    type: TypeClient
    telephone: str | None
    email: str | None
    adresse: str | None
    ville: str | None
    pays: str | None
    statut: StatutClient
    charge_de_compte_id: int | None
    date_creation: datetime
    cin: str | None
    nom: str | None
    prenom: str | None
    date_naissance: date | None
    sexe: str | None
    profession: str | None
    raison_sociale: str | None
    ice: str | None
    responsable: str | None
    banque_principale: str | None
    rib: str | None


class LienFamilialCreate(BaseModel):
    souscripteur_id: int
    membre_id: int
    lien_parente: str


class LienFamilialRead(ORMBase):
    id: int
    souscripteur_id: int
    membre_id: int
    lien_parente: str


# ============================================================
# BLOC 3 — Souscription
# ============================================================

class PoliceCreate(BaseModel):
    # numero_police n'est PAS fourni par le client : généré automatiquement par le serveur
    client_id: int
    produit_id: int
    statut: StatutPolice = StatutPolice.en_attente_effet
    date_effet: date
    date_echeance: date


class PoliceRead(ORMBase):
    id: int
    numero_police: str
    client_id: int
    produit_id: int
    statut: StatutPolice
    date_effet: date
    date_echeance: date
    date_creation: datetime


class RisqueCreate(BaseModel):
    police_id: int
    type_risque: str = "vehicule"
    attributs: dict = {}


class RisqueRead(ORMBase):
    id: int
    police_id: int
    type_risque: str
    attributs: dict


class AvenantCreate(BaseModel):
    police_id: int
    type_avenant: TypeAvenant
    motif: str | None = None
    date_effet: date
    statut: StatutAvenant = StatutAvenant.brouillon
    valide_par: int | None = None


class AvenantRead(ORMBase):
    id: int
    police_id: int
    type_avenant: TypeAvenant
    motif: str | None
    date_effet: date
    statut: StatutAvenant
    valide_par: int | None
    date_creation: datetime
    date_validation: datetime | None


class PoliceGarantieCreate(BaseModel):
    police_id: int
    risque_id: int | None = None
    garantie_id: int
    montant_prime: Decimal | None = None


class PoliceGarantieRead(ORMBase):
    id: int
    police_id: int
    risque_id: int | None
    garantie_id: int
    montant_prime: Decimal | None


# ============================================================
# BLOC 4 — Quittance
# ============================================================

class QuittanceRead(ORMBase):
    id: int
    numero_quittance: str
    police_id: int
    avenant_id: int
    periode_debut: date
    periode_fin: date
    prime_nette: Decimal
    taxes: Decimal
    timbres: Decimal
    commission: Decimal
    accessoires: Decimal
    prime_ttc: Decimal
    statut: StatutQuittance
    date_creation: datetime


# ============================================================
# BLOC 5 — Encaissement
# ============================================================

class EncaissementCreate(BaseModel):
    # enregistre_par n'est PAS fourni par le client : déduit automatiquement
    # de l'utilisateur connecté (jeton d'authentification)
    client_id: int
    mode_paiement: ModePaiement
    montant: Decimal
    date_encaissement: date
    statut: StatutEncaissement = StatutEncaissement.enregistre
    cheque_banque: str | None = None
    cheque_numero: str | None = None
    cheque_echeance: date | None = None
    virement_banque: str | None = None
    virement_rib: str | None = None
    virement_reference: str | None = None


class EncaissementRead(ORMBase):
    id: int
    client_id: int
    mode_paiement: ModePaiement
    montant: Decimal
    date_encaissement: date
    statut: StatutEncaissement
    cheque_banque: str | None
    cheque_numero: str | None
    cheque_echeance: date | None
    virement_banque: str | None
    virement_rib: str | None
    virement_reference: str | None
    enregistre_par: int | None
    date_creation: datetime


class EncaissementQuittanceCreate(BaseModel):
    encaissement_id: int
    quittance_id: int
    montant_affecte: Decimal


class EncaissementQuittanceRead(ORMBase):
    id: int
    encaissement_id: int
    quittance_id: int
    montant_affecte: Decimal


class AffectationCreate(BaseModel):
    # encaissement_id et quittance_id viennent de l'URL (/encaissements/{id}/affecter/{qid}), pas du corps
    montant_affecte: Decimal


# ============================================================
# BLOC 6 — Versement bancaire
# ============================================================

class BanqueAgenceCreate(BaseModel):
    nom: str
    rib: str | None = None
    actif: bool = True


class BanqueAgenceRead(ORMBase):
    id: int
    nom: str
    rib: str | None
    actif: bool


class BordereauVersementCreate(BaseModel):
    # numero_bordereau n'est PAS fourni par le client : généré automatiquement par le serveur
    banque_agence_id: int
    date_bordereau: date
    statut: StatutBordereauVersement = StatutBordereauVersement.brouillon


class BordereauVersementRead(ORMBase):
    id: int
    numero_bordereau: str
    banque_agence_id: int
    date_bordereau: date
    statut: StatutBordereauVersement
    date_creation: datetime


class BordereauVersementLigneCreate(BaseModel):
    bordereau_versement_id: int
    encaissement_id: int
    montant: Decimal


class BordereauVersementLigneRead(ORMBase):
    id: int
    bordereau_versement_id: int
    encaissement_id: int
    montant: Decimal


# ============================================================
# BLOC 7 — Reversement compagnie
# ============================================================

class BordereauReversementCreate(BaseModel):
    # numero_bordereau n'est PAS fourni par le client : généré automatiquement par le serveur
    compagnie_id: int
    periode_debut: date
    periode_fin: date
    montant_total: Decimal = Decimal("0")
    commission_totale: Decimal = Decimal("0")
    statut: StatutBordereauReversement = StatutBordereauReversement.brouillon
    valide_par: int | None = None


class BordereauReversementRead(ORMBase):
    id: int
    numero_bordereau: str
    compagnie_id: int
    periode_debut: date
    periode_fin: date
    montant_total: Decimal
    commission_totale: Decimal
    statut: StatutBordereauReversement
    date_generation: datetime
    valide_par: int | None
    date_validation: datetime | None


class BordereauReversementLigneCreate(BaseModel):
    bordereau_reversement_id: int
    quittance_id: int
    prime_nette_reversee: Decimal
    commission_calculee: Decimal


class BordereauReversementLigneRead(ORMBase):
    id: int
    bordereau_reversement_id: int
    quittance_id: int
    prime_nette_reversee: Decimal
    commission_calculee: Decimal


# ============================================================
# BLOC 8 — Recouvrement
# ============================================================

class DossierRecouvrementCreate(BaseModel):
    quittance_id: int
    statut: StatutDossierRecouv = StatutDossierRecouv.ouvert
    date_ouverture: date | None = None
    date_cloture: date | None = None


class DossierRecouvrementRead(ORMBase):
    id: int
    quittance_id: int
    statut: StatutDossierRecouv
    date_ouverture: date
    date_cloture: date | None


class RelanceCreate(BaseModel):
    # dossier_recouvrement_id vient de l'URL (/recouv/dossiers/{dossier_id}/relances), pas du corps
    type_relance: TypeRelance
    date_relance: date | None = None
    contenu: str | None = None
    resultat: str | None = None


class RelanceRead(ORMBase):
    id: int
    dossier_recouvrement_id: int
    type_relance: TypeRelance
    date_relance: date
    contenu: str | None
    resultat: str | None


# ============================================================
# Journal d'audit (consultation seule — jamais créé via l'API)
# ============================================================

class JournalAuditRead(ORMBase):
    id: int
    table_cible: str
    enregistrement_id: int
    action: str
    auteur_id: int | None
    date_action: datetime
    ancienne_valeur: dict | None
    nouvelle_valeur: dict | None
