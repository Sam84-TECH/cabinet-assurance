"""
Archivage horodaté des documents PDF (RF-POL-04).

Chaque génération écrit le PDF dans le répertoire d'archives (rangé par type de document),
avec un nom de fichier horodaté (jusqu'à la microseconde, donc jamais de collision), et
enregistre une ligne de trace dans `document_archive` (type, entité source, numéro, chemin,
auteur, date). Le répertoire est paramétrable via ARCHIVES_DIR.
"""

import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from . import models

REPERTOIRE_ARCHIVES = Path(os.environ.get("ARCHIVES_DIR", "archives"))


def _slug(texte: str) -> str:
    """Nom de fichier sûr : ne garde que lettres, chiffres, point, tiret et souligné."""
    nettoye = re.sub(r"[^A-Za-z0-9._-]+", "-", texte).strip("-")
    return nettoye or "document"


def archiver_document(db: Session, *, type_document: models.TypeDocument, entite_id: int,
                      numero: str | None, contenu_pdf: bytes,
                      genere_par: int | None) -> models.DocumentArchive:
    """Écrit le PDF sur disque (horodaté) et enregistre sa trace ; renvoie la ligne d'archive."""
    horodatage = datetime.now()
    base = _slug(numero or f"{type_document.value}-{entite_id}")
    nom_fichier = f"{base}_{horodatage:%Y%m%d-%H%M%S-%f}.pdf"

    dossier = REPERTOIRE_ARCHIVES / type_document.value
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom_fichier
    chemin.write_bytes(contenu_pdf)

    archive = models.DocumentArchive(
        type_document=type_document,
        entite_id=entite_id,
        numero=numero,
        nom_fichier=nom_fichier,
        chemin_fichier=str(chemin.resolve()),
        genere_par=genere_par,
    )
    db.add(archive)
    db.commit()
    db.refresh(archive)
    return archive
