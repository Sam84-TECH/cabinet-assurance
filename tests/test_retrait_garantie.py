# -*- coding: utf-8 -*-
"""
Retrait de garantie sous avenant de modification (règles 13 / 17) et garde-fou RC obligatoire.

Scénario réel via l'API HTTP (même base de test isolée que la recette) :
  1. police engagée (affaire nouvelle validée) ;
  2. retrait direct refusé hors modification (composition verrouillée) ;
  3. avenant de modification en brouillon -> retrait d'une garantie OPTIONNELLE fonctionnel ;
  4. ré-ajout fonctionnel ;
  5. la garantie OBLIGATOIRE (RC) n'est jamais retirable, avec un message explicite.
"""

import datetime

AUJ = datetime.date.today()
DANS_UN_AN = AUJ + datetime.timedelta(days=365)


def _pg_id(client, auth, police_id, code_garantie, refs):
    """Retourne l'id de la ligne police_garantie correspondant au code de garantie donné."""
    pgs = client.get(f"/police-garanties?police_id={police_id}", headers=auth).json()
    cible = refs["garanties"][code_garantie]
    return next(pg["id"] for pg in pgs if pg["garantie_id"] == cible)


def test_retrait_garantie_modification_et_rc_obligatoire(client, auth, refs):
    # 1. Police engagée : client -> police -> véhicule -> RC + DC -> pièces -> affaire nouvelle validée
    client_id = client.post("/clients", headers=auth, json={
        "type": "entreprise", "raison_sociale": "Modif SARL", "ice": "MODIF00001",
    }).json()["id"]
    police_id = client.post("/sous/polices", headers=auth, json={
        "client_id": client_id, "produit_id": refs["produit_id"],
        "date_effet": AUJ.isoformat(), "date_echeance": DANS_UN_AN.isoformat(),
    }).json()["id"]
    risque_id = client.post("/risques", headers=auth, json={
        "police_id": police_id, "type_risque": "vehicule",
        "attributs": {
            "immatriculation": "99999-B-1", "marque": "Renault", "modele": "Clio",
            "date_mise_en_circulation": "05/2020", "valeur_neuf": "120000.00",
            "puissance_fiscale": 8,
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
    assert r.status_code == 200, r.text  # police engagée

    # 2. Hors modification : le retrait direct d'une garantie optionnelle est refusé (verrou 13)
    dc_id = _pg_id(client, auth, police_id, "DC", refs)
    r = client.delete(f"/police-garanties/{dc_id}", headers=auth)
    assert r.status_code == 400, r.text
    assert "avenant" in r.json()["detail"].lower()

    # 3. Avenant de modification en brouillon -> la composition se rouvre
    client.post("/sous/avenants", headers=auth, json={
        "police_id": police_id, "type_avenant": "modification", "date_effet": AUJ.isoformat(),
        "motif": "retrait de la garantie dommages collision",
    })

    # 3b. Retrait de la garantie OPTIONNELLE (DC) : fonctionne (204)
    r = client.delete(f"/police-garanties/{dc_id}", headers=auth)
    assert r.status_code == 204, r.text
    restantes = client.get(f"/police-garanties?police_id={police_id}", headers=auth).json()
    assert all(pg["garantie_id"] != refs["garanties"]["DC"] for pg in restantes), restantes

    # 4. Ré-ajout d'une garantie optionnelle : fonctionne (200)
    r = client.post("/police-garanties", headers=auth, json={
        "police_id": police_id, "risque_id": risque_id,
        "garantie_id": refs["garanties"]["DC"], "montant_prime": "200.00",
    })
    assert r.status_code == 200, r.text

    # 5. RC (obligatoire) : jamais retirable, même modification ouverte, avec message explicite
    rc_id = _pg_id(client, auth, police_id, "RC", refs)
    r = client.delete(f"/police-garanties/{rc_id}", headers=auth)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"].lower()
    assert "obligatoire" in detail, r.text
