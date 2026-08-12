from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QComboBox, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt

from app.views.widgets.data_table import DataTable
from app.views.widgets.search_bar import SearchBar
from app.views.widgets.price_input import PriceSpinBox
from app.controllers.stock_controller import StockController, LOSS_REASONS, LOSS_REASON_LABELS
from app.controllers.product_controller import ProductController
from app.utils.helpers import format_datetime, format_price
from app.views.invoice_scan_dialog import InvoiceScanDialog

_UNIT_SUFFIX = {"piece": " pcs", "kg": " kg", "litre": " L"}

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
    # Destructive action: must not share the green of the confirm buttons.
    "QPushButton#btnDanger { background: #DC2626; color: #FFFFFF; }"
    "QPushButton#btnDanger:hover { background: #B91C1C; }"
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

        btn_loss = QPushButton("🗑️  Déclarer une perte")
        btn_loss.setObjectName("btnDanger")
        btn_loss.setMinimumHeight(42)
        btn_loss.setToolTip("Retirer du stock un produit cassé, périmé, détruit ou perdu")
        btn_loss.clicked.connect(self._open_loss)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(btn_loss)
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
            # A loss is stored as an 'out' movement (see StockController); show
            # it as its own kind so it is not read as a sale.
            loss_reason = m.get("loss_reason")
            if loss_reason:
                d["movement_type"] = f"🗑️ Perte — {LOSS_REASON_LABELS.get(loss_reason, loss_reason)}"
            else:
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

    def _open_loss(self):
        dlg = StockLossDialog(self)
        if dlg.exec():
            summary = dlg.result_summary() or {}
            self.refresh()
            QMessageBox.information(
                self,
                "Perte enregistrée",
                f"{summary.get('quantity', 0):g} × {summary.get('product_name', '')} "
                f"retiré(s) du stock.\n"
                f"Motif : {summary.get('reason_label', '')}\n"
                f"Coût de la perte : {format_price(summary.get('total_cost', 0))}\n"
                f"Stock restant : {summary.get('remaining_stock', 0):g}",
            )


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


class StockLossDialog(QDialog):
    """Déclare une sortie de stock qui n'est pas une vente.

    Le mouvement est enregistré avec son motif et le prix d'achat du moment,
    donc il apparaît dans l'historique existant et pèse sur le gain net.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Déclarer une perte")
        self.setFixedWidth(480)
        self.setStyleSheet(_WHITE_QSS)
        self._products = ProductController.get_all()
        self._result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Produit cassé, périmé, détruit ou perdu")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self._product_combo = QComboBox()
        self._product_combo.setMinimumHeight(42)
        for p in self._products:
            self._product_combo.addItem(f"{p['name']}", p["id"])
        self._product_combo.currentIndexChanged.connect(self._update_stock_label)

        self._qty = PriceSpinBox()
        self._qty.setMinimumHeight(42)
        self._qty.setMinimum(0.001)
        self._qty.setMaximum(99999)
        self._qty.setDecimals(3)
        self._qty.setValue(1)

        self._reason = QComboBox()
        self._reason.setMinimumHeight(42)
        for key, label in LOSS_REASONS:
            self._reason.addItem(label, key)

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(42)
        self._notes.setPlaceholderText("Commentaire (optionnel)")

        self._stock_lbl = QLabel()
        self._stock_lbl.setStyleSheet("font-size: 12px; color: #6B7280;")

        form.addRow("Produit:", self._product_combo)
        form.addRow("", self._stock_lbl)
        form.addRow("Quantité perdue:", self._qty)
        form.addRow("Motif:", self._reason)
        form.addRow("Commentaire:", self._notes)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("🗑️  Retirer du stock")
        btn_ok.setObjectName("btnDanger")
        btn_ok.clicked.connect(self._confirm)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._update_stock_label()

    def _current_product(self) -> dict | None:
        pid = self._product_combo.currentData()
        return next((p for p in self._products if p["id"] == pid), None)

    def _update_stock_label(self):
        product = self._current_product()
        if not product:
            self._stock_lbl.clear()
            return
        unit = _UNIT_SUFFIX.get(product.get("unit_type", "piece"), "")
        self._stock_lbl.setText(
            f"Stock actuel : {float(product['stock_quantity']):g}{unit}  •  "
            f"prix d'achat {float(product.get('purchase_price') or 0):.3f} TND"
        )

    def _confirm(self):
        product = self._current_product()
        if not product:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un produit.")
            return

        quantity = self._qty.value()
        reason_key = self._reason.currentData()
        reason_label = self._reason.currentText()

        confirm = QMessageBox.question(
            self,
            "Confirmer la perte",
            f"Retirer {quantity:g} × {product['name']} du stock ?\n"
            f"Motif : {reason_label}\n\n"
            f"Stock : {float(product['stock_quantity']):g} → "
            f"{float(product['stock_quantity']) - quantity:g}\n"
            "Cette sortie sera enregistrée dans l'historique.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            self._result = StockController.record_loss(
                product["id"], quantity, reason_key, self._notes.text().strip()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Impossible", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return

        self.accept()

    def result_summary(self) -> dict | None:
        return self._result
