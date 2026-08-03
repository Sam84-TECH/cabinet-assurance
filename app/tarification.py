"""
Moteur de tarification par garantie (RF-SOUS-02 ; CDCF §3.2 « Règle de tarification »
paramétrée par produit).

La règle de tarification d'une garantie est portée par `Garantie.parametres` (JSONB déjà
existant), selon deux modes :

  - taux    : prime = capital assuré × taux %     ->  {"mode": "taux", "taux": "1.5"}
  - forfait : prime = montant fixe                ->  {"mode": "forfait", "montant_forfait": "220.00"}
              (ex. Assistance, Carte verte, Bris de glace)

`parametres` peut contenir d'autres clés (ex. "obligatoire") : elles sont conservées, seule
la partie tarification est validée par les schémas ci-dessous.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class TarificationTaux(BaseModel):
    """Tarification proportionnelle : la prime est un pourcentage du capital assuré."""
    model_config = ConfigDict(extra="allow")  # conserve les clés hors tarification (ex. "obligatoire")
    mode: Literal["taux"]
    taux: Decimal = Field(ge=0)  # pourcentage (>= 0) appliqué au capital assuré


class TarificationForfait(BaseModel):
    """Tarification forfaitaire : la prime est un montant fixe, indépendant du capital."""
    model_config = ConfigDict(extra="allow")
    mode: Literal["forfait"]
    montant_forfait: Decimal = Field(ge=0)


# Union discriminée par le champ `mode` : documente la structure attendue de Garantie.parametres.
ParametresTarification = Annotated[
    Union[TarificationTaux, TarificationForfait], Field(discriminator="mode")
]
_ADAPTATEUR = TypeAdapter(ParametresTarification)


def valider_parametres_tarification(parametres: dict):
    """Valide `parametres` et renvoie la règle de tarification typée. Lève `ValueError` (message
    en clair) si `parametres` est mal formé : mode absent/inconnu, champ requis manquant
    (taux / montant_forfait), ou valeur non numérique."""
    if not isinstance(parametres, dict):
        raise ValueError("Les paramètres de tarification doivent être un objet JSON.")
    try:
        return _ADAPTATEUR.validate_python(parametres)
    except ValidationError as exc:
        detail = exc.errors()[0].get("msg", "structure invalide")
        raise ValueError(f"Paramètres de tarification invalides : {detail}.") from exc


def _centimes(montant: Decimal) -> Decimal:
    return montant.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculer_prime_garantie(parametres: dict, capital_assure: Decimal | None) -> Decimal:
    """Prime d'une garantie selon sa règle de tarification (RF-SOUS-02) :
      - mode « taux »    : capital assuré × taux / 100 (le capital est alors obligatoire) ;
      - mode « forfait » : le montant forfaitaire (le capital est ignoré).

    Lève `ValueError` si les paramètres sont mal formés, ou si le mode « taux » est demandé
    sans capital assuré fourni.
    """
    tarif = valider_parametres_tarification(parametres)
    if isinstance(tarif, TarificationForfait):
        return _centimes(tarif.montant_forfait)
    # mode « taux »
    if capital_assure is None:
        raise ValueError(
            "Le mode de tarification « taux » exige un capital assuré (champ capital_assure)."
        )
    if Decimal(capital_assure) < 0:
        raise ValueError("Le capital assuré ne peut pas être négatif.")
    return _centimes(Decimal(capital_assure) * tarif.taux / Decimal("100"))
