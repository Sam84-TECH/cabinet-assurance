# Projet — Application de gestion cabinet agent d'assurance (Sanlam Maroc)

## Contexte
Remplacement de DIAM (ancien ERP d'assurance) par une application moderne pour une
agence Sanlam au Maroc. Projet de stage. Deux documents de référence :
- `CDCF_Application_gestion_cabinet_agent_assurance_v1.docx` (cahier des charges, exigences RF-*)
- `description_DIAM_Sanlam_Complet.docx` (analyse de l'existant + modules attendus)

## Périmètre de la phase actuelle — À RESPECTER STRICTEMENT
**Inclus :** branche **Automobile uniquement**, processus de souscription complet
de bout en bout : SOUS → POL (quittance) → ENC (encaissement) → BANQ (versement
bancaire) → REV (reversement compagnie) → RECOUV (recouvrement).

**Exclus de cette phase :** module SIN (sinistres), import OCR, autres branches
(AT, voyage, multirisque…). Ne pas créer de code pour ces modules. Le modèle de
données doit toutefois rester générique (paramétrage produit) pour les accueillir
plus tard sans refonte.

## Stack
- Python / FastAPI, SQLAlchemy 2.0 (style `Mapped[]` / `mapped_column`)
- PostgreSQL, ENUMs natifs Postgres, JSONB pour les attributs paramétrables
- Alembic pour les migrations
- Auth : JWT maison (python-jose + passlib/bcrypt), pas de Keycloak
- Pas de frontend pour l'instant — le backend doit être auto-suffisant et testable via `/docs`

## Environnement de développement
PostgreSQL tourne dans **Docker** (conteneur `cabinet-db`), l'application FastAPI est
lancée localement.

**Environnement Python :** le projet utilise un venv situé dans `venv/` à la racine, sur
Windows. Activer le venv avant toute commande Python, ou utiliser directement
`venv\Scripts\python.exe`.

```powershell
# activer le venv (PowerShell)
.\venv\Scripts\Activate.ps1
```

```bash
# lancer le serveur
uvicorn app.main:app --reload

# accéder à la base
docker exec -it cabinet-db psql -U postgres -d cabinet

# appliquer les migrations
alembic upgrade head
```

Connexion : `postgresql+psycopg://postgres:postgres@localhost:5433/cabinet` (voir `.env`).
Documentation interactive de l'API : http://localhost:8000/docs

**Manque important :** il n'existe pas de `docker-compose.yml`. Le conteneur a été créé
à la main, rien ne permet de reconstruire l'environnement sur une autre machine. À créer
en priorité (service postgres, port 5433, volume persistant pour les données).

## Conventions du projet
- **Tout est en français** : noms de tables, colonnes, variables, fonctions, endpoints, docstrings, commentaires.
- Un router par module métier dans `app/routers/`, préfixe + tag FastAPI.
- Un schéma Pydantic `XxxCreate` (entrée) et `XxxRead` (sortie, avec `id`) par entité, dans `app/schemas.py`.
- Les opérations génériques passent par `app/crud.py` (`create`, `get_or_404`, `list_all`, `update`, `delete`).
- Les numéros métier (police, quittance, bordereaux) sont générés **côté serveur** dans `app/numerotation.py`, jamais fournis par le client.
- L'auteur d'une action est déduit du jeton JWT (`user.id`), jamais envoyé dans le payload.
- Les actions sensibles (validation de versement, validation de reversement) sont réservées au rôle `super_administrateur` via `Depends(exiger_role("super_administrateur"))`.
- Chaque endpoint référence dans sa docstring l'exigence du CDCF qu'il implémente (ex. `RF-BANQ-02`).

## Règles métier clés
1. Une police passe automatiquement de `en_attente_effet` à `en_vigueur` quand sa date d'effet arrive (`app/sync.py`).
2. Un avenant est créé en `brouillon` et doit être **validé** pour prendre effet.
3. La quittance doit être **générée automatiquement** à la validation de l'avenant (RF-SOUS-07) — actuellement saisie manuellement, à corriger.
4. `prime_ttc = prime_nette + taxes + timbres + accessoires` (la commission est la part de l'agence, elle ne s'ajoute pas au TTC client).
5. Un encaissement n'est définitivement traité que lorsqu'il est rapproché avec un mouvement bancaire, c'est-à-dire inclus dans un bordereau de versement validé (RF-BANQ-02).
6. Un virement ne transite pas par un bordereau de versement physique.
7. Un bordereau (versement ou reversement) **validé n'est plus modifiable** — toute correction passe par un bordereau rectificatif tracé.
8. La commission de reversement suit le barème : priorité au barème compagnie+produit, sinon barème général de la compagnie (produit_id NULL).
9. Règle terrain de l'agence : le bordereau de reversement peut être généré **même si le chèque client n'est pas encore encaissé**.
10. Toute création / modification / suppression significative doit être historisée dans `journal_audit` (auteur, date, ancienne et nouvelle valeur).
11. **Paramétrage figé → seed ; paramétrage mouvant → CRUD.** Compagnie, banques et
    produit Auto sont créés par le seed (pas d'endpoint de création). Garanties, barèmes de
    commission et pièces justificatives ont un CRUD, parce que l'agence doit pouvoir les
    modifier sans développeur.
12. **Une police ne se supprime jamais** : elle se **résilie par un avenant** (type
    `resiliation`), qui trace l'auteur et la date. L'absence d'endpoint `DELETE` sur
    `/sous/polices` est **délibérée**, ce n'est pas un oubli. La même règle vaut pour
    les autres entités comptables — **avenant, quittance, encaissement, bordereaux de
    versement et de reversement** : aucune n'expose de `DELETE`. Une écriture comptable
    se corrige ou s'annule par un changement de statut ou un document rectificatif tracé
    (cf. règle 7), jamais par suppression physique. Les entités *non* comptables peuvent,
    elles, garder un `DELETE` : paramétrage mouvant (garantie, barème, pièce justificative,
    cf. règle 11) et éléments de composition d'une police (risque, police_garantie).
13. La suppression d'un **risque** ou d'une **police_garantie** est refusée dès qu'un
    avenant est **validé** sur la police concernée : passé ce point, retirer un véhicule
    ou une garantie passe par un avenant (message d'erreur explicite l'indiquant). Tant
    qu'aucun avenant n'est validé, la suppression reste possible (composition en cours).
14. La suppression d'un **client** est refusée s'il est **référencé ailleurs** — police,
    encaissement, ou lien familial (cas particulier de la règle 15).
15. **Aucune suppression ne doit provoquer une erreur 500** par violation de contrainte
    d'intégrité. Toute entité référencée ailleurs est vérifiée **avant** suppression —
    contrôle générique des clés étrangères entrantes dans `crud.delete` — et un `DELETE`
    bloqué renvoie un **409** nommant ce qui référence l'entité, jamais un traceback SQL.

## État actuel — travail restant, par ordre de priorité

### 1. Débloquer le socle (rien ne fonctionne de bout en bout sans ça)
- [ ] Router `risque.py` — CRUD des véhicules rattachés à une police (le schéma `RisqueCreate` existe déjà, l'endpoint non)
- [ ] Router `police_garantie.py` — rattacher garanties + prime à une police/risque
- [ ] CRUD `BaremeCommission` — sans lui, `rev.py` renvoie systématiquement 400
- [ ] `PieceJustificativeRequise` : CRUD léger. Pour la **Compagnie**, pas de CRUD : le cabinet est agent général d'une seule compagnie (Sanlam), elle est créée par le seed. Un simple PATCH suffit pour modifier ses coordonnées. **La table `compagnie` et tous les `compagnie_id` restent en place** — le barème de commission et le bordereau de reversement s'appuient dessus, et le modèle doit rester multi-compagnie.
- [ ] Script de seed : Sanlam Maroc, produit Auto, ses garanties, un barème, les 2 banques de l'agence
- [ ] `docker-compose.yml` pour reconstruire l'environnement (postgres, port 5433, volume persistant)

### 2. Corriger les bugs existants
- [ ] Le filtrage se fait en Python **après** `limit=100` dans `list_polices`, `list_avenants`, `list_quittances`, `list_encaissements`, `list_bordereaux`, `list_dossiers` → passer en `WHERE` SQL
- [ ] `numerotation.py` utilise `count() + 1` → collision après suppression et en concurrence. Remplacer par une séquence Postgres
- [ ] `affecter_a_quittance` : ajouter les garde-fous (ne pas dépasser le montant de l'encaissement ni le TTC de la quittance, refuser une quittance annulée), passer `montant_affecte` dans le body
- [ ] `crud.update` ignore les valeurs `None` → impossible de vider un champ
- [ ] `journal_audit` n'est jamais alimenté → brancher un event listener SQLAlchemy
- [ ] Le statut de la police ne change pas à la validation d'un avenant de résiliation ou suspension
- [ ] `@app.on_event` déprécié → passer au `lifespan` FastAPI
- [ ] CORS en `*` → restreindre
- [ ] **Validation des clés étrangères** : envoyer un `produit_id` ou `client_id` inexistant provoque une erreur 500 avec un traceback SQL brut. Doit renvoyer un 404 ou 422 explicite (« Produit 1 introuvable »). C'est une validation **serveur** — une liste déroulante côté frontend ne remplace pas ce contrôle, puisque `/docs` reste accessible directement.

### 3. Compléter le workflow
- [ ] Génération automatique de la quittance à la validation de l'avenant
- [ ] Endpoint de renouvellement en un geste (avenant + décalage de période + quittance)
- [ ] Recherche multicritère `GET /recherche?q=` (nom, CIN, ICE, n° police, immatriculation, n° quittance)
- [ ] Solde client / vue 360 (encaissé vs restant dû)
- [ ] Reçu d'encaissement, rejet de chèque (statut `rejete` défini mais jamais utilisé)
- [ ] Reversement : sélection automatique des quittances de la période, bordereau rectificatif
- [ ] Recouvrement : balance âgée 0-30 / 30-60 / 60-90 / 90+ jours, bascule automatique en recouvrement au dépassement du délai
- [ ] Router `LienFamilial` (gestion familiale)

### 4. Éditions et livraison
- [ ] Génération PDF : quittance, police, attestation, bordereau de versement, bordereau de reversement
- [ ] Exports Excel des rapports
- [ ] Scénario de recette bout en bout (voir ci-dessous)
- [ ] Tests pytest, Dockerfile + docker-compose, README
- [ ] `.gitignore` (au minimum `venv/`, `.env`, `__pycache__/`)

## Scénario de recette de référence
Le backend est considéré terminé pour cette phase quand ce scénario passe au vert
sans intervention manuelle :

```
créer un client entreprise
  → créer une police (produit Auto)
  → ajouter un véhicule (risque)
  → ajouter les garanties avec leurs primes
  → créer l'avenant « affaire nouvelle » puis le valider
  → vérifier que la quittance a été générée automatiquement
  → enregistrer un encaissement par chèque et l'affecter à la quittance
  → vérifier que la quittance passe en « réglée »
  → créer un bordereau de versement, y ajouter l'encaissement, le valider (super admin)
  → vérifier que l'encaissement passe en « rapproché banque »
  → créer un bordereau de reversement, y ajouter la quittance, le valider
  → vérifier le calcul de la commission selon le barème
  → appeler /dashboard et /reporting/* et vérifier la cohérence des chiffres
```

## Phase suivante — direction visuelle du frontend (pour mémoire, ne pas coder maintenant)
Décisions déjà arrêtées, à respecter le moment venu :
- Couleur principale : bleu marine `#12253E`
- Typographie : **Playfair Display** (serif) réservée au nom du client sur sa fiche, aux
  montants mis en évidence et aux titres de section importants — jamais sur les boutons,
  menus ou champs de formulaire. **Inter** (sans-serif) pour tout le reste de l'interface.
  **Fira Code** (monospace) pour les numéros de police / quittance / bordereau, les
  montants en tableau et les dates numériques.
- Icônes linéaires (non remplies)
- Interface dense plutôt qu'aérée : outil professionnel utilisé toute la journée, l'utilisateur
  doit voir le maximum sans naviguer
- Principe directeur repris du CDCF : navigation par processus métier, assistant étape par
  étape (wizard), à l'opposé des menus multiples de DIAM

## Ce qu'il ne faut pas faire
- Ne pas coder de spécificités « automobile » en dur : les particularités produit
  passent par le paramétrage (`Garantie.parametres` en JSONB, `Risque.attributs` en JSONB).
- Ne pas ajouter de dépendance lourde sans raison — l'app doit tourner en agence sur un serveur modeste.
- Ne pas mettre de règle métier uniquement côté client : le Swagger `/docs` est accessible, toute règle non appliquée côté serveur est contournable.
- Ne pas renommer les tables ou colonnes existantes sans migration Alembic.
