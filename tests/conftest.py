# -*- coding: utf-8 -*-
"""
Fixtures de la recette — base PostgreSQL de test ISOLÉE (jamais la base de dev).

On redirige DATABASE_URL vers une base dédiée (cabinet_test) AVANT tout import applicatif,
car app.database lit DATABASE_URL au moment de son import. La base est recréée à neuf à chaque
session, migrée via Alembic (schéma strictement identique à la prod, séquences et contraintes
uniques comprises), puis peuplée du paramétrage de référence (seed) et d'un super administrateur.

Prérequis : le serveur PostgreSQL de dev doit tourner (conteneur cabinet-db, port 5433). La
base « cabinet » de dev n'est jamais touchée — on travaille sur « cabinet_test ».
"""

import os
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# --- Redirection vers la base de test, AVANT tout import de l'application ---
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/cabinet_test",
)
os.environ["DATABASE_URL"] = TEST_DB_URL

# Répertoire d'archives PDF isolé (hors projet) : la recette ne pollue pas le dossier de dev.
os.environ["ARCHIVES_DIR"] = os.path.join(tempfile.gettempdir(), "cabinet_test_archives")

# Fiscalité figée pour que la recette soit DÉTERMINISTE quel que soit le .env du poste :
# facturation.py lit ces variables à l'import, et la recette assère des montants exacts
# (taxes 14 % -> 140, TTC 1140). On force donc les valeurs de référence ici.
os.environ["TAUX_TAXE_ASSURANCE"] = "14.00"
os.environ["DROIT_TIMBRE"] = "0.00"

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

EMAIL_ADMIN = "admin@recette.test"
MDP_ADMIN = "recette-admin-2026"


def _recreer_base_test():
    """Supprime puis recrée la base de test : schéma et données vierges à chaque session."""
    url = make_url(TEST_DB_URL)
    nom = url.database
    # Garde-fou : on ne DROP JAMAIS qu'une base dont le nom se termine par « _test ».
    # Protège contre un TEST_DATABASE_URL mal réglé qui pointerait sur la base de dev.
    assert nom and nom.endswith("_test"), (
        f"Base de test refusée : « {nom} » ne se termine pas par « _test ». "
        "Refus de DROP pour ne jamais détruire une base non dédiée aux tests."
    )
    maintenance = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{nom}"'))
    maintenance.dispose()


def _migrer():
    """Applique toutes les migrations Alembic sur la base de test (env.py lit DATABASE_URL)."""
    from alembic.config import Config
    from alembic import command

    cfg = Config(str(RACINE / "alembic.ini"))
    cfg.set_main_option("script_location", str(RACINE / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def app_recette():
    """Base de test recréée + migrée + peuplée ; renvoie l'app FastAPI prête à l'emploi."""
    _recreer_base_test()
    _migrer()

    from app.database import SessionLocal
    from app import models
    from app.auth import hacher_mot_de_passe
    from seed import seed as seed_reference

    db = SessionLocal()
    try:
        seed_reference(db)  # compagnie, banques, produit Auto, garanties, barème, pièces
        db.add(models.Utilisateur(
            nom="Admin", prenom="Recette", email=EMAIL_ADMIN,
            mot_de_passe_hash=hacher_mot_de_passe(MDP_ADMIN),
            role=models.RoleUtilisateur.super_administrateur, actif=True,
        ))
        db.commit()
    finally:
        db.close()

    # Import APRÈS le seed : configure_audit() s'active ici ; le scénario sera donc audité.
    from app.main import app
    return app


@pytest.fixture(scope="session")
def client(app_recette):
    """TestClient SANS gestionnaire de contexte : on n'exécute pas le lifespan, donc le
    planificateur (scheduler) ne démarre pas pendant les tests."""
    from fastapi.testclient import TestClient
    return TestClient(app_recette)


@pytest.fixture(scope="session")
def auth(client):
    """En-tête d'autorisation d'un super administrateur (login réel via l'API)."""
    reponse = client.post("/auth/login", data={"username": EMAIL_ADMIN, "password": MDP_ADMIN})
    assert reponse.status_code == 200, reponse.text
    return {"Authorization": f"Bearer {reponse.json()['access_token']}"}


@pytest.fixture(scope="session")
def refs(app_recette):
    """Identifiants du paramétrage de référence (produit Auto, garanties, banque, pièces
    obligatoires, compagnie) — lus en base, ils viennent du seed."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        produit = db.query(models.Produit).filter_by(code="AUTO").one()
        garanties = {g.code: g.id for g in db.query(models.Garantie).filter_by(produit_id=produit.id)}
        banque = db.query(models.BanqueAgence).first()
        pieces_oblig = [
            p.id for p in db.query(models.PieceJustificativeRequise).filter_by(
                produit_id=produit.id, obligatoire=True)
        ]
        return {
            "produit_id": produit.id,
            "compagnie_id": produit.compagnie_id,
            "garanties": garanties,
            "banque_id": banque.id,
            "pieces_oblig": pieces_oblig,
        }
    finally:
        db.close()
