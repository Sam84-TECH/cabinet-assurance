# Notes de traçabilité — écarts frontend/backend (côté backend)

La source de vérité des écarts est **`ECARTS_FRONTEND_BACKEND.md`, qui vit dans le dépôt
frontend** (non dupliqué ici). Ce fichier se contente de tracer, côté backend, les écarts
traités de ce côté.

## Lot 3

- **§28 (détail bordereau reversement)** : `GET /rev/bordereaux/{id}` renvoie désormais les
  lignes, enrichies du numéro de quittance et de police (`BordereauReversementDetailRead`) — résolu.
- **§27 (reste dû quittance)** : `QuittanceRead` expose `montant_regle` et `reste_du` réels — résolu.
- **§26 (quittance à la validation)** : `PATCH /sous/avenants/{id}/valider` renvoie la quittance
  générée en plus de l'avenant (`AvenantValideRead`) — résolu.
- **§25 (identité client)** : `POST /clients` valide l'identité selon le type (422 explicite) au
  lieu de laisser la contrainte CHECK remonter un 400 technique — résolu.

## Lots précédents

- **§24 (RC auto)** : RC corrigée côté backend (mode `bareme_puissance`), voir
  `QUESTIONS_ENCADRANT.md` — **écart §24 du frontend résolu.**
- **§23 (`GET /auth/me`)** : endpoint **déjà ajouté** (profil du connecté, testé dans la recette) —
  résolu côté backend, à reprendre côté frontend si l'ECARTS le liste encore « en attente ».
- **§22 (`DashboardRead`)** : en attente, non urgent (seul écart encore ouvert).
