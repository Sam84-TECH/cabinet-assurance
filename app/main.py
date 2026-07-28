"""
Point d'entrée de l'API — assemble tous les modules (routers).
Lancement en dev : uvicorn app.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import referentiel, client, sous, risque, police_garantie, piece_fournie, quittance, encaissement, banq, rev, recouv, dashboard, reporting, audit, auth as auth_router
from .scheduler import demarrer_scheduler, arreter_scheduler
from .audit import configurer_audit

# Active l'historisation automatique (journal d'audit) sur tous les mappers.
configurer_audit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : lance le planificateur (synchronisation périodique des statuts).
    demarrer_scheduler()
    yield
    # Arrêt : coupe proprement le planificateur.
    arreter_scheduler()


app = FastAPI(
    title="Cabinet Assurance — API",
    description="Souscription auto, quittance, encaissement, versement, reversement, recouvrement",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS : origines autorisées via CORS_ORIGINS (liste séparée par des virgules), par défaut
# les ports de dev locaux du frontend React. Ne jamais laisser "*" en production.
origines_cors = [
    origine.strip()
    for origine in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if origine.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origines_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(referentiel.router)
app.include_router(client.router)
app.include_router(sous.router)
app.include_router(risque.router)
app.include_router(police_garantie.router)
app.include_router(piece_fournie.router)
app.include_router(quittance.router)
app.include_router(encaissement.router)
app.include_router(banq.router)
app.include_router(rev.router)
app.include_router(recouv.router)
app.include_router(dashboard.router)
app.include_router(reporting.router)
app.include_router(audit.router)


@app.get("/", tags=["Santé"])
def racine():
    return {"statut": "API opérationnelle"}
