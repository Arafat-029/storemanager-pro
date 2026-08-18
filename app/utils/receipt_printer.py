"""Impression des tickets sur une imprimante Windows.

L'application produit deja le ticket en PDF au format 80 mm. Ce module se
charge de l'envoyer a l'imprimante SANS ouvrir de visionneuse : le caissier
ne doit rien faire d'autre que valider la vente.

Le rendu passe par QtPdf + QtPrintSupport, tous deux fournis avec PySide6 :
pas de pywin32, pas d'outil tiers a installer chez le client, et ca marche
avec n'importe quelle imprimante ayant un pilote Windows (thermique ou non).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QSize, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

# Les imprimantes thermiques travaillent typiquement en 203 dpi. On borne le
# rendu : trop bas le ticket est illisible, trop haut on fabrique une image
# enorme pour rien et l'impression traine.
_MIN_DPI = 150
_MAX_DPI = 400


def available_printers() -> list[str]:
    """Noms des imprimantes installees sur le poste."""
    return [info.printerName() for info in QPrinterInfo.availablePrinters()]


def default_printer_name() -> str:
    """Imprimante par defaut de Windows, ou chaine vide s'il n'y en a pas."""
    return QPrinterInfo.defaultPrinter().printerName() or ""


def printer_exists(name: str) -> bool:
    return bool(name) and name in available_printers()


# Imprimantes qui produisent un fichier au lieu de sortir du papier. Elles
# sont souvent l'imprimante par defaut d'un PC neuf : sans avertissement, le
# caissier se retrouve avec une fenetre « Enregistrer sous » a chaque vente.
_VIRTUAL_MARKERS = (
    "pdf", "xps", "onenote", "fax", "document writer",
    "microsoft print to", "send to onenote",
)


def is_virtual_printer(name: str) -> bool:
    """Vrai si cette imprimante ecrit un fichier au lieu d'imprimer."""
    lowered = (name or "").strip().lower()
    return any(marker in lowered for marker in _VIRTUAL_MARKERS)


def effective_printer_name(configured: str = "") -> str:
    """Imprimante reellement utilisee : celle choisie, sinon la defaut."""
    return configured or default_printer_name()


def print_pdf(pdf_path: str | Path, printer_name: str = "") -> str:
    """Envoie un PDF a l'imprimante. Renvoie le nom de l'imprimante utilisee.

    `printer_name` vide => imprimante par defaut de Windows. Toute erreur
    leve une exception avec un message en francais : l'appelant l'affiche au
    caissier, en precisant que la vente est deja enregistree.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Ticket introuvable : {pdf_path}")

    document = QPdfDocument()
    if document.load(str(pdf_path)) != QPdfDocument.Error.None_:
        raise RuntimeError("Le fichier du ticket est illisible.")
    if document.pageCount() <= 0:
        raise RuntimeError("Le ticket ne contient aucune page.")

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if printer_name:
        if not printer_exists(printer_name):
            raise RuntimeError(
                f"L'imprimante « {printer_name} » est introuvable. "
                "Vérifiez qu'elle est allumée et branchée, ou choisissez-en "
                "une autre dans Paramètres."
            )
        printer.setPrinterName(printer_name)
    elif not default_printer_name():
        raise RuntimeError(
            "Aucune imprimante n'est installée sur ce poste. "
            "Installez-en une, ou choisissez-en une dans Paramètres."
        )

    if not printer.isValid():
        raise RuntimeError("L'imprimante sélectionnée n'est pas utilisable.")

    # Le format papier suit celui du PDF (80 mm de large, hauteur variable
    # selon le nombre de lignes) : sans ca, Windows imposerait du A4 et le
    # ticket sortirait minuscule dans un coin de la page.
    page_pt: QSizeF = document.pagePointSize(0)
    printer.setPageSize(QPageSize(page_pt, QPageSize.Unit.Point))
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)

    dpi = max(_MIN_DPI, min(printer.resolution() or _MIN_DPI, _MAX_DPI))

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(
            "Impossible de démarrer l'impression. L'imprimante est peut-être "
            "hors ligne ou déjà occupée."
        )
    try:
        for index in range(document.pageCount()):
            if index > 0:
                printer.newPage()
            size_pt = document.pagePointSize(index)
            image = document.render(
                index,
                QSize(
                    max(1, int(size_pt.width() / 72.0 * dpi)),
                    max(1, int(size_pt.height() / 72.0 * dpi)),
                ),
            )
            if image.isNull():
                raise RuntimeError("Le rendu du ticket a échoué.")
            painter.drawImage(painter.viewport(), image)
    finally:
        painter.end()

    return printer.printerName() or default_printer_name()
