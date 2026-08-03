# -*- coding: utf-8 -*-
"""
Tests unitaires du moteur de tarification par garantie (RF-SOUS-02).
Purement en mémoire — aucune base de données requise.
"""

from decimal import Decimal

import pytest

from app.tarification import calculer_prime_garantie


def test_mode_taux():
    # 150 000 × 1,5 % = 2 250,00
    assert calculer_prime_garantie({"mode": "taux", "taux": "1.5"}, Decimal("150000")) == Decimal("2250.00")


def test_mode_taux_arrondi_centime():
    # 12 345 × 0,8 % = 98,76
    assert calculer_prime_garantie({"mode": "taux", "taux": "0.8"}, Decimal("12345")) == Decimal("98.76")


def test_mode_forfait():
    assert calculer_prime_garantie({"mode": "forfait", "montant_forfait": "220.00"}, None) == Decimal("220.00")


def test_mode_forfait_ignore_le_capital():
    # Le forfait ne dépend pas du capital, même s'il est fourni.
    assert calculer_prime_garantie(
        {"mode": "forfait", "montant_forfait": "220"}, Decimal("999999")
    ) == Decimal("220.00")


def test_cles_supplementaires_conservees():
    # Une clé hors tarification (ex. "obligatoire") ne fait pas échouer la validation.
    assert calculer_prime_garantie(
        {"mode": "taux", "taux": "2", "obligatoire": True}, Decimal("1000")
    ) == Decimal("20.00")


def test_taux_sans_capital_leve_erreur():
    with pytest.raises(ValueError, match="capital"):
        calculer_prime_garantie({"mode": "taux", "taux": "1.5"}, None)


def test_capital_negatif_rejete():
    with pytest.raises(ValueError, match="négatif"):
        calculer_prime_garantie({"mode": "taux", "taux": "1.5"}, Decimal("-150000"))


@pytest.mark.parametrize("parametres", [
    {"mode": "taux", "taux": "-1.5"},              # taux négatif
    {"mode": "forfait", "montant_forfait": "-10"},  # forfait négatif
])
def test_montants_negatifs_rejetes(parametres):
    with pytest.raises(ValueError):
        calculer_prime_garantie(parametres, Decimal("1000"))


@pytest.mark.parametrize("parametres", [
    {"taux": "1.5"},                      # mode absent
    {"mode": "taux"},                     # taux manquant
    {"mode": "forfait"},                  # montant_forfait manquant
    {"mode": "inconnu", "taux": "1.5"},   # mode inconnu
    {"mode": "taux", "taux": "abc"},      # taux non numérique
    "pas un dict",                        # type invalide
])
def test_parametres_mal_formes_levent_erreur(parametres):
    with pytest.raises(ValueError):
        calculer_prime_garantie(parametres, Decimal("1000"))
