# -*- coding: utf-8 -*-
"""
Vérifie le script de données de démonstration `demo_data.py` : diversité conforme à la
demande (clients, flotte, historique, résiliés, suspendu, client parti, tranches de balance
âgée, chèque rejeté) et IDEMPOTENCE (un second passage ne duplique rien).

S'exécute en DERNIER (nom `test_zz_...`) sur la base de test partagée : il crée beaucoup de
données globales, il ne doit donc pas précéder la recette qui asserte des compteurs absolus
(cf. mémoire projet « ordre des tests »).
"""


def _compteurs(models, db):
    return (
        db.query(models.Client).count(),
        db.query(models.Police).count(),
        db.query(models.Quittance).count(),
        db.query(models.Encaissement).count(),
    )


def test_demo_data_diversite_et_idempotence(app_recette):
    import demo_data
    from app.database import SessionLocal
    from app import models
    from app.recouvrement import calculer_balance_agee

    # --- 1er passage : peuple ---
    demo_data.main()

    db = SessionLocal()
    try:
        # Au moins 5 particuliers et 2 entreprises
        nb_part = db.query(models.Client).filter_by(type=models.TypeClient.particulier).count()
        nb_ent = db.query(models.Client).filter_by(type=models.TypeClient.entreprise).count()
        assert nb_part >= 5, nb_part
        assert nb_ent >= 2, nb_ent

        polices = db.query(models.Police).all()
        par_client = {}
        for p in polices:
            par_client.setdefault(p.client_id, []).append(p)

        # Une entreprise avec >= 3 contrats ACTIFS (en vigueur) simultanés (flotte)
        flotte = [
            cid for cid, ps in par_client.items()
            if db.get(models.Client, cid).type == models.TypeClient.entreprise
            and sum(1 for p in ps if p.statut == models.StatutPolice.en_vigueur) >= 3
        ]
        assert flotte, "aucune entreprise avec >=3 polices actives (flotte)"

        # Au moins deux contrats résiliés, à des dates de résiliation différentes
        resil_avenants = db.query(models.Avenant).filter_by(
            type_avenant=models.TypeAvenant.resiliation, statut=models.StatutAvenant.valide
        ).all()
        assert len(resil_avenants) >= 2, len(resil_avenants)
        assert len({a.date_effet for a in resil_avenants}) >= 2, "résiliations à la même date"
        assert db.query(models.Police).filter_by(statut=models.StatutPolice.resilie).count() >= 2

        # Au moins un contrat suspendu
        assert db.query(models.Police).filter_by(statut=models.StatutPolice.suspendu).count() >= 1

        # Au moins un contrat à historique : >=3 avenants dont un renouvellement et une modification
        polices_historique = [
            cid_ps for cid_ps in (
                (p.id, db.query(models.Avenant).filter_by(police_id=p.id).all()) for p in polices
            )
            if len(cid_ps[1]) >= 3
            and any(a.type_avenant == models.TypeAvenant.renouvellement for a in cid_ps[1])
            and any(a.type_avenant == models.TypeAvenant.modification for a in cid_ps[1])
        ]
        assert polices_historique, "aucune police avec historique renouvellement + modification"

        # Au moins un client « parti » : a des polices, toutes résiliées (aucune active)
        parti = [
            cid for cid, ps in par_client.items()
            if ps and all(p.statut == models.StatutPolice.resilie for p in ps)
        ]
        assert parti, "aucun client dont tous les contrats sont résiliés"

        # Balance âgée : chaque tranche (0-30, 30-60, 60-90, 90+) a au moins une quittance
        bal = calculer_balance_agee(db)
        for cle in ("tranche_0_30", "tranche_30_60", "tranche_60_90", "tranche_90_plus"):
            assert bal[cle]["nombre"] >= 1, (cle, bal[cle])

        # Au moins un chèque rejeté
        assert db.query(models.Encaissement).filter_by(
            statut=models.StatutEncaissement.rejete
        ).count() >= 1

        # Paiements variés (au moins deux modes présents)
        modes = {e.mode_paiement for e in db.query(models.Encaissement).all()}
        assert len(modes) >= 2, modes

        avant = _compteurs(models, db)
    finally:
        db.close()

    # --- 2e passage : idempotent, aucun doublon ---
    demo_data.main()
    db = SessionLocal()
    try:
        apres = _compteurs(models, db)
        assert apres == avant, (avant, apres)
    finally:
        db.close()
