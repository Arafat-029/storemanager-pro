"""Filet de securite global contre les erreurs imprevues.

Sans cela, une exception non rattrapee dans un bouton fait, selon les cas,
disparaitre l'action sans un mot ou fermer l'application d'un coup — en
pleine file d'attente, sans trace exploitable pour comprendre apres coup.

Ici, toute exception non rattrapee est :
  1. ecrite dans data/logs/erreurs.log (avec la trace complete) ;
  2. montree au caissier en francais, avec la consigne de verifier la vente
     avant de la refaire, jamais un message technique brut ;
  3. absorbee, pour que l'application reste ouverte : fermer une caisse au
     milieu d'un encaissement coute plus cher que l'erreur elle-meme.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
LOG_FILE = LOG_DIR / "erreurs.log"

_MESSAGE = (
    "Une erreur inattendue s'est produite.\n\n"
    "L'application reste ouverte et vos donnees enregistrees ne sont pas "
    "affectees.\n\n"
    "Si vous etiez en train d'encaisser, VERIFIEZ dans l'historique des "
    "ventes si la vente a ete enregistree avant de la refaire.\n\n"
    "Details techniques : {summary}\n"
    "Journal : {log}"
)


def _write_log(exc_type, exc_value, exc_tb) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{'=' * 70}\n{datetime.now():%Y-%m-%d %H:%M:%S}\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)
    except Exception:
        pass  # ne jamais laisser l'ecriture du journal masquer l'erreur


def install(app=None) -> None:
    """Branche le gestionnaire sur sys.excepthook."""

    def handle(exc_type, exc_value, exc_tb):
        # Ctrl+C garde son comportement normal.
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        _write_log(exc_type, exc_value, exc_tb)
        traceback.print_exception(exc_type, exc_value, exc_tb)

        summary = f"{exc_type.__name__}: {exc_value}"
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical)
                box.setWindowTitle("Erreur inattendue")
                box.setText(_MESSAGE.format(summary=summary[:300], log=LOG_FILE))
                box.setStandardButtons(QMessageBox.Ok)
                box.exec()
        except Exception:
            pass  # pas d'interface disponible : le journal suffit

        try:
            from app.controllers.auth_controller import AuthController

            AuthController.log("APP_ERROR", summary[:400])
        except Exception:
            pass  # la base est peut-etre justement la cause de l'erreur

    sys.excepthook = handle
