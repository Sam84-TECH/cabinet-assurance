"""
Module Police-Garantie (SOUS) — rattachement des garanties (et de leur prime)
à une police, éventuellement ciblées sur un risque précis (véhicule).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..avenant import composition_verrouillee
from ..tarification import calculer_prime_garantie

router = APIRouter(prefix="/police-garanties", tags=["Police garantie"])


@router.post("", response_model=schemas.PoliceGarantieRead)
def create_police_garantie(payload: schemas.PoliceGarantieCreate, db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    """Rattache une garantie à une police. Si `montant_prime` est omis, il est calculé selon la
    règle de tarification du produit (Garantie.parametres) et le capital_assure (RF-SOUS-02) ;
    s'il est fourni, il est accepté tel quel (cas d'un forfait négocié à la main)."""
    data = payload.model_dump()
    if data.get("montant_prime") is None:
        garantie = crud.get_or_404(db, models.Garantie, data["garantie_id"])
        # La puissance fiscale (barème RC) est un attribut du véhicule : on la lit sur le risque.
        puissance = None
        if data.get("risque_id") is not None:
            risque = db.get(models.Risque, data["risque_id"])
            brut = (risque.attributs or {}).get("puissance_fiscale") if risque else None
            puissance = int(brut) if brut is not None else None
        try:
            data["montant_prime"] = calculer_prime_garantie(
                garantie.parametres, data.get("capital_assure"), puissance)
        except ValueError as erreur:
            raise HTTPException(400, str(erreur))
    return crud.create(db, models.PoliceGarantie, data)


@router.get("", response_model=list[schemas.PoliceGarantieRead])
def list_police_garanties(police_id: int | None = None, risque_id: int | None = None,
                          skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_all(db, models.PoliceGarantie, skip, limit,
                         police_id=police_id, risque_id=risque_id)


@router.get("/{police_garantie_id}", response_model=schemas.PoliceGarantieRead)
def get_police_garantie(police_garantie_id: int, db: Session = Depends(get_db)):
    return crud.get_or_404(db, models.PoliceGarantie, police_garantie_id)


@router.patch("/{police_garantie_id}", response_model=schemas.PoliceGarantieRead)
def update_police_garantie(police_garantie_id: int, payload: schemas.PoliceGarantieCreate,
                           db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    return crud.update(db, models.PoliceGarantie, police_garantie_id, payload.model_dump(exclude_unset=True))


@router.delete("/{police_garantie_id}", status_code=204)
def delete_police_garantie(police_garantie_id: int, db: Session = Depends(get_db),
                           user: models.Utilisateur = Depends(get_current_user)):
    """Retire une garantie de la composition d'une police.

    Deux garde-fous, dans cet ordre :
    1. Une garantie **obligatoire** (RC en auto : couverture minimale légale, marquée
       `parametres.obligatoire` — paramétrage, pas de code produit en dur) n'est **jamais**
       retirable : le message l'explique au lieu d'un blocage muet.
    2. Sinon, suppression autorisée tant qu'aucun avenant n'est validé sur la police (règle 13),
       ou le temps d'un avenant de modification en brouillon qui rouvre la composition (règle 17).
       Une fois la police engagée, retirer une garantie optionnelle passe par un avenant, pas un
       DELETE sec."""
    ligne = crud.get_or_404(db, models.PoliceGarantie, police_garantie_id)
    garantie = crud.get_or_404(db, models.Garantie, ligne.garantie_id)
    if (garantie.parametres or {}).get("obligatoire"):
        raise HTTPException(
            400,
            f"La garantie « {garantie.nom} » est obligatoire (couverture minimale légale) : "
            "elle ne peut pas être retirée d'une police. Seules les garanties optionnelles "
            "sont retirables.",
        )
    if composition_verrouillee(db, ligne.police_id):
        raise HTTPException(
            400,
            "Un avenant est validé sur cette police : le retrait d'une garantie passe par un "
            "avenant de modification (créez-le en brouillon, puis validez-le).",
        )
    crud.delete(db, models.PoliceGarantie, police_garantie_id)
