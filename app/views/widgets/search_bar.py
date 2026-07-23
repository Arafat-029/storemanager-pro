from __future__ import annotations
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt, Signal, QTimer


class SearchBar(QLineEdit):
    search_changed = Signal(str)

    def __init__(self, placeholder: str = "Rechercher...", debounce_ms: int = 300, parent=None):
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setPlaceholderText(placeholder)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit)
        self.textChanged.connect(lambda: self._timer.start(debounce_ms))

    def _emit(self):
        self.search_changed.emit(self.text().strip())
