# Questions en attente pour l'encadrant

Liste des décisions/données métier à confirmer avec l'encadrant. À répercuter aussi dans
`ECARTS_FRONTEND_BACKEND.md` (côté frontend).

## En attente

### Q1 — Barème réel de tarification de la Responsabilité civile auto (RC) — écart §24
La RC auto est à **capital illimité** : elle ne se tarifie pas en % d'un capital, mais par
**tranches de puissance fiscale** (mode `bareme_puissance`, cf. `app/tarification.py`).

Le barème actuellement en base (seed, constante `BAREME_RC`) est **INDICATIF et PROVISOIRE** :

| Puissance fiscale | Prime RC (indicative) |
|-------------------|-----------------------|
| jusqu'à 4 CV      | 1 200,00 DH           |
| 5 à 7 CV          | 1 700,00 DH           |
| 8 à 10 CV         | 2 400,00 DH           |
| 11 CV et au-delà  | 3 200,00 DH           |

**À faire :** obtenir le **vrai barème réglementaire** de la compagnie (Sanlam) auprès de
l'encadrant, puis remplacer les valeurs de `BAREME_RC` dans `seed.py` (et re-seed). D'autres
critères peuvent entrer en jeu (usage, carburant, zone) : à préciser si le barème réel les
utilise — le mode `bareme_puissance` pourra être étendu en conséquence.

_Origine : tarification par garantie (RF-SOUS-02), lot 2._
