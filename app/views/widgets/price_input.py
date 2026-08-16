from __future__ import annotations
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox
from PySide6.QtGui import QValidator, QWheelEvent


class PriceSpinBox(QDoubleSpinBox):
    """Manual entry spinbox for Tunisian dinar amounts (X.XXX format).

    Mouse wheel is ignored to prevent accidental changes.

    Cash-register convention: plain digits fill in from the millime up (1
    TND = 1000 millimes), so "50" becomes 0.050 and "1000" becomes 1.000 —
    never fifty or a thousand dinars. Typing an explicit decimal point
    ("12.5") is still taken literally as 12.500. A comma is treated the same
    as a dot, since the app only ever displays/accepts "." as the separator.
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
        s = s.replace(" ", "").replace(" ", "").replace("\xa0", "").strip()
        return s.replace(",", ".")

    def valueFromText(self, text: str) -> float:
        clean = self._clean(text)
        if not clean:
            return 0.0
        if clean.isdigit():
            # Cash-register convention: raw digits fill in from the millime
            # up, so "50" means 0.050 TND and "1000" means 1.000 TND.
            return int(clean) / 1000.0
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
            val = self.valueFromText(text)
            return self.textFromValue(val) if val > 0 else ""
        return text
