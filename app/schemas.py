"""
Schémas Pydantic — validation des données entrantes/sortantes de l'API.
Un schéma "Create" (ce qu'on envoie pour créer) et un schéma "Read" (ce que l'API renvoie,
incluant l'id généré) par entité.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    TypeClient, StatutClient, RoleUtilisateur, StatutPolice, TypeAvenant,
    StatutAvenant, StatutQuittance, ModePaiement, StatutEncaissement,
    StatutBordereauVersement, StatutBordereauReversement,
    StatutDossierRecouv, TypeRelance, TypeDocument,
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


class VehiculeAttributs(BaseModel):
    """Attributs d'un risque de type « vehicule » (contenu du JSONB `Risque.attributs`).
    `extra="allow"` conserve d'éventuels attributs supplémentaires paramétrés sans les rejeter —
    le modèle reste générique, tout en imposant les champs indispensables à un véhicule assuré."""
    model_config = ConfigDict(extra="allow")

    # --- Champs obligatoires ---
    immatriculation: str
    marque: str
    modele: str
    date_mise_en_circulation: str  # format "MM/AAAA"
    valeur_neuf: Decimal

    # --- Champs optionnels ---
    type_version: str | None = None
    numero_chassis: str | None = None
    numero_moteur: str | None = None
    genre_carrosserie: str | None = None
    puissance_fiscale: int | None = None
    usage: str | None = None
    nombre_places: int | None = None
    conducteur_habituel: str | None = None
    valeur_venale: Decimal | None = None

    @field_validator("date_mise_en_circulation")
    @classmethod
    def _valider_mois_annee(cls, valeur):
        if valeur is not None and not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", valeur):
            raise ValueError("date_mise_en_circulation doit être au format MM/AAAA (ex. « 03/2021 »).")
        return valeur


class VehiculeAttributsPartiel(VehiculeAttributs):
    """Version partielle pour le PATCH : aucun champ n'est obligatoire — on ne valide QUE le type
    des champs réellement fournis (les 5 champs obligatoires de VehiculeAttributs sont redéclarés
    optionnels ici), pour pouvoir modifier un seul attribut sans devoir tout renvoyer."""
    immatriculation: str | None = None
    marque: str | None = None
    modele: str | None = None
    date_mise_en_circulation: str | None = None
    valeur_neuf: Decimal | None = None


class RisqueCreate(BaseModel):
    police_id: int
    type_risque: str = "vehicule"
    attributs: dict = {}

    @model_validator(mode="after")
    def _valider_attributs_vehicule(self):
        """Un risque « vehicule » doit décrire un véhicule complet : `attributs` est validé contre
        VehiculeAttributs (champs obligatoires + types), puis réassigné sous sa forme normalisée et
        sérialisable JSON (stockage JSONB)."""
        if self.type_risque == "vehicule":
            valide = VehiculeAttributs(**self.attributs)
            self.attributs = valide.model_dump(mode="json", exclude_none=True)
        return self


class RisqueUpdate(BaseModel):
    """Mise à jour partielle d'un risque (PATCH) : tous les champs sont facultatifs. Si `attributs`
    est fourni, on ne valide QUE le type des champs présents (pas leur présence complète)."""
    police_id: int | None = None
    type_risque: str | None = None
    attributs: dict | None = None

    @model_validator(mode="after")
    def _valider_types_attributs(self):
        if self.attributs is not None:
            valide = VehiculeAttributsPartiel(**self.attributs)
            self.attributs = valide.model_dump(mode="json", exclude_unset=True)
        return self


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
    capital_assure: Decimal | None = Field(default=None, ge=0)
    # montant_prime facultatif : s'il est omis, il est calculé côté serveur à partir de la règle
    # de tarification du produit (Garantie.parametres) et du capital_assure (RF-SOUS-02).
    montant_prime: Decimal | None = Field(default=None, ge=0)


class PoliceGarantieRead(ORMBase):
    id: int
    police_id: int
    risque_id: int | None
    garantie_id: int
    capital_assure: Decimal | None
    montant_prime: Decimal | None


class PieceJustificativeFournieCreate(BaseModel):
    police_id: int
    piece_requise_id: int
    reference: str | None = None


class PieceJustificativeFournieRead(ORMBase):
    id: int
    police_id: int
    piece_requise_id: int
    reference: str | None
    date_fourniture: date


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


class RejetChequeCreate(BaseModel):
    # encaissement_id vient de l'URL (/encaissements/{id}/rejeter), pas du corps
    motif: str
    date_rejet: date | None = None  # défaut : date du jour


class LigneRecu(ORMBase):
    quittance_id: int
    numero_quittance: str
    montant_affecte: Decimal


class RecuEncaissement(BaseModel):
    """Reçu d'encaissement (RF-ENC-04) — édition à la demande, dérivée de l'encaissement
    (pas de table dédiée, à l'image des rapports en JSON tant que le PDF n'est pas branché)."""
    numero_recu: str
    date_edition: date
    encaissement: EncaissementRead
    client: ClientRead
    montant_affecte: Decimal
    montant_non_affecte: Decimal
    quittances_reglees: list[LigneRecu]
    enregistre_par: UtilisateurRead | None


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
    # numero_bordereau n'est PAS fourni par le client : généré automatiquement par le serveur.
    # statut non exposé : un bordereau naît toujours en brouillon côté serveur, la validation
    # (super admin) est le seul chemin vers `verse` (anti-contournement).
    banque_agence_id: int
    date_bordereau: date


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
    # numero_bordereau n'est PAS fourni par le client : généré automatiquement par le serveur.
    # statut et valide_par ne sont PAS exposés : un bordereau naît toujours en brouillon côté
    # serveur, et la validation (super admin) est le seul chemin vers `valide` (anti-contournement).
    compagnie_id: int
    periode_debut: date
    periode_fin: date
    montant_total: Decimal = Decimal("0")
    commission_totale: Decimal = Decimal("0")


class ReversementCreate(BaseModel):
    # id du bordereau dans l'URL. Reversement effectif à la compagnie (statut -> `reverse`).
    reference_virement: str = Field(max_length=100)  # borné à la taille de la colonne (évite un 500)
    date_reversement: date

    @field_validator("reference_virement")
    @classmethod
    def _reference_non_vide(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if not valeur:
            raise ValueError("La référence de virement est obligatoire (texte non vide).")
        return valeur


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
    rectifie_bordereau_id: int | None  # bordereau original corrigé (règle 7), NULL si initial
    reference_virement: str | None
    date_reversement: date | None
    reverse_par: int | None


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


# ----- Balance âgée des impayés (RF-RECOUV-01) -----

class TrancheBalance(BaseModel):
    nombre: int
    montant: Decimal


class LigneBalanceAgee(BaseModel):
    quittance_id: int
    numero_quittance: str
    police_id: int
    client_id: int | None
    client: str
    periode_debut: date
    reste_du: Decimal
    jours_retard: int
    tranche: str


class BalanceAgee(BaseModel):
    """Créances client impayées ventilées par ancienneté (0-30, 30-60, 60-90, +90 jours)."""
    date_reference: date
    tranche_0_30: TrancheBalance
    tranche_30_60: TrancheBalance
    tranche_60_90: TrancheBalance
    tranche_90_plus: TrancheBalance
    total_impaye: Decimal
    nombre_quittances: int
    lignes: list[LigneBalanceAgee]


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


# ============================================================
# Archivage des éditions PDF (RF-POL-04)
# ============================================================

class DocumentArchiveRead(ORMBase):
    # chemin_fichier volontairement ABSENT de la sortie : le chemin disque du serveur ne doit
    # pas fuiter côté client. Le re-téléchargement passe par /documents/archives/{id}/telecharger.
    id: int
    type_document: TypeDocument
    entite_id: int
    numero: str | None
    nom_fichier: str
    genere_par: int | None
    date_generation: datetime


# ============================================================
# Recherche multicritère
# ============================================================

class RechercheResultats(BaseModel):
    clients: list[ClientRead]
    polices: list[PoliceRead]
    quittances: list[QuittanceRead]
    risques: list[RisqueRead]


# ============================================================
# Vue 360 client (RF-CRM-06, RF-ENC-05)
# ============================================================

class SoldeClient(BaseModel):
    total_du: Decimal
    total_encaisse: Decimal
    reste_du: Decimal


class Vue360Client(BaseModel):
    client: ClientRead
    polices: list[PoliceRead]
    quittances: list[QuittanceRead]
    solde: SoldeClient
    encaissements: list[EncaissementRead]
