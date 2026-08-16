from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controllers.supplier_controller import SupplierController
from app.utils.helpers import format_price
from app.views.widgets.price_input import PriceSpinBox
from app.views.widgets.quantity_input import QuantitySpinBox, configure_manual_spinbox
from app.views.widgets.screen_fit import clamp_min_size
from app.views.dialog_theme import light_question, light_warning, light_information, light_critical


_WHITE_QSS = (
    "QDialog, QWidget, QFrame { background: #FFFFFF; color: #111827; }"
    "QLabel { background: transparent; color: #111827; }"
    "QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {"
    "  background: #F9FAFB; color: #111827; border: 1.5px solid #D1D5DB; border-radius: 8px; padding: 9px 12px; }"
    "QComboBox { padding-right: 48px; }"
    "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 38px; border: none; background: transparent; }"
    "QComboBox::down-arrow { width: 12px; height: 12px; margin-right: 12px; }"
    "QComboBox QAbstractItemView::item { background: #FFFFFF; color: #111827; }"
    "QComboBox QAbstractItemView::item:hover { background: #E0F2FE; color: #0F172A; }"
    "QComboBox QAbstractItemView::item:selected { background: #DBEAFE; color: #1D4ED8; }"
    "QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {"
    "  border-color: #059669; background: #FAFFFE; }"
    "QPushButton { background: #059669; color: white; border: none;"
    "  border-radius: 8px; padding: 9px 18px; font-weight: 600; }"
    "QPushButton:hover { background: #10B981; }"
    "QPushButton:pressed { background: #047857; }"
    "QPushButton:disabled { background: #E5E7EB; color: #9CA3AF; }"
    "QPushButton#btnSecondary, QPushButton[cssClass=\"btnSecondary\"] { background: transparent; border: 1.5px solid #D1D5DB; color: #6B7280; }"
    "QPushButton#btnSecondary:hover, QPushButton[cssClass=\"btnSecondary\"]:hover { border-color: #059669; color: #111827; background: #F0FDF4; }"
    "QPushButton#btnDanger, QPushButton[cssClass=\"btnDanger\"] { background: #E5E7EB; color: #374151; border: 1.5px solid #CBD5E1; }"
    "QPushButton#btnDanger:hover, QPushButton[cssClass=\"btnDanger\"]:hover { background: #D1D5DB; color: #111827; }"
    "QPushButton#btnSuccess, QPushButton[cssClass=\"btnSuccess\"] { background: #059669; color: white; }"
    "QPushButton#btnWarning, QPushButton[cssClass=\"btnWarning\"] { background: #F59E0B; color: white; }"
    "QPushButton#btnSm { padding: 7px 12px; font-size: 12px; min-height: 30px; }"
    "QTableWidget { background: #FFFFFF; color: #111827; border: 1.5px solid #E5E7EB;"
    "  border-radius: 10px; alternate-background-color: #F9FAFB; gridline-color: #F9FAFB; }"
    "QTableWidget::item { color: #374151; background: transparent; padding: 10px 8px; }"
    "QTableWidget::item:selected { background: rgba(16,185,129,0.1); color: #111827; }"
    "QHeaderView::section { background: #F9FAFB; color: #9CA3AF; border: none;"
    "  border-bottom: 2px solid #E5E7EB; font-weight: 700; font-size: 11px; padding: 10px 8px; }"
    "QHeaderView { background: transparent; border: none; }"
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; height: 0; border: 0; }"
    "QScrollBar:vertical { background: transparent; width: 5px; border-radius: 3px; }"
    "QScrollBar::handle:vertical { background: #D1D5DB; border-radius: 3px; min-height: 30px; }"
    "QScrollBar::handle:vertical:hover { background: #059669; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    "QFrame#separator, QFrame[cssClass=\"separator\"] { background: #E5E7EB; max-height: 1px; border: none; }"
)


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setStyleSheet("background: #D1D5DB; max-width: 1px; border: none; margin: 4px 8px;")
    return sep


_SUPPLIER_ACTION_BTN_H = 32  # fixed height for each of the 4 action buttons
# QTableWidget::item { padding: 11px 10px } in the theme also insets the rect
# a setCellWidget() is placed into (not just painted QTableWidgetItems), so
# the actions cell actually only ever gets row_height - 22px of real height —
# without adding it back here the button grid was squeezed into ~22px less
# space than intended, silently eating the vertical spacing between the two
# button rows until they nearly touched.
_SUPPLIER_ITEM_VPADDING = 22
# Row tall enough for a 2x2 button grid at that height plus generous, even
# margins on every side (14px) and spacing between buttons (12px) — this
# exact number is also what _limit_supplier_table_height() sums per row, so
# the two can never drift apart and silently produce a vertical scrollbar.
_SUPPLIER_ROW_H = (2 * _SUPPLIER_ACTION_BTN_H) + 12 + (2 * 14) + _SUPPLIER_ITEM_VPADDING


def _money_item(value: float, color: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(format_price(value))
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if color:
        item.setForeground(QColor(color))
    return item


def _format_invoice_quantity(value: float, unit_type: str) -> str:
    unit = (unit_type or "piece").strip().lower()
    qty = float(value or 0.0)
    if unit == "piece" and abs(qty - round(qty)) < 0.001:
        return f"{int(round(qty))} pcs"
    if unit == "kg":
        return f"{qty:.3f}".rstrip("0").rstrip(".") + " kg"
    if unit == "litre":
        return f"{qty:.3f}".rstrip("0").rstrip(".") + " L"
    return f"{qty:.3f}".rstrip("0").rstrip(".")

def _invoice_items_summary_widget(items: list[dict]) -> QWidget:
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(3)

    if not items:
        empty = QLabel("Montant manuel")
        empty.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(empty)
        return wrap

    max_visible = 6
    for item in items[:max_visible]:
        qty_text = _format_invoice_quantity(item.get("quantity") or 0, item.get("unit_type") or "piece")
        price_text = format_price(float(item.get("unit_price") or 0))
        text = f"• {item.get('product_name') or 'Produit'} — {qty_text} × {price_text}"
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11px; color: #111827; padding: 0;")
        lbl.setToolTip(text)
        layout.addWidget(lbl)

    if len(items) > max_visible:
        more = QLabel(f"+ {len(items) - max_visible} autre(s) produit(s)")
        more.setStyleSheet("font-size: 10px; color: #6B7280; font-style: italic;")
        layout.addWidget(more)

    layout.addStretch()
    return wrap


class SuppliersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Gestion des fournisseurs")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher par nom ou téléphone…")
        self._search.setFixedHeight(40)
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self.refresh)

        btn_add = QPushButton("＋  Nouveau fournisseur")
        btn_add.setFixedHeight(40)
        btn_add.clicked.connect(self._add_supplier)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._search)
        header.addWidget(btn_add)
        layout.addLayout(header)

        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet(
            "background: #EFF6FF; color: #1D4ED8; border-radius: 8px;"
            "padding: 8px 14px; font-size: 13px;"
        )
        layout.addWidget(self._stats_lbl)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Nom", "Téléphone", "Dernière facture",
            "Montant", "Payé", "Reste", "Actions",
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.ElideRight)
        self._table.setShowGrid(False)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Was ScrollBarAlwaysOn: forced a visible scrollbar even when every
        # row already fits (the table's own height is capped to exactly fit
        # its rows in _limit_supplier_table_height), which is why one always
        # showed up regardless of how many suppliers exist.
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._table.verticalHeader().setVisible(False)
        header_view = self._table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.Fixed)
        header_view.setSectionResizeMode(5, QHeaderView.Fixed)
        header_view.setSectionResizeMode(6, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 130)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 120)
        self._table.setColumnWidth(5, 120)
        self._table.setColumnWidth(6, 230)
        self._table.setMinimumHeight(140)
        layout.addWidget(self._table)
        layout.addStretch()

    def refresh(self):
        q = self._search.text().strip().lower()
        suppliers = SupplierController.get_all()
        if q:
            suppliers = [
                s
                for s in suppliers
                if q in s["name"].lower() or q in (s.get("phone") or "").lower()
            ]

        total_inv = sum(float(s.get("total_invoiced", 0)) for s in suppliers)
        total_paid = sum(float(s.get("total_paid", 0)) for s in suppliers)
        total_bal = sum(float(s.get("balance", 0)) for s in suppliers)

        self._stats_lbl.setText(
            f"  {len(suppliers)} fournisseur(s)   •   "
            f"Factures : {format_price(total_inv)}   •   "
            f"Payé : {format_price(total_paid)}   •   "
            f"Solde dû : {format_price(total_bal)}"
        )

        self._table.setRowCount(len(suppliers))
        for row, supplier in enumerate(suppliers):
            latest_invoice = SupplierController.get_latest_invoice(supplier["id"])

            self._table.setItem(row, 0, QTableWidgetItem(supplier["name"]))
            self._table.setItem(row, 1, QTableWidgetItem(supplier.get("phone") or "—"))

            latest_wrap = QWidget()
            latest_wrap.setStyleSheet("background: transparent;")
            latest_layout = QVBoxLayout(latest_wrap)
            latest_layout.setContentsMargins(8, 6, 8, 6)
            latest_layout.setSpacing(2)

            latest_title = QLabel("Aucune facture")
            latest_title.setWordWrap(True)
            latest_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #111827;")

            latest_meta = QLabel("Utilisez le bouton Historique pour consulter les factures.")
            latest_meta.setWordWrap(True)
            latest_meta.setStyleSheet("font-size: 10px; color: #6B7280;")

            amount_total = 0.0
            amount_paid = 0.0
            remaining = 0.0

            if latest_invoice:
                ref = latest_invoice.get("reference") or f"Facture #{latest_invoice['id']}"
                created_at = (latest_invoice.get("created_at") or "")[:16]
                latest_title.setText(ref)
                latest_meta.setText(f"Dernière facture : {created_at}")
                amount_total = float(latest_invoice.get("amount_total") or 0)
                amount_paid = float(latest_invoice.get("amount_paid") or 0)
                remaining = float(latest_invoice.get("remaining_amount") or 0)

            latest_layout.addWidget(latest_title)
            latest_layout.addWidget(latest_meta)
            self._table.setCellWidget(row, 2, latest_wrap)

            self._table.setItem(row, 3, _money_item(amount_total, "#D97706"))
            self._table.setItem(row, 4, _money_item(amount_paid, "#059669"))

            remaining_color = "#DC2626" if remaining > 0 else "#059669"
            self._table.setItem(row, 5, _money_item(remaining, remaining_color))
            self._table.setRowHeight(row, _SUPPLIER_ROW_H)

            actions = QWidget()
            actions.setStyleSheet("background: transparent;")
            act_lay = QGridLayout(actions)
            act_lay.setContentsMargins(14, 14, 14, 14)
            act_lay.setHorizontalSpacing(12)
            act_lay.setVerticalSpacing(12)
            act_lay.setColumnStretch(0, 1)
            act_lay.setColumnStretch(1, 1)

            def _action_btn(text: str, bg: str, fg: str, border: str = "none") -> QPushButton:
                btn = QPushButton(text)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.setStyleSheet(
                    "QPushButton {"
                    f"  font-size: 10px; font-weight: 700; background: {bg}; color: {fg};"
                    f"  border: {border}; border-radius: 6px; padding: 0 6px;"
                    # Explicit min/max-height: the app's global QPushButton rule
                    # also sets a min-height, and without an equally explicit
                    # override here it wins for whichever buttons don't
                    # separately match it via their border width, producing
                    # inconsistent per-button heights (buttons "too close
                    # together" because the grid was sized for the shortest one).
                    f"  min-height: {_SUPPLIER_ACTION_BTN_H}px; max-height: {_SUPPLIER_ACTION_BTN_H}px;"
                    "}"
                )
                return btn

            # Original color set, restored: Historique in amber, Payer in
            # green, Modifier neutral, Suppr. in slate — not the app's usual
            # secondary/danger palette, but this is what the supplier table
            # had before and is being kept as-is.
            btn_hist = _action_btn("Historique", "#F59E0B", "#FFFFFF")
            btn_hist.clicked.connect(
                lambda _, sid=supplier["id"], sn=supplier["name"]: self._manage_invoices(sid, sn)
            )

            btn_pay = _action_btn("Payer", "#059669", "#FFFFFF")
            btn_pay.clicked.connect(
                lambda _, sid=supplier["id"], sn=supplier["name"]: self._pay_supplier(sid, sn)
            )

            btn_edit = _action_btn("Modifier", "#E5E7EB", "#374151", "1px solid #CBD5E1")
            btn_edit.clicked.connect(lambda _, sid=supplier["id"]: self._edit_supplier(sid))

            btn_del = _action_btn("Suppr.", "#CBD5E1", "#1F2937", "1px solid #B6C2D1")
            btn_del.clicked.connect(
                lambda _, sid=supplier["id"], sn=supplier["name"]: self._delete_supplier(sid, sn)
            )

            act_lay.addWidget(btn_hist, 0, 0)
            act_lay.addWidget(btn_pay, 0, 1)
            act_lay.addWidget(btn_edit, 1, 0)
            act_lay.addWidget(btn_del, 1, 1)
            self._table.setCellWidget(row, 6, actions)

        self._limit_supplier_table_height(len(suppliers))

    def _limit_supplier_table_height(self, total_rows: int) -> None:
        visible_rows = max(1, min(total_rows, 10))
        header_h = self._table.horizontalHeader().height() or 36
        # Must match the row height actually applied in refresh() exactly
        # (_SUPPLIER_ROW_H) — any mismatch between an assumed row height here
        # and the real one is what produces an unwanted vertical scrollbar
        # even though every row is technically visible.
        frame_h = 12
        target_h = header_h + (visible_rows * _SUPPLIER_ROW_H) + frame_h
        self._table.setMinimumHeight(target_h)
        self._table.setMaximumHeight(target_h)


    def _add_supplier(self):
        dlg = SupplierDialog(parent=self)
        if dlg.exec():
            self.refresh()

    def _edit_supplier(self, supplier_id: int):
        supplier = SupplierController.get_by_id(supplier_id)
        if not supplier:
            return
        dlg = SupplierDialog(sup=supplier, parent=self)
        if dlg.exec():
            self.refresh()

    def _delete_supplier(self, supplier_id: int, name: str):
        reply = light_question(
            self,
            "Supprimer fournisseur",
            f"Voulez-vous vraiment supprimer «{name}» et tout son historique ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            SupplierController.delete(supplier_id)
            self.refresh()

    def _pay_supplier(self, supplier_id: int, name: str):
        dlg = SupplierInvoicesDialog(supplier_id, name, parent=self)
        if dlg.exec():
            self.refresh()

    def _manage_invoices(self, supplier_id: int, name: str):
        dlg = SupplierInvoicesDialog(supplier_id, name, parent=self)
        if dlg.exec():
            self.refresh()

    def _view_history(self, supplier_id: int, name: str):
        transactions = SupplierController.get_transactions(supplier_id)
        balance_info = SupplierController.get_balance(supplier_id)
        dlg = HistoryDialog(name, transactions, balance_info, parent=self)
        dlg.exec()


class SupplierDialog(QDialog):
    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background: transparent; border: none; padding: 0; margin: 0;"
            "color: #6B7280; font-size: 11px; font-weight: 600;"
        )
        return lbl

    def __init__(self, sup: dict = None, parent=None):
        super().__init__(parent)
        self._sup = sup
        self.setWindowTitle("Modifier" if sup else "Nouveau fournisseur")
        self.setFixedWidth(440)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui()
        if sup:
            self._name.setText(sup.get("name", ""))
            self._phone.setText(sup.get("phone") or "")
            self._notes.setPlainText(sup.get("notes") or "")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_lbl = QLabel("Modifier fournisseur" if self._sup else "Nouveau fournisseur")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 700; padding: 20px 24px 12px;")
        layout.addWidget(title_lbl)

        form = QFormLayout()
        form.setContentsMargins(24, 12, 24, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._name = QLineEdit()
        self._name.setMinimumHeight(38)
        self._name.setPlaceholderText("Nom du fournisseur *")

        self._phone = QLineEdit()
        self._phone.setMinimumHeight(38)
        self._phone.setPlaceholderText("+216 XX XXX XXX")

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(72)
        self._notes.setPlaceholderText("Notes (optionnel)")

        form.addRow(self._lbl("Nom *:"), self._name)
        form.addRow(self._lbl("Téléphone:"), self._phone)
        form.addRow(self._lbl("Notes:"), self._notes)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 8, 24, 20)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Le nom est obligatoire.")
            return
        data = {
            "name": name,
            "phone": self._phone.text().strip() or None,
            "email": None,
            "address": None,
            "notes": self._notes.toPlainText().strip() or None,
        }
        try:
            if self._sup:
                SupplierController.update(self._sup["id"], data)
            else:
                SupplierController.create(data)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))



class InvoiceDialog(QDialog):
    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background: transparent; border: none; padding: 0; margin: 0;"
            "color: #6B7280; font-size: 11px; font-weight: 600;"
        )
        return lbl

    def __init__(self, supplier_id: int, supplier_name: str, invoice: dict | None = None, parent=None):
        super().__init__(parent)
        self._supplier_id = supplier_id
        self._supplier_name = supplier_name
        self._invoice = invoice
        self._products = SupplierController.get_products_for_supplier(supplier_id)
        self._rows: list[tuple[PriceSpinBox, PriceSpinBox, QLabel, dict]] = []
        self._last_items_total = 0.0

        self.setWindowTitle("Modifier la facture" if invoice else "Ajouter une facture")
        clamp_min_size(self, 820, 520)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("Modifier la facture fournisseur" if self._invoice else "Nouvelle facture fournisseur")
        title.setStyleSheet("font-size: 15px; font-weight: 700; padding: 14px 16px 4px;")
        layout.addWidget(title)

        sub = QLabel(
            f"Fournisseur : <b>{self._supplier_name}</b><br>"
            "Sélectionnez les produits livrés puis saisissez quantité et prix d'achat."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 10px; color: #6B7280; padding: 0 16px 6px;")
        layout.addWidget(sub)

        fields_wrap = QWidget()
        fields = QGridLayout(fields_wrap)
        fields.setContentsMargins(16, 4, 16, 6)
        fields.setHorizontalSpacing(6)
        fields.setVerticalSpacing(5)

        self._ref = QLineEdit()
        self._ref.setMinimumHeight(28)
        self._ref.setPlaceholderText("N° facture")

        self._amount = PriceSpinBox()
        self._amount.setMinimumHeight(28)
        self._amount.setMaximum(9_999_999.999)
        self._amount.setDecimals(3)

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(28)
        self._notes.setPlaceholderText("Notes")

        self._items_total_lbl = QLabel("Total calculé produits : 0.000 TND")
        self._items_total_lbl.setStyleSheet(
            "background: #EFF6FF; color: #1D4ED8; border-radius: 8px; padding: 6px 10px;"
        )

        fields.addWidget(self._lbl("Référence:"), 0, 0)
        fields.addWidget(self._ref, 0, 1)
        fields.addWidget(self._lbl("Montant (TND) *:"), 0, 2)
        fields.addWidget(self._amount, 0, 3)
        fields.addWidget(self._lbl("Notes:"), 1, 0)
        fields.addWidget(self._notes, 1, 1, 1, 3)
        fields.addWidget(self._lbl("Résumé:"), 2, 0)
        fields.addWidget(self._items_total_lbl, 2, 1, 1, 3)
        fields.setColumnStretch(1, 3)
        fields.setColumnStretch(3, 2)
        layout.addWidget(fields_wrap)

        prod_header = QHBoxLayout()
        prod_header.setContentsMargins(16, 0, 16, 4)
        prod_title = QLabel("Produits du fournisseur")
        prod_title.setStyleSheet("font-size: 12px; font-weight: 700;")
        btn_new_product = QPushButton("＋ Produit fournisseur")
        btn_new_product.setObjectName("btnSecondary")
        btn_new_product.setMinimumHeight(28)
        btn_new_product.clicked.connect(self._add_product_for_supplier)
        prod_header.addWidget(prod_title)
        prod_header.addStretch()
        prod_header.addWidget(btn_new_product)
        layout.addLayout(prod_header)

        self._products_table = QTableWidget(0, 5)
        self._products_table.setHorizontalHeaderLabels([
            "Produit", "Fournisseur", "Prix achat", "Qté", "Total ligne",
        ])
        self._products_table.setAlternatingRowColors(True)
        self._products_table.verticalHeader().setVisible(False)
        self._products_table.verticalHeader().setDefaultSectionSize(34)
        self._products_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._products_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._products_table.setWordWrap(True)
        self._products_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        header = self._products_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self._products_table.setColumnWidth(2, 96)
        self._products_table.setColumnWidth(3, 82)
        self._products_table.setColumnWidth(4, 110)
        layout.addWidget(self._products_table, 1)

        info = QLabel(
            "Astuce : mettez la quantité à 0 pour exclure un produit."
            if self._products
            else "Aucun produit n'est encore lié à ce fournisseur. Vous pouvez saisir un montant manuel."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #6B7280; font-size: 10px; padding: 4px 16px 0;")
        self._info_lbl = info
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 12)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Enregistrer")
        btn_ok.clicked.connect(self._validate)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _populate(self):
        self._products = SupplierController.get_products_for_supplier(self._supplier_id)
        invoice_items = {
            item.get("product_id"): item
            for item in (SupplierController.get_invoice_items(self._invoice["id"]) if self._invoice else [])
        }

        self._products_table.setRowCount(len(self._products))
        self._rows.clear()

        for row, product in enumerate(self._products):
            product_label = QLabel(product["name"])
            product_label.setWordWrap(True)
            product_label.setStyleSheet("font-weight: 600; font-size: 10px; color: #111827; padding: 0 4px;")
            self._products_table.setCellWidget(row, 0, product_label)

            sup_label = QLabel(product.get("supplier_name") or self._supplier_name)
            sup_label.setWordWrap(True)
            sup_label.setStyleSheet("color: #6B7280; font-size: 9px; padding: 0 4px;")
            self._products_table.setCellWidget(row, 1, sup_label)

            item = invoice_items.get(product["id"]) or {}
            price = PriceSpinBox()
            price.setMaximum(999999)
            price.setDecimals(3)
            price.setMinimumHeight(26)
            configure_manual_spinbox(price, decimals=3, placeholder="0.000")
            price.setValue(float(item.get("unit_price") or product.get("purchase_price") or 0))
            self._products_table.setCellWidget(row, 2, price)

            qty = QuantitySpinBox(product.get("unit_type") or "piece")
            qty.setMaximum(999999)
            qty.setMinimumHeight(26)
            qty.setValue(float(item.get("quantity") or 0))
            self._products_table.setCellWidget(row, 3, qty)

            total_lbl = QLabel("0.000 TND")
            total_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_lbl.setStyleSheet("font-weight: 700; font-size: 10px; color: #059669; padding-right: 6px;")
            self._products_table.setCellWidget(row, 4, total_lbl)

            self._rows.append((qty, price, total_lbl, product))
            qty.valueChanged.connect(self._recalculate_items_total)
            price.valueChanged.connect(self._recalculate_items_total)
            self._products_table.setRowHeight(row, 34)

        if self._invoice:
            self._ref.setText(self._invoice.get("reference") or "")
            self._notes.setText(self._invoice.get("notes") or "")
            self._amount.setValue(float(self._invoice.get("amount_total") or 0))

        if self._products:
            self._info_lbl.setText("Astuce : quantité 0 = produit exclu de la facture.")
        else:
            self._info_lbl.setText(
                "Aucun produit lié à ce fournisseur. Utilisez “Produit fournisseur” pour en ajouter un."
            )

        self._products_table.resizeRowsToContents()
        self._recalculate_items_total(force_amount=not bool(self._invoice))

    def _add_product_for_supplier(self):
        from app.views.products_view import ProductDialog

        dlg = ProductDialog(self, preset_supplier_id=self._supplier_id)
        if dlg.exec():
            self._populate()

    def _recalculate_items_total(self, *_args, force_amount: bool = False):
        previous_total = self._last_items_total
        items_total = 0.0

        for qty_spin, price_spin, total_lbl, _product in self._rows:
            line_total = round(qty_spin.value() * price_spin.value(), 3)
            total_lbl.setText(format_price(line_total))
            items_total += line_total

        items_total = round(items_total, 3)
        self._last_items_total = items_total
        self._items_total_lbl.setText(f"Total calculé produits : {format_price(items_total)}")

        current_amount = round(self._amount.value(), 3)
        should_sync = force_amount or current_amount <= 0 or abs(current_amount - previous_total) < 0.001
        if should_sync and items_total > 0:
            self._amount.setValue(items_total)

    def _validate(self):
        if self._amount.value() <= 0:
            QMessageBox.warning(self, "Erreur", "Le montant doit être supérieur à 0.")
            return
        self.accept()

    def get_amount(self) -> float:
        return round(self._amount.value(), 3)

    def get_reference(self) -> str | None:
        return self._ref.text().strip() or None

    def get_notes(self) -> str | None:
        return self._notes.text().strip() or None

    def get_items(self) -> list[dict]:
        rows: list[dict] = []
        for qty_spin, price_spin, _total_lbl, product in self._rows:
            quantity = round(qty_spin.value(), 3)
            unit_price = round(price_spin.value(), 3)
            if quantity <= 0:
                continue
            rows.append(
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "supplier_name": product.get("supplier_name") or self._supplier_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            )
        return rows




class SupplierPaymentDialog(QDialog):
    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background: transparent; border: none; padding: 0; margin: 0;"
            "color: #6B7280; font-size: 11px; font-weight: 600;"
        )
        return lbl

    def __init__(self, supplier_name: str, balance: float, invoice_ref: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enregistrer un paiement")
        self.setFixedWidth(420)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui(supplier_name, balance, invoice_ref)

    def _build_ui(self, name: str, balance: float, invoice_ref: str | None):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("Paiement fournisseur")
        title.setStyleSheet("font-size: 17px; font-weight: 700; padding: 20px 24px 4px;")
        layout.addWidget(title)

        target = f"Facture : <b>{invoice_ref}</b>   •   " if invoice_ref else ""
        sub = QLabel(
            f"Fournisseur : <b>{name}</b>   •   {target}"
            f"Reste : <b style='color:#DC2626'>{format_price(balance)}</b>"
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #6B7280; padding: 0 24px 12px;")
        layout.addWidget(sub)

        form = QFormLayout()
        form.setContentsMargins(24, 8, 24, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._amount = PriceSpinBox()
        self._amount.setMinimumHeight(42)
        self._amount.setMaximum(max(balance, 0.001))
        self._amount.setValue(balance)
        self._amount.setDecimals(3)
        configure_manual_spinbox(self._amount, decimals=3, placeholder="0.000")

        self._ref = QLineEdit()
        self._ref.setMinimumHeight(38)
        self._ref.setPlaceholderText("Référence de paiement (optionnel)")

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(38)
        self._notes.setPlaceholderText("Notes (optionnel)")

        form.addRow(self._lbl("Montant payé (TND) *:"), self._amount)
        form.addRow(self._lbl("Référence:"), self._ref)
        form.addRow(self._lbl("Notes:"), self._notes)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 8, 24, 20)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider le paiement")
        btn_ok.clicked.connect(self._validate)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _validate(self):
        if self._amount.value() <= 0:
            QMessageBox.warning(self, "Erreur", "Le montant payé doit être supérieur à 0.")
            return
        self.accept()

    def get_amount(self) -> float:
        return self._amount.value()

    def get_reference(self) -> str | None:
        return self._ref.text().strip() or None

    def get_notes(self) -> str | None:
        return self._notes.text().strip() or None


class SupplierInvoicesDialog(QDialog):
    def __init__(self, supplier_id: int, supplier_name: str, parent=None):
        super().__init__(parent)
        self._supplier_id = supplier_id
        self._supplier_name = supplier_name
        self._dirty = False
        self.setWindowTitle(f"Factures fournisseur — {supplier_name}")
        clamp_min_size(self, 1320, 760)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui()
        self._refresh()

    def exec(self) -> int:
        result = super().exec()
        return result

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel(f"Historique factures — {self._supplier_name}")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        top.addWidget(title)
        top.addStretch()

        btn_add = QPushButton("＋  Ajouter facture")
        btn_add.clicked.connect(self._add_invoice)
        btn_hist = QPushButton("Historique")
        btn_hist.setObjectName("btnSecondary")
        btn_hist.clicked.connect(self._view_history)

        top.addWidget(btn_hist)
        top.addWidget(btn_add)
        layout.addLayout(top)

        self._summary = QLabel()
        self._summary.setStyleSheet(
            "background: #F0FDF4; color: #065F46; border: 1px solid #A7F3D0;"
            "border-radius: 8px; padding: 10px 14px; font-size: 13px;"
        )
        layout.addWidget(self._summary)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "Référence", "Date", "Produits", "Montant", "Payé", "Reste", "Notes", "Actions",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 420)
        self._table.setColumnWidth(6, 220)
        self._table.setColumnWidth(7, 300)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("btnSecondary")
        btn_close.clicked.connect(self._close_dialog)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _close_dialog(self):
        self.done(QDialog.Accepted if self._dirty else QDialog.Rejected)

    def _refresh(self):
        invoices = SupplierController.get_supplier_invoices(self._supplier_id)
        balance = SupplierController.get_balance(self._supplier_id)
        self._summary.setText(
            f"Factures : {format_price(balance['total_invoiced'])}   •   "
            f"Payé : {format_price(balance['total_paid'])}   •   "
            f"Reste : {format_price(balance['balance'])}"
        )

        self._table.setRowCount(len(invoices))
        for row, invoice in enumerate(invoices):
            ref = invoice.get("reference") or f"Facture #{invoice['id']}"
            items = SupplierController.get_invoice_items(invoice["id"])

            self._table.setItem(row, 0, QTableWidgetItem(ref))
            self._table.setItem(row, 1, QTableWidgetItem((invoice.get("created_at") or "")[:16]))
            self._table.setCellWidget(row, 2, _invoice_items_summary_widget(items))
            self._table.setItem(row, 3, _money_item(float(invoice.get("amount_total") or 0), "#D97706"))
            self._table.setItem(row, 4, _money_item(float(invoice.get("amount_paid") or 0), "#059669"))

            remaining = float(invoice.get("remaining_amount") or 0)
            remaining_color = "#DC2626" if remaining > 0 else "#059669"
            self._table.setItem(row, 5, _money_item(remaining, remaining_color))
            self._table.setItem(row, 6, QTableWidgetItem(invoice.get("notes") or "—"))

            # +8 over the previous baseline: the theme's QTableWidget::item
            # padding (10px top + 10px bottom) also insets the rect a
            # setCellWidget() is placed into, not just painted text — without
            # the extra room the action buttons were squeezed vertically,
            # which is also what made their horizontal spacing collapse.
            row_height = 82 if not items else min(188, 52 + (min(len(items), 6) * 22))
            self._table.setRowHeight(row, row_height)

            actions = QWidget()
            act_lay = QHBoxLayout(actions)
            act_lay.setContentsMargins(10, 8, 10, 8)
            act_lay.setSpacing(10)

            # min/max-height constrain the *content* box; _WHITE_QSS's base
            # QPushButton rule adds its own 9px top/bottom padding on top of
            # that unless explicitly zeroed here too, which is what was
            # inflating these buttons past the row's available height.
            action_btn_style = "QPushButton { min-height: 30px; max-height: 30px; padding: 0 10px; }"

            btn_pay = QPushButton("Payer")
            btn_pay.setObjectName("btnSuccess")
            btn_pay.setCursor(Qt.PointingHandCursor)
            btn_pay.setStyleSheet(action_btn_style)
            btn_pay.setEnabled(remaining > 0)
            btn_pay.clicked.connect(lambda _, inv=invoice: self._pay_invoice(inv))

            btn_edit = QPushButton("Modifier")
            btn_edit.setObjectName("btnSecondary")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setStyleSheet(action_btn_style)
            btn_edit.clicked.connect(lambda _, inv=invoice: self._edit_invoice(inv))

            btn_del = QPushButton("×")
            btn_del.setObjectName("btnDanger")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedWidth(36)
            btn_del.setStyleSheet(action_btn_style)
            btn_del.setToolTip("Supprimer la facture")
            btn_del.clicked.connect(lambda _, inv=invoice: self._delete_invoice(inv))

            act_lay.addWidget(btn_pay)
            act_lay.addWidget(btn_edit)
            act_lay.addWidget(btn_del)
            self._table.setCellWidget(row, 7, actions)

        self._table.resizeRowsToContents()

    def _add_invoice(self):
        dlg = InvoiceDialog(self._supplier_id, self._supplier_name, parent=self)
        if not dlg.exec():
            return
        try:
            SupplierController.create_invoice(
                self._supplier_id,
                dlg.get_amount(),
                reference=dlg.get_reference(),
                notes=dlg.get_notes(),
                items=dlg.get_items(),
            )
            self._dirty = True
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))

    def _edit_invoice(self, invoice: dict):
        dlg = InvoiceDialog(self._supplier_id, self._supplier_name, invoice=invoice, parent=self)
        if not dlg.exec():
            return
        try:
            SupplierController.update_invoice(
                invoice["id"],
                {
                    "amount_total": dlg.get_amount(),
                    "reference": dlg.get_reference(),
                    "notes": dlg.get_notes(),
                    "items": dlg.get_items(),
                },
            )
            self._dirty = True
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))

    def _delete_invoice(self, invoice: dict):
        ref = invoice.get("reference") or f"Facture #{invoice['id']}"
        reply = QMessageBox.question(
            self,
            "Supprimer facture",
            f"Supprimer «{ref}» et ses paiements ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        SupplierController.delete_invoice(invoice["id"])
        self._dirty = True
        self._refresh()

    def _pay_invoice(self, invoice: dict):
        remaining = float(invoice.get("remaining_amount") or 0)
        if remaining <= 0:
            return
        dlg = SupplierPaymentDialog(
            self._supplier_name,
            remaining,
            invoice_ref=invoice.get("reference") or f"Facture #{invoice['id']}",
            parent=self,
        )
        if not dlg.exec():
            return
        try:
            SupplierController.record_invoice_payment(
                invoice["id"],
                dlg.get_amount(),
                reference=dlg.get_reference(),
                notes=dlg.get_notes(),
            )
            self._dirty = True
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))

    def _view_history(self):
        transactions = SupplierController.get_transactions(self._supplier_id)
        balance_info = SupplierController.get_balance(self._supplier_id)
        dlg = HistoryDialog(self._supplier_name, transactions, balance_info, parent=self)
        dlg.exec()


class HistoryDialog(QDialog):
    def __init__(self, supplier_name: str, transactions: list, balance_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Historique — {supplier_name}")
        clamp_min_size(self, 720, 540)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui(supplier_name, transactions, balance_info)

    def _build_ui(self, name: str, transactions: list, balance_info: dict):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(f"Historique des transactions — {name}")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        summary = QFrame()
        summary.setStyleSheet(
            "QFrame { background: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 10px; }"
        )
        sum_lay = QHBoxLayout(summary)
        sum_lay.setContentsMargins(20, 14, 20, 14)
        sum_lay.setSpacing(0)

        def _stat_block(label: str, value: float, color: str) -> QVBoxLayout:
            vl = QVBoxLayout()
            vl.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"font-size: 11px; color: #6B7280; font-weight: 600; background: transparent; border: none;"
            )
            val_lbl = QLabel(format_price(value))
            val_lbl.setStyleSheet(
                f"font-size: 16px; font-weight: 700; color: {color}; background: transparent; border: none;"
            )
            vl.addWidget(lbl)
            vl.addWidget(val_lbl)
            return vl

        balance_color = "#DC2626" if balance_info["balance"] > 0 else "#059669"
        sum_lay.addLayout(_stat_block("Total factures", balance_info["total_invoiced"], "#D97706"))
        sum_lay.addStretch()
        sum_lay.addWidget(_vsep())
        sum_lay.addStretch()
        sum_lay.addLayout(_stat_block("Total payé", balance_info["total_paid"], "#059669"))
        sum_lay.addStretch()
        sum_lay.addWidget(_vsep())
        sum_lay.addStretch()
        sum_lay.addLayout(_stat_block("Solde dû", balance_info["balance"], balance_color))
        layout.addWidget(summary)

        tbl = QTableWidget(len(transactions), 5)
        tbl.setHorizontalHeaderLabels(["Date", "Type", "Montant", "Référence", "Notes"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)

        for row, txn in enumerate(transactions):
            tbl.setItem(row, 0, QTableWidgetItem((txn.get("created_at") or "")[:16]))

            is_invoice = txn["type"] == "invoice"
            type_text = "Facture" if is_invoice else "Paiement"
            type_item = QTableWidgetItem(type_text)
            type_item.setForeground(QColor("#D97706") if is_invoice else QColor("#059669"))
            tbl.setItem(row, 1, type_item)

            amount_item = _money_item(float(txn["amount"]), "#D97706" if is_invoice else "#059669")
            tbl.setItem(row, 2, amount_item)
            tbl.setItem(row, 3, QTableWidgetItem(txn.get("reference") or "—"))
            tbl.setItem(row, 4, QTableWidgetItem(txn.get("notes") or "—"))

        tbl.resizeRowsToContents()
        layout.addWidget(tbl, 1)

        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("btnSecondary")
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
