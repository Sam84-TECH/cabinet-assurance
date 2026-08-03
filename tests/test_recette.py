# -*- coding: utf-8 -*-
"""
Recette bout en bout du workflow métier décrit dans CLAUDE.md :
SOUS -> POL (quittance) -> ENC -> BANQ -> REV, puis contrôle du tableau de bord.

Un seul test déroule tout le scénario, via l'API HTTP réelle, sur la base de test isolée
(voir conftest.py). C'est le « cahier de recette » exigé au §9 du CDCF : quand il passe au
vert sans intervention manuelle, le backend est considéré terminé pour le périmètre auto.
"""

import datetime
from decimal import Decimal

AUJ = datetime.date.today()
DANS_UN_AN = AUJ + datetime.timedelta(days=365)


def dec(valeur):
    """Normalise une valeur JSON (nombre ou chaîne) en Decimal pour des comparaisons exactes."""
    return Decimal(str(valeur))


def test_recette_bout_en_bout(client, auth, refs):
    # 1. Client entreprise
    reponse = client.post("/clients", headers=auth, json={
        "type": "entreprise", "raison_sociale": "Recette Auto SARL", "ice": "RECETTE0001",
        "telephone": "0522000000", "ville": "Casablanca",
    })
    assert reponse.status_code == 200, reponse.text
    client_id = reponse.json()["id"]

    # 2. Police auto (produit paramétré par le seed)
    reponse = client.post("/sous/polices", headers=auth, json={
        "client_id": client_id, "produit_id": refs["produit_id"],
        "date_effet": AUJ.isoformat(), "date_echeance": DANS_UN_AN.isoformat(),
    })
    assert reponse.status_code == 200, reponse.text
    police = reponse.json()
    police_id = police["id"]
    assert police["numero_police"].startswith("POL-")

    # 3. Véhicule (risque) rattaché à la police
    reponse = client.post("/risques", headers=auth, json={
        "police_id": police_id, "type_risque": "vehicule",
        "attributs": {
            "immatriculation": "12345-A-6", "marque": "Dacia", "modele": "Logan",
            "date_mise_en_circulation": "03/2021", "valeur_neuf": "150000.00",
        },
    })
    assert reponse.status_code == 200, reponse.text
    risque_id = reponse.json()["id"]

    # 4. Garanties avec leurs primes : RC 800 + DC 200 = 1000 de prime nette
    for code, prime in (("RC", "800.00"), ("DC", "200.00")):
        reponse = client.post("/police-garanties", headers=auth, json={
            "police_id": police_id, "risque_id": risque_id,
            "garantie_id": refs["garanties"][code], "montant_prime": prime,
        })
        assert reponse.status_code == 200, reponse.text

    # 5. Avenant « affaire nouvelle »
    reponse = client.post("/sous/avenants", headers=auth, json={
        "police_id": police_id, "type_avenant": "affaire_nouvelle", "date_effet": AUJ.isoformat(),
    })
    assert reponse.status_code == 200, reponse.text
    avenant_id = reponse.json()["id"]

    # 5b. RF-SOUS-04 : l'émission est bloquée tant que les pièces obligatoires manquent
    reponse = client.patch(f"/sous/avenants/{avenant_id}/valider", headers=auth)
    assert reponse.status_code == 400, reponse.text
    assert "pi" in reponse.json()["detail"].lower()  # « pièces … manquantes »

    # 6. Fourniture des pièces justificatives obligatoires
    for piece_id in refs["pieces_oblig"]:
        reponse = client.post("/pieces-fournies", headers=auth, json={
            "police_id": police_id, "piece_requise_id": piece_id, "reference": "fournie",
        })
        assert reponse.status_code == 200, reponse.text

    # 7. Validation de l'avenant -> quittance générée automatiquement (RF-SOUS-07)
    reponse = client.patch(f"/sous/avenants/{avenant_id}/valider", headers=auth)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["statut"] == "valide"

    # 8. Quittance auto : prime_ttc = prime_nette + taxes + timbres + accessoires (règle n°4)
    reponse = client.get("/quittances", headers=auth, params={"police_id": police_id})
    assert reponse.status_code == 200, reponse.text
    quittances = reponse.json()
    assert len(quittances) == 1, quittances
    quittance = quittances[0]
    quittance_id = quittance["id"]
    assert dec(quittance["prime_nette"]) == Decimal("1000.00")
    assert dec(quittance["taxes"]) == Decimal("140.00")  # 14 % de la prime nette (défaut)
    assert dec(quittance["prime_ttc"]) == (
        dec(quittance["prime_nette"]) + dec(quittance["taxes"])
        + dec(quittance["timbres"]) + dec(quittance["accessoires"])
    )
    assert dec(quittance["prime_ttc"]) == Decimal("1140.00")
    assert dec(quittance["commission"]) == Decimal("100.00")  # 10 % (barème Sanlam/Auto)
    assert quittance["statut"] == "emise"

    # 9. Encaissement par chèque du montant TTC
    reponse = client.post("/encaissements", headers=auth, json={
        "client_id": client_id, "mode_paiement": "cheque", "montant": "1140.00",
        "date_encaissement": AUJ.isoformat(),
        "cheque_banque": "Attijariwafa Bank", "cheque_numero": "REC-0001",
    })
    assert reponse.status_code == 200, reponse.text
    encaissement_id = reponse.json()["id"]

    # 10. Affectation de l'encaissement à la quittance
    reponse = client.post(f"/encaissements/{encaissement_id}/affecter/{quittance_id}",
                          headers=auth, json={"montant_affecte": "1140.00"})
    assert reponse.status_code == 200, reponse.text

    # 11. La quittance passe en « réglée »
    reponse = client.get(f"/quittances/{quittance_id}", headers=auth)
    assert reponse.json()["statut"] == "reglee", reponse.json()

    # 12. Bordereau de versement, ajout de l'encaissement, validation (super admin)
    reponse = client.post("/banq/bordereaux", headers=auth, json={
        "banque_agence_id": refs["banque_id"], "date_bordereau": AUJ.isoformat(),
    })
    assert reponse.status_code == 200, reponse.text
    bordereau_versement_id = reponse.json()["id"]
    reponse = client.post(f"/banq/bordereaux/{bordereau_versement_id}/ajouter/{encaissement_id}", headers=auth)
    assert reponse.status_code == 200, reponse.text
    reponse = client.patch(f"/banq/bordereaux/{bordereau_versement_id}/valider", headers=auth)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["statut"] == "verse"

    # 13. L'encaissement passe en « rapproché banque » (RF-BANQ-02)
    reponse = client.get(f"/encaissements/{encaissement_id}", headers=auth)
    assert reponse.json()["statut"] == "rapproche_banque", reponse.json()

    # 14. Bordereau de reversement : sélection automatique de la période, puis validation
    reponse = client.post("/rev/bordereaux", headers=auth, json={
        "compagnie_id": refs["compagnie_id"],
        "periode_debut": (AUJ - datetime.timedelta(days=1)).isoformat(),
        "periode_fin": (AUJ + datetime.timedelta(days=1)).isoformat(),
    })
    assert reponse.status_code == 200, reponse.text
    bordereau_reversement_id = reponse.json()["id"]

    reponse = client.post(f"/rev/bordereaux/{bordereau_reversement_id}/selectionner-periode", headers=auth)
    assert reponse.status_code == 200, reponse.text
    lignes = reponse.json()
    assert any(ligne["quittance_id"] == quittance_id for ligne in lignes), lignes

    reponse = client.patch(f"/rev/bordereaux/{bordereau_reversement_id}/valider", headers=auth)
    assert reponse.status_code == 200, reponse.text
    bordereau_reversement = reponse.json()

    # 15. Commission calculée selon le barème : 10 % de 1000 = 100 ; prime nette reversée = 1000
    assert dec(bordereau_reversement["commission_totale"]) == Decimal("100.00"), bordereau_reversement
    assert dec(bordereau_reversement["montant_total"]) == Decimal("1000.00"), bordereau_reversement

    # 16. Tableau de bord cohérent (base isolée : seules nos données existent)
    reponse = client.get("/dashboard", headers=auth)
    assert reponse.status_code == 200, reponse.text
    tableau = reponse.json()
    assert tableau["nombre_clients"] == 1, tableau
    assert tableau["contrats_actifs"] == 1, tableau               # police en vigueur (effet = aujourd'hui)
    assert tableau["paiements_en_attente"] == 0, tableau          # la seule quittance est réglée
    assert tableau["cheques_non_encaisses"] == 0, tableau         # le chèque est rapproché banque
    assert tableau["dossiers_recouvrement_ouverts"] == 0, tableau

    # 17. Éditions PDF (RF-POL-04) : génération côté serveur + archivage horodaté
    documents = [
        ("quittances", quittance_id),
        ("attestations", police_id),
        ("polices", police_id),
        ("bordereaux-versement", bordereau_versement_id),
        ("bordereaux-reversement", bordereau_reversement_id),
    ]
    for chemin, entite_id in documents:
        reponse = client.get(f"/documents/{chemin}/{entite_id}", headers=auth)
        assert reponse.status_code == 200, (chemin, reponse.text)
        assert reponse.headers["content-type"] == "application/pdf", (chemin, reponse.headers)
        assert reponse.content[:5] == b"%PDF-", chemin  # en-tête d'un PDF valide

    # Les 5 générations ont laissé une trace d'archive horodatée, re-téléchargeable
    reponse = client.get("/documents/archives", headers=auth)
    assert reponse.status_code == 200, reponse.text
    archives = reponse.json()
    assert len(archives) == 5, archives
    reponse = client.get(f"/documents/archives/{archives[0]['id']}/telecharger", headers=auth)
    assert reponse.status_code == 200 and reponse.content[:5] == b"%PDF-", reponse.status_code
