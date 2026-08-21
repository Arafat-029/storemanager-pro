from __future__ import annotations
import sys
import shutil
from pathlib import Path

_root = Path(__file__).parent

# Purge du bytecode périmé : utile en développement, où l'on édite les .py
# entre deux lancements. Sautée une fois empaquetée — il n'y a plus de
# sources à recompiler, et le balayage porterait sur le dossier temporaire
# d'extraction de PyInstaller, qu'il ne faut surtout pas toucher.
if not getattr(sys, "frozen", False):
    for _d in list(_root.rglob("__pycache__")):
        shutil.rmtree(_d, ignore_errors=True)
    # Rend le paquet importable quand on lance depuis les sources.
    sys.path.insert(0, str(_root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

import config
from config import APP_NAME, APP_VERSION, ASSETS_DIR, DEFAULT_THEME
from app.database.schema import init_schema
from app.database.connection import db
from app.views.login_dialog import LoginDialog
from app.views.main_window import MainWindow
from app.views.widgets.form_behavior import install_form_field_guard
from app.utils import crash_handler


def _load_selected_theme(app: QApplication) -> None:
    row = db.fetchone("SELECT value FROM settings WHERE `key`='theme'")
    theme_name = (row or {}).get("value") or DEFAULT_THEME
    theme_path = ASSETS_DIR / "themes" / f"{theme_name}.qss"
    if not theme_path.exists():
        theme_path = ASSETS_DIR / "themes" / f"{DEFAULT_THEME}.qss"
    if theme_path.exists():
        app.setStyleSheet(theme_path.read_text(encoding="utf-8"))


def _run_diagnostic(app) -> int:
    """Contrôle d'installation, lancé par « StoreManagerPro.exe --check ».

    Une fois empaquetée, l'application n'a plus de console : le résultat
    s'affiche donc dans une fenêtre, lisible par la personne sur place, et
    s'écrit dans le dossier de données pour être transmis au dépannage.
    """
    lignes: list[str] = []
    ok = True

    def verifie(libelle: str, reussi: bool, detail: str = "") -> None:
        nonlocal ok
        lignes.append(("[ OK ]  " if reussi else "[ÉCHEC] ") + libelle + (f"  → {detail}" if detail else ""))
        if not reussi:
            ok = False

    lignes.append(f"{APP_NAME} {APP_VERSION}")
    lignes.append(f"Programme : {config.RESOURCE_DIR}")
    lignes.append(f"Données   : {config.DATA_DIR}")
    lignes.append(f"Config    : {config.ENV_FILE}")
    lignes.append("")

    verifie("Fichier de configuration présent", config.ENV_FILE.is_file())
    verifie("Thème graphique accessible", (config.THEMES_DIR / "light.qss").is_file())

    ui_dir = config.RESOURCE_DIR / "app" / "ui"
    formulaires = list(ui_dir.glob("*.ui"))
    verifie(f"Formulaires d'écran ({len(formulaires)})", len(formulaires) >= 30)

    try:
        from pyzbar.pyzbar import decode  # noqa: F401
        verifie("Lecture de codes-barres", True)
    except Exception as exc:
        verifie("Lecture de codes-barres", False, str(exc)[:60])

    try:
        import cv2  # noqa: F401
        verifie("Caméra (OpenCV)", True)
    except Exception as exc:
        verifie("Caméra (OpenCV)", False, str(exc)[:60])

    try:
        from app.database.connection import db
        db.get_connection()
        verifie("Connexion à la base de données", True, config.MYSQL_DATABASE or "SQLite")
    except Exception as exc:
        verifie("Connexion à la base de données", False, str(exc)[:90])
    else:
        # Le diagnostic tourne juste après l'installation, avant le premier
        # lancement : la base est alors vide. Créer les tables ici plutôt que
        # d'échouer sur « Table products doesn't exist » — l'opération est
        # sans effet si elles existent déjà, et rend la caisse utilisable
        # dès la fin de l'installation.
        try:
            init_schema()
            total = db.fetchone("SELECT COUNT(*) AS n FROM products")["n"]
            verifie("Tables de la base", True, f"{total} produit(s)")
        except Exception as exc:
            verifie("Tables de la base", False, str(exc)[:90])

    try:
        from app.utils import receipt_printer
        imprimantes = receipt_printer.available_printers()
        utilisee = receipt_printer.effective_printer_name()
        verifie(f"Imprimantes détectées ({len(imprimantes)})", bool(imprimantes), utilisee)
        if utilisee and receipt_printer.is_virtual_printer(utilisee):
            lignes.append(f"[AVIS]  « {utilisee} » enregistre un fichier au lieu d'imprimer sur papier.")
    except Exception as exc:
        verifie("Imprimantes", False, str(exc)[:60])

    lignes.append("")
    lignes.append("RÉSULTAT : " + ("PRÊT" if ok else "CORRECTIONS NÉCESSAIRES"))
    rapport = "\n".join(lignes)

    try:
        config.ensure_dirs()
        (config.LOGS_DIR / "diagnostic.txt").write_text(rapport, encoding="utf-8")
    except Exception:
        pass

    box = QMessageBox()
    box.setWindowTitle("Diagnostic de l'installation")
    box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
    box.setText(rapport)
    box.exec()
    return 0 if ok else 1


def main():
    # Qt6 keeps per-monitor DPI scaling on by default (correct for touch
    # targets on high-density POS screens), but its default rounding policy
    # snaps fractional factors (125%, 150%...) to the nearest integer. That's
    # harmless on one screen, but across two monitors running different
    # scale factors (e.g. a 125% laptop panel next to a 100% external
    # display) it makes the same logical size drift out of sync between
    # them. PassThrough applies the exact factor on each screen instead.
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Filet de sécurité : une erreur imprévue est journalisée et expliquée au
    # caissier, au lieu de disparaître en silence ou de fermer la caisse.
    crash_handler.install(app)

    import platform
    font_family = "Segoe UI" if platform.system() == "Windows" else (
        "SF Pro Display" if platform.system() == "Darwin" else "Ubuntu"
    )
    font = QFont(font_family, 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # Uniform form behaviour everywhere (admin and cashier): the wheel never
    # edits a dropdown/spin box, and arrow keys never change a closed dropdown.
    install_form_field_guard(app)

    if "--check" in sys.argv:
        sys.exit(_run_diagnostic(app))

    try:
        init_schema()
        _load_selected_theme(app)
    except Exception as e:
        # Message actionnable plutôt que l'erreur brute du pilote : sur la
        # caisse, la personne devant l'écran n'est pas développeuse et doit
        # pouvoir agir (ou dire quoi transmettre) sans traduire un code
        # d'erreur MySQL.
        details = str(e)
        conseils = [
            f"Fichier de configuration attendu :\n{config.ENV_FILE}",
        ]
        if not config.ENV_FILE.is_file():
            conseils.insert(0, "Ce fichier est ABSENT : la configuration de la base n'a jamais été créée.")
        elif config.DB_BACKEND == "mysql":
            conseils.insert(0, (
                "Vérifiez que le service MySQL est démarré "
                "(Windows : services.msc → MySQL), puis que l'identifiant et "
                "le mot de passe du fichier ci-dessus sont corrects."
            ))
        QMessageBox.critical(
            None,
            "Impossible de démarrer",
            "L'application n'a pas pu ouvrir sa base de données.\n\n"
            + "\n\n".join(conseils)
            + f"\n\nDétail technique :\n{details}",
        )
        sys.exit(1)

    login = LoginDialog()
    if login.exec() != LoginDialog.Accepted:
        sys.exit(0)

    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
