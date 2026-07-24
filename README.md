# Cabinet Assurance — Backend

API de gestion d'un cabinet d'agent d'assurance (**Sanlam Maroc**), branche
**Automobile**. Elle couvre le processus de souscription de bout en bout :

```
SOUS → POL (quittance) → ENC (encaissement) → BANQ (versement) → REV (reversement) → RECOUV
```

**Stack :** Python / FastAPI · SQLAlchemy 2.0 · PostgreSQL · Alembic · JWT (python-jose + passlib).

## Prérequis

- Python 3.11+
- Docker (pour PostgreSQL)

## Installation & démarrage

1. **Environnement virtuel + dépendances** (Windows / PowerShell) :

   ```powershell
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Base de données PostgreSQL** (conteneur `cabinet-db`, port 5433, volume persistant) :

   ```bash
   docker compose up -d
   ```

3. **Configuration** — copier le modèle d'environnement :

   ```bash
   cp .env.example .env
   ```

4. **Migrations** — créer le schéma :

   ```bash
   alembic upgrade head
   ```

5. **Jeu de données de départ** (voir ci-dessous) :

   ```bash
   python seed.py
   ```

6. **Lancer le serveur** :

   ```bash
   uvicorn app.main:app --reload
   ```

Documentation interactive de l'API : <http://localhost:8000/docs>

## Jeu de données de départ (seed)

Le script [`seed.py`](seed.py) crée le paramétrage « figé » nécessaire pour utiliser
l'application (règle : *paramétrage figé → seed, paramétrage mouvant → CRUD*) :

- la **compagnie** Sanlam Maroc ;
- les **2 banques** de l'agence (Attijariwafa Bank, Banque Populaire) ;
- le **produit Automobile** et ses **garanties** habituelles au Maroc : RC, dommages
  collision, vol, incendie, bris de glace, personnes transportées, défense et recours ;
- un **barème de commission** pour Sanlam / Auto ;
- la liste des **pièces justificatives** exigées pour une souscription auto.

Lancement :

```bash
python seed.py
```

Le script est **idempotent** : chaque objet n'est créé que s'il n'existe pas déjà
(recherche par clé naturelle). On peut donc le relancer autant de fois que nécessaire
sans créer de doublon, et sans écraser une valeur modifiée entre-temps via les endpoints.

> Prérequis : la base doit exister et les migrations être appliquées
> (`docker compose up -d` puis `alembic upgrade head`) avant de lancer le seed.

## Commandes utiles

```bash
# Accéder à la base
docker exec -it cabinet-db psql -U postgres -d cabinet

# Réinitialiser complètement la base (SUPPRIME les données)
docker compose down -v && docker compose up -d && alembic upgrade head && python seed.py
```
