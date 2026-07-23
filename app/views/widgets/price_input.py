from __future__ import annotations
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox
from PySide6.QtGui import QValidator, QWheelEvent


class PriceSpinBox(QDoubleSpinBox):
    """Manual entry spinbox for Tunisian dinar amounts (X.XXX format).

    Mouse wheel is ignored to prevent accidental changes.
    Integer input is kept as dinars:
    10 -> 10.000, 20 -> 20.000
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(3)
        self.setMaximum(9_999_999.999)
        self.setMinimum(0.0)
        self.setKeyboardTracking(False)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setSpecialValueText("")
        if le := self.lineEdit():
            le.setPlaceholderText("0.000")

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def textFromValue(self, v: float) -> str:
        if v == 0.0:
            return ""
        s = f"{v:.3f}"
        int_str, dec_str = s.split(".")
        int_fmt = f"{int(int_str):,}".replace(",", " ")
        return f"{int_fmt}.{dec_str}"

    def _clean(self, text: str) -> str:
        s = text
        if sfx := self.suffix():
            s = s.replace(sfx, "")
        if pfx := self.prefix():
            s = s.replace(pfx, "")
        return s.replace(" ", "").replace(" ", "").replace("\xa0", "").strip()

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
        if clean.isdigit():
            return (QValidator.State.Intermediate, text, pos)
        if clean.count(".") == 1:
            try:
                float(clean)
                return (QValidator.State.Acceptable, text, pos)
            except ValueError:
                pass
        return (QValidator.State.Invalid, text, pos)

    def fixup(self, text: str) -> str:
        clean = self._clean(text)
        if not clean or clean == "0":
            return ""
        if "." not in clean and clean.isdigit():
            try:
                val = float(clean)
                return self.textFromValue(val) if val > 0 else ""
            except ValueError:
                pass
        return text
