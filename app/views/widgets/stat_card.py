from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class StatCard(QFrame):
    """A KPI stat card with a compact rounded style."""

    def __init__(self, title: str, value: str = "0", icon: str = "📊",
                 color: str = "#7B8CDE", colored: bool = False, parent=None):
        super().__init__(parent)
        self._color = color
        self._colored = colored

        if colored:
            self.setObjectName("statCardColored")
            self.setStyleSheet(
                f"#statCardColored {{ background: {color}; border-radius: 18px; }}"
            )
        else:
            self.setObjectName("statCard")
            self.setStyleSheet(
                "#statCard { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 18px; }"
            )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(8)

        self._label = QLabel(title)
        self._label.setObjectName("cardLabel")

        self._value = QLabel(value)
        self._value.setObjectName("cardValue")

        if colored:
            self._label.setStyleSheet("color: rgba(255,255,255,0.88); font-size: 11px; font-weight: 700;")
            self._value.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 800;")
        else:
            self._label.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700;")
            self._value.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: 800;")

        left.addWidget(self._label)
        left.addWidget(self._value)
        left.addStretch()

        icon_lbl = QLabel(icon)
        icon_style = "font-size: 36px;"
        if colored:
            icon_style += " color: rgba(255,255,255,0.82);"
        else:
            icon_style += f" color: {color};"
        icon_lbl.setStyleSheet(icon_style)
        icon_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addLayout(left, 1)
        layout.addWidget(icon_lbl)

    def set_value(self, value: str):
        self._value.setText(value)
