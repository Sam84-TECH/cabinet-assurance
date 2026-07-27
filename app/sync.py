"""
Synchronisation automatique du statut des polices selon la date du jour.
Appelée à chaque lecture (liste, détail, tableau de bord, reporting) pour que
le statut reflète toujours la réalité, sans tâche planifiée séparée (niveau 1
"à la demande" — suffisant tant que l'appli est consultée quotidiennement).
"""

from datetime import date
from sqlalchemy.orm import Session

from . import models


def synchroniser_statuts_polices(db: Session) -> None:
    """
    Aligne le statut des polices sur la date du jour et les avenants validés :
      - `en_attente_effet` -> `en_vigueur` dès que la date d'effet est atteinte ;
      - -> `suspendu` dès qu'un avenant de suspension validé a pris effet ;
      - -> `resilie` dès qu'un avenant de résiliation validé a pris effet (état terminal).

    Un avenant à effet futur ne s'applique qu'une fois sa date d'effet atteinte. Les trois
    passes sont ordonnées activation -> suspension -> résiliation : la résiliation, terminale,
    l'emporte sur le reste. Appelée à chaque lecture et à la validation d'un avenant.
    """
    aujourdhui = date.today()
    modifie = False

    # 1) Activation : en_attente_effet -> en_vigueur
    for police in db.query(models.Police).filter(
        models.Police.statut == models.StatutPolice.en_attente_effet,
        models.Police.date_effet <= aujourdhui,
    ).all():
        police.statut = models.StatutPolice.en_vigueur
        modifie = True

    # 2) Suspension : avenant de suspension validé et arrivé à effet, sur une police active
    for police in db.query(models.Police).join(
        models.Avenant, models.Avenant.police_id == models.Police.id
    ).filter(
        models.Police.statut.in_([models.StatutPolice.en_attente_effet, models.StatutPolice.en_vigueur]),
        models.Avenant.type_avenant == models.TypeAvenant.suspension,
        models.Avenant.statut == models.StatutAvenant.valide,
        models.Avenant.date_effet <= aujourdhui,
    ).distinct().all():
        police.statut = models.StatutPolice.suspendu
        modifie = True

    # 3) Résiliation : état terminal, prioritaire sur activation et suspension
    for police in db.query(models.Police).join(
        models.Avenant, models.Avenant.police_id == models.Police.id
    ).filter(
        models.Police.statut != models.StatutPolice.resilie,
        models.Avenant.type_avenant == models.TypeAvenant.resiliation,
        models.Avenant.statut == models.StatutAvenant.valide,
        models.Avenant.date_effet <= aujourdhui,
    ).distinct().all():
        police.statut = models.StatutPolice.resilie
        modifie = True

    if modifie:
        db.commit()
