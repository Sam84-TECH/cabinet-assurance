"""
Point d'entrée de l'API — assemble tous les modules (routers).
Lancement en dev : uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import referentiel, client, sous, risque, police_garantie, quittance, encaissement, banq, rev, recouv, dashboard, reporting, auth as auth_router
from .scheduler import demarrer_scheduler, arreter_scheduler

app = FastAPI(
    title="Cabinet Assurance — API",
    description="Souscription auto, quittance, encaissement, versement, reversement, recouvrement",
    version="0.1.0",
)


@app.on_event("startup")
def au_demarrage():
    demarrer_scheduler()


@app.on_event("shutdown")
def a_larret():
    arreter_scheduler()

# Autorise le frontend React (dev, sur un autre port) à appeler cette API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # à restreindre à l'URL réelle du frontend en production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(referentiel.router)
app.include_router(client.router)
app.include_router(sous.router)
app.include_router(risque.router)
app.include_router(police_garantie.router)
app.include_router(quittance.router)
app.include_router(encaissement.router)
app.include_router(banq.router)
app.include_router(rev.router)
app.include_router(recouv.router)
app.include_router(dashboard.router)
app.include_router(reporting.router)


@app.get("/", tags=["Santé"])
def racine():
    return {"statut": "API opérationnelle"}
