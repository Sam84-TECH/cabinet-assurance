"""
Recouvrement — balance âgée des impayés (RF-RECOUV-01) et bascule automatique en
recouvrement des quittances échues (RF-ECH-04).

RF-RECOUV-01 : les créances client impayées sont ventilées par ancienneté
(0-30, 30-60, 60-90 et +90 jours), calculées à la demande depuis les quittances —
pas de table dédiée. Le reste dû exclut les encaissements rejetés (cf. app/reglement.py).

RF-ECH-04 : au-delà du délai réglementaire, une quittance impayée bascule
automatiquement en recouvrement (ouverture d'un dossier). Déclenché par le
planificateur (app/scheduler.py) et disponible à la demande via un endpoint.

L'ancienneté se compte depuis `periode_debut` (date d'exigibilité de la prime),
bornée à 0 pour une prime pas encore échue.
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from . import models
from .reglement import montant_regle

# Délai (jours) au-delà duquel une quittance impayée bascule en recouvrement (RF-ECH-04).
# Surchargé par l'environnement pour ne pas figer une règle qui varie selon l'agence.
DELAI_RECOUVREMENT_JOURS = int(os.environ.get("DELAI_RECOUVREMENT_JOURS", "30"))

# Délai (jours) passé lequel un dossier progresse automatiquement vers l'étape de relance
# suivante (RF-RECOUV-02). Paramétrable comme DELAI_RECOUVREMENT_JOURS.
DELAI_ENTRE_ETAPES_JOURS = int(os.environ.get("DELAI_ENTRE_ETAPES_JOURS", "15"))

# Un dossier dans l'un de ces statuts est clos : il n'empêche pas d'en rouvrir un nouveau.
STATUTS_DOSSIER_CLOS = (
    models.StatutDossierRecouv.regularise,
    models.StatutDossierRecouv.resilie,
)

# --- Escalade des étapes de relance (RF-RECOUV-02/03) ---
# ouvert -> en_relance (relance amiable) -> mise_en_demeure -> suspendu (suspension auto du contrat).
# Les statuts absents des clés sont terminaux (suspendu, resilie, regularise) : plus de progression.
PROCHAINE_ETAPE = {
    models.StatutDossierRecouv.ouvert: models.StatutDossierRecouv.en_relance,
    models.StatutDossierRecouv.en_relance: models.StatutDossierRecouv.mise_en_demeure,
    models.StatutDossierRecouv.mise_en_demeure: models.StatutDossierRecouv.suspendu,
}
# Étapes qui génèrent une relance datée (RF-RECOUV-03) lors de l'entrée dans l'étape.
RELANCE_POUR_ETAPE = {
    models.StatutDossierRecouv.en_relance: models.TypeRelance.amiable,
    models.StatutDossierRecouv.mise_en_demeure: models.TypeRelance.mise_en_demeure,
}


def _nom_client(client: models.Client | None) -> str:
    """Libellé d'affichage du client : raison sociale (entreprise) ou nom + prénom (particulier)."""
    if client is None:
        return ""
    if client.raison_sociale:
        return client.raison_sociale
    return " ".join(part for part in (client.nom, client.prenom) if part)


def _tranche(jours: int) -> str:
    """Range une ancienneté en jours dans l'une des quatre tranches de la balance âgée."""
    if jours <= 30:
        return "0_30"
    if jours <= 60:
        return "30_60"
    if jours <= 90:
        return "60_90"
    return "90_plus"


def _quittances_impayees(db: Session):
    """(quittance, reste_du, jours_retard) pour chaque quittance non annulée dont le reste dû
    est strictement positif. Le reste dû exclut les chèques rejetés ; on ne se fie pas au seul
    statut stocké (self-correcting : une quittance marquée `reglee` mais dont le chèque a été
    rejeté réapparaît si son reste dû redevient positif)."""
    aujourdhui = date.today()
    resultats = []
    quittances = db.query(models.Quittance).filter(
        models.Quittance.statut != models.StatutQuittance.annulee
    ).all()
    for quittance in quittances:
        reste = quittance.prime_ttc - montant_regle(db, quittance.id)
        if reste <= 0:
            continue
        jours = max((aujourdhui - quittance.periode_debut).days, 0)
        resultats.append((quittance, reste, jours))
    return resultats


def calculer_balance_agee(db: Session) -> dict:
    """Balance âgée des impayés (RF-RECOUV-01) : totaux par tranche + détail ligne à ligne,
    trié du plus ancien au plus récent."""
    tranches = {
        cle: {"nombre": 0, "montant": Decimal("0")}
        for cle in ("0_30", "30_60", "60_90", "90_plus")
    }
    lignes = []
    total = Decimal("0")

    for quittance, reste, jours in _quittances_impayees(db):
        cle = _tranche(jours)
        tranches[cle]["nombre"] += 1
        tranches[cle]["montant"] += reste
        total += reste

        police = db.get(models.Police, quittance.police_id)
        client = db.get(models.Client, police.client_id) if police else None
        lignes.append({
            "quittance_id": quittance.id,
            "numero_quittance": quittance.numero_quittance,
            "police_id": quittance.police_id,
            "numero_police": police.numero_police if police else None,  # écart §14
            "client_id": police.client_id if police else None,
            "client": _nom_client(client),
            "periode_debut": quittance.periode_debut,
            "reste_du": reste,
            "jours_retard": jours,
            "tranche": cle,
        })

    lignes.sort(key=lambda ligne: ligne["jours_retard"], reverse=True)
    return {
        "date_reference": date.today(),
        "tranche_0_30": tranches["0_30"],
        "tranche_30_60": tranches["30_60"],
        "tranche_60_90": tranches["60_90"],
        "tranche_90_plus": tranches["90_plus"],
        "total_impaye": total,
        "nombre_quittances": len(lignes),
        "lignes": lignes,
    }


def basculer_quittances_en_recouvrement_detaille(db: Session) -> dict:
    """RF-ECH-04 : ouvre un dossier de recouvrement pour chaque quittance impayée dont le
    retard dépasse le délai réglementaire (DELAI_RECOUVREMENT_JOURS), sauf si un dossier
    non clôturé existe déjà pour cette quittance. Idempotent (rejouable sans doublon).

    Renvoie un résumé exploitable côté écran plutôt qu'un simple compteur : nombre de quittances
    impayées vérifiées, nombre d'échues, dossiers réellement ouverts, dossiers déjà en cours (donc
    non rouverts), et le détail des quittances pour lesquelles un dossier vient d'être ouvert.
    « 0 dossier ouvert » devient ainsi lisible (aucune échéance dépassée vs toutes déjà suivies)."""
    impayees = _quittances_impayees(db)
    echues = [(q, reste, jours) for (q, reste, jours) in impayees if jours > DELAI_RECOUVREMENT_JOURS]

    ouverts = []
    deja_en_cours = 0
    for quittance, reste, jours in echues:
        deja_ouvert = db.query(models.DossierRecouvrement).filter(
            models.DossierRecouvrement.quittance_id == quittance.id,
            models.DossierRecouvrement.statut.not_in(STATUTS_DOSSIER_CLOS),
        ).first()
        if deja_ouvert is not None:
            deja_en_cours += 1
            continue
        db.add(models.DossierRecouvrement(
            quittance_id=quittance.id,
            statut=models.StatutDossierRecouv.ouvert,
        ))
        police = db.get(models.Police, quittance.police_id)
        client = db.get(models.Client, police.client_id) if police else None
        ouverts.append({
            "quittance_id": quittance.id,
            "numero_quittance": quittance.numero_quittance,
            "numero_police": police.numero_police if police else None,
            "client": _nom_client(client),
            "jours_retard": jours,
            "reste_du": reste,
        })
    if ouverts:
        db.commit()

    return {
        "delai_jours": DELAI_RECOUVREMENT_JOURS,
        "quittances_verifiees": len(impayees),
        "quittances_echues": len(echues),
        "dossiers_ouverts": len(ouverts),
        "deja_en_cours": deja_en_cours,
        "dossiers": ouverts,
    }


def basculer_quittances_en_recouvrement(db: Session) -> int:
    """Variante « compteur » conservée pour le planificateur (app/scheduler.py) : renvoie le
    seul nombre de dossiers ouverts. S'appuie sur la version détaillée pour rester unique."""
    return basculer_quittances_en_recouvrement_detaille(db)["dossiers_ouverts"]


# ============================================================
# Étapes de relance, historique et suspension (RF-RECOUV-02/03/05)
# ============================================================

def _journaliser(db: Session, dossier: models.DossierRecouvrement, type_evenement: str,
                 description: str, *, ancien=None, nouveau=None, auteur_id: int | None = None) -> None:
    """Ajoute une ligne d'historique au dossier (RF-RECOUV-05). Ne committe pas."""
    db.add(models.EvenementRecouvrement(
        dossier_recouvrement_id=dossier.id,
        type_evenement=type_evenement,
        ancien_statut=ancien.value if ancien is not None else None,
        nouveau_statut=nouveau.value if nouveau is not None else None,
        description=description,
        auteur_id=auteur_id,
    ))


def _reste_du_dossier(db: Session, dossier: models.DossierRecouvrement) -> Decimal:
    """Reste dû de la quittance du dossier (hors chèques rejetés) ; 0 si quittance introuvable."""
    quittance = db.get(models.Quittance, dossier.quittance_id)
    if quittance is None:
        return Decimal("0")
    return quittance.prime_ttc - montant_regle(db, quittance.id)


def _echeancier_respecte(db: Session, dossier: models.DossierRecouvrement) -> bool:
    """Vrai si un échéancier négocié (RF-RECOUV-04) est en cours et RESPECTÉ pour ce dossier :
    il existe et aucun de ses versements n'est marqué « manqué ». Tant qu'il est respecté,
    l'escalade des relances est gelée (le client honore son plan de paiement). Un versement
    manqué le rompt et laisse l'escalade reprendre."""
    echeancier = db.query(models.EcheancierRecouvrement).filter_by(
        dossier_recouvrement_id=dossier.id).first()
    if echeancier is None:
        return False
    manque = db.query(models.VersementEcheancier).filter_by(
        echeancier_id=echeancier.id, statut=models.StatutVersementEcheancier.manque).first()
    return manque is None


def _suspendre_contrat_du_dossier(db: Session, dossier: models.DossierRecouvrement,
                                  auteur_id: int | None) -> models.Police | None:
    """Suspend le contrat de la quittance en recouvrement (RF-RECOUV-03), en RÉUTILISANT la
    logique métier de suspension : un avenant de suspension validé, à effet immédiat, + le
    statut de police aligné (comme le fait la validation d'avenant via sync). Idempotent : ne
    re-suspend pas une police déjà suspendue/résiliée."""
    quittance = db.get(models.Quittance, dossier.quittance_id)
    police = db.get(models.Police, quittance.police_id) if quittance else None
    if police is None or police.statut in (models.StatutPolice.suspendu, models.StatutPolice.resilie):
        return police
    db.add(models.Avenant(
        police_id=police.id, type_avenant=models.TypeAvenant.suspension,
        motif="Suspension automatique pour non-régularisation en recouvrement (RF-RECOUV-03).",
        date_effet=date.today(), statut=models.StatutAvenant.valide,
        valide_par=auteur_id, date_validation=datetime.now(),
    ))
    # Effet immédiat (date d'effet = aujourd'hui), cohérent avec app/sync.py.
    police.statut = models.StatutPolice.suspendu
    db.flush()
    return police


def progresser_dossier(db: Session, dossier: models.DossierRecouvrement, *,
                       auteur_id: int | None = None) -> models.DossierRecouvrement:
    """Fait progresser un dossier d'une étape de relance à la suivante (RF-RECOUV-02) :
    met à jour le statut et la date d'étape, génère la relance datée correspondante
    (RF-RECOUV-03), trace tout dans l'historique (RF-RECOUV-05) et, à la dernière étape,
    suspend automatiquement le contrat (RF-RECOUV-03).

    Lève ValueError si le dossier est déjà à une étape terminale. Ne committe pas (l'appelant
    décide) — utilisé par l'endpoint manuel comme par la tâche planifiée.

    NB (décision à confirmer avec l'encadrant) : à l'issue de la mise en demeure sans
    régularisation, on bascule le contrat en SUSPENSION (réversible) plutôt qu'en résiliation
    (terminale), le CDCF ne tranchant pas explicitement à ce stade. Cf. QUESTIONS_ENCADRANT.md."""
    if dossier.statut not in PROCHAINE_ETAPE:
        raise ValueError(
            f"Le dossier {dossier.id} est à une étape terminale ({dossier.statut.value}) : "
            "aucune progression possible.")
    ancien = dossier.statut
    nouveau = PROCHAINE_ETAPE[ancien]
    dossier.statut = nouveau
    dossier.date_derniere_etape = date.today()

    type_relance = RELANCE_POUR_ETAPE.get(nouveau)
    if type_relance is not None:
        db.add(models.Relance(
            dossier_recouvrement_id=dossier.id, type_relance=type_relance, date_relance=date.today(),
            contenu=f"Relance {type_relance.value} générée automatiquement (passage à l'étape « {nouveau.value} »).",
        ))
        _journaliser(db, dossier, "relance", f"Relance {type_relance.value} générée.", auteur_id=auteur_id)

    if nouveau == models.StatutDossierRecouv.suspendu:
        police = _suspendre_contrat_du_dossier(db, dossier, auteur_id)
        numero = police.numero_police if police else "?"
        _journaliser(db, dossier, "suspension_auto",
                     f"Suspension automatique du contrat {numero} pour non-régularisation.",
                     auteur_id=auteur_id)

    _journaliser(db, dossier, "progression",
                 f"Passage de l'étape « {ancien.value} » à « {nouveau.value} ».",
                 ancien=ancien, nouveau=nouveau, auteur_id=auteur_id)
    db.flush()
    return dossier


def _regulariser_dossier(db: Session, dossier: models.DossierRecouvrement) -> None:
    """Clôt un dossier dont la quittance a été réglée entre-temps (RF-RECOUV) : statut
    `regularise`, date de clôture, trace. Ne committe pas."""
    ancien = dossier.statut
    dossier.statut = models.StatutDossierRecouv.regularise
    dossier.date_cloture = date.today()
    _journaliser(db, dossier, "regularisation",
                 "Régularisation : la quittance a été réglée, dossier clôturé.",
                 ancien=ancien, nouveau=models.StatutDossierRecouv.regularise)


def progresser_dossiers_echus(db: Session) -> list[dict]:
    """RF-RECOUV-02 (tâche planifiée) : fait progresser d'une étape chaque dossier NON terminal
    dont l'étape courante dure depuis au moins DELAI_ENTRE_ETAPES_JOURS. Un dossier dont la
    quittance a été réglée entre-temps est régularisé et clôturé plutôt qu'escaladé. Idempotent
    (une seule progression par exécution, l'horloge d'étape étant remise à zéro) — renvoie la
    liste des transitions effectuées."""
    aujourdhui = date.today()
    transitions: list[dict] = []
    dossiers = db.query(models.DossierRecouvrement).filter(
        models.DossierRecouvrement.statut.in_(list(PROCHAINE_ETAPE.keys()))
    ).all()
    for dossier in dossiers:
        if _reste_du_dossier(db, dossier) <= 0:
            _regulariser_dossier(db, dossier)
            transitions.append({"dossier_id": dossier.id, "de": None, "vers": "regularise"})
            continue
        # RF-RECOUV-04 : un échéancier négocié respecté gèle l'escalade (le client honore son plan).
        if _echeancier_respecte(db, dossier):
            continue
        if (aujourdhui - dossier.date_derniere_etape).days < DELAI_ENTRE_ETAPES_JOURS:
            continue
        ancien = dossier.statut
        progresser_dossier(db, dossier)
        transitions.append({"dossier_id": dossier.id, "de": ancien.value, "vers": dossier.statut.value})
    if transitions:
        db.commit()
    return transitions


# ============================================================
# Échéancier de paiement négocié (RF-RECOUV-04)
# ============================================================

def creer_echeancier(db: Session, dossier: models.DossierRecouvrement, *, montant_total: Decimal,
                     nombre_versements: int, date_premier_versement: date, intervalle_jours: int,
                     auteur_id: int | None = None) -> models.EcheancierRecouvrement:
    """Crée un échéancier négocié pour le dossier (RF-RECOUV-04) : `nombre_versements` versements
    de montant égal (le dernier absorbe l'arrondi), espacés de `intervalle_jours`. Un seul
    échéancier par dossier. Ne committe pas."""
    if db.query(models.EcheancierRecouvrement).filter_by(dossier_recouvrement_id=dossier.id).first():
        raise ValueError("Un échéancier existe déjà pour ce dossier.")
    if nombre_versements < 1:
        raise ValueError("Le nombre de versements doit être au moins 1.")

    echeancier = models.EcheancierRecouvrement(
        dossier_recouvrement_id=dossier.id, montant_total=montant_total,
        nombre_versements=nombre_versements,
    )
    db.add(echeancier)
    db.flush()

    part = (montant_total / nombre_versements).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    for i in range(nombre_versements):
        # Le dernier versement absorbe l'écart d'arrondi pour que la somme = montant_total.
        montant = part if i < nombre_versements - 1 else montant_total - part * (nombre_versements - 1)
        db.add(models.VersementEcheancier(
            echeancier_id=echeancier.id, numero_ordre=i + 1,
            date_prevue=date_premier_versement + timedelta(days=intervalle_jours * i),
            montant=montant, statut=models.StatutVersementEcheancier.prevu,
        ))
    _journaliser(db, dossier, "echeancier",
                 f"Échéancier négocié créé : {nombre_versements} versement(s) pour {montant_total}.",
                 auteur_id=auteur_id)
    db.flush()
    return echeancier
