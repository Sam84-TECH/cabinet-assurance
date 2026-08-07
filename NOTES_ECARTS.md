# Notes de traçabilité — écarts frontend/backend (côté backend)

La source de vérité des écarts est **`ECARTS_FRONTEND_BACKEND.md`, qui vit dans le dépôt
frontend** (non dupliqué ici). Ce fichier se contente de tracer, côté backend, les écarts
traités de ce côté.

## Lot 3 — revue complète des écarts (tous résolus côté backend)

- **§28 (détail bordereau reversement)** : `GET /rev/bordereaux/{id}` renvoie désormais les
  lignes, enrichies du numéro de quittance et de police (`BordereauReversementDetailRead`) — résolu.
- **§27 (reste dû quittance)** : `QuittanceRead` expose `montant_regle` et `reste_du` réels — résolu.
- **§26 (quittance à la validation)** : `PATCH /sous/avenants/{id}/valider` renvoie la quittance
  générée en plus de l'avenant (`AvenantValideRead`) — résolu.
- **§25 (identité client)** : `POST /clients` valide l'identité selon le type (422 explicite) au
  lieu de laisser la contrainte CHECK remonter un 400 technique — résolu.
- **§22 (`DashboardRead`)** : `GET /dashboard` typé par un `response_model` — résolu.
- **§14 (numéro de police)** : `LigneBalanceAgee` expose `numero_police` — résolu.
- **§11 (annulation de quittance)** : `PATCH /quittances/{id}/annuler` (super admin, motif
  obligatoire, seulement si `emise`, refus si déjà reversée) — résolu.

_§13 sera revérifié séparément au câblage frontend (hors de ce lot)._

### Écart « modification » — `type_avenant=modification` sans sémantique backend
`type_avenant=modification` n'avait aucun effet serveur (ni champ « quoi modifier », ni
quittance, ni endpoint) ; le frontend avait désactivé l'action. **Résolu côté backend par une
sémantique minimale et tracée** (décision : définir plutôt que retirer le type — c'est un
concept d'assurance central, attendu par la règle 13) :

- l'avenant de modification **en brouillon rouvre la composition** d'une police engagée
  (suppression d'un risque / police_garantie de nouveau autorisée) ; sa validation la
  reverrouille en traçant auteur + date — `app/avenant.py`, branché dans `risque.py` et
  `police_garantie.py` (matérialise le « passer par un avenant » de la règle 13) ;
- son **`motif` est obligatoire** (422 sinon) : seule trace du « quoi » modifié en l'absence
  de champs structurés — `AvenantCreate` ;
- **aucune quittance** générée (`AvenantValideRead.quittance` = None) ; règle 17 du CLAUDE.md.

Le **volet financier** (prorata de prime, avoir/remboursement) est une **question encadrant** :
voir `QUESTIONS_ENCADRANT.md` (Q2). Frontend : l'action « modification » peut être réactivée
pour son usage non financier (ajustement de composition tracé).

## Lots précédents

- **§24 (RC auto)** : RC corrigée côté backend (mode `bareme_puissance`), voir
  `QUESTIONS_ENCADRANT.md` — **écart §24 du frontend résolu.**
- **§23 (`GET /auth/me`)** : endpoint **déjà ajouté** (profil du connecté, testé dans la recette) —
  résolu côté backend, à reprendre côté frontend si l'ECARTS le liste encore « en attente ».
