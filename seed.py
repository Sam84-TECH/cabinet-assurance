"""
Script de peuplement initial (seed) — jeu de données de départ du cabinet.

Crée le paramétrage « figé » décrit dans le CDCF (règle métier n°11 : paramétrage
figé → seed) : la compagnie Sanlam Maroc, les banques de l'agence, le produit
Automobile avec ses garanties, un barème de commission et les pièces justificatives
exigées à la souscription auto.

IDEMPOTENT : chaque objet n'est créé que s'il n'existe pas déjà (recherche par clé
naturelle). Le script peut donc être relancé autant de fois que nécessaire sans
jamais créer de doublon, et sans écraser une valeur modifiée entre-temps par l'agence.

Usage :
    python seed.py

Prérequis : la base doit exister et les migrations être appliquées :
    docker compose up -d
    alembic upgrade head
"""

from datetime import date
from decimal import Decimal

# Charge un éventuel .env AVANT d'importer app.database, qui lit DATABASE_URL au
# moment de son import (l'ordre est donc important).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.database import SessionLocal  # noqa: E402  (après load_dotenv, volontairement)
from app import models                 # noqa: E402


# ------------------------------------------------------------------
# Données de référence (paramétrage de départ)
# ------------------------------------------------------------------

# Barème RC par puissance fiscale (RF-SOUS-02, écart §24). La RC auto est à capital ILLIMITÉ :
# elle ne se tarifie pas en % d'un capital, mais par tranches de puissance fiscale (CV).
# /!\ VALEURS INDICATIVES, PROVISOIRES — à remplacer par le vrai barème réglementaire de la
# compagnie dès qu'il sera fourni par l'encadrant (cf. QUESTIONS_ENCADRANT.md).
BAREME_RC = {
    "mode": "bareme_puissance",
    "tranches": [
        {"puissance_max": 4,    "montant": "1200.00"},   # jusqu'à 4 CV
        {"puissance_max": 7,    "montant": "1700.00"},   # 5 à 7 CV
        {"puissance_max": 10,   "montant": "2400.00"},   # 8 à 10 CV
        {"puissance_max": None, "montant": "3200.00"},   # 11 CV et au-delà
    ],
}

# Garanties habituelles d'un contrat auto au Maroc. Le détail paramétrable va dans
# `parametres` (JSONB) pour rester générique : "obligatoire" + la règle de tarification
# (RF-SOUS-02, cf. app/tarification.py). Taux/forfaits/tranches indicatifs, à caler sur le
# vrai barème de la compagnie.
GARANTIES_AUTO = [
    ("RC",     "Responsabilité civile",  {"obligatoire": True, **BAREME_RC}),  # barème par puissance (§24)
    ("DC",     "Dommages collision",     {"obligatoire": False, "mode": "taux",    "taux": "2.50"}),
    ("VOL",    "Vol",                    {"obligatoire": False, "mode": "taux",    "taux": "1.50"}),
    ("INC",    "Incendie",               {"obligatoire": False, "mode": "taux",    "taux": "0.80"}),
    ("BDG",    "Bris de glace",          {"obligatoire": False, "mode": "forfait", "montant_forfait": "220.00"}),
    ("PT",     "Personnes transportées", {"obligatoire": False, "mode": "forfait", "montant_forfait": "150.00"}),
    ("DR",     "Défense et recours",     {"obligatoire": False, "mode": "forfait", "montant_forfait": "80.00"}),
    ("ASSIST", "Assistance",             {"obligatoire": False, "mode": "forfait", "montant_forfait": "300.00"}),
    ("CV",     "Carte verte",            {"obligatoire": False, "mode": "forfait", "montant_forfait": "100.00"}),
]

# Pièces justificatives exigées pour une souscription auto.
PIECES_AUTO = [
    ("Copie de la CIN",                              True),
    ("Copie de la carte grise",                      True),
    ("Copie du permis de conduire",                  True),
    ("Relevé d'information de l'assureur précédent",  False),
    ("Procès-verbal du contrôle technique",          False),
]

# Les deux banques où l'agence dépose ses encaissements.
BANQUES_AGENCE = [
    "Attijariwafa Bank",
    "Banque Populaire",
]

TAUX_COMMISSION_AUTO = Decimal("10.00")   # % — barème agent Sanlam / Auto
DATE_DEBUT_BAREME = date(2025, 1, 1)


def get_or_create(db, model, defaults=None, **cle):
    """Renvoie l'objet identifié par `cle`, ou le crée (avec `cle` + `defaults`)
    s'il n'existe pas. Cœur de l'idempotence du seed.

    Retourne (objet, cree) où `cree` vaut True si l'objet vient d'être inséré.
    """
    obj = db.query(model).filter_by(**cle).first()
    if obj is not None:
        return obj, False
    obj = model(**{**cle, **(defaults or {})})
    db.add(obj)
    db.flush()  # attribue l'id sans clôturer la transaction
    return obj, True


def seed(db):
    faits = []  # un booléen « créé ? » par objet, pour le récapitulatif final

    # 1. Compagnie — clé naturelle : code
    sanlam, cree = get_or_create(
        db, models.Compagnie, code="SANLAM",
        defaults={"nom": "Sanlam Maroc", "actif": True},
    )
    faits.append(cree)

    # 2. Banques de l'agence — clé naturelle : nom
    for nom in BANQUES_AGENCE:
        _, cree = get_or_create(db, models.BanqueAgence, nom=nom, defaults={"actif": True})
        faits.append(cree)

    # 3. Produit Automobile — clé naturelle : code
    auto, cree = get_or_create(
        db, models.Produit, code="AUTO",
        defaults={"nom": "Automobile", "compagnie_id": sanlam.id, "actif": True},
    )
    faits.append(cree)

    # 4. Garanties du produit Auto — clé naturelle : produit_id + code.
    # Idempotent AVEC rattrapage : les barèmes de tarification (RF-SOUS-02) ont été introduits
    # après le premier seed. Une garantie déjà en base mais dont les `parametres` n'ont pas encore
    # de règle de tarification (clé "mode") est complétée avec son barème — sans toucher aux autres
    # clés ni écraser un mode déjà défini par l'agence.
    maj_tarification = 0
    for code, libelle, params in GARANTIES_AUTO:
        garantie, cree = get_or_create(
            db, models.Garantie, produit_id=auto.id, code=code,
            defaults={"nom": libelle, "parametres": params},
        )
        if not cree and "mode" not in (garantie.parametres or {}):
            tarif = {c: v for c, v in params.items() if c in ("mode", "taux", "montant_forfait")}
            garantie.parametres = {**(garantie.parametres or {}), **tarif}  # nouveau dict -> changement détecté
            maj_tarification += 1
        faits.append(cree)

    # Correction ciblée §24 : une RC déjà en base avait été paramétrée en mode "taux" (faux, la RC
    # est à capital illimité). On la bascule vers son barème par puissance si ce n'est pas déjà fait,
    # en retirant les anciennes clés de tarification et en conservant le reste (ex. "obligatoire").
    rc = db.query(models.Garantie).filter_by(produit_id=auto.id, code="RC").first()
    if rc is not None and (rc.parametres or {}).get("mode") != "bareme_puissance":
        conserve = {c: v for c, v in (rc.parametres or {}).items()
                    if c not in ("mode", "taux", "montant_forfait", "tranches")}
        rc.parametres = {**conserve, **BAREME_RC}
        maj_tarification += 1

    # 5. Barème de commission Sanlam / Auto — clé naturelle : compagnie_id + produit_id
    _, cree = get_or_create(
        db, models.BaremeCommission, compagnie_id=sanlam.id, produit_id=auto.id,
        defaults={
            "taux_commission": TAUX_COMMISSION_AUTO,
            "date_debut": DATE_DEBUT_BAREME,
            "date_fin": None,
        },
    )
    faits.append(cree)

    # 6. Pièces justificatives exigées à la souscription — clé naturelle : produit_id + nom
    for nom, obligatoire in PIECES_AUTO:
        _, cree = get_or_create(
            db, models.PieceJustificativeRequise, produit_id=auto.id, nom=nom,
            defaults={"obligatoire": obligatoire},
        )
        faits.append(cree)

    db.commit()

    crees = sum(faits)
    existants = len(faits) - crees
    # Décorations en ASCII pur : la console Windows (cp1252) ne sait pas encoder les caractères
    # de filet « ─ », le tiret cadratin « — » ni la flèche « → » (les lettres accentuées, elles,
    # existent en cp1252 et s'affichent correctement).
    print("=== Seed du cabinet - Sanlam Maroc " + "=" * 25)
    print(f"  Compagnie    : {sanlam.nom} [{sanlam.code}] (id={sanlam.id})")
    print(f"  Produit      : {auto.nom} [{auto.code}] (id={auto.id})")
    print(f"  Garanties    : {len(GARANTIES_AUTO)}")
    print(f"  Banques      : {len(BANQUES_AGENCE)}")
    print(f"  Pièces just. : {len(PIECES_AUTO)}")
    print(f"  Barème       : {TAUX_COMMISSION_AUTO} % (Sanlam / Auto, depuis {DATE_DEBUT_BAREME})")
    print("=" * 60)
    print(f"-> {crees} objet(s) créé(s), {existants} déjà présent(s), aucun doublon.")
    if maj_tarification:
        print(f"-> {maj_tarification} garantie(s) existante(s) complétée(s) avec leur barème de tarification.")


def main():
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
