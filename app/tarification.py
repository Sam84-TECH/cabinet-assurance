"""
Moteur de tarification par garantie (RF-SOUS-02 ; CDCF §3.2 « Règle de tarification »
paramétrée par produit).

La règle de tarification d'une garantie est portée par `Garantie.parametres` (JSONB déjà
existant), selon trois modes :

  - taux             : prime = capital assuré × taux %  -> {"mode": "taux", "taux": "1.5"}
                       (ex. Dommages, Vol, Incendie : % de la valeur du véhicule)
  - forfait          : prime = montant fixe             -> {"mode": "forfait", "montant_forfait": "220.00"}
                       (ex. Assistance, Carte verte, Bris de glace)
  - bareme_puissance : prime = tranche de puissance     -> {"mode": "bareme_puissance", "tranches": [
                       fiscale du véhicule (ex. RC auto,      {"puissance_max": 7, "montant": "1700.00"}, …]}
                       à capital illimité)

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


class TrancheBareme(BaseModel):
    """Une tranche du barème par puissance fiscale : montant fixe jusqu'à `puissance_max` CV
    (borne INCLUSE). `puissance_max = null` désigne la tranche « au-delà » (attrape-tout)."""
    puissance_max: int | None = None
    montant: Decimal = Field(ge=0)


class TarificationBaremePuissance(BaseModel):
    """Tarification par grille de puissance fiscale — cas de la Responsabilité civile auto, à
    capital illimité (elle ne se tarifie pas en % d'un capital, mais par tranches de CV fiscaux).
    La prime est le montant de la première tranche dont `puissance_max >= puissance du véhicule`."""
    model_config = ConfigDict(extra="allow")
    mode: Literal["bareme_puissance"]
    tranches: list[TrancheBareme] = Field(min_length=1)


# Union discriminée par le champ `mode` : documente la structure attendue de Garantie.parametres.
ParametresTarification = Annotated[
    Union[TarificationTaux, TarificationForfait, TarificationBaremePuissance],
    Field(discriminator="mode"),
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


def calculer_prime_garantie(parametres: dict, capital_assure: Decimal | None = None,
                            puissance_fiscale: int | None = None) -> Decimal:
    """Prime d'une garantie selon sa règle de tarification (RF-SOUS-02) :
      - mode « taux »              : capital assuré × taux / 100 (capital obligatoire) ;
      - mode « forfait »           : le montant forfaitaire (capital et puissance ignorés) ;
      - mode « bareme_puissance »  : montant de la tranche couvrant la puissance fiscale du
                                     véhicule (cas de la RC auto, à capital illimité).

    Lève `ValueError` si les paramètres sont mal formés, ou si l'entrée requise par le mode
    est absente (capital pour « taux », puissance fiscale pour « bareme_puissance »).
    """
    tarif = valider_parametres_tarification(parametres)

    if isinstance(tarif, TarificationForfait):
        return _centimes(tarif.montant_forfait)

    if isinstance(tarif, TarificationBaremePuissance):
        if puissance_fiscale is None:
            raise ValueError(
                "Le mode « bareme_puissance » exige la puissance fiscale du véhicule "
                "(attribut puissance_fiscale du risque)."
            )
        if puissance_fiscale < 0:
            raise ValueError("La puissance fiscale ne peut pas être négative.")
        # Tranches triées par borne croissante, la tranche « au-delà » (puissance_max = None) en dernier.
        for tranche in sorted(tarif.tranches, key=lambda t: (t.puissance_max is None, t.puissance_max or 0)):
            if tranche.puissance_max is None or puissance_fiscale <= tranche.puissance_max:
                return _centimes(tranche.montant)
        raise ValueError(
            f"Aucune tranche du barème ne couvre une puissance fiscale de {puissance_fiscale} CV."
        )

    # mode « taux »
    if capital_assure is None:
        raise ValueError(
            "Le mode de tarification « taux » exige un capital assuré (champ capital_assure)."
        )
    if Decimal(capital_assure) < 0:
        raise ValueError("Le capital assuré ne peut pas être négatif.")
    return _centimes(Decimal(capital_assure) * tarif.taux / Decimal("100"))
