# -*- coding: utf-8 -*-
"""
Peuplement de DÉMONSTRATION — jeu de données FICTIF, réaliste et diversifié.

⚠️  DONNÉES DE DÉMONSTRATION FICTIVES — ne pas confondre avec de la production réelle.
    Clients, véhicules, immatriculations, CIN, ICE, montants : tout est inventé pour
    donner à l'application un aspect « vécu » lors d'une présentation. Aucune de ces
    données ne correspond à une personne, une entreprise ou un contrat réels.

Séparé du seed de référence (`seed.py`) qui reste inchangé : `seed.py` crée le
paramétrage figé (compagnie Sanlam, produit Auto, garanties, barème, banques, pièces)
et l'admin ; `demo_data.py` s'exécute EN PLUS, UNE FOIS, pour remplir la base de
contrats, quittances et paiements variés.

Contenu généré (voir le détail plus bas) :
  - 6 clients particuliers + 2 entreprises, noms marocains fictifs ;
  - une entreprise « flotte » avec 4 contrats actifs simultanés (un véhicule par police) ;
  - un contrat à historique : affaire nouvelle -> renouvellement -> modification ;
  - deux contrats résiliés à des dates différentes (dont un client « parti », sans contrat actif) ;
  - un contrat suspendu ; le reste en vigueur ;
  - quittances réglées, impayées et un chèque rejeté ;
  - impayés étalés dans le temps pour peupler les 4 tranches de la balance âgée
    (0-30, 30-60, 60-90, 90+), et ouverture des dossiers de recouvrement correspondants.

IDEMPOTENT : un garde-fou (présence d'un client sentinelle) empêche tout doublon si le
script est relancé — il ne réinsère rien et se termine proprement.

Usage (identique au seed) :
    python demo_data.py
Prérequis : base migrée (`alembic upgrade head`) et seed de référence déjà passé
(`python seed.py`). La chaîne de connexion est lue depuis DATABASE_URL (.env en local,
variable d'environnement en production Neon).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.database import SessionLocal  # noqa: E402  (après load_dotenv, volontairement)
from app import models                 # noqa: E402
from app.numerotation import generer_numero_police  # noqa: E402
from app.facturation import generer_quittance_pour_avenant  # noqa: E402
from app.recouvrement import basculer_quittances_en_recouvrement  # noqa: E402

AUJ = date.today()
# CIN du premier client de démo : sert de sentinelle d'idempotence (présence = déjà peuplé).
SENTINELLE_CIN = "EE445123"


def j(offset: int) -> date:
    """Date décalée de `offset` jours par rapport à aujourd'hui (négatif = passé)."""
    return AUJ + timedelta(days=offset)


def _dt(d: date) -> datetime:
    """Datetime (minuit) correspondant à une date — pour horodater date_creation dans le passé."""
    return datetime.combine(d, time(9, 0))


# ------------------------------------------------------------------
# Référentiel (créé par le seed) — chargé, jamais recréé ici
# ------------------------------------------------------------------

class Refs:
    def __init__(self, db):
        self.produit = db.query(models.Produit).filter_by(code="AUTO").first()
        if self.produit is None:
            raise SystemExit("Produit AUTO introuvable : lancez d'abord `python seed.py`.")
        self.garanties = {
            g.code: g.id
            for g in db.query(models.Garantie).filter_by(produit_id=self.produit.id)
        }
        self.compagnie_id = self.produit.compagnie_id
        admin = (
            db.query(models.Utilisateur)
            .filter_by(role=models.RoleUtilisateur.super_administrateur)
            .first()
        )
        # valide_par est nullable : sans admin en base, on laisse None (pas de blocage).
        self.admin_id = admin.id if admin else None


# ------------------------------------------------------------------
# Briques de construction
# ------------------------------------------------------------------

def _client_particulier(db, *, cin, nom, prenom, ville, tel, profession, statut=models.StatutClient.actif):
    c = models.Client(
        type=models.TypeClient.particulier, cin=cin, nom=nom, prenom=prenom,
        telephone=tel, ville=ville, pays="Maroc", profession=profession, statut=statut,
    )
    db.add(c)
    db.flush()
    return c


def _client_entreprise(db, *, raison_sociale, ice, ville, tel, responsable, statut=models.StatutClient.actif):
    c = models.Client(
        type=models.TypeClient.entreprise, raison_sociale=raison_sociale, ice=ice,
        telephone=tel, ville=ville, pays="Maroc", responsable=responsable, statut=statut,
    )
    db.add(c)
    db.flush()
    return c


def _vehicule(immatriculation, marque, modele, mise_en_circ, valeur_neuf, puissance):
    return {
        "immatriculation": immatriculation, "marque": marque, "modele": modele,
        "date_mise_en_circulation": mise_en_circ, "valeur_neuf": valeur_neuf,
        "puissance_fiscale": puissance,
    }


def _souscrire(db, refs, client, *, date_effet, date_echeance, vehicule, garanties,
               statut_police, periode_fin=None, quittance_statut=models.StatutQuittance.emise,
               date_creation=None):
    """Crée une police complète (police + véhicule + garanties + pièces + avenant d'affaire
    nouvelle validé + quittance générée) et renvoie (police, avenant, quittance).
    `garanties` : liste de (code, prime_str). Les dates sont posées explicitement (données
    « vécues » étalées). La quittance est générée par la vraie logique de facturation puis
    ajustée (période/statut/horodatage)."""
    dc = date_creation or _dt(date_effet)
    police = models.Police(
        numero_police=generer_numero_police(db),
        client_id=client.id, produit_id=refs.produit.id,
        statut=statut_police, date_effet=date_effet, date_echeance=date_echeance,
        date_creation=dc,
    )
    db.add(police)
    db.flush()

    risque = models.Risque(police_id=police.id, type_risque="vehicule", attributs=vehicule)
    db.add(risque)
    db.flush()

    for code, prime in garanties:
        db.add(models.PoliceGarantie(
            police_id=police.id, risque_id=risque.id,
            garantie_id=refs.garanties[code], montant_prime=Decimal(prime),
        ))
    db.flush()

    # Pièces obligatoires fournies (dossier complet, comme en émission réelle).
    for piece in db.query(models.PieceJustificativeRequise).filter_by(
        produit_id=refs.produit.id, obligatoire=True
    ):
        db.add(models.PieceJustificativeFournie(
            police_id=police.id, piece_requise_id=piece.id, reference="démo", date_fourniture=date_effet,
        ))
    db.flush()

    avenant = models.Avenant(
        police_id=police.id, type_avenant=models.TypeAvenant.affaire_nouvelle,
        date_effet=date_effet, statut=models.StatutAvenant.valide,
        valide_par=refs.admin_id, date_creation=dc, date_validation=dc,
    )
    db.add(avenant)
    db.flush()

    quittance = generer_quittance_pour_avenant(db, avenant)
    quittance.periode_debut = date_effet
    quittance.periode_fin = periode_fin or date_echeance
    quittance.date_creation = dc
    quittance.statut = quittance_statut
    db.flush()
    return police, avenant, quittance


def _avenant(db, refs, police, type_avenant, *, date_effet, motif=None):
    """Avenant validé supplémentaire (renouvellement / modification / suspension / résiliation)."""
    av = models.Avenant(
        police_id=police.id, type_avenant=type_avenant, motif=motif,
        date_effet=date_effet, statut=models.StatutAvenant.valide,
        valide_par=refs.admin_id, date_creation=_dt(date_effet), date_validation=_dt(date_effet),
    )
    db.add(av)
    db.flush()
    return av


def _encaisser(db, client, quittance, *, date_enc, mode, montant=None, rejete=False):
    """Enregistre un encaissement affecté à la quittance. Si `rejete`, le chèque est marqué
    impayé (le montant réglé effectif l'exclut -> la quittance redevient/reste impayée)."""
    montant = Decimal(montant) if montant is not None else quittance.prime_ttc
    enc = models.Encaissement(
        client_id=client.id, mode_paiement=mode, montant=montant,
        date_encaissement=date_enc, statut=models.StatutEncaissement.enregistre,
        date_creation=_dt(date_enc),
    )
    if mode == models.ModePaiement.cheque:
        enc.cheque_banque = "Attijariwafa Bank"
        enc.cheque_numero = f"CHQ{date_enc.strftime('%y%m%d')}{quittance.id:03d}"
    elif mode == models.ModePaiement.virement:
        enc.virement_banque = "Banque Populaire"
        enc.virement_reference = f"VIR{date_enc.strftime('%y%m%d')}{quittance.id:03d}"
    db.add(enc)
    db.flush()
    db.add(models.EncaissementQuittance(
        encaissement_id=enc.id, quittance_id=quittance.id, montant_affecte=montant,
    ))
    db.flush()
    if rejete:
        enc.statut = models.StatutEncaissement.rejete
        enc.motif_rejet = "Provision insuffisante"
        enc.date_rejet = date_enc + timedelta(days=3)
    db.flush()
    return enc


# ------------------------------------------------------------------
# Scénario de démonstration
# ------------------------------------------------------------------

def peupler(db):
    refs = Refs(db)

    # --- Garanties types (code, prime) selon la puissance du véhicule ---
    def gar_standard(rc):  # RC + dommages + vol + bris de glace + assistance
        return [("RC", rc), ("DC", "1800.00"), ("VOL", "900.00"), ("BDG", "220.00"), ("ASSIST", "300.00")]

    def gar_rc_seule(rc):  # tiers simple : RC + défense/recours + assistance
        return [("RC", rc), ("DR", "80.00"), ("ASSIST", "300.00")]

    def gar_flotte(rc):  # utilitaire de flotte
        return [("RC", rc), ("DC", "1500.00"), ("VOL", "700.00"), ("DR", "80.00")]

    # ============================================================
    # PARTICULIERS
    # ============================================================

    # 1. Youssef El Amrani — contrat À HISTORIQUE (affaire nouvelle -> renouvellement -> modification)
    youssef = _client_particulier(
        db, cin=SENTINELLE_CIN, nom="El Amrani", prenom="Youssef", ville="Casablanca",
        tel="0661120034", profession="Ingénieur", statut=models.StatutClient.vip,
    )
    # Police souscrite il y a ~13 mois, échéance initiale il y a ~35 jours, puis renouvelée (+1 an).
    pol_y, _, q_y1 = _souscrire(
        db, refs, youssef,
        date_effet=j(-400), date_echeance=j(330),  # échéance FINALE après renouvellement
        vehicule=_vehicule("45231-A-6", "Dacia", "Duster", "04/2021", "245000.00", 8),
        garanties=gar_standard("2400.00"),
        statut_police=models.StatutPolice.en_vigueur,
        periode_fin=j(-35),  # la 1re quittance couvre la période initiale
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, youssef, q_y1, date_enc=j(-395), mode=models.ModePaiement.cheque)
    # Renouvellement il y a ~35 jours -> 2e quittance (nouvelle période), réglée récemment.
    av_renouv = _avenant(db, refs, pol_y, models.TypeAvenant.renouvellement, date_effet=j(-35))
    q_y2 = generer_quittance_pour_avenant(db, av_renouv)
    q_y2.periode_debut = j(-35)
    q_y2.periode_fin = j(330)
    q_y2.date_creation = _dt(j(-35))
    q_y2.statut = models.StatutQuittance.reglee
    db.flush()
    _encaisser(db, youssef, q_y2, date_enc=j(-30), mode=models.ModePaiement.virement)
    # Modification de garanties il y a ~10 jours (ajout bris de glace), tracée, sans quittance.
    _avenant(db, refs, pol_y, models.TypeAvenant.modification, date_effet=j(-10),
             motif="Ajout de la garantie bris de glace à la demande du client")

    # 2. Fatima Zahra Bennani — en vigueur, réglée (espèces)
    fatima = _client_particulier(
        db, cin="BK220876", nom="Bennani", prenom="Fatima Zahra", ville="Rabat",
        tel="0662233445", profession="Médecin",
    )
    _, _, q_f = _souscrire(
        db, refs, fatima, date_effet=j(-200), date_echeance=j(165),
        vehicule=_vehicule("18902-B-1", "Renault", "Clio", "06/2022", "175000.00", 6),
        garanties=gar_standard("1700.00"), statut_police=models.StatutPolice.en_vigueur,
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, fatima, q_f, date_enc=j(-195), mode=models.ModePaiement.especes)

    # 3. Karim Tazi — en vigueur, IMPAYÉ récent (tranche 0-30)
    karim = _client_particulier(
        db, cin="TA109834", nom="Tazi", prenom="Karim", ville="Marrakech",
        tel="0663344556", profession="Commerçant",
    )
    _souscrire(
        db, refs, karim, date_effet=j(-15), date_echeance=j(350),
        vehicule=_vehicule("77410-C-6", "Peugeot", "208", "01/2023", "195000.00", 7),
        garanties=gar_standard("1700.00"), statut_police=models.StatutPolice.en_vigueur,
        quittance_statut=models.StatutQuittance.emise,  # impayé
    )

    # 4. Salma Idrissi — en vigueur, CHÈQUE REJETÉ (impayé, tranche 30-60)
    salma = _client_particulier(
        db, cin="IB556201", nom="Idrissi", prenom="Salma", ville="Fès",
        tel="0664455667", profession="Enseignante",
    )
    _, _, q_s = _souscrire(
        db, refs, salma, date_effet=j(-45), date_echeance=j(320),
        vehicule=_vehicule("30125-D-5", "Hyundai", "i10", "09/2020", "125000.00", 5),
        garanties=gar_rc_seule("1200.00"), statut_police=models.StatutPolice.en_vigueur,
        quittance_statut=models.StatutQuittance.emise,  # redevient impayé après rejet
    )
    _encaisser(db, salma, q_s, date_enc=j(-40), mode=models.ModePaiement.cheque, rejete=True)

    # 5. Rachid Alaoui — SUSPENDU
    rachid = _client_particulier(
        db, cin="AL778432", nom="Alaoui", prenom="Rachid", ville="Tanger",
        tel="0665566778", profession="Chauffeur",
    )
    pol_r, _, q_r = _souscrire(
        db, refs, rachid, date_effet=j(-120), date_echeance=j(245),
        vehicule=_vehicule("52063-E-2", "Ford", "Fiesta", "03/2019", "110000.00", 6),
        garanties=gar_rc_seule("1700.00"), statut_police=models.StatutPolice.suspendu,
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, rachid, q_r, date_enc=j(-115), mode=models.ModePaiement.cheque)
    _avenant(db, refs, pol_r, models.TypeAvenant.suspension, date_effet=j(-20),
             motif="Véhicule immobilisé (panne moteur)")

    # 6. Nadia Chraibi — client « PARTI » : son unique contrat est RÉSILIÉ (aucun actif)
    nadia = _client_particulier(
        db, cin="CH334519", nom="Chraibi", prenom="Nadia", ville="Agadir",
        tel="0666677889", profession="Architecte",
    )
    pol_n, _, q_n = _souscrire(
        db, refs, nadia, date_effet=j(-300), date_echeance=j(65),
        vehicule=_vehicule("64890-H-8", "Volkswagen", "Golf", "11/2018", "210000.00", 8),
        garanties=gar_standard("2400.00"), statut_police=models.StatutPolice.resilie,
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, nadia, q_n, date_enc=j(-295), mode=models.ModePaiement.cheque)
    _avenant(db, refs, pol_n, models.TypeAvenant.resiliation, date_effet=j(-60),
             motif="Résiliation à la demande du client (départ à l'étranger)")

    # ============================================================
    # ENTREPRISES
    # ============================================================

    # A. Transports Atlas SARL — FLOTTE : 4 polices actives simultanées (un véhicule chacune)
    atlas = _client_entreprise(
        db, raison_sociale="Transports Atlas SARL", ice="001789456000073", ville="Casablanca",
        tel="0522445566", responsable="Hicham Berrada", statut=models.StatutClient.vip,
    )
    # L'ancienneté d'un impayé se compte depuis periode_debut, que `_souscrire` fixe à date_effet :
    # la date d'effet de la police EST donc le levier des tranches de balance âgée (75 j -> 60-90, 120 j -> 90+).
    flotte = [
        # (immat, marque, modèle, mise en circ, valeur, CV, RC, effet, statut quittance)
        ("A-11001-20", "Renault", "Kangoo",  "05/2022", "180000.00", 6, "1700.00", j(-180), models.StatutQuittance.reglee),
        ("A-11002-20", "Peugeot", "Partner",  "07/2022", "185000.00", 6, "1700.00", j(-150), models.StatutQuittance.reglee),
        ("A-11003-20", "Dacia",   "Dokker",   "02/2021", "160000.00", 5, "1200.00", j(-75),  models.StatutQuittance.emise),   # impayé -> tranche 60-90
        ("A-11004-20", "Fiat",    "Doblo",    "10/2020", "155000.00", 5, "1200.00", j(-120), models.StatutQuittance.emise),  # impayé -> tranche 90+
    ]
    for immat, marque, modele, mec, valeur, cv, rc, effet, qstatut in flotte:
        _, _, q = _souscrire(
            db, refs, atlas,
            date_effet=effet, date_echeance=effet + timedelta(days=365),
            vehicule=_vehicule(immat, marque, modele, mec, valeur, cv),
            garanties=gar_flotte(rc), statut_police=models.StatutPolice.en_vigueur,
            quittance_statut=qstatut,
        )
        if qstatut == models.StatutQuittance.reglee:
            _encaisser(db, atlas, q, date_enc=effet + timedelta(days=5), mode=models.ModePaiement.virement)

    # B. Cabinet Médical Ibn Sina SARL — 1 contrat en vigueur (réglé) + 1 résilié (2e résiliation, autre date)
    ibnsina = _client_entreprise(
        db, raison_sociale="Cabinet Médical Ibn Sina SARL", ice="002456123000048", ville="Rabat",
        tel="0537889900", responsable="Dr. Leila Fassi",
    )
    _, _, q_i1 = _souscrire(
        db, refs, ibnsina, date_effet=j(-220), date_echeance=j(145),
        vehicule=_vehicule("29875-A-1", "Toyota", "Yaris", "08/2022", "185000.00", 6),
        garanties=gar_standard("1700.00"), statut_police=models.StatutPolice.en_vigueur,
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, ibnsina, q_i1, date_enc=j(-215), mode=models.ModePaiement.virement)
    pol_i2, _, q_i2 = _souscrire(
        db, refs, ibnsina, date_effet=j(-365), date_echeance=j(0),
        vehicule=_vehicule("41200-B-1", "Citroën", "C3", "03/2019", "150000.00", 6),
        garanties=gar_rc_seule("1700.00"), statut_police=models.StatutPolice.resilie,
        quittance_statut=models.StatutQuittance.reglee,
    )
    _encaisser(db, ibnsina, q_i2, date_enc=j(-360), mode=models.ModePaiement.cheque)
    _avenant(db, refs, pol_i2, models.TypeAvenant.resiliation, date_effet=j(-120),
             motif="Résiliation pour vente du véhicule")

    # Ouverture des dossiers de recouvrement pour les impayés dépassant le délai (RF-ECH-04) :
    # rend l'écran Recouvrement « vécu » (Salma 45 j, flotte Atlas 75 j et 120 j). Appelé AVANT
    # le commit : la bascule lit les impayés déjà flushés et son commit interne persiste tout d'un
    # bloc (contrats + dossiers), y compris le client sentinelle — pas d'état partiel possible.
    dossiers = basculer_quittances_en_recouvrement(db)
    db.commit()  # filet si la bascule n'a rien committé (aucun impayé au-delà du délai)
    return dossiers


def main():
    db = SessionLocal()
    try:
        if db.query(models.Client).filter_by(cin=SENTINELLE_CIN).first() is not None:
            print("-> Données de démonstration déjà présentes : rien à faire (idempotent).")
            return
        dossiers = peupler(db)
        nb_clients = db.query(models.Client).count()
        nb_polices = db.query(models.Police).count()
        nb_quittances = db.query(models.Quittance).count()
        nb_encaissements = db.query(models.Encaissement).count()
        print("=== Donnees de DEMONSTRATION (fictives) " + "=" * 20)
        print(f"  Clients        : {nb_clients}")
        print(f"  Polices        : {nb_polices}")
        print(f"  Quittances     : {nb_quittances}")
        print(f"  Encaissements  : {nb_encaissements}")
        print(f"  Dossiers recouvrement ouverts : {dossiers}")
        print("=" * 60)
        print("-> Base de demonstration peuplee. (Donnees fictives, ne pas confondre avec la production.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
