"""Envoi d'un ticket a l'imprimante, avec les messages destines au caissier.

Regroupe ici pour que l'encaissement et la reimpression depuis l'historique
se comportent exactement pareil : meme reglage, meme repli, memes mots.

Regle constante : quand on arrive ici, la vente EST enregistree. Aucun
message ne doit laisser croire le contraire, sinon le caissier refait
l'encaissement et le client paie deux fois.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.database.connection import db
from app.utils import receipt_printer
from app.views.dialog_theme import light_information, light_warning


def _settings() -> dict:
    return {
        row["key"]: row["value"]
        for row in db.fetchall("SELECT `key` AS `key`, value FROM settings")
    }


def _open_externally(pdf_path: str | Path) -> None:
    """Repli : ouvrir le PDF dans la visionneuse du systeme."""
    pdf_path = str(pdf_path)
    if sys.platform == "linux":
        subprocess.Popen(["xdg-open", pdf_path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", pdf_path])
    else:
        subprocess.Popen(["start", pdf_path], shell=True)


def print_receipt(parent, pdf_path: str | Path, settings: dict | None = None,
                  sale_id=None, silent_success: bool = True) -> bool:
    """Imprime le ticket. Renvoie True si l'envoi a l'imprimante a reussi.

    `silent_success` : en caisse, une impression reussie ne doit afficher
    aucune fenetre — le caissier enchaine avec le client suivant. Depuis
    l'historique, on confirme au contraire que l'ordre est parti.
    """
    settings = settings if settings is not None else _settings()
    reference = f"La vente #{sale_id}" if sale_id else "La vente"

    if str(settings.get("receipt_auto_print", "1")) == "0":
        # Impression desactivee volontairement : on ouvre la visionneuse,
        # qui reste le moyen d'imprimer a la demande.
        _open_externally(pdf_path)
        return False

    try:
        used = receipt_printer.print_pdf(pdf_path, settings.get("receipt_printer") or "")
    except Exception as exc:
        light_warning(
            parent,
            "Ticket non imprimé",
            f"{reference} est bien enregistrée — ne la refaites pas.\n\n"
            f"Seule l'impression a échoué : {exc}\n\n"
            "Le ticket va s'ouvrir à l'écran ; vous pouvez l'imprimer "
            "manuellement, ou régler l'imprimante dans Paramètres.",
        )
        try:
            _open_externally(pdf_path)
        except Exception:
            light_information(
                parent,
                "Ticket",
                f"{reference} est enregistrée.\nTicket enregistré ici :\n{pdf_path}",
            )
        return False

    if not silent_success:
        light_information(parent, "Ticket", f"Ticket envoyé à « {used} ».")
    return True
