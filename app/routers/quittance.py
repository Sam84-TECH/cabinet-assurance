"""
Module Quittance (POL) — le détail financier d'un avenant.
Les quittances sont générées automatiquement à la validation d'un avenant (RF-SOUS-07,
voir app/facturation.py) ; la création manuelle est verrouillée. La table reste en
lecture seule via l'API (consultation), sans DELETE (règle métier n°12).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..reglement import enrichir_quittance
from ..auth import exiger_role

router = APIRouter(prefix="/quittances", tags=["Quittance"])


@router.post("", deprecated=True)
def create_quittance():
    """Verrouillé : la quittance est générée automatiquement à la validation d'un avenant
    (RF-SOUS-07). La création manuelle est désactivée pour éviter les doublons."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Création manuelle de quittance désactivée : elle est générée automatiquement "
               "à la validation de l'avenant (RF-SOUS-07).",
    )


@router.get("", response_model=list[schemas.QuittanceRead])
def list_quittances(police_id: int | None = None, statut: models.StatutQuittance | None = None,
                     skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    quittances = crud.list_all(db, models.Quittance, skip, limit, police_id=police_id, statut=statut)
    return [enrichir_quittance(db, q) for q in quittances]  # + montant_regle / reste_du (§27)


@router.get("/{quittance_id}", response_model=schemas.QuittanceRead)
def get_quittance(quittance_id: int, db: Session = Depends(get_db)):
    return enrichir_quittance(db, crud.get_or_404(db, models.Quittance, quittance_id))  # + reste_du (§27)


@router.patch("/{quittance_id}/annuler", response_model=schemas.QuittanceRead)
def annuler_quittance(quittance_id: int, payload: schemas.AnnulationQuittanceCreate,
                      db: Session = Depends(get_db),
                      admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """Annule une quittance (écart §11) : statut `emise` -> `annulee`. Réservé au Super
    Administrateur, motif obligatoire. Autorisé uniquement tant que la quittance est encore
    `emise` — jamais une quittance réglée (même partiellement) ni déjà annulée. Le motif, la
    date et l'auteur sont enregistrés et la transition est tracée dans le journal d'audit.
    Une écriture comptable ne se supprime pas : elle s'annule par changement de statut (règle 12).
    Note : un éventuel dossier de recouvrement ouvert sur la quittance n'est pas refermé
    automatiquement (à traiter manuellement) ; la bascule auto, elle, exclut déjà les annulées."""
    quittance = crud.get_or_404(db, models.Quittance, quittance_id)
    if quittance.statut != models.StatutQuittance.emise:
        raise HTTPException(400, "Seule une quittance au statut « émise » peut être annulée.")

    # Règle 9 : une quittance encore `emise` a pu être portée à un bordereau de reversement validé
    # (reversement avant encaissement du chèque). L'annuler laisserait une prime reversée sans
    # quittance active : on refuse, la correction passe par un bordereau rectificatif (règle 7).
    deja_reversee = db.query(models.BordereauReversementLigne.id).join(
        models.BordereauReversement,
        models.BordereauReversement.id == models.BordereauReversementLigne.bordereau_reversement_id,
    ).filter(
        models.BordereauReversementLigne.quittance_id == quittance_id,
        models.BordereauReversement.statut.in_([
            models.StatutBordereauReversement.valide, models.StatutBordereauReversement.reverse,
        ]),
    ).first()
    if deja_reversee is not None:
        raise HTTPException(
            409, "Cette quittance figure sur un bordereau de reversement validé : son annulation "
                 "doit passer par un bordereau rectificatif (règle 7).")

    quittance.statut = models.StatutQuittance.annulee
    quittance.motif_annulation = payload.motif
    quittance.date_annulation = date.today()
    quittance.annule_par = admin.id
    db.commit()
    db.refresh(quittance)
    return enrichir_quittance(db, quittance)
