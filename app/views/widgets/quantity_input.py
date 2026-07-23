from __future__ import annotations

from PySide6.QtGui import QValidator, QWheelEvent
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox


class QuantitySpinBox(QDoubleSpinBox):
    """Manual quantity input.

    - piece -> integer only
    - kg/litre -> 3 decimals
    Mouse wheel is ignored to avoid accidental edits.
    """

    def __init__(self, unit_type: str = "piece", parent=None):
        super().__init__(parent)
        self.setMinimum(0.0)
        self.setMaximum(999_999.999)
        self.setKeyboardTracking(False)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.configure_for_unit(unit_type)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def configure_for_unit(self, unit_type: str) -> None:
        self._unit_type = unit_type or "piece"
        decimals = 0 if self._unit_type == "piece" else 3
        self.setDecimals(decimals)
        self.setSingleStep(1 if decimals == 0 else 0.001)
        if le := self.lineEdit():
            le.setPlaceholderText("0" if decimals == 0 else "0.000")

    def _clean(self, text: str) -> str:
        return text.replace(" ", "").replace(" ", "").replace("\xa0", "").strip()

    def textFromValue(self, value: float) -> str:
        if self.decimals() == 0:
            return str(int(round(value)))
        int_str, dec_str = f"{value:.3f}".split(".")
        int_fmt = f"{int(int_str):,}".replace(",", " ")
        return f"{int_fmt}.{dec_str}"

    def valueFromText(self, text: str) -> float:
        clean = self._clean(text)
        if not clean:
            return 0.0
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def validate(self, text: str, pos: int):
        clean = self._clean(text)
        if not clean:
            return (QValidator.State.Acceptable, text, pos)
        if self.decimals() == 0:
            return (
                (QValidator.State.Acceptable if clean.isdigit() else QValidator.State.Invalid),
                text,
                pos,
            )
        if clean.isdigit():
            return (QValidator.State.Intermediate, text, pos)
        if clean.count(".") == 1:
            left, right = clean.split(".", 1)
            if (not left or left.isdigit()) and right.isdigit() and len(right) <= 3:
                return (QValidator.State.Acceptable, text, pos)
        return (QValidator.State.Invalid, text, pos)

def configure_manual_spinbox(spin: QDoubleSpinBox, *, decimals: int | None = None, placeholder: str | None = None) -> QDoubleSpinBox:
    spin.setKeyboardTracking(False)
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    if decimals is not None:
        spin.setDecimals(decimals)
    if placeholder is not None and spin.lineEdit():
        spin.lineEdit().setPlaceholderText(placeholder)
    spin.wheelEvent = lambda event: event.ignore()
    return spin
