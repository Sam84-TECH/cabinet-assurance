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
    StatutDossierRecouv, TypeRelance, StatutVersementEcheancier, TypeDocument,
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

    @model_validator(mode="after")
    def _valider_identite(self):
        """Identité obligatoire selon le type (RF-CRM, écart §25) : un particulier doit avoir
        CIN + nom + prénom, une entreprise raison sociale + ICE. Donne un 422 explicite plutôt
        que de laisser la contrainte CHECK de la base remonter un 400 technique."""
        def _absents(champs):
            return [nom for nom, valeur in champs if not (valeur and valeur.strip())]

        if self.type == TypeClient.particulier:
            manquants = _absents([("cin", self.cin), ("nom", self.nom), ("prenom", self.prenom)])
            if manquants:
                raise ValueError("Un particulier doit renseigner : " + ", ".join(manquants) + ".")
        elif self.type == TypeClient.entreprise:
            manquants = _absents([("raison_sociale", self.raison_sociale), ("ice", self.ice)])
            if manquants:
                raise ValueError("Une entreprise doit renseigner : " + ", ".join(manquants) + ".")
        return self


class ClientUpdate(BaseModel):
    """Mise à jour partielle d'un client (PATCH) : tous les champs sont facultatifs, l'identité
    déjà en base n'a pas à être renvoyée. La cohérence identité/type reste garantie en base par
    les contraintes CHECK (backstop si un PATCH rend la ligne incohérente)."""
    type: TypeClient | None = None
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None
    ville: str | None = None
    pays: str | None = None
    statut: StatutClient | None = None
    charge_de_compte_id: int | None = None
    cin: str | None = None
    nom: str | None = None
    prenom: str | None = None
    date_naissance: date | None = None
    sexe: str | None = None
    profession: str | None = None
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


# ----- Import de clients en masse depuis un fichier Excel (RF-CRM) -----

class LigneImportErreur(BaseModel):
    ligne: int  # numéro de ligne dans le fichier (1 = en-tête), pour que l'agent la retrouve
    valeur: str | None = None  # libellé de la ligne fautive (nom/raison sociale), si lisible
    message: str


class ResultatImportClients(BaseModel):
    """Rapport de POST /clients/import-excel : combien de lignes lues, combien créées, et le
    détail des lignes rejetées (doublon CIN/ICE, champ obligatoire manquant, type invalide…)."""
    lignes_totales: int  # lignes de données (hors en-tête)
    crees: int
    noms_crees: list[str]
    erreurs: list[LigneImportErreur]


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
    # numero_police et statut ne sont PAS fournis par le client : le numéro est généré par le
    # serveur et la police naît toujours en `en_attente_effet` (la synchro fait évoluer le statut
    # selon la date d'effet et les avenants validés). (Anti-contournement.)
    client_id: int
    produit_id: int
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
    # statut et valide_par ne sont PAS exposés : un avenant naît toujours en brouillon côté
    # serveur, et la validation (PATCH .../valider) est le seul chemin vers `valide` — c'est elle
    # qui contrôle les pièces (RF-SOUS-04) et génère la quittance. (Anti-contournement.)
    police_id: int
    type_avenant: TypeAvenant
    motif: str | None = None
    date_effet: date

    @model_validator(mode="after")
    def _motif_requis_pour_modification(self):
        # Un avenant de modification n'a pas (encore) de champs structurés disant « quoi
        # modifier » : le motif en texte libre est la seule trace du changement, on l'exige
        # donc à la création (règle 17). Volet financier prorata/avoir différé (Q2 encadrant).
        if self.type_avenant == TypeAvenant.modification:
            if self.motif is None or not self.motif.strip():
                raise ValueError(
                    "Un avenant de modification doit préciser un motif (ce qui est modifié).")
            self.motif = self.motif.strip()
        return self


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
    # Montant réglé effectif (hors chèques rejetés) et reste dû réel (écart §27). Calculés à la
    # lecture (get/list quittances, réponse de validation d'avenant) ; None si non enrichi.
    montant_regle: Decimal | None = None
    reste_du: Decimal | None = None
    # Annulation (écart §11) : renseignés uniquement pour une quittance `annulee`.
    motif_annulation: str | None = None
    date_annulation: date | None = None
    annule_par: int | None = None


class AnnulationQuittanceCreate(BaseModel):
    # quittance_id vient de l'URL (/quittances/{id}/annuler), pas du corps.
    motif: str = Field(max_length=255)  # motif d'annulation obligatoire (écart §11)

    @field_validator("motif")
    @classmethod
    def _motif_non_vide(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if not valeur:
            raise ValueError("Le motif d'annulation est obligatoire (texte non vide).")
        return valeur


class AvenantValideRead(AvenantRead):
    """Réponse de la validation d'un avenant (écart §26) : les champs de l'avenant validé + la
    quittance générée automatiquement (RF-SOUS-07), pour éviter au frontend un GET séparé.
    `quittance` vaut None si le type d'avenant n'en génère pas (modification, suspension…)."""
    quittance: QuittanceRead | None = None


# ============================================================
# BLOC 5 — Encaissement
# ============================================================

class EncaissementCreate(BaseModel):
    # enregistre_par n'est PAS fourni par le client : déduit automatiquement
    # de l'utilisateur connecté (jeton d'authentification)
    # statut non exposé : un encaissement naît toujours `enregistre` ; il passe à
    # `rapproche_banque` via la validation d'un bordereau de versement (super admin) ou à
    # `rejete` via le rejet de chèque — jamais fixé par le client. (Anti-contournement.)
    client_id: int
    mode_paiement: ModePaiement
    montant: Decimal
    date_encaissement: date
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
    # Total du bordereau = somme des lignes (encaissements déposés). L'entête ne le stocke pas ;
    # il est calculé à la lecture (liste et détail) pour l'écran « Liste des bordereaux ». None si
    # non calculé.
    montant_total: Decimal | None = None


class BordereauVersementLigneCreate(BaseModel):
    bordereau_versement_id: int
    encaissement_id: int
    montant: Decimal


class BordereauVersementLigneRead(ORMBase):
    id: int
    bordereau_versement_id: int
    encaissement_id: int
    montant: Decimal


class BordereauVersementLigneDetailRead(BordereauVersementLigneRead):
    """Ligne enrichie pour le détail : rattache le client et le mode de paiement de
    l'encaissement déposé, pour un écran lisible sans jointure côté frontend."""
    client_id: int | None = None
    mode_paiement: str | None = None
    reference: str | None = None  # n° / banque du chèque, sinon None


class BordereauVersementDetailRead(BordereauVersementRead):
    """Détail d'un bordereau de versement : l'entête (avec montant_total) + ses lignes
    enrichies, renvoyé par GET /banq/bordereaux/{id}."""
    lignes: list[BordereauVersementLigneDetailRead]


# ============================================================
# BLOC 7 — Reversement compagnie
# ============================================================

class BordereauReversementCreate(BaseModel):
    # numero_bordereau n'est PAS fourni par le client : généré automatiquement par le serveur.
    # statut, valide_par, montant_total et commission_totale ne sont PAS exposés : un bordereau naît
    # en brouillon avec des totaux à 0, recalculés depuis les lignes à la validation (super admin,
    # seul chemin vers `valide`). (Anti-contournement.)
    compagnie_id: int
    periode_debut: date
    periode_fin: date


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


class BordereauReversementLigneDetailRead(BordereauReversementLigneRead):
    """Ligne enrichie (écart §28) : ajoute le numéro de quittance et le numéro de police,
    pour que le détail du bordereau soit lisible sans jointure côté frontend."""
    numero_quittance: str | None = None
    numero_police: str | None = None


class BordereauReversementDetailRead(BordereauReversementRead):
    """Détail d'un bordereau de reversement (écart §28) : le bordereau + ses lignes enrichies,
    renvoyé par GET /rev/bordereaux/{id}."""
    lignes: list[BordereauReversementLigneDetailRead]


# ============================================================
# BLOC 8 — Recouvrement
# ============================================================

class DossierRecouvrementCreate(BaseModel):
    # statut non exposé : un dossier de recouvrement naît toujours `ouvert` ; ses transitions
    # passent par PATCH .../statut. (Anti-contournement.)
    quittance_id: int
    date_ouverture: date | None = None
    date_cloture: date | None = None


class DossierRecouvrementRead(ORMBase):
    id: int
    quittance_id: int
    statut: StatutDossierRecouv
    date_ouverture: date
    date_derniere_etape: date  # entrée dans l'étape courante (base du délai de progression)
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


# ----- Historique tracé du dossier (RF-RECOUV-05) -----

class EvenementRecouvrementRead(ORMBase):
    id: int
    dossier_recouvrement_id: int
    type_evenement: str
    ancien_statut: str | None
    nouveau_statut: str | None
    description: str | None
    auteur_id: int | None
    date_evenement: datetime


# ----- Échéancier de paiement négocié (RF-RECOUV-04) -----

class EcheancierRecouvrementCreate(BaseModel):
    # dossier_recouvrement_id vient de l'URL. Les versements sont générés côté serveur
    # (montants égaux, dernier arrondi), espacés de `intervalle_jours`.
    montant_total: Decimal = Field(gt=0)
    nombre_versements: int = Field(ge=1, le=36)
    date_premier_versement: date
    intervalle_jours: int = Field(default=30, ge=1, le=365)


class VersementEcheancierRead(ORMBase):
    id: int
    echeancier_id: int
    numero_ordre: int
    date_prevue: date
    montant: Decimal
    statut: StatutVersementEcheancier


class VersementEcheancierUpdate(BaseModel):
    # Seul le statut se met à jour (prévu -> réglé / manqué).
    statut: StatutVersementEcheancier


class EcheancierRecouvrementRead(ORMBase):
    id: int
    dossier_recouvrement_id: int
    montant_total: Decimal
    nombre_versements: int
    date_creation: datetime
    versements: list[VersementEcheancierRead]


class DossierRecouvrementDetailRead(DossierRecouvrementRead):
    """Détail d'un dossier de recouvrement : le dossier + son historique tracé (RF-RECOUV-05),
    ses relances et son éventuel échéancier négocié (RF-RECOUV-04)."""
    relances: list[RelanceRead]
    evenements: list[EvenementRecouvrementRead]
    echeancier: EcheancierRecouvrementRead | None = None


# ----- Balance âgée des impayés (RF-RECOUV-01) -----

class TrancheBalance(BaseModel):
    nombre: int
    montant: Decimal


class LigneBalanceAgee(BaseModel):
    quittance_id: int
    numero_quittance: str
    police_id: int
    numero_police: str | None  # libellé affiché à l'écran (écart §14)
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


# ----- Résultat de la bascule en recouvrement (RF-ECH-04) -----

class LigneBasculeRecouv(BaseModel):
    quittance_id: int
    numero_quittance: str
    numero_police: str | None
    client: str
    jours_retard: int
    reste_du: Decimal


class ResultatBasculeRecouv(BaseModel):
    """Résumé de POST /recouv/basculer-echus : rend « 0 dossier ouvert » lisible (aucune échéance
    dépassée vs toutes déjà suivies) et détaille les dossiers réellement ouverts."""
    delai_jours: int
    quittances_verifiees: int
    quittances_echues: int
    dossiers_ouverts: int
    deja_en_cours: int
    dossiers: list[LigneBasculeRecouv]


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


# ============================================================
# Tableau de bord (écart §22 : contrat OpenAPI typé)
# ============================================================

class DashboardRead(BaseModel):
    contrats_actifs: int
    contrats_expirant_sous_30_jours: int
    contrats_renouveles_aujourdhui: int
    paiements_en_attente: int
    cheques_non_encaisses: int
    dossiers_recouvrement_ouverts: int
    nombre_clients: int
