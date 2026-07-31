"""
Génération des éditions PDF côté serveur (RF-POL-04) : quittance, attestation d'assurance,
police, bordereau de versement et bordereau de reversement.

Bibliothèque : fpdf2 — pur Python, sans dépendance système (contrairement à WeasyPrint qui
exige Cairo/Pango), conforme à la contrainte « serveur modeste » du CDCF. Polices cœur PDF
(Helvetica) pour ne rien embarquer ; accents en bleu marine, clin d'œil à la charte.

Chaque fonction renvoie le PDF en `bytes` ; l'archivage horodaté est fait par app/archivage.py.
"""

import os
from datetime import datetime
from decimal import Decimal

from fpdf import FPDF
from fpdf.enums import XPos, YPos

NAVY = (18, 37, 62)      # #12253E — couleur principale de la charte
GRIS = (90, 90, 90)
ZEBRE = (242, 244, 247)

NOM_CABINET = os.environ.get("NOM_CABINET", "Cabinet d'assurance - Agent général Sanlam")
SOUS_TITRE_CABINET = os.environ.get("SOUS_TITRE_CABINET", "Sanlam Maroc - Branche Automobile")

# Les polices cœur PDF (Helvetica) ne codent que le Latin-1. On normalise donc la typographie
# courante (tirets cadratin, puces, guillemets/apostrophes courbes, points de suspension) et on
# remplace tout caractère restant hors Latin-1 (ex. arabe) par « ? » — la génération ne plante
# jamais sur une donnée inattendue, sans avoir à embarquer une police Unicode.
_REMPLACEMENTS = {
    "—": "-", "–": "-",           # tirets cadratin / demi-cadratin
    "•": "-",                            # puce
    "’": "'", "‘": "'",           # apostrophes courbes
    "“": '"', "”": '"',           # guillemets courbes
    "…": "...",                          # points de suspension
    " ": " ", " ": " ",           # espaces insécables
}


def _latin1(texte) -> str:
    texte = str(texte)
    for source, cible in _REMPLACEMENTS.items():
        texte = texte.replace(source, cible)
    return texte.encode("latin-1", "replace").decode("latin-1")


def _mad(montant) -> str:
    """Formate un montant en dirhams, séparateur de milliers espace et décimale virgule."""
    valeur = Decimal(str(montant if montant is not None else 0))
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",") + " DH"


def _date(valeur) -> str:
    return valeur.strftime("%d/%m/%Y") if valeur else "—"


def _nom_client(client) -> str:
    if client is None:
        return "—"
    if client.raison_sociale:
        return client.raison_sociale
    return " ".join(part for part in (client.nom, client.prenom) if part) or "—"


class _Document(FPDF):
    """Gabarit commun : en-tête cabinet, titre, pied de page horodaté."""

    def __init__(self, titre: str):
        super().__init__()
        self.titre_document = titre
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*NAVY)
        self.cell(0, 8, _latin1(NOM_CABINET), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _latin1(SOUS_TITRE_CABINET), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(*NAVY)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)
        if self.titre_document:
            self.set_font("Helvetica", "B", 16)
            self.set_text_color(*NAVY)
            self.cell(0, 10, _latin1(self.titre_document), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _latin1(f"Document généré le {datetime.now():%d/%m/%Y à %H:%M} - page {self.page_no()}"),
                  align="C")

    def titre_section(self, texte: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 7, _latin1(texte), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*NAVY)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def paire(self, label: str, valeur, largeur_label: int = 55):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GRIS)
        self.cell(largeur_label, 6, _latin1(label), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 0, 0)
        self.cell(0, 6, _latin1(valeur), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def tableau(self, entetes, largeurs, aligns, lignes, gras_derniere=False):
        # En-têtes
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        for entete, largeur in zip(entetes, largeurs):
            self.cell(largeur, 7, _latin1(entete), new_x=XPos.RIGHT, new_y=YPos.TOP, align="C", fill=True)
        self.ln(7)
        # Corps — zébrage une ligne sur deux, bandeau appuyé sur la ligne de total
        self.set_text_color(0, 0, 0)
        for index, ligne in enumerate(lignes):
            derniere = gras_derniere and index == len(lignes) - 1
            self.set_font("Helvetica", "B" if derniere else "", 9)
            if derniere:
                self.set_fill_color(224, 228, 234)
                remplir = True
            else:
                self.set_fill_color(*ZEBRE)
                remplir = index % 2 == 1
            for valeur, largeur, align in zip(ligne, largeurs, aligns):
                self.cell(largeur, 6, _latin1(valeur), border="B", new_x=XPos.RIGHT, new_y=YPos.TOP,
                          align=align, fill=remplir)
            self.ln(6)


def _octets(pdf: _Document) -> bytes:
    return bytes(pdf.output())


def _tableau_vehicules(pdf: _Document, risques):
    lignes = []
    for risque in risques:
        attributs = risque.attributs or {}
        lignes.append([
            attributs.get("immatriculation", "—"),
            attributs.get("marque", "—"),
            attributs.get("modele", "—"),
        ])
    if lignes:
        pdf.tableau(["Immatriculation", "Marque", "Modèle"], [60, 55, 55], ["L", "L", "L"], lignes)
    else:
        pdf.paire("Véhicule", "Aucun risque enregistré")


# ------------------------------------------------------------------
# Générateurs, un par type de document
# ------------------------------------------------------------------

def generer_quittance_pdf(quittance, police, client) -> bytes:
    pdf = _Document("Quittance de prime")
    pdf.paire("N° quittance", quittance.numero_quittance)
    pdf.paire("N° police", police.numero_police)
    pdf.paire("Assuré", _nom_client(client))
    pdf.paire("Période", f"{_date(quittance.periode_debut)} au {_date(quittance.periode_fin)}")
    pdf.titre_section("Détail de la prime")
    pdf.tableau(
        ["Composante", "Montant"], [130, 45], ["L", "R"],
        [
            ["Prime nette", _mad(quittance.prime_nette)],
            ["Taxes", _mad(quittance.taxes)],
            ["Timbres", _mad(quittance.timbres)],
            ["Accessoires", _mad(quittance.accessoires)],
            ["Prime TTC", _mad(quittance.prime_ttc)],
        ],
        gras_derniere=True,
    )
    pdf.ln(3)
    pdf.paire("Statut", quittance.statut.value)
    pdf.paire("Commission agence", _mad(quittance.commission))
    return _octets(pdf)


def generer_attestation_pdf(police, client, risques, garanties) -> bytes:
    pdf = _Document("Attestation d'assurance automobile")
    pdf.paire("N° police", police.numero_police)
    pdf.paire("Assuré", _nom_client(client))
    pdf.paire("Validité", f"{_date(police.date_effet)} au {_date(police.date_echeance)}")
    pdf.titre_section("Véhicule(s) assuré(s)")
    _tableau_vehicules(pdf, risques)
    pdf.titre_section("Garanties couvertes")
    if garanties:
        for nom in garanties:
            pdf.paire("•", nom, largeur_label=8)
    else:
        pdf.paire("Garantie", "Aucune garantie rattachée")
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(
        0, 5,
        _latin1(
            "La présente attestation certifie que le(s) véhicule(s) désigné(s) ci-dessus bénéficie(nt) "
            "des garanties souscrites pour la période de validité indiquée, sous réserve du paiement "
            "de la prime correspondante."
        ),
    )
    return _octets(pdf)


def generer_police_pdf(police, client, produit, risques, garanties_primes) -> bytes:
    pdf = _Document("Police d'assurance")
    pdf.paire("N° police", police.numero_police)
    pdf.paire("Produit", produit.nom if produit else "—")
    pdf.paire("Assuré", _nom_client(client))
    pdf.paire("Effet", _date(police.date_effet))
    pdf.paire("Échéance", _date(police.date_echeance))
    pdf.paire("Statut", police.statut.value)
    pdf.titre_section("Véhicule(s)")
    _tableau_vehicules(pdf, risques)
    pdf.titre_section("Garanties et primes")
    lignes = [[nom, _mad(prime)] for nom, prime in garanties_primes]
    total = sum((Decimal(str(prime or 0)) for _, prime in garanties_primes), Decimal("0"))
    lignes.append(["Total prime nette", _mad(total)])
    pdf.tableau(["Garantie", "Prime"], [130, 45], ["L", "R"], lignes, gras_derniere=True)
    return _octets(pdf)


def generer_bordereau_versement_pdf(bordereau, banque, lignes) -> bytes:
    pdf = _Document("Bordereau de versement")
    pdf.paire("N° bordereau", bordereau.numero_bordereau)
    pdf.paire("Banque", banque.nom if banque else "—")
    pdf.paire("Date", _date(bordereau.date_bordereau))
    pdf.paire("Statut", bordereau.statut.value)
    pdf.titre_section("Encaissements versés")
    corps = [[ligne["libelle"], _mad(ligne["montant"])] for ligne in lignes]
    total = sum((Decimal(str(ligne["montant"])) for ligne in lignes), Decimal("0"))
    corps.append(["Total versé", _mad(total)])
    pdf.tableau(["Encaissement", "Montant"], [135, 40], ["L", "R"], corps, gras_derniere=True)
    return _octets(pdf)


def generer_bordereau_reversement_pdf(bordereau, compagnie, lignes) -> bytes:
    pdf = _Document("Bordereau de reversement")
    pdf.paire("N° bordereau", bordereau.numero_bordereau)
    pdf.paire("Compagnie", compagnie.nom if compagnie else "—")
    pdf.paire("Période", f"{_date(bordereau.periode_debut)} au {_date(bordereau.periode_fin)}")
    pdf.paire("Statut", bordereau.statut.value)
    if bordereau.rectifie_bordereau_id:
        pdf.paire("Rectifie le bordereau n°", bordereau.rectifie_bordereau_id)
    pdf.titre_section("Quittances reversées")
    corps = [[numero, _mad(prime_nette), _mad(commission)] for numero, prime_nette, commission in lignes]
    pdf.tableau(["Quittance", "Prime nette", "Commission"], [85, 45, 45], ["L", "R", "R"], corps)
    pdf.ln(3)
    pdf.paire("Total reversé (prime nette)", _mad(bordereau.montant_total))
    pdf.paire("Commission totale", _mad(bordereau.commission_totale))
    return _octets(pdf)
