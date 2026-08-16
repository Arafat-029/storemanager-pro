from __future__ import annotations
import sys
import shutil
from pathlib import Path

# Clear stale bytecode cache so updated .py files are always be used
_root = Path(__file__).parent
for _d in list(_root.rglob("__pycache__")):
    shutil.rmtree(_d, ignore_errors=True)

# Make sure the store_management package is importable
sys.path.insert(0, str(_root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

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

    try:
        init_schema()
        _load_selected_theme(app)
    except Exception as e:
        QMessageBox.critical(None, "Erreur base de données", str(e))
        sys.exit(1)

    login = LoginDialog()
    if login.exec() != LoginDialog.Accepted:
        sys.exit(0)

    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
