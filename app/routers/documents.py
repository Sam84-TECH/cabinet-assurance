"""
Module Éditions PDF (RF-POL-04) — génération côté serveur et archivage horodaté des
documents : quittance, attestation d'assurance, police, bordereau de versement et
bordereau de reversement.

Chaque endpoint de génération produit le PDF, l'archive (fichier horodaté + trace en base,
auteur déduit du jeton), et le renvoie en `application/pdf`. Les archives sont consultables
et re-téléchargeables. Aucun DELETE : une trace d'archivage ne se supprime pas (traçabilité).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import crud, models, schemas, pdf
from ..database import get_db
from ..archivage import archiver_document
from ..auth import get_current_user

router = APIRouter(prefix="/documents", tags=["Éditions PDF"])


def _reponse_pdf(contenu: bytes, nom_fichier: str) -> Response:
    return Response(
        content=contenu, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nom_fichier}"'},
    )


def _risques(db: Session, police_id: int):
    return db.query(models.Risque).filter_by(police_id=police_id).all()


def _garanties_primes(db: Session, police_id: int):
    """(nom_garantie, montant_prime) pour chaque garantie rattachée à la police."""
    couples = (
        db.query(models.PoliceGarantie, models.Garantie)
        .join(models.Garantie, models.Garantie.id == models.PoliceGarantie.garantie_id)
        .filter(models.PoliceGarantie.police_id == police_id)
        .all()
    )
    return [(garantie.nom, pg.montant_prime) for pg, garantie in couples]


# ----- Génération + archivage -----

@router.get("/quittances/{quittance_id}")
def pdf_quittance(quittance_id: int, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    quittance = crud.get_or_404(db, models.Quittance, quittance_id)
    police = crud.get_or_404(db, models.Police, quittance.police_id)
    client = crud.get_or_404(db, models.Client, police.client_id)
    contenu = pdf.generer_quittance_pdf(quittance, police, client)
    archive = archiver_document(db, type_document=models.TypeDocument.quittance,
                                entite_id=quittance.id, numero=quittance.numero_quittance,
                                contenu_pdf=contenu, genere_par=user.id)
    return _reponse_pdf(contenu, archive.nom_fichier)


@router.get("/attestations/{police_id}")
def pdf_attestation(police_id: int, db: Session = Depends(get_db),
                    user: models.Utilisateur = Depends(get_current_user)):
    police = crud.get_or_404(db, models.Police, police_id)
    client = crud.get_or_404(db, models.Client, police.client_id)
    garanties = [nom for nom, _ in _garanties_primes(db, police_id)]
    contenu = pdf.generer_attestation_pdf(police, client, _risques(db, police_id), garanties)
    archive = archiver_document(db, type_document=models.TypeDocument.attestation,
                                entite_id=police.id, numero=police.numero_police,
                                contenu_pdf=contenu, genere_par=user.id)
    return _reponse_pdf(contenu, archive.nom_fichier)


@router.get("/polices/{police_id}")
def pdf_police(police_id: int, db: Session = Depends(get_db),
               user: models.Utilisateur = Depends(get_current_user)):
    police = crud.get_or_404(db, models.Police, police_id)
    client = crud.get_or_404(db, models.Client, police.client_id)
    produit = db.get(models.Produit, police.produit_id)
    contenu = pdf.generer_police_pdf(police, client, produit, _risques(db, police_id),
                                     _garanties_primes(db, police_id))
    archive = archiver_document(db, type_document=models.TypeDocument.police,
                                entite_id=police.id, numero=police.numero_police,
                                contenu_pdf=contenu, genere_par=user.id)
    return _reponse_pdf(contenu, archive.nom_fichier)


@router.get("/bordereaux-versement/{bordereau_id}")
def pdf_bordereau_versement(bordereau_id: int, db: Session = Depends(get_db),
                            user: models.Utilisateur = Depends(get_current_user)):
    bordereau = crud.get_or_404(db, models.BordereauVersement, bordereau_id)
    banque = db.get(models.BanqueAgence, bordereau.banque_agence_id)
    lignes = []
    for ligne in db.query(models.BordereauVersementLigne).filter_by(bordereau_versement_id=bordereau_id):
        encaissement = db.get(models.Encaissement, ligne.encaissement_id)
        reference = (encaissement.cheque_numero or encaissement.virement_reference
                     or f"#{encaissement.id}") if encaissement else f"#{ligne.encaissement_id}"
        mode = encaissement.mode_paiement.value if encaissement else "—"
        lignes.append({"libelle": f"{mode} — {reference}", "montant": ligne.montant})
    contenu = pdf.generer_bordereau_versement_pdf(bordereau, banque, lignes)
    archive = archiver_document(db, type_document=models.TypeDocument.bordereau_versement,
                                entite_id=bordereau.id, numero=bordereau.numero_bordereau,
                                contenu_pdf=contenu, genere_par=user.id)
    return _reponse_pdf(contenu, archive.nom_fichier)


@router.get("/bordereaux-reversement/{bordereau_id}")
def pdf_bordereau_reversement(bordereau_id: int, db: Session = Depends(get_db),
                              user: models.Utilisateur = Depends(get_current_user)):
    bordereau = crud.get_or_404(db, models.BordereauReversement, bordereau_id)
    compagnie = db.get(models.Compagnie, bordereau.compagnie_id)
    lignes = []
    for ligne in db.query(models.BordereauReversementLigne).filter_by(bordereau_reversement_id=bordereau_id):
        quittance = db.get(models.Quittance, ligne.quittance_id)
        numero = quittance.numero_quittance if quittance else f"#{ligne.quittance_id}"
        lignes.append((numero, ligne.prime_nette_reversee, ligne.commission_calculee))
    contenu = pdf.generer_bordereau_reversement_pdf(bordereau, compagnie, lignes)
    archive = archiver_document(db, type_document=models.TypeDocument.bordereau_reversement,
                                entite_id=bordereau.id, numero=bordereau.numero_bordereau,
                                contenu_pdf=contenu, genere_par=user.id)
    return _reponse_pdf(contenu, archive.nom_fichier)


# ----- Archives (consultation / re-téléchargement) -----

@router.get("/archives", response_model=list[schemas.DocumentArchiveRead])
def list_archives(type_document: models.TypeDocument | None = None, entite_id: int | None = None,
                  skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                  user: models.Utilisateur = Depends(get_current_user)):
    return crud.list_all(db, models.DocumentArchive, skip, limit,
                         type_document=type_document, entite_id=entite_id)


@router.get("/archives/{archive_id}/telecharger")
def telecharger_archive(archive_id: int, db: Session = Depends(get_db),
                        user: models.Utilisateur = Depends(get_current_user)):
    """Re-télécharge un document déjà archivé, depuis le fichier horodaté conservé sur le serveur."""
    archive = crud.get_or_404(db, models.DocumentArchive, archive_id)
    chemin = Path(archive.chemin_fichier)
    if not chemin.exists():
        raise HTTPException(404, "Fichier archivé introuvable sur le serveur.")
    return FileResponse(str(chemin), media_type="application/pdf", filename=archive.nom_fichier)
