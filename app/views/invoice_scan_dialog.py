from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.controllers.stock_controller import StockController
from app.controllers.supplier_controller import SupplierController
from app.views.widgets.price_input import PriceSpinBox
from app.views.widgets.quantity_input import QuantitySpinBox
from app.views.widgets.screen_fit import clamp_min_size


_WHITE_QSS = (
    "QDialog, QWidget, QFrame { background: #FFFFFF; color: #111827; }"
    "QLabel { background: transparent; color: #111827; }"
    "QLineEdit, QComboBox, QDoubleSpinBox {"
    "  background: #F9FAFB; color: #111827;"
    "  border: 1.5px solid #D1D5DB; border-radius: 8px; padding: 8px 12px; }"
    "QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {"
    "  border-color: #059669; background: #FAFFFE; }"
    "QPushButton { background: #059669; color: white; border: none;"
    "  border-radius: 8px; padding: 9px 18px; font-weight: 600; }"
    "QPushButton:hover { background: #10B981; }"
    "QPushButton:pressed { background: #047857; }"
    "QPushButton:disabled { background: #E5E7EB; color: #9CA3AF; }"
    "QPushButton#btnSecondary, QPushButton[cssClass=\"btnSecondary\"] {"
    "  background: transparent; border: 1.5px solid #D1D5DB; color: #6B7280; }"
    "QPushButton#btnSecondary:hover, QPushButton[cssClass=\"btnSecondary\"]:hover {"
    "  border-color: #059669; color: #111827; }"
    "QComboBox::drop-down { border: none; width: 24px; background: transparent; }"
    "QComboBox::down-arrow { border-left: 4px solid transparent;"
    "  border-right: 4px solid transparent; border-top: 5px solid #9CA3AF; width: 0; height: 0; }"
    "QComboBox QAbstractItemView { background: #FFFFFF; color: #111827;"
    "  border: 1.5px solid #E5E7EB; border-radius: 6px; }"
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; height: 0; border: 0; }"
    "QScrollBar:vertical { background: transparent; width: 5px; border-radius: 3px; }"
    "QScrollBar::handle:vertical { background: #D1D5DB; border-radius: 3px; min-height: 30px; }"
    "QScrollBar::handle:vertical:hover { background: #059669; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
)


def _unit_label(unit_type: str) -> str:
    normalized = (unit_type or "piece").strip().lower()
    if normalized == "kg":
        return "kg"
    if normalized == "litre":
        return "L"
    return "pcs"


class _InvoiceItemRow(QWidget):
    changed = Signal()

    def __init__(self, product: dict, parent=None):
        super().__init__(parent)
        self._product = dict(product)
        self._unit_type = (self._product.get("unit_type") or "piece").strip().lower()
        self._pack_piece_count = max(0, int(round(float(self._product.get("pack_quantity") or 0.0))))
        self.setMinimumHeight(58)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(8)

        name = self._product.get("name", "")
        stock_quantity = float(self._product.get("stock_quantity") or 0.0)
        supplier_name = self._product.get("supplier_name") or ""
        unit_label = _unit_label(self._unit_type)

        product_wrap = QWidget()
        product_layout = QVBoxLayout(product_wrap)
        product_layout.setContentsMargins(0, 0, 0, 0)
        product_layout.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #111827;")
        name_lbl.setWordWrap(True)

        stock_text = f"Stock actuel : {stock_quantity:.3f} {unit_label}"
        if self._unit_type == "piece" and self._pack_piece_count >= 2:
            stock_text += f" • Pack {self._pack_piece_count} pcs"
        if supplier_name:
            stock_text += f" • {supplier_name}"
        stock_lbl = QLabel(stock_text)
        stock_lbl.setStyleSheet("font-size: 10px; color: #6B7280;")
        stock_lbl.setWordWrap(True)

        product_layout.addWidget(name_lbl)
        product_layout.addWidget(stock_lbl)

        self._qty = QuantitySpinBox(self._unit_type)
        self._qty.setFixedSize(90, 38)
        self._qty.setMaximum(999999.999)
        self._qty.setValue(0.0)
        self._qty.setToolTip("Quantité en pièces" if self._unit_type == "piece" else "Quantité")
        self._qty.valueChanged.connect(self._recalc)

        pack_wrap = None
        self._pack_qty = None
        if self._unit_type == "piece" and self._pack_piece_count >= 2:
            self.setMinimumHeight(68)
            pack_wrap = QWidget()
            pack_layout = QVBoxLayout(pack_wrap)
            pack_layout.setContentsMargins(0, 0, 0, 0)
            pack_layout.setSpacing(2)

            pack_lbl = QLabel(f"Pack x{self._pack_piece_count}")
            pack_lbl.setAlignment(Qt.AlignCenter)
            pack_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #475569;")

            self._pack_qty = QuantitySpinBox("piece")
            self._pack_qty.setFixedSize(76, 38)
            self._pack_qty.setMaximum(999999)
            self._pack_qty.setValue(0.0)
            self._pack_qty.setToolTip(f"Nombre de packs de {self._pack_piece_count} pièces")
            self._pack_qty.valueChanged.connect(self._recalc)

            pack_layout.addWidget(pack_lbl)
            pack_layout.addWidget(self._pack_qty, 0, Qt.AlignCenter)

        self._price = PriceSpinBox()
        self._price.setFixedSize(110, 38)
        self._price.setMaximum(9_999_999.999)
        self._price.setDecimals(3)
        self._price.setValue(float(self._product.get("purchase_price") or 0.0))
        if self._price.lineEdit() is not None:
            self._price.lineEdit().setPlaceholderText("0.000 / pièce")
            self._price.lineEdit().setToolTip("Exemple : 4500 = 4.500 TND par pièce")
        self._price.valueChanged.connect(self._recalc)

        self._total_lbl = QLabel("0 TND")
        self._total_lbl.setFixedWidth(110)
        self._total_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._total_lbl.setStyleSheet(
            "font-weight: 700; color: #059669; font-size: 13px; background: transparent;"
        )

        layout.addWidget(product_wrap, 1)
        layout.addWidget(self._qty)
        if pack_wrap is not None:
            layout.addWidget(pack_wrap)
        layout.addWidget(self._price)
        layout.addWidget(self._total_lbl)

        self._recalc()

    def _effective_quantity(self) -> float:
        qty = round(float(self._qty.value()), 3)
        if self._pack_qty is not None and self._pack_piece_count >= 2:
            qty += float(self._pack_qty.value()) * float(self._pack_piece_count)
        return round(qty, 3)

    def _recalc(self):
        total = self._effective_quantity() * self._price.value()
        value = f"{total:.3f}".rstrip("0").rstrip(".")
        self._total_lbl.setText(f"{value or '0'} TND")
        self.changed.emit()

    def get_data(self) -> dict:
        qty = self._effective_quantity()
        price = round(float(self._price.value()), 3)
        loose_qty = round(float(self._qty.value()), 3)
        pack_count = int(round(float(self._pack_qty.value()))) if self._pack_qty is not None else 0
        return {
            "product_id": self._product["id"],
            "product_name": self._product.get("name") or "",
            "supplier_name": self._product.get("supplier_name") or "",
            "qty": qty,
            "price": price,
            "total": round(qty * price, 3),
            "pack_count": pack_count,
            "pack_piece_count": self._pack_piece_count,
            "loose_qty": loose_qty,
        }


class _ReceptionWarningsDialog(QDialog):
    """Informative check shown before a delivery is added to the stock.

    Never blocks on its own — the admin can always continue. Its job is to put
    the products that need a look (sensitive categories, short shelf life,
    expiry dates) in front of them while it is still cheap to refuse a crate.
    """

    def __init__(self, warnings: list[dict], parent=None):
        super().__init__(parent)
        self._warnings = warnings
        self.setWindowTitle("Vérifications avant réception")
        self.setMinimumWidth(560)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Produits à vérifier")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #B45309;")
        layout.addWidget(title)

        intro = QLabel(
            f"{len(self._warnings)} produit(s) de cette livraison demandent une vérification "
            "avant l'ajout au stock."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 12px; color: #6B7280;")
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(320)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(10)

        for warning in self._warnings:
            card = QFrame()
            # Scoped by objectName: QLabel inherits from QFrame, so a bare
            # "QFrame { ... }" rule here would draw the border around every
            # line of text inside the card too.
            card.setObjectName("warnCard")
            card.setStyleSheet(
                "QFrame#warnCard { background: #FFFBEB; border: 1px solid #FDE68A;"
                " border-radius: 8px; }"
                "QFrame#warnCard QLabel { border: none; background: transparent; }"
            )
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(12, 10, 12, 10)
            card_lay.setSpacing(4)

            head = QLabel(f"<b>{warning['product_name']}</b> — {warning['quantity']:g} reçu(s)")
            head.setStyleSheet("font-size: 13px; color: #111827; background: transparent;")
            card_lay.addWidget(head)

            for message in warning["messages"]:
                line = QLabel(f"• {message}")
                line.setWordWrap(True)
                line.setStyleSheet("font-size: 12px; color: #92400E; background: transparent;")
                card_lay.addWidget(line)

            content_lay.addWidget(card)

        content_lay.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Only offered when at least one category declares a shelf life.
        self._apply_expiry = None
        datable = [w for w in self._warnings if w.get("suggested_expiry")]
        if datable:
            self._apply_expiry = QCheckBox(
                f"Mettre à jour la date d'expiration de {len(datable)} produit(s) "
                "d'après la durée de conservation"
            )
            self._apply_expiry.setChecked(True)
            self._apply_expiry.setStyleSheet("font-size: 12px; color: #111827;")
            layout.addWidget(self._apply_expiry)

            note = QLabel(
                "Un produit n'a qu'une seule date d'expiration : celle-ci remplacera la précédente."
            )
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 11px; color: #9CA3AF;")
            layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler la réception")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Continuer")
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def should_apply_expiry(self) -> bool:
        return bool(self._apply_expiry and self._apply_expiry.isChecked())


class _InvoicePaymentDialog(QDialog):
    def __init__(self, total_amount: float, parent=None):
        super().__init__(parent)
        self._total_amount = round(float(total_amount), 3)
        self.setWindowTitle("Montant payé")
        self.setFixedWidth(420)
        self.setStyleSheet(_WHITE_QSS)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Paiement de la facture")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        info = QLabel(
            "Donnez le montant payé maintenant. Le reste sera enregistré comme crédit fournisseur."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 12px; color: #6B7280;")
        layout.addWidget(info)

        total_lbl = QLabel(f"Total facture : <b>{self._total_amount:.3f} TND</b>")
        total_lbl.setStyleSheet("font-size: 14px; color: #111827;")
        layout.addWidget(total_lbl)

        self._paid = PriceSpinBox()
        self._paid.setMinimumHeight(42)
        self._paid.setMaximum(self._total_amount)
        self._paid.setDecimals(3)
        self._paid.setValue(self._total_amount)
        layout.addWidget(self._paid)

        buttons = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Continuer")
        btn_ok.clicked.connect(self._validate)

        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

    def _validate(self):
        paid = round(float(self._paid.value()), 3)
        if paid < 0:
            QMessageBox.warning(self, "Montant invalide", "Le montant payé doit être positif.")
            return
        if paid > self._total_amount:
            QMessageBox.warning(
                self,
                "Montant invalide",
                "Le montant payé ne peut pas dépasser le total de la facture.",
            )
            return
        self.accept()

    def get_paid_amount(self) -> float:
        return round(float(self._paid.value()), 3)


class InvoiceEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajout facture fournisseur")
        clamp_min_size(self, 980, 620)
        self.setStyleSheet(_WHITE_QSS)

        self._suppliers = SupplierController.get_all()
        self._rows: list[_InvoiceItemRow] = []
        self._build_ui()
        self._set_empty_message("Choisissez un fournisseur pour afficher ses produits.")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet("QFrame { background: #059669; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        title_lbl = QLabel("Ajout facture fournisseur")
        title_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: white; background: transparent;"
        )
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        layout.addWidget(header)

        ref_bar = QFrame()
        ref_bar.setStyleSheet("QFrame { background: #F9FAFB; border-bottom: 1px solid #E5E7EB; }")
        ref_layout = QHBoxLayout(ref_bar)
        ref_layout.setContentsMargins(20, 10, 20, 10)
        ref_layout.setSpacing(10)

        def _label(text: str) -> QLabel:
            widget = QLabel(text)
            widget.setStyleSheet("font-weight: 600; color: #374151; background: transparent;")
            return widget

        self._ref = QLineEdit()
        self._ref.setMinimumHeight(38)
        self._ref.setMaximumWidth(220)
        self._ref.setPlaceholderText("N° facture fournisseur…")

        self._supplier_combo = QComboBox()
        self._supplier_combo.setMinimumHeight(38)
        self._supplier_combo.setMinimumWidth(300)
        self._supplier_combo.addItem("— Choisir un fournisseur —", None)
        for supplier in self._suppliers:
            self._supplier_combo.addItem(supplier["name"], supplier["id"])
        self._supplier_combo.currentIndexChanged.connect(self._on_supplier_changed)

        self._btn_add_product = QPushButton("＋  Ajout produit")
        self._btn_add_product.setObjectName("btnSecondary")
        self._btn_add_product.setMinimumHeight(38)
        self._btn_add_product.setEnabled(False)
        self._btn_add_product.clicked.connect(self._add_product_for_supplier)

        ref_layout.addWidget(_label("Réf. facture :"))
        ref_layout.addWidget(self._ref)
        ref_layout.addSpacing(24)
        ref_layout.addWidget(_label("Fournisseur :"))
        ref_layout.addWidget(self._supplier_combo)
        ref_layout.addWidget(self._btn_add_product)
        ref_layout.addStretch()
        layout.addWidget(ref_bar)

        helper = QLabel(
            "Choisissez d'abord le fournisseur, puis saisissez seulement les quantités facturées. "
            "Pièce = entier sans virgule, kg/L = valeurs décimales autorisées (ex: 5.5). "
            "Les lignes laissées à 0 ne changent pas le stock."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet(
            "padding: 8px 20px; color: #6B7280; font-size: 11px; background: #FFFFFF;"
        )
        layout.addWidget(helper)

        col_hdr = QWidget()
        col_hdr.setFixedHeight(30)
        col_hdr.setStyleSheet("QWidget { background: #F3F4F6; }")
        col_layout = QHBoxLayout(col_hdr)
        col_layout.setContentsMargins(20, 0, 20, 0)
        col_layout.setSpacing(8)

        def _col(text: str, width: int | None = None) -> QLabel:
            widget = QLabel(text)
            if width is not None:
                widget.setFixedWidth(width)
            widget.setStyleSheet(
                "font-size: 10px; font-weight: 700; color: #6B7280; letter-spacing: 0.5px; background: transparent;"
            )
            return widget

        col_layout.addWidget(_col("PRODUIT"), 1)
        col_layout.addWidget(_col("QTÉ AJOUTÉE", 90))
        col_layout.addWidget(_col("PRIX ACHAT", 110))
        col_layout.addWidget(_col("TOTAL", 110))
        layout.addWidget(col_hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet("QWidget { background: #FFFFFF; }")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(20, 8, 20, 8)
        self._rows_layout.setSpacing(4)

        self._empty_lbl = QLabel()
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 32px;")
        self._rows_layout.addWidget(self._empty_lbl)
        self._rows_layout.addStretch()

        self._scroll.setWidget(self._rows_widget)
        layout.addWidget(self._scroll, 1)

        footer = QFrame()
        footer.setStyleSheet("QFrame { background: #FFFFFF; border-top: 1.5px solid #E5E7EB; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 12, 20, 12)
        footer_layout.setSpacing(12)

        footer_layout.addStretch()

        total_label = QLabel("Total facture :")
        total_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #374151; background: transparent;"
        )
        footer_layout.addWidget(total_label)

        self._total_lbl = QLabel("0 TND")
        self._total_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #059669; min-width: 150px; background: transparent;"
        )
        footer_layout.addWidget(self._total_lbl)
        footer_layout.addSpacing(20)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Confirmer facture")
        btn_ok.setFixedHeight(38)
        btn_ok.clicked.connect(self._confirm)

        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(btn_ok)
        layout.addWidget(footer)

    def _clear_rows(self):
        while self._rows:
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.deleteLater()

    def _set_empty_message(self, text: str):
        self._empty_lbl.setText(text)
        self._empty_lbl.setVisible(True)

    def _show_rows(self):
        self._empty_lbl.setVisible(False)

    def _selected_items(self) -> list[dict]:
        items: list[dict] = []
        for row in self._rows:
            data = row.get_data()
            if data["qty"] <= 0:
                continue
            items.append(
                {
                    "product_id": data["product_id"],
                    "product_name": data["product_name"],
                    "supplier_name": data["supplier_name"],
                    "quantity": data["qty"],
                    "unit_price": data["price"],
                    "line_total": data["total"],
                    "pack_count": data.get("pack_count", 0),
                    "pack_piece_count": data.get("pack_piece_count", 0),
                    "loose_qty": data.get("loose_qty", data["qty"]),
                }
            )
        return items

    def _on_supplier_changed(self):
        supplier_id = self._supplier_combo.currentData()
        self._btn_add_product.setEnabled(bool(supplier_id))
        self._clear_rows()

        if not supplier_id:
            self._set_empty_message("Choisissez un fournisseur pour afficher ses produits.")
            self._update_total()
            return

        products = SupplierController.get_products_for_supplier(int(supplier_id))
        if not products:
            self._set_empty_message(
                "Aucun produit actif pour ce fournisseur. Utilisez “Ajout produit” pour en créer un."
            )
            self._update_total()
            return

        self._show_rows()
        insert_at = self._rows_layout.count() - 1
        for product in products:
            row = _InvoiceItemRow(product, self._rows_widget)
            row.changed.connect(self._update_total)
            self._rows.append(row)
            self._rows_layout.insertWidget(insert_at, row)
            insert_at += 1
        self._update_total()

    def _add_product_for_supplier(self):
        supplier_id = self._supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "Fournisseur requis", "Choisissez d'abord un fournisseur.")
            return

        from app.views.products_view import ProductDialog

        dlg = ProductDialog(self, preset_supplier_id=int(supplier_id))
        if dlg.exec():
            self._on_supplier_changed()

    def _update_total(self):
        total = sum(row.get_data()["total"] for row in self._rows)
        value = f"{total:.3f}".rstrip("0").rstrip(".")
        self._total_lbl.setText(f"{value or '0'} TND")

    def _confirm(self):
        supplier_id = self._supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "Fournisseur requis", "Choisissez d'abord un fournisseur.")
            return

        items = self._selected_items()
        if not items:
            QMessageBox.warning(
                self,
                "Aucune quantité saisie",
                "Saisissez une quantité supérieure à 0 pour au moins un produit.",
            )
            return

        total_amount = round(sum(float(item["line_total"]) for item in items), 3)
        if total_amount <= 0:
            QMessageBox.warning(
                self,
                "Montant invalide",
                "Le total de la facture doit être supérieur à 0.",
            )
            return

        # Vérifications avant de toucher au stock : catégories sensibles,
        # conservation courte, dates d'expiration. Purement informatif, mais
        # placé ici pour laisser une chance de refuser la marchandise avant
        # que la facture et le stock ne soient enregistrés.
        warnings = StockController.check_reception(items)
        apply_expiry = False
        if warnings:
            warn_dialog = _ReceptionWarningsDialog(warnings, self)
            if not warn_dialog.exec():
                return
            apply_expiry = warn_dialog.should_apply_expiry()

        payment_dialog = _InvoicePaymentDialog(total_amount, self)
        if not payment_dialog.exec():
            return

        amount_paid = payment_dialog.get_paid_amount()
        remaining = round(total_amount - amount_paid, 3)
        supplier_name = self._supplier_combo.currentText().strip()
        reference = self._ref.text().strip() or None

        summary_lines = [
            f"Fournisseur : {supplier_name}",
            f"Total facture : {total_amount:.3f} TND",
            f"Montant payé : {amount_paid:.3f} TND",
        ]
        if remaining > 0:
            summary_lines.append(f"Crédit fournisseur : {remaining:.3f} TND")
        else:
            summary_lines.append("Facture réglée بالكامل.")
        summary_lines.append("")
        summary_lines.append("Confirmer l'enregistrement de la facture ?")

        reply = QMessageBox.question(
            self,
            "Confirmer facture",
            "\n".join(summary_lines),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            result = SupplierController.create_stock_invoice(
                int(supplier_id),
                items=items,
                amount_paid=amount_paid,
                reference=reference,
                notes=f"Ajout facture fournisseur : {supplier_name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", str(exc))
            return

        # Après l'enregistrement : la facture est la source de vérité du stock,
        # la date d'expiration n'est qu'une information dérivée. Si elle échoue,
        # la réception reste valide.
        expiry_updated = 0
        if apply_expiry:
            try:
                expiry_updated = StockController.apply_suggested_expiry(warnings)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Dates d'expiration",
                    f"La facture est enregistrée, mais les dates d'expiration n'ont pas pu "
                    f"être mises à jour :\n{exc}",
                )

        message = (
            f"Facture enregistrée.\n"
            f"Produits mis à jour : {result['item_count']}\n"
            f"Total : {result['amount_total']:.3f} TND\n"
            f"Payé : {result['amount_paid']:.3f} TND\n"
            f"Crédit : {result['remaining_amount']:.3f} TND"
        )
        if expiry_updated:
            message += f"\nDates d'expiration mises à jour : {expiry_updated}"
        QMessageBox.information(self, "Facture enregistrée", message)
        self.accept()


InvoiceScanDialog = InvoiceEntryDialog
