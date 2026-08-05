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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..numerotation import generer_numero_bordereau_reversement
from ..auth import exiger_role, get_current_user

router = APIRouter(prefix="/rev", tags=["Reversement compagnie"])

# Statuts d'un bordereau où le reversement est définitivement engagé : une quittance qui y
# figure est considérée comme déjà reversée. Un bordereau en brouillon, lui, peut être abandonné.
STATUTS_REVERSEMENT_DEFINITIFS = (
    models.StatutBordereauReversement.valide,
    models.StatutBordereauReversement.reverse,
)


def _quittances_deja_reversees(db: Session):
    """Sous-requête des quittances déjà reversées définitivement (portées à un bordereau validé
    ou reversé). On n'exclut PAS les quittances d'un simple brouillon : un brouillon peut être
    abandonné, et l'exclure définitivement bloquerait à jamais la quittance (aucun DELETE sur les
    lignes, règle 12). L'anti-double-reversement s'appuie donc sur les seuls bordereaux définitifs."""
    return (
        select(models.BordereauReversementLigne.quittance_id)
        .join(models.BordereauReversement,
              models.BordereauReversement.id == models.BordereauReversementLigne.bordereau_reversement_id)
        .where(models.BordereauReversement.statut.in_(STATUTS_REVERSEMENT_DEFINITIFS))
    )


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


def _commission_ligne(db: Session, compagnie_id: int, produit_id: int, prime_nette: Decimal) -> Decimal:
    """Commission d'une ligne de reversement = prime nette × taux du barème applicable."""
    taux = _trouver_taux_commission(db, compagnie_id, produit_id)
    return (prime_nette * taux / Decimal("100")).quantize(Decimal("0.01"))


@router.post("/bordereaux", response_model=schemas.BordereauReversementRead)
def create_bordereau(payload: schemas.BordereauReversementCreate, db: Session = Depends(get_db),
                      user: models.Utilisateur = Depends(get_current_user)):
    data = payload.model_dump()
    data["numero_bordereau"] = generer_numero_bordereau_reversement(db)
    data["statut"] = models.StatutBordereauReversement.brouillon  # forcé serveur (anti-contournement)
    return crud.create(db, models.BordereauReversement, data)


@router.get("/bordereaux", response_model=list[schemas.BordereauReversementRead])
def list_bordereaux(compagnie_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.BordereauReversement, skip, limit, compagnie_id=compagnie_id)


@router.get("/bordereaux/{bordereau_id}", response_model=schemas.BordereauReversementDetailRead)
def get_bordereau(bordereau_id: int, db: Session = Depends(get_db)):
    """Détail du bordereau + ses lignes enrichies du numéro de quittance et du numéro de police
    (écart §28 : les lignes sont désormais incluses dans le GET de détail, avec les libellés)."""
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    lignes = []
    for ligne in db.query(models.BordereauReversementLigne).filter_by(bordereau_reversement_id=bordereau_id):
        quittance = db.get(models.Quittance, ligne.quittance_id)
        police = db.get(models.Police, quittance.police_id) if quittance else None
        lignes.append(schemas.BordereauReversementLigneDetailRead(
            id=ligne.id,
            bordereau_reversement_id=ligne.bordereau_reversement_id,
            quittance_id=ligne.quittance_id,
            numero_quittance=quittance.numero_quittance if quittance else None,
            numero_police=police.numero_police if police else None,
            prime_nette_reversee=ligne.prime_nette_reversee,
            commission_calculee=ligne.commission_calculee,
        ))
    return schemas.BordereauReversementDetailRead(
        **schemas.BordereauReversementRead.model_validate(bordereau).model_dump(),
        lignes=lignes,
    )


@router.post("/bordereaux/{bordereau_id}/ajouter/{quittance_id}",
             response_model=schemas.BordereauReversementLigneRead)
def ajouter_quittance(bordereau_id: int, quittance_id: int, db: Session = Depends(get_db),
                       user: models.Utilisateur = Depends(get_current_user)):
    """
    Ajoute une quittance au bordereau, avec calcul automatique de la commission
    selon le barème compagnie/produit (RF-REV-01, RF-REV-03). Refuse une quittance déjà
    reversée (bordereau validé/reversé), sauf sur un bordereau rectificatif — qui corrige
    justement un reversement antérieur.
    """
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if bordereau.statut != models.StatutBordereauReversement.brouillon:
        raise HTTPException(400, "Ce bordereau est validé : toute correction doit passer par un bordereau rectificatif.")

    quittance = crud.get_or_404(db, models.Quittance, quittance_id)
    police = crud.get_or_404(db, models.Police, quittance.police_id)

    # Anti-double-reversement : une quittance déjà reversée définitivement ne peut l'être à
    # nouveau. Exemption pour un bordereau rectificatif, dont c'est précisément le rôle.
    if bordereau.rectifie_bordereau_id is None and db.query(
        _quittances_deja_reversees(db).where(
            models.BordereauReversementLigne.quittance_id == quittance_id
        ).exists()
    ).scalar():
        raise HTTPException(
            409, "Cette quittance figure déjà sur un bordereau de reversement validé : "
                 "toute correction passe par un bordereau rectificatif.")

    commission = _commission_ligne(db, bordereau.compagnie_id, police.produit_id, quittance.prime_nette)

    return crud.create(db, models.BordereauReversementLigne, {
        "bordereau_reversement_id": bordereau_id,
        "quittance_id": quittance_id,
        "prime_nette_reversee": quittance.prime_nette,
        "commission_calculee": commission,
    })


@router.post("/bordereaux/{bordereau_id}/selectionner-periode",
             response_model=list[schemas.BordereauReversementLigneRead])
def selectionner_quittances_periode(bordereau_id: int, db: Session = Depends(get_db),
                                     user: models.Utilisateur = Depends(get_current_user)):
    """
    Sélection automatique des quittances à reverser pour la période du bordereau (RF-REV-01) :
    ajoute d'un seul geste toutes les quittances non annulées de la compagnie du bordereau,
    émises entre `periode_debut` et `periode_fin`, qui ne sont pas déjà reversées (portées à un
    bordereau validé ou reversé) pour éviter tout double reversement, avec leur commission
    calculée selon le barème. Le statut d'encaissement n'est pas un critère (règle 9 : le
    reversement peut précéder l'encaissement du chèque). Réservé à un bordereau en brouillon ;
    renvoie les lignes ajoutées.
    """
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if bordereau.statut != models.StatutBordereauReversement.brouillon:
        raise HTTPException(400, "Ce bordereau est validé : toute correction doit passer par un bordereau rectificatif.")

    # Quittances déjà reversées définitivement (bordereau validé/reversé) : exclues pour ne
    # jamais reverser deux fois la même prime. Les brouillons ne comptent pas (cf. helper).
    deja_reversees = _quittances_deja_reversees(db)
    # Quittances déjà présentes sur CE bordereau : exclues pour rendre l'appel idempotent
    # (une 2e sélection ne duplique pas les lignes déjà ajoutées).
    deja_sur_ce_bordereau = select(models.BordereauReversementLigne.quittance_id).where(
        models.BordereauReversementLigne.bordereau_reversement_id == bordereau_id
    )

    quittances = (
        db.query(models.Quittance)
        .join(models.Police, models.Police.id == models.Quittance.police_id)
        .join(models.Produit, models.Produit.id == models.Police.produit_id)
        .filter(
            models.Produit.compagnie_id == bordereau.compagnie_id,
            models.Quittance.statut != models.StatutQuittance.annulee,
            func.date(models.Quittance.date_creation) >= bordereau.periode_debut,
            func.date(models.Quittance.date_creation) <= bordereau.periode_fin,
            models.Quittance.id.not_in(deja_reversees),
            models.Quittance.id.not_in(deja_sur_ce_bordereau),
        )
        .order_by(models.Quittance.id)
        .all()
    )

    lignes = []
    for quittance in quittances:
        police = db.get(models.Police, quittance.police_id)
        commission = _commission_ligne(db, bordereau.compagnie_id, police.produit_id, quittance.prime_nette)
        ligne = models.BordereauReversementLigne(
            bordereau_reversement_id=bordereau_id,
            quittance_id=quittance.id,
            prime_nette_reversee=quittance.prime_nette,
            commission_calculee=commission,
        )
        db.add(ligne)
        lignes.append(ligne)
    db.commit()
    for ligne in lignes:
        db.refresh(ligne)
    return lignes


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


@router.patch("/bordereaux/{bordereau_id}/reverser", response_model=schemas.BordereauReversementRead)
def reverser_bordereau(bordereau_id: int, payload: schemas.ReversementCreate, db: Session = Depends(get_db),
                       admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    """
    Marque le bordereau comme effectivement reversé à la compagnie (§18) : statut `valide` ->
    `reverse`. Exige la référence du virement (texte non vide) et la date de reversement.
    Réservé au Super Administrateur ; l'auteur est déduit du jeton. Seul un bordereau au statut
    `valide` peut être reversé (la transition est tracée dans le journal d'audit).
    """
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if bordereau.statut != models.StatutBordereauReversement.valide:
        raise HTTPException(400, "Seul un bordereau au statut « valide » peut être marqué comme reversé.")

    bordereau.statut = models.StatutBordereauReversement.reverse
    bordereau.reference_virement = payload.reference_virement
    bordereau.date_reversement = payload.date_reversement
    bordereau.reverse_par = admin.id
    db.commit()
    db.refresh(bordereau)
    return bordereau


@router.post("/bordereaux/{bordereau_id}/rectifier", response_model=schemas.BordereauReversementRead)
def rectifier_bordereau(bordereau_id: int, db: Session = Depends(get_db),
                        user: models.Utilisateur = Depends(get_current_user)):
    """
    Crée un bordereau de reversement rectificatif (règle CDCF n°7) : un bordereau validé n'étant
    plus modifiable, toute correction passe par un NOUVEAU bordereau en brouillon qui référence
    l'original (`rectifie_bordereau_id`) pour la traçabilité. Il reprend la compagnie et la
    période de l'original ; les lignes correctives s'y ajoutent ensuite **une par une** via
    `ajouter/{quittance_id}` (la sélection de période ne reprend pas les quittances déjà
    reversées, c'est voulu), puis il suit le circuit de validation habituel (super administrateur).
    Seul un bordereau déjà validé peut être rectifié — un brouillon se corrige directement.
    """
    original = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    if original.statut == models.StatutBordereauReversement.brouillon:
        raise HTTPException(
            400, "Ce bordereau est encore en brouillon : modifiez-le directement, un rectificatif est inutile.")

    return crud.create(db, models.BordereauReversement, {
        "numero_bordereau": generer_numero_bordereau_reversement(db),
        "compagnie_id": original.compagnie_id,
        "periode_debut": original.periode_debut,
        "periode_fin": original.periode_fin,
        "statut": models.StatutBordereauReversement.brouillon,
        "rectifie_bordereau_id": original.id,
    })
