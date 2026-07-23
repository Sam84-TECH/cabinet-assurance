"""
Module Reversement compagnie (REV).
Calcule les primes nettes dues à la compagnie et la commission du cabinet
selon les barèmes paramétrés (RF-REV-03), et génère le bordereau détaillé
par quittance (RF-REV-02).

Règle du terrain (observée dans DIAM, étape 9) : le bordereau de reversement
peut être généré même si le chèque client n'est pas encore encaissé côté banque,
selon les règles propres à l'agence — on ne bloque donc pas sur le statut
d'encaissement de la quittance.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_bordereau_reversement
from ..auth import exiger_role, get_current_user

router = APIRouter(prefix="/rev", tags=["Reversement compagnie"])


def _trouver_taux_commission(db: Session, compagnie_id: int, produit_id: int) -> Decimal:
    """
    Cherche le barème applicable (RF-REV-03) : priorité à un barème spécifique
    au produit, sinon barème général de la compagnie (produit_id NULL).
    """
    bareme_produit = db.query(models.BaremeCommission).filter_by(
        compagnie_id=compagnie_id, produit_id=produit_id
    ).first()
    if bareme_produit:
        return bareme_produit.taux_commission

    bareme_general = db.query(models.BaremeCommission).filter_by(
        compagnie_id=compagnie_id, produit_id=None
    ).first()
    if bareme_general:
        return bareme_general.taux_commission

    raise HTTPException(400, "Aucun barème de commission paramétré pour cette compagnie/produit.")


@router.post("/bordereaux", response_model=schemas.BordereauReversementRead)
def create_bordereau(payload: schemas.BordereauReversementCreate, db: Session = Depends(get_db),
                      user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_bordereau"] = generer_numero_bordereau_reversement(db)
    return crud.create(db, models.BordereauReversement, data)


@router.get("/bordereaux", response_model=list[schemas.BordereauReversementRead])
def list_bordereaux(compagnie_id: int | None = None, db: Session = Depends(get_db)):
    bordereaux = crud.list_all(db, models.BordereauReversement)
    if compagnie_id is not None:
        bordereaux = [b for b in bordereaux if b.compagnie_id == compagnie_id]
    return bordereaux


@router.get("/bordereaux/{bordereau_id}", response_model=schemas.BordereauReversementRead)
def get_bordereau(bordereau_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.BordereauReversement, bordereau_id)


@router.post("/bordereaux/{bordereau_id}/ajouter/{quittance_id}",
             response_model=schemas.BordereauReversementLigneRead)
def ajouter_quittance(bordereau_id: int, quittance_id: int, db: Session = Depends(get_db),
                       user: models.Utilisateur = Depends(get_current_user)):
    """
    Ajoute une quittance au bordereau, avec calcul automatique de la commission
    selon le barème compagnie/produit (RF-REV-01, RF-REV-03).
    """
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if bordereau.statut != models.StatutBordereauReversement.brouillon:
        raise HTTPException(400, "Ce bordereau est validé : toute correction doit passer par un bordereau rectificatif.")

    quittance = crud.get_or_404(db, models.Quittance, quittance_id)
    police = crud.get_or_404(db, models.Police, quittance.police_id)

    taux = _trouver_taux_commission(db, bordereau.compagnie_id, police.produit_id)
    commission = (quittance.prime_nette * taux / Decimal("100")).quantize(Decimal("0.01"))

    return crud.create(db, models.BordereauReversementLigne, {
        "bordereau_reversement_id": bordereau_id,
        "quittance_id": quittance_id,
        "prime_nette_reversee": quittance.prime_nette,
        "commission_calculee": commission,
    })


@router.patch("/bordereaux/{bordereau_id}/valider", response_model=schemas.BordereauReversementRead)
def valider_bordereau(bordereau_id: int, db: Session = Depends(get_db),
                       admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """
    Valide le bordereau (RF-REV-02) : fige les totaux. Un bordereau validé
    ne peut plus être modifié — règle explicite du CDCF. Réservé au Super
    Administrateur (identifié automatiquement via le jeton de connexion).
    """
    from datetime import datetime

    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if bordereau.statut != models.StatutBordereauReversement.brouillon:
        raise HTTPException(400, "Ce bordereau a déjà été validé.")

    lignes = db.query(models.BordereauReversementLigne).filter_by(bordereau_reversement_id=bordereau_id).all()
    if not lignes:
        raise HTTPException(400, "Impossible de valider un bordereau vide.")

    bordereau.montant_total = sum((l.prime_nette_reversee for l in lignes), Decimal("0"))
    bordereau.commission_totale = sum((l.commission_calculee for l in lignes), Decimal("0"))
    bordereau.statut = models.StatutBordereauReversement.valide
    bordereau.valide_par = admin.id
    bordereau.date_validation = datetime.now()
    db.commit()
    db.refresh(bordereau)
    return bordereau
