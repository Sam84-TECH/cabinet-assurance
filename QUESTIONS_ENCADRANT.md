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

### Q2 — Traitement financier de l'avenant de modification (prorata + avoir) — écart « modification »
Un avenant de `modification` (changement de véhicule, ajout/retrait de garantie sur un contrat
en cours) est aujourd'hui traité côté backend dans sa **dimension administrative uniquement** :
il rouvre la composition de la police le temps d'un brouillon, la reverrouille à sa validation,
et trace auteur/date/motif — **sans aucun calcul financier** (voir `app/avenant.py`, et la note
dans `app/facturation.py`).

Le **volet financier** reste à définir avec l'encadrant :
- Une modification en cours de contrat doit-elle donner lieu à un **ajustement de prime au
  prorata temporis** (supplément si la couverture augmente, avoir/remboursement si elle
  diminue) ? Sinon, comment l'agence gère-t-elle concrètement ces cas ?
- Faut-il émettre une **quittance complémentaire** (supplément) et/ou un **avoir** (note de
  crédit / montant négatif) ? Quel document, quelle numérotation ?
- Quels changements déclenchent un ajustement (garantie, capital, usage, puissance…) et
  lesquels sont neutres (adresse, conducteur à tarif égal) ?

**À faire :** une fois la règle métier connue, ajouter au module `modification` le calcul du
delta de prime au prorata de la période restante et l'émission du document correspondant
(quittance complémentaire / avoir). En attendant, l'action « modification » côté frontend peut
être réactivée pour son usage **non financier** (ajustement de composition tracé).

_Origine : écart « type_avenant=modification sans sémantique backend », lot 3._
