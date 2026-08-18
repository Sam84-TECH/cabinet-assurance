# -*- coding: utf-8 -*-
"""
Recette du module Recouvrement étendu (RF-RECOUV-02 à 05) :
  - progression d'un dossier à travers les étapes de relance jusqu'à la suspension automatique
    du contrat, avec vérification de l'historique tracé et des relances générées ;
  - progression automatique planifiée après dépassement du délai d'étape ;
  - échéancier de paiement négocié (création + mise à jour d'un versement).

S'exécute APRÈS la recette (nom `test_reco...` > `test_rece...`) : crée des données globales,
ne doit pas précéder la recette qui asserte des compteurs absolus (cf. mémoire « ordre des tests »).
"""

import datetime

AUJ = datetime.date.today()
DANS_UN_AN = AUJ + datetime.timedelta(days=365)


def _contrat_impaye(client, auth, refs, ice):
    """Crée un contrat auto complet, avenant d'affaire nouvelle validé -> quittance IMPAYÉE
    (non réglée). Renvoie (client_id, police_id, quittance_id)."""
    client_id = client.post("/clients", headers=auth, json={
        "type": "entreprise", "raison_sociale": "Recouv Test SARL", "ice": ice,
    }).json()["id"]
    police_id = client.post("/sous/polices", headers=auth, json={
        "client_id": client_id, "produit_id": refs["produit_id"],
        "date_effet": AUJ.isoformat(), "date_echeance": DANS_UN_AN.isoformat(),
    }).json()["id"]
    risque_id = client.post("/risques", headers=auth, json={
        "police_id": police_id, "type_risque": "vehicule",
        "attributs": {
            "immatriculation": "REC-001", "marque": "Dacia", "modele": "Logan",
            "date_mise_en_circulation": "01/2021", "valeur_neuf": "150000.00", "puissance_fiscale": 8,
        },
    }).json()["id"]
    for code, prime in (("RC", "800.00"), ("DC", "200.00")):
        r = client.post("/police-garanties", headers=auth, json={
            "police_id": police_id, "risque_id": risque_id,
            "garantie_id": refs["garanties"][code], "montant_prime": prime,
        })
        assert r.status_code == 200, r.text
    avenant_id = client.post("/sous/avenants", headers=auth, json={
        "police_id": police_id, "type_avenant": "affaire_nouvelle", "date_effet": AUJ.isoformat(),
    }).json()["id"]
    for piece_id in refs["pieces_oblig"]:
        client.post("/pieces-fournies", headers=auth, json={
            "police_id": police_id, "piece_requise_id": piece_id, "reference": "fournie",
        })
    r = client.patch(f"/sous/avenants/{avenant_id}/valider", headers=auth)
    assert r.status_code == 200, r.text
    quittance_id = r.json()["quittance"]["id"]
    return client_id, police_id, quittance_id


def test_progression_dossier_jusqu_a_suspension_et_historique(client, auth, refs):
    _, police_id, quittance_id = _contrat_impaye(client, auth, refs, ice="RECOUV00001")

    # Ouverture d'un dossier (quittance impayée)
    r = client.post("/recouv/dossiers", headers=auth, json={"quittance_id": quittance_id})
    assert r.status_code == 200, r.text
    dossier = r.json()
    dossier_id = dossier["id"]
    assert dossier["statut"] == "ouvert"
    assert dossier["date_derniere_etape"] == AUJ.isoformat()

    # Progression manuelle étape par étape : ouvert -> en_relance -> mise_en_demeure -> suspendu
    etapes_attendues = ["en_relance", "mise_en_demeure", "suspendu"]
    for attendu in etapes_attendues:
        r = client.patch(f"/recouv/dossiers/{dossier_id}/progresser", headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["statut"] == attendu, r.json()

    # 4e progression refusée : étape terminale
    r = client.patch(f"/recouv/dossiers/{dossier_id}/progresser", headers=auth)
    assert r.status_code == 400, r.text

    # Le contrat a été suspendu automatiquement (RF-RECOUV-03), en réutilisant la logique avenant
    r = client.get(f"/sous/polices/{police_id}", headers=auth)
    assert r.json()["statut"] == "suspendu", r.json()
    avenants = client.get(f"/sous/avenants?police_id={police_id}", headers=auth).json()
    assert any(a["type_avenant"] == "suspension" and a["statut"] == "valide" for a in avenants), avenants

    # Deux relances générées (amiable puis mise en demeure)
    relances = client.get(f"/recouv/dossiers/{dossier_id}/relances", headers=auth).json()
    types = sorted(rl["type_relance"] for rl in relances)
    assert types == ["amiable", "mise_en_demeure"], relances

    # Historique tracé (RF-RECOUV-05) : progressions + relances + suspension auto, consultable
    detail = client.get(f"/recouv/dossiers/{dossier_id}", headers=auth).json()
    types_evt = [e["type_evenement"] for e in detail["evenements"]]
    assert types_evt.count("progression") == 3, types_evt
    assert types_evt.count("relance") == 2, types_evt
    assert "suspension_auto" in types_evt, types_evt
    # L'historique est aussi accessible via son endpoint dédié
    histo = client.get(f"/recouv/dossiers/{dossier_id}/historique", headers=auth).json()
    assert len(histo) == len(detail["evenements"]) >= 6


def test_progression_automatique_apres_delai(client, auth, refs):
    """RF-RECOUV-02 : la tâche planifiée fait progresser un dossier dont l'étape courante dépasse
    le délai. On simule l'ancienneté en reculant date_derniere_etape en base, puis on appelle la
    fonction planifiée."""
    from app.database import SessionLocal
    from app import models
    from app.recouvrement import progresser_dossiers_echus, DELAI_ENTRE_ETAPES_JOURS

    _, _, quittance_id = _contrat_impaye(client, auth, refs, ice="RECOUV00002")
    dossier_id = client.post("/recouv/dossiers", headers=auth,
                             json={"quittance_id": quittance_id}).json()["id"]

    # Recule l'entrée dans l'étape au-delà du délai
    db = SessionLocal()
    try:
        dossier = db.get(models.DossierRecouvrement, dossier_id)
        dossier.date_derniere_etape = AUJ - datetime.timedelta(days=DELAI_ENTRE_ETAPES_JOURS + 1)
        db.commit()
        transitions = progresser_dossiers_echus(db)
        assert any(t["dossier_id"] == dossier_id and t["vers"] == "en_relance" for t in transitions), transitions
        db.refresh(dossier)
        assert dossier.statut == models.StatutDossierRecouv.en_relance
    finally:
        db.close()


def test_echeancier_negocie(client, auth, refs):
    """RF-RECOUV-04 : échéancier de paiement négocié (versements générés, statut modifiable)."""
    _, _, quittance_id = _contrat_impaye(client, auth, refs, ice="RECOUV00003")
    dossier_id = client.post("/recouv/dossiers", headers=auth,
                             json={"quittance_id": quittance_id}).json()["id"]

    r = client.post(f"/recouv/dossiers/{dossier_id}/echeancier", headers=auth, json={
        "montant_total": "1140.00", "nombre_versements": 3,
        "date_premier_versement": AUJ.isoformat(), "intervalle_jours": 30,
    })
    assert r.status_code == 200, r.text
    echeancier = r.json()
    assert echeancier["nombre_versements"] == 3
    versements = echeancier["versements"]
    assert len(versements) == 3
    from decimal import Decimal
    assert sum(Decimal(v["montant"]) for v in versements) == Decimal("1140.00")  # somme = total
    assert all(v["statut"] == "prevu" for v in versements)

    # Un 2e échéancier sur le même dossier est refusé (409)
    r = client.post(f"/recouv/dossiers/{dossier_id}/echeancier", headers=auth, json={
        "montant_total": "500.00", "nombre_versements": 2,
        "date_premier_versement": AUJ.isoformat(),
    })
    assert r.status_code == 409, r.text

    # Marquer un versement comme réglé -> tracé dans l'historique
    versement_id = versements[0]["id"]
    r = client.patch(f"/recouv/versements/{versement_id}", headers=auth, json={"statut": "regle"})
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "regle"

    detail = client.get(f"/recouv/dossiers/{dossier_id}", headers=auth).json()
    assert detail["echeancier"] is not None
    assert any(e["type_evenement"] == "versement" for e in detail["evenements"]), detail["evenements"]


def test_echeancier_respecte_gele_escalade(client, auth, refs):
    """RF-RECOUV-04 : un échéancier négocié RESPECTÉ (aucun versement manqué) gèle l'escalade —
    le dossier ne progresse pas malgré le délai dépassé ; un versement manqué la relance."""
    from app.database import SessionLocal
    from app import models
    from app.recouvrement import progresser_dossiers_echus, DELAI_ENTRE_ETAPES_JOURS

    _, _, quittance_id = _contrat_impaye(client, auth, refs, ice="RECOUV00004")
    dossier_id = client.post("/recouv/dossiers", headers=auth,
                             json={"quittance_id": quittance_id}).json()["id"]
    r = client.post(f"/recouv/dossiers/{dossier_id}/echeancier", headers=auth, json={
        "montant_total": "1140.00", "nombre_versements": 3,
        "date_premier_versement": AUJ.isoformat(), "intervalle_jours": 30,
    })
    assert r.status_code == 200, r.text
    premier_versement_id = r.json()["versements"][0]["id"]

    # Recule l'horloge d'étape au-delà du délai
    db = SessionLocal()
    try:
        dossier = db.get(models.DossierRecouvrement, dossier_id)
        dossier.date_derniere_etape = AUJ - datetime.timedelta(days=DELAI_ENTRE_ETAPES_JOURS + 1)
        db.commit()
        # Échéancier respecté -> pas d'escalade
        progresser_dossiers_echus(db)
        db.refresh(dossier)
        assert dossier.statut == models.StatutDossierRecouv.ouvert, "l'échéancier respecté n'a pas gelé l'escalade"
    finally:
        db.close()

    # Un versement manqué rompt le plan -> l'escalade reprend
    client.patch(f"/recouv/versements/{premier_versement_id}", headers=auth, json={"statut": "manque"})
    db = SessionLocal()
    try:
        progresser_dossiers_echus(db)
        dossier = db.get(models.DossierRecouvrement, dossier_id)
        assert dossier.statut == models.StatutDossierRecouv.en_relance, "un versement manqué doit relancer l'escalade"
    finally:
        db.close()
