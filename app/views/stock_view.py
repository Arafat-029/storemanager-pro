from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QComboBox, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt

from app.views.widgets.data_table import DataTable
from app.views.widgets.search_bar import SearchBar
from app.views.widgets.price_input import PriceSpinBox
from app.controllers.stock_controller import StockController
from app.controllers.product_controller import ProductController
from app.utils.helpers import format_datetime, format_price
from app.views.invoice_scan_dialog import InvoiceScanDialog

_WHITE_QSS = (
    "QDialog, QWidget, QFrame { background: #FFFFFF; color: #111827; }"
    "QLabel { background: transparent; color: #111827; }"
    "QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit {"
    "  background: #F9FAFB; color: #111827;"
    "  border: 1.5px solid #D1D5DB; border-radius: 8px; padding: 8px 12px; }"
    "QComboBox { padding-right: 48px; }"
    "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 38px; border: none; background: transparent; }"
    "QComboBox::down-arrow { width: 12px; height: 12px; margin-right: 12px; }"
    "QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {"
    "  border-color: #059669; background: #FAFFFE; }"
    "QPushButton { background: #059669; color: white; border: none;"
    "  border-radius: 8px; padding: 9px 18px; font-weight: 600; }"
    "QPushButton:hover { background: #10B981; }"
    "QPushButton:pressed { background: #047857; }"
    "QPushButton#btnSecondary, QPushButton[cssClass=\"btnSecondary\"] { background: transparent; border: 1.5px solid #D1D5DB; color: #6B7280; }"
    "QPushButton#btnSecondary:hover, QPushButton[cssClass=\"btnSecondary\"]:hover { border-color: #059669; color: #111827; }"
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; height: 0; border: 0; }"
    "QComboBox QAbstractItemView { background: #FFFFFF; color: #111827;"
    "  border: 1.5px solid #E5E7EB; }"
)


class StockView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._inv_frame = QFrame()
        self._inv_frame.setObjectName("statCard")
        inv_row = QHBoxLayout(self._inv_frame)
        self._lbl_purchase = QLabel()
        self._lbl_sale = QLabel()
        self._lbl_count = QLabel()
        for lbl in [self._lbl_purchase, self._lbl_sale, self._lbl_count]:
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 14px;")
            inv_row.addWidget(lbl, 1)
        layout.addWidget(self._inv_frame)

        toolbar = QHBoxLayout()
        self._search = SearchBar("🔍  Rechercher un produit...")
        self._search.setMinimumHeight(42)
        self._search.search_changed.connect(self._filter_movements)

        btn_scan = QPushButton("📄  Ajout facture")
        btn_scan.setObjectName("btnWarning")
        btn_scan.setMinimumHeight(42)
        btn_scan.clicked.connect(self._open_invoice_scan)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(btn_scan)
        layout.addLayout(toolbar)

        lbl = QLabel("Historique des mouvements de stock")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(lbl)

        self._table = DataTable(["Date", "Produit", "Type", "Quantité", "Référence", "Notes", "Utilisateur"])
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self._table, 1)

    def refresh(self):
        inv = StockController.get_inventory_value()
        self._lbl_purchase.setText(f"<b>Valeur achat</b><br>{format_price(inv.get('purchase_value', 0))}")
        self._lbl_sale.setText(f"<b>Valeur vente</b><br>{format_price(inv.get('sale_value', 0))}")
        self._lbl_count.setText(f"<b>Produits</b><br>{inv.get('product_count', 0)} ({inv.get('low_stock_count', 0)} en stock faible)")
        self._load_movements()

    def _load_movements(self, product_id: int = None):
        movements = StockController.get_movements(product_id)
        type_labels = {"in": "✅ Entrée", "out": "📤 Sortie", "adjustment": "⚙️ Ajustement", "return": "↩️ Retour"}
        display = []
        for m in movements:
            d = dict(m)
            d["created_at"] = format_datetime(m["created_at"])
            d["movement_type"] = type_labels.get(m["movement_type"], m["movement_type"])
            d["quantity"] = f"{m['quantity']:.3f}"
            display.append(d)
        self._table.set_data(display, ["created_at", "product_name", "movement_type", "quantity", "reference", "notes", "user_name"])
        self._limit_table_height(len(display))


    def _limit_table_height(self, total_rows: int):
        visible_rows = max(1, min(int(total_rows), 10))
        header_h = self._table.horizontalHeader().height() or 36
        row_h = 48
        frame_h = 12
        target_h = header_h + (visible_rows * row_h) + frame_h
        self._table.setMinimumHeight(target_h)
        self._table.setMaximumHeight(target_h)

    def _filter_movements(self, text: str):
        if not text:
            self._load_movements()
            return
        products = ProductController.search(text)
        if products:
            self._load_movements(products[0]["id"])

    def _add_product(self):
        from app.views.products_view import ProductDialog

        dlg = ProductDialog(self)
        if dlg.exec():
            self.refresh()

    def _open_adjust(self):
        dlg = StockAdjustDialog(self)
        if dlg.exec():
            self.refresh()

    def _open_entry(self):
        dlg = StockEntryDialog(self)
        if dlg.exec():
            self.refresh()

    def _open_invoice_scan(self):
        dlg = InvoiceScanDialog(self)
        if dlg.exec():
            self.refresh()


class StockAdjustDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustement de stock")
        self.setFixedWidth(460)
        self.setStyleSheet(_WHITE_QSS)
        self._products = ProductController.get_all()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel("<b>Ajustement d'inventaire</b>"))

        form = QFormLayout()
        self._product_combo = QComboBox()
        self._product_combo.setMinimumHeight(42)
        for p in self._products:
            supplier = f" — {p['supplier_name']}" if p.get("supplier_name") else ""
            self._product_combo.addItem(f"{p['name']}{supplier} (stock: {p['stock_quantity']:.3f})", p["id"])
        self._product_combo.currentIndexChanged.connect(self._update_current)

        self._current_lbl = QLabel()
        self._new_qty = PriceSpinBox()
        self._new_qty.setMinimumHeight(42)
        self._new_qty.setMaximum(999999)
        self._new_qty.setDecimals(3)

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(42)
        self._notes.setPlaceholderText("Raison de l'ajustement...")

        form.addRow("Produit:", self._product_combo)
        form.addRow("Stock actuel:", self._current_lbl)
        form.addRow("Nouveau stock:", self._new_qty)
        form.addRow("Notes:", self._notes)
        layout.addLayout(form)
        self._update_current()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Confirmer")
        btn_ok.clicked.connect(self._confirm)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _update_current(self):
        pid = self._product_combo.currentData()
        p = next((x for x in self._products if x["id"] == pid), None)
        if p:
            self._current_lbl.setText(f"{p['stock_quantity']:.3f} {p['unit_type']}")

    def _confirm(self):
        pid = self._product_combo.currentData()
        StockController.adjust_stock(pid, self._new_qty.value(), self._notes.text() or "Ajustement inventaire")
        self.accept()


class StockEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Entrée de stock")
        self.setFixedWidth(460)
        self.setStyleSheet(_WHITE_QSS)
        self._products = ProductController.get_all()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        self._product_combo = QComboBox()
        self._product_combo.setMinimumHeight(42)
        for p in self._products:
            supplier = f" — {p['supplier_name']}" if p.get("supplier_name") else ""
            self._product_combo.addItem(f"{p['name']}{supplier}", p["id"])

        self._qty = PriceSpinBox()
        self._qty.setMinimumHeight(42)
        self._qty.setMinimum(0.001)
        self._qty.setMaximum(99999)
        self._qty.setDecimals(3)
        self._qty.setValue(1)

        self._ref = QLineEdit()
        self._ref.setMinimumHeight(42)
        self._ref.setPlaceholderText("N° BL, fournisseur...")

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(42)

        form.addRow("Produit:", self._product_combo)
        form.addRow("Quantité:", self._qty)
        form.addRow("Référence:", self._ref)
        form.addRow("Notes:", self._notes)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Confirmer")
        btn_ok.setObjectName("btnSuccess")
        btn_ok.clicked.connect(self._confirm)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _confirm(self):
        pid = self._product_combo.currentData()
        StockController.add_stock(pid, self._qty.value(), self._notes.text(), self._ref.text())
        self.accept()
