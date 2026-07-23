"""Central QUiLoader helper used by every view and dialog in this project.

Usage
-----
    from app.ui.ui_loader import load_ui

    class MyDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._ui = load_ui("my_dialog.ui", self)
            # widgets are accessible as attributes: self._ui.btnSave, etc.
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QObject
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.views.widgets.price_input import PriceSpinBox

_UI_DIR = Path(__file__).parent


def _bind_named_children(target: QWidget, source: QObject | None = None) -> QWidget:
    """Expose named child widgets as attributes on *target*.

    The binding source defaults to the target itself, but callers may bind
    children discovered in a loaded UI tree onto another container such as the
    hosting QDialog.
    """
    source = source or target
    for child in source.findChildren(QObject):
        name = child.objectName().strip()
        if not name or name.startswith("qt_") or hasattr(target, name):
            continue
        setattr(target, name, child)
    return target


def load_ui(ui_name: str, parent: QWidget | None = None) -> QWidget:
    """Load a .ui file from app/ui/ and return the top-level widget."""
    loader = QUiLoader()
    loader.registerCustomWidget(PriceSpinBox)

    path = _UI_DIR / ui_name
    f = QFile(str(path))
    if not f.open(QIODevice.ReadOnly):
        raise FileNotFoundError(f"UI file not found: {path}")
    widget = loader.load(f, parent)
    f.close()

    if widget is None:
        raise RuntimeError(f"QUiLoader failed to load: {path}")
    return _bind_named_children(widget)


def embed_ui(dialog: QWidget, ui_name: str) -> QWidget:
    """Load a .ui file and embed it as the sole child of *dialog*."""
    ui = load_ui(ui_name, dialog)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(ui)
    _bind_named_children(dialog, ui)
    return ui
