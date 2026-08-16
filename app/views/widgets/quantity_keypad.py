"""Clavier numerique tactile pour saisir une quantite.

Remplace les boutons + / - du panier : sur un ecran de caisse, corriger une
quantite de 1 a 12 demandait onze appuis. Ici on tape la valeur directement.

Le clavier s'adapte a ce qu'on saisit :
  - piece  -> entiers uniquement, pas de separateur decimal
  - kg / L -> jusqu'a 3 decimales
  - gramme -> entiers, en grammes (la conversion en kg reste a l'appelant)
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

# Assez grand pour etre frappe au doigt sans viser.
_KEY_H = 62
_KEY_MIN_W = 78
_MAX_DECIMALS = 3

_QSS = """
QDialog { background: #FFFFFF; }
QLabel { background: transparent; border: none; }

QLabel#kpTitle    { font-size: 16px; font-weight: 700; color: #0F172A; }
QLabel#kpSubtitle { font-size: 12px; color: #64748B; }

QFrame#kpDisplayFrame {
    background: #F8FAFC; border: 2px solid #CBD5E1; border-radius: 12px;
}
QFrame#kpDisplayFrame QLabel { background: transparent; }
QLabel#kpDisplay  { font-size: 34px; font-weight: 800; color: #0F172A; }
QLabel#kpUnit     { font-size: 14px; font-weight: 700; color: #64748B; padding-bottom: 8px; }
QLabel#kpError    { font-size: 12px; font-weight: 700; color: #DC2626; }

QPushButton#kpDigit {
    background: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 12px;
    font-size: 24px; font-weight: 700; color: #0F172A;
}
QPushButton#kpDigit:hover   { border-color: #059669; color: #059669; }
QPushButton#kpDigit:pressed { background: #ECFDF5; }

QPushButton#kpAction {
    background: #F1F5F9; border: 1.5px solid #CBD5E1; border-radius: 12px;
    font-size: 17px; font-weight: 700; color: #475569;
}
QPushButton#kpAction:hover   { border-color: #DC2626; color: #DC2626; }

QPushButton#kpValidate {
    background: #059669; border: none; border-radius: 12px;
    font-size: 17px; font-weight: 800; color: #FFFFFF;
}
QPushButton#kpValidate:hover    { background: #047857; }
QPushButton#kpValidate:disabled { background: #E5E7EB; color: #9CA3AF; }

QPushButton#kpCancel {
    background: transparent; border: 1.5px solid #CBD5E1; border-radius: 12px;
    font-size: 15px; font-weight: 700; color: #64748B;
}
QPushButton#kpCancel:hover { border-color: #DC2626; color: #DC2626; }
"""


class QuantityKeypadDialog(QDialog):
    """Saisie d'une quantite au clavier numerique.

    `maximum` est la quantite disponible en stock : elle est verifiee au fur
    et a mesure de la frappe, pour que le caissier voie le probleme avant de
    valider plutot qu'un refus apres coup.
    """

    def __init__(
        self,
        product_name: str,
        unit_label: str,
        *,
        allow_decimals: bool = False,
        initial: float | int | None = None,
        maximum: float | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._allow_decimals = allow_decimals
        self._maximum = maximum
        self._buffer = ""
        # La valeur de depart s'efface des la premiere touche : on corrige une
        # quantite bien plus souvent qu'on ne l'allonge.
        self._replace_on_next_digit = True
        if initial:
            self._buffer = (
                f"{float(initial):.3f}".rstrip("0").rstrip(".")
                if allow_decimals
                else str(int(round(float(initial))))
            )

        self.setWindowTitle("Quantité")
        self.setModal(True)
        self.setStyleSheet(_QSS)
        # Largeur figée : sinon la boîte se rétrécit ou s'élargit selon la
        # longueur du nom du produit, et les touches changent de taille d'un
        # article à l'autre — déroutant quand on frappe sans regarder.
        self.setFixedWidth(360)
        self._build_ui(product_name, unit_label)
        self._refresh()

    # ── Construction ────────────────────────────────────────────────────

    def _build_ui(self, product_name: str, unit_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        # ── En-tete : quel produit, et combien il en reste ───────────────
        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel(product_name)
        title.setObjectName("kpTitle")
        title.setWordWrap(True)
        header.addWidget(title)
        if self._maximum is not None:
            sub = QLabel(f"Stock disponible : {self._format_number(self._maximum)} {unit_label}")
            sub.setObjectName("kpSubtitle")
            header.addWidget(sub)
        root.addLayout(header)

        # ── Ecran : la valeur et son unite dans le meme cadre, avec la
        #    touche d'effacement total juste a cote (elle agit sur l'ecran,
        #    sa place est donc ici et pas noyee dans le pave de chiffres).
        display_row = QHBoxLayout()
        display_row.setSpacing(10)

        display_frame = QFrame()
        display_frame.setObjectName("kpDisplayFrame")
        display_inner = QHBoxLayout(display_frame)
        display_inner.setContentsMargins(18, 0, 18, 0)
        display_inner.setSpacing(8)
        self._display = QLabel()
        self._display.setObjectName("kpDisplay")
        self._display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        display_inner.addWidget(self._display, 1)
        unit = QLabel(unit_label)
        unit.setObjectName("kpUnit")
        unit.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        display_inner.addWidget(unit, 0)
        display_frame.setMinimumHeight(68)
        display_row.addWidget(display_frame, 1)

        clear = QPushButton("C")
        clear.setObjectName("kpAction")
        clear.setFixedWidth(60)
        clear.setMinimumHeight(68)
        clear.setCursor(Qt.PointingHandCursor)
        clear.setToolTip("Tout effacer")
        clear.clicked.connect(self._clear)
        display_row.addWidget(clear, 0)
        root.addLayout(display_row)

        self._error = QLabel("")
        self._error.setObjectName("kpError")
        self._error.setAlignment(Qt.AlignRight)
        self._error.setMinimumHeight(16)  # reserve la place : pas de saut
        root.addWidget(self._error)

        # ── Pave 3x4, sans trou ni case surdimensionnee ──────────────────
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, digit in enumerate("789456123"):
            grid.addWidget(self._digit_button(digit), index // 3, index % 3)

        # Derniere rangee : separateur (si utile), 0, effacement arriere.
        # Sans decimales il n'y a pas de separateur a placer : le 0 occupe
        # les deux cases plutot que de laisser un trou dans la grille.
        if self._allow_decimals:
            grid.addWidget(self._digit_button(","), 3, 0)
            grid.addWidget(self._digit_button("0"), 3, 1)
        else:
            grid.addWidget(self._digit_button("0"), 3, 0, 1, 2)

        back = QPushButton("⌫")
        back.setObjectName("kpAction")
        back.setMinimumHeight(_KEY_H)
        back.setCursor(Qt.PointingHandCursor)
        back.setToolTip("Effacer le dernier chiffre")
        back.clicked.connect(self._backspace)
        grid.addWidget(back, 3, 2)

        for column in range(3):
            grid.setColumnStretch(column, 1)
        root.addLayout(grid)

        # ── Pied : ordre habituel, Valider mis en avant sans ecraser ─────
        footer = QHBoxLayout()
        footer.setSpacing(10)
        cancel = QPushButton("Annuler")
        cancel.setObjectName("kpCancel")
        cancel.setMinimumHeight(52)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self._btn_validate = QPushButton("Valider")
        self._btn_validate.setObjectName("kpValidate")
        self._btn_validate.setMinimumHeight(52)
        self._btn_validate.setCursor(Qt.PointingHandCursor)
        self._btn_validate.clicked.connect(self.accept)
        footer.addWidget(cancel, 1)
        footer.addWidget(self._btn_validate, 2)
        root.addLayout(footer)

    def _digit_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("kpDigit")
        btn.setMinimumHeight(_KEY_H)
        btn.setMinimumWidth(_KEY_MIN_W)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, t=text: self._append(t))
        return btn

    # ── Saisie ──────────────────────────────────────────────────────────

    def _append(self, key: str) -> None:
        if self._replace_on_next_digit:
            self._buffer = ""
            self._replace_on_next_digit = False

        if key == ",":
            if not self._allow_decimals or "." in self._buffer:
                return
            self._buffer = (self._buffer or "0") + "."
        else:
            whole, _, decimals = self._buffer.partition(".")
            if "." in self._buffer and len(decimals) >= _MAX_DECIMALS:
                return
            if "." not in self._buffer and len(whole) >= 6:
                return  # garde-fou : au-dela, c'est une faute de frappe
            self._buffer = ("" if self._buffer == "0" else self._buffer) + key

        self._refresh()

    def _backspace(self) -> None:
        self._replace_on_next_digit = False
        self._buffer = self._buffer[:-1]
        self._refresh()

    def _clear(self) -> None:
        self._replace_on_next_digit = False
        self._buffer = ""
        self._refresh()

    def keyPressEvent(self, event):
        """Le pave numerique du clavier physique fait la meme chose."""
        text = event.text()
        if text.isdigit():
            self._append(text)
            return
        if text in (",", "."):
            self._append(",")
            return
        key = event.key()
        if key == Qt.Key_Backspace:
            self._backspace()
            return
        if key in (Qt.Key_Delete, Qt.Key_Escape) and self._buffer:
            self._clear()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._btn_validate.isEnabled():
                self.accept()
            return
        super().keyPressEvent(event)

    # ── Affichage ───────────────────────────────────────────────────────

    @staticmethod
    def _format_number(value: float) -> str:
        text = f"{float(value):.3f}".rstrip("0").rstrip(".")
        return text or "0"

    def _refresh(self) -> None:
        self._display.setText((self._buffer or "0").replace(".", ","))

        value = self.value()
        message = ""
        if value <= 0:
            message = "Saisissez une quantité supérieure à 0"
        elif self._maximum is not None and value > float(self._maximum) + 0.0005:
            message = f"Stock insuffisant : {self._format_number(self._maximum)} disponible(s)"
        self._error.setText(message)
        self._btn_validate.setEnabled(not message)

    # ── Resultat ────────────────────────────────────────────────────────

    def value(self) -> float:
        try:
            return round(float(self._buffer or 0), _MAX_DECIMALS)
        except ValueError:
            return 0.0


def ask_quantity(
    parent,
    product_name: str,
    unit_label: str,
    *,
    allow_decimals: bool = False,
    initial: float | int | None = None,
    maximum: float | None = None,
) -> float | None:
    """Ouvre le clavier et renvoie la quantite saisie, ou None si annule."""
    dialog = QuantityKeypadDialog(
        product_name,
        unit_label,
        allow_decimals=allow_decimals,
        initial=initial,
        maximum=maximum,
        parent=parent,
    )
    if dialog.exec() != QDialog.Accepted:
        return None
    value = dialog.value()
    return value if value > 0 else None
