from __future__ import annotations
import os
import shutil
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QTextEdit, QDateEdit, QFileDialog, QMessageBox, QFrame,
    QScrollArea, QSizePolicy, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox,
)
from PySide6.QtCore import Qt, QDate, QLocale, Signal
from PySide6.QtGui import QPixmap

from app.views.widgets.search_bar import SearchBar
from app.views.widgets.data_table import DataTable
from app.views.widgets.price_input import PriceSpinBox
from app.views.widgets.quantity_input import configure_manual_spinbox
from app.controllers.product_controller import ProductController
from app.controllers.category_controller import CategoryController
from app.controllers.supplier_controller import SupplierController
from app.utils.qr_utils import generate_qr, generate_barcode_value
from app.utils.helpers import format_price, format_date
from app.ui.ui_loader import embed_ui
from app.views.dialog_theme import apply_light_dialog_theme
from config import PRODUCT_IMAGES_DIR


# Category → accent color mapping for card badges / placeholders
_CAT_COLORS: dict[str, str] = {
    "Produits laitiers":       "#2196F3",
    "Yaourts":                 "#9C27B0",
    "Boulangerie":             "#FF9800",
    "Pâtisseries":             "#E91E63",
    "Boissons":                "#00BCD4",
    "Fruits et légumes":       "#4CAF50",
    "Produits ménagers":       "#607D8B",
    "Épicerie":                "#FF5722",
    "Produits au poids":       "#8D6E63",
    "Autres (Pièces uniques)": "#FF6B35",
    "Autres":                  "#9E9E9E",
}

_UNIT_LABELS = {"piece": "pcs", "kg": "kg", "litre": "L"}

_PRODUCTS_PER_ROW = 7
_CARD_MIN_WIDTH = 165
_CARD_IMAGE_HEIGHT = 110
_CARD_BODY_HORIZONTAL_PADDING = 10

_CARD_QSS = (
    "QFrame#productCard {"
    "  background: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; }"
    "QFrame#productCard:hover {"
    "  border-color: #059669; background: #F7FFFE; }"
    "QFrame#productCard QLabel { background: transparent; }"
)


def _resolve_product_image_path(image_path: str | None) -> str:
    if not image_path:
        return ""
    path = Path(image_path)
    if not path.is_absolute():
        path = PRODUCT_IMAGES_DIR / image_path
    return str(path) if path.exists() else ""




def _normalized_price_text(raw_text: str) -> str:
    raw = (raw_text or "").replace(" ", "").replace("\u202f", "").replace("\xa0", "").strip().lower()
    for suffix in ("tnd", "dt", "t"):
        raw = raw.replace(suffix, "")
    if not raw:
        return ""
    if raw.isdigit():
        millimes = int(raw)
        return f"{millimes / 1000:.3f}"
    return raw.replace(",", ".")


def _product_price_spin_value(spin: QDoubleSpinBox) -> float:
    line_edit = spin.lineEdit()
    raw_user_text = spin.property("_last_user_text") or ""
    raw_text = raw_user_text or (line_edit.text() if line_edit is not None else spin.text())
    normalized = _normalized_price_text(raw_text)
    if not normalized:
        return 0.0
    try:
        return float(normalized)
    except ValueError:
        return float(spin.value())


def _normalize_product_price_spin(spin: QDoubleSpinBox) -> None:
    line_edit = spin.lineEdit()
    raw_user_text = spin.property("_last_user_text") or ""
    raw_text = raw_user_text or (line_edit.text() if line_edit is not None else spin.text())
    normalized = _normalized_price_text(raw_text)
    if not normalized:
        if line_edit is not None:
            line_edit.clear()
        spin.setProperty("_last_user_text", "")
        spin.setValue(0.0)
        return

    try:
        value = float(normalized)
    except ValueError:
        value = float(spin.value())

    spin.setProperty("_last_user_text", "")
    spin.setValue(value)


def _bind_product_price_spin(spin: QDoubleSpinBox) -> None:
    configure_manual_spinbox(spin, decimals=3, placeholder="0.000")
    line_edit = spin.lineEdit()
    if line_edit is None:
        return
    spin.setProperty("_last_user_text", "")
    line_edit.textEdited.connect(lambda text, s=spin: s.setProperty("_last_user_text", text))
    line_edit.editingFinished.connect(lambda s=spin: _normalize_product_price_spin(s))


def _store_product_image(source_path: str) -> str:
    PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    source = Path(source_path)
    safe_name = f"{source.stem}_{int(time.time() * 1000)}{source.suffix.lower()}"
    destination = PRODUCT_IMAGES_DIR / safe_name
    shutil.copy2(source, destination)
    return destination.name


# ─────────────────────────────────────────────────────────────────────────────
# Product Card widget
# ─────────────────────────────────────────────────────────────────────────────

class _ProductCard(QFrame):
    edit_requested   = Signal(dict)
    delete_requested = Signal(dict)

    def __init__(self, product: dict, card_width: int = _CARD_MIN_WIDTH, parent=None):
        super().__init__(parent)
        self._product = product
        self._card_width = max(_CARD_MIN_WIDTH, card_width)
        self._image_height = _CARD_IMAGE_HEIGHT
        self._body_width = self._card_width - (_CARD_BODY_HORIZONTAL_PADDING * 2)
        self.setObjectName("productCard")
        self.setFixedWidth(self._card_width)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_CARD_QSS)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build(self):
        p        = self._product
        cat_name = p.get("category_name") or ""
        color    = _CAT_COLORS.get(cat_name, "#059669")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        # ── Image area ────────────────────────────────────────────────────
        img_lbl = QLabel()
        img_lbl.setFixedSize(self._card_width, self._image_height)
        img_lbl.setAlignment(Qt.AlignCenter)

        img_path = _resolve_product_image_path(p.get("image_path"))
        if img_path:
            pix = QPixmap(img_path).scaled(
                self._card_width, self._image_height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            img_lbl.setPixmap(pix)
            img_lbl.setStyleSheet(
                "border-radius: 12px 12px 0 0; background: #F9FAFB;"
            )
        else:
            initial = (p.get("name") or "?")[0].upper()
            img_lbl.setText(initial)
            img_lbl.setStyleSheet(
                f"background: {color}20; color: {color};"
                "font-size: 56px; font-weight: 800;"
                "border-radius: 12px 12px 0 0;"
            )

        root.addWidget(img_lbl)

        # ── Body ──────────────────────────────────────────────────────────
        body = QVBoxLayout()
        body.setContentsMargins(_CARD_BODY_HORIZONTAL_PADDING, 8, _CARD_BODY_HORIZONTAL_PADDING, 0)
        body.setSpacing(4)

        name_lbl = QLabel(p.get("name", ""))
        name_lbl.setWordWrap(True)
        name_lbl.setFixedWidth(self._body_width)
        name_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #111827;"
        )
        body.addWidget(name_lbl)

        if cat_name:
            badge = QLabel(cat_name)
            badge.setMaximumWidth(self._body_width)
            badge.setStyleSheet(
                f"background: {color}22; color: {color};"
                "font-size: 10px; font-weight: 700; padding: 2px 8px;"
                "border-radius: 10px;"
            )
            body.addWidget(badge)

        supplier_name = p.get("supplier_name") or ""
        if supplier_name:
            supplier_lbl = QLabel(f"Fournisseur : {supplier_name}")
            supplier_lbl.setWordWrap(True)
            supplier_lbl.setMaximumWidth(self._body_width)
            supplier_lbl.setStyleSheet("font-size: 10px; color: #6B7280;")
            body.addWidget(supplier_lbl)

        body.addSpacing(6)

        price_lbl = QLabel(format_price(p.get("sale_price", 0)))
        price_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #059669;"
        )
        body.addWidget(price_lbl)

        qty     = p.get("stock_quantity", 0)
        min_qty = p.get("min_stock", 5)
        unit    = _UNIT_LABELS.get(p.get("unit_type", "piece"), "pcs")
        low     = qty <= min_qty
        s_color = "#EF4444" if low else "#6B7280"
        s_icon  = "⚠ " if low else ""
        stock_lbl = QLabel(f"{s_icon}Stock : {qty:.1f} {unit}")
        stock_lbl.setStyleSheet(f"font-size: 11px; color: {s_color};")
        body.addWidget(stock_lbl)

        root.addLayout(body)
        root.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        acts = QHBoxLayout()
        acts.setContentsMargins(12, 8, 12, 0)
        acts.setSpacing(6)

        btn_edit = QPushButton("Modifier")
        btn_edit.setFixedHeight(28)
        btn_edit.setStyleSheet(
            "QPushButton { background: transparent; border: 1.5px solid #D1D5DB;"
            "  color: #374151; border-radius: 6px; font-size: 10px; font-weight: 700;"
            "  padding: 0 6px; }"
            "QPushButton:hover { border-color: #059669; color: #059669; }"
        )
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self._product))

        btn_del = QPushButton("Supprimer")
        btn_del.setFixedHeight(28)
        btn_del.setStyleSheet(
            "QPushButton { background: #FEF2F2; border: 1.5px solid #FCA5A5; color: #DC2626;"
            "  border-radius: 6px; font-size: 10px; font-weight: 800; padding: 0 6px; }"
            "QPushButton:hover { background: #DC2626; color: white; border-color: #DC2626; }"
        )
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self._product))

        acts.addWidget(btn_edit, 1)
        acts.addWidget(btn_del, 1)
        root.addLayout(acts)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self._product)
        super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Main view
# ─────────────────────────────────────────────────────────────────────────────

class ProductsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_products: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self._search = SearchBar("🔍  Rechercher un produit...")
        self._search.search_changed.connect(self._filter)
        self._search.setMinimumHeight(42)

        self._cat_filter = QComboBox()
        self._cat_filter.setMinimumHeight(42)
        self._cat_filter.setMinimumWidth(200)
        self._cat_filter.currentIndexChanged.connect(self._filter)

        btn_add = QPushButton("＋  Nouveau produit")
        btn_add.setMinimumHeight(42)
        btn_add.clicked.connect(self._add_product)

        btn_low = QPushButton("⚠️  Stock faible")
        btn_low.setObjectName("btnWarning")
        btn_low.setMinimumHeight(42)
        btn_low.clicked.connect(self._show_low_stock)

        btn_pdf = QPushButton("📋  Importer PDF")
        btn_pdf.setObjectName("btnSecondary")
        btn_pdf.setMinimumHeight(42)
        btn_pdf.clicked.connect(self._import_pdf)

        btn_excel = QPushButton("📊  Importer Excel")
        btn_excel.setObjectName("btnSecondary")
        btn_excel.setMinimumHeight(42)
        btn_excel.clicked.connect(self._import_excel)

        toolbar.addWidget(self._search, 2)
        toolbar.addWidget(self._cat_filter)
        toolbar.addWidget(btn_low)
        toolbar.addWidget(btn_pdf)
        toolbar.addWidget(btn_excel)
        toolbar.addWidget(btn_add)
        layout.addLayout(toolbar)

        # ── Count label ───────────────────────────────────────────────────
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self._count_lbl)

        # ── Card grid (scrollable) ────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 4, 0, 16)
        self._grid.setSpacing(10)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

    # ── Data ──────────────────────────────────────────────────────────────

    def refresh(self):
        self._all_products = ProductController.get_all()
        self._load_categories()
        self._display(self._all_products)

    def _load_categories(self):
        self._cat_filter.blockSignals(True)
        current = self._cat_filter.currentData()
        self._cat_filter.clear()
        self._cat_filter.addItem("Toutes les catégories", None)
        for cat in CategoryController.get_all():
            self._cat_filter.addItem(cat["name"], cat["id"])
        if current:
            idx = self._cat_filter.findData(current)
            if idx >= 0:
                self._cat_filter.setCurrentIndex(idx)
        self._cat_filter.blockSignals(False)

    def _filter(self, *_args):
        query  = self._search.text().strip().lower()
        cat_id = self._cat_filter.currentData()
        result = self._all_products
        if query:
            result = [p for p in result if
                      query in p["name"].lower() or
                      query in (p.get("barcode") or "").lower()]
        if cat_id:
            result = [p for p in result if p.get("category_id") == cat_id]
        self._display(result)

    def _display(self, products: list[dict]):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        self._count_lbl.setText(f"{len(products)} produit(s)")

        if not products:
            lbl = QLabel("Aucun produit trouvé")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #9CA3AF; font-size: 15px; padding: 60px;")
            self._grid.addWidget(lbl, 0, 0, 1, _PRODUCTS_PER_ROW)
            return

        cols = min(_PRODUCTS_PER_ROW, max(1, len(products)))
        spacing = self._grid.horizontalSpacing()
        if spacing < 0:
            spacing = self._grid.spacing()

        margins = self._grid.contentsMargins()
        viewport_width = max(self._scroll.viewport().width(), 1)
        available_width = viewport_width - margins.left() - margins.right() - (spacing * (cols - 1))
        card_width = max(_CARD_MIN_WIDTH, available_width // cols)

        self._grid_widget.setMinimumWidth(viewport_width)

        for col in range(_PRODUCTS_PER_ROW):
            self._grid.setColumnStretch(col, 0)
        for col in range(cols):
            self._grid.setColumnStretch(col, 1)

        for i, p in enumerate(products):
            card = _ProductCard(p, card_width=card_width)
            card.edit_requested.connect(self._edit_product)
            card.delete_requested.connect(self._delete_product)
            self._grid.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._filter()

    # ── Actions ───────────────────────────────────────────────────────────

    def _add_product(self):
        dlg = ProductDialog(self)
        if dlg.exec():
            self.refresh()

    def _edit_product(self, product_data: dict):
        product = ProductController.get_by_id(product_data["id"])
        dlg = ProductDialog(self, product)
        if dlg.exec():
            self.refresh()

    def _delete_product(self, product_data: dict):
        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Voulez-vous vraiment supprimer le produit «{product_data['name']}» ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ProductController.delete(product_data["id"])
            self.refresh()

    def _show_low_stock(self):
        products = ProductController.get_low_stock()
        LowStockDialog(products, self).exec()

    def _open_barcode_import(self):
        from app.views.barcode_import_dialog import BarcodeBatchImportDialog
        BarcodeBatchImportDialog(self).exec()
        self.refresh()

    def _import_pdf(self):
        from app.views.pdf_import_dialog import PDFImportDialog
        dlg = PDFImportDialog(self)
        if dlg.exec():
            self.refresh()

    def _import_excel(self):
        from app.views.excel_import_dialog import ExcelImportDialog
        dlg = ExcelImportDialog(self)
        if dlg.exec():
            self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Product add / edit dialog
# ─────────────────────────────────────────────────────────────────────────────

class ProductDialog(QDialog):
    """
    Product add/edit dialog.

    UI is defined in  app/ui/product_dialog.ui  and loaded at runtime via
    QUiLoader — open that file in Qt Designer to change the layout visually.

    To edit the UI:
        pyside6-designer app/ui/product_dialog.ui

    To compile to Python (optional, for faster startup):
        python -m app.ui.compile_ui
    """

    _UI_FILE = Path(__file__).parent.parent / "ui" / "product_dialog.ui"

    def __init__(self, parent=None, product: dict = None, preset_supplier_id: int | None = None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self._product = product
        self._preset_supplier_id = preset_supplier_id
        self._image_path = product.get("image_path") if product else None
        self._sale_units: list[dict] = []

        self._load_ui()
        # Tall enough that the footer's buttons (now ~84px including their own
        # padding — see product_dialog.ui) sit below a comfortable amount of
        # visible form content instead of immediately clipping the last field.
        self.resize(780, 780)

        title = "Modifier le produit" if product else "Nouveau produit"
        self.setWindowTitle(title)
        self._ui.lblTitle.setText(title)

        # Populate dynamic combos from DB
        for cat in CategoryController.get_all():
            self._category.addItem(cat["name"], cat["id"])

        default_supplier_id = self._preset_supplier_id or ProductController.get_or_create_default_supplier_id()
        self._supplier.clear()
        for sup in SupplierController.get_all():
            self._supplier.addItem(sup["name"], sup["id"])
        default_index = self._supplier.findData(default_supplier_id)
        if default_index >= 0:
            self._supplier.setCurrentIndex(default_index)
        if self._preset_supplier_id:
            self._supplier.setEnabled(False)

        # Unit type data values (items are pre-defined in .ui)
        self._unit_type.setItemData(0, "piece")
        self._unit_type.setItemData(1, "kg")
        self._unit_type.setItemData(2, "litre")

        # Signal connections
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_save.clicked.connect(self._save)
        self._btn_pick_image.clicked.connect(self._pick_image)
        self._update_image_preview()

        if product:
            self._populate(product)

    def _load_ui(self):
        self._ui = embed_ui(self, self._UI_FILE.name)

        # Keep the embedded form surface explicitly light to avoid black areas
        # when the app was previously saved in dark mode.
        #
        # IMPORTANT: these must be selector-qualified ("QWidget#name { ... }"),
        # never a bare declaration list ("background: #FFFFFF;"). A bare
        # stylesheet on a container silently breaks Qt's style cascade for
        # every descendant: buttons and inputs inside it stop seeing both the
        # dialog's own theme (apply_light_dialog_theme) AND the app's global
        # stylesheet, rendering as colorless/blank instead of themed. This is
        # exactly what made the barcode field and "Enregistrer" button look
        # broken/unusable — they still worked, they just were not visible.
        self._ui.setObjectName("productDialogUiRoot")
        self._ui.setAttribute(Qt.WA_StyledBackground, True)
        self._ui.setStyleSheet("QWidget#productDialogUiRoot { background: #FFFFFF; }")
        scroll_area = getattr(self._ui, "scrollArea", None)
        form_widget = getattr(self._ui, "formWidget", None)
        if scroll_area is not None:
            scroll_area.setStyleSheet("QScrollArea { background: #FFFFFF; border: none; }")
            viewport = scroll_area.viewport()
            viewport.setObjectName("productDialogScrollViewport")
            viewport.setAttribute(Qt.WA_StyledBackground, True)
            viewport.setStyleSheet("QWidget#productDialogScrollViewport { background: #FFFFFF; }")
        if form_widget is not None:
            form_widget.setObjectName("productDialogFormWidget")
            form_widget.setAttribute(Qt.WA_StyledBackground, True)
            form_widget.setStyleSheet("QWidget#productDialogFormWidget { background: #FFFFFF; }")

        # Typed widget references (match objectName in .ui)
        self._name           = self._ui.name
        self._barcode        = self._ui.barcode
        self._category       = self._ui.category
        self._supplier       = self._ui.supplier
        self._purchase_price = self._ui.purchasePrice
        self._sale_price     = self._ui.salePrice
        self._stock          = self._ui.stock
        self._min_stock      = self._ui.minStock
        self._unit_type      = self._ui.unitType
        self._expiry         = self._ui.expiry
        self._description    = self._ui.description
        self._img_lbl        = self._ui.imgPreview
        self._btn_cancel     = getattr(self._ui, "btnCancel", None) or getattr(self, "btnCancel")
        self._btn_save       = getattr(self._ui, "btnSave", None) or getattr(self, "btnSave")
        self._btn_pick_image = getattr(self._ui, "btnPickImage", None) or getattr(self, "btnPickImage")

        _bind_product_price_spin(self._purchase_price)
        _bind_product_price_spin(self._sale_price)
        configure_manual_spinbox(self._stock, decimals=0, placeholder="0")
        configure_manual_spinbox(self._min_stock, decimals=0, placeholder="0")
        self._unit_type.currentIndexChanged.connect(self._apply_quantity_mode)
        self._apply_quantity_mode()
        self._build_sale_units_row()

    def _build_sale_units_row(self):
        form_layout = getattr(self._ui, "formLayout", None)
        if form_layout is None:
            return

        self._pack_enabled = QCheckBox("Activer le prix pack")
        self._pack_enabled.toggled.connect(self._sync_pack_fields_state)

        self._pack_qty = QDoubleSpinBox()
        configure_manual_spinbox(self._pack_qty, decimals=0, placeholder="6")
        self._pack_qty.setSingleStep(1)
        self._pack_qty.setMinimum(2)
        self._pack_qty.setMaximum(100000)
        self._pack_qty.setEnabled(False)

        self._pack_price = QDoubleSpinBox()
        _bind_product_price_spin(self._pack_price)
        self._pack_price.setEnabled(False)

        self._pack_hint_lbl = QLabel("Si activé, la caisse affichera un bouton Pack près du produit. Exemple prix pack : 4500 = 4.500 TND.")
        self._pack_hint_lbl.setWordWrap(True)
        self._pack_hint_lbl.setStyleSheet("color: #64748B; font-size: 11px;")

        row_fields = QHBoxLayout()
        row_fields.setContentsMargins(0, 0, 0, 0)
        row_fields.setSpacing(8)
        row_fields.addWidget(QLabel("Nb pièces"))
        row_fields.addWidget(self._pack_qty)
        row_fields.addWidget(QLabel("Prix pack"))
        row_fields.addWidget(self._pack_price, 1)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self._pack_enabled)
        lay.addLayout(row_fields)
        lay.addWidget(self._pack_hint_lbl)

        row = form_layout.rowCount()
        form_layout.insertRow(row, QLabel("Pack"), container)
        self._sale_units = []
        self._sync_pack_fields_state()

    def _sync_pack_fields_state(self):
        enabled = bool(getattr(self, "_pack_enabled", None) and self._pack_enabled.isChecked())
        unit_is_piece = (self._unit_type.currentData() or "piece") == "piece"
        row_enabled = enabled and unit_is_piece

        for widget in (getattr(self, "_pack_qty", None), getattr(self, "_pack_price", None)):
            if widget is not None:
                widget.setEnabled(row_enabled)

        if hasattr(self, "_pack_enabled"):
            self._pack_enabled.setVisible(unit_is_piece)
        if hasattr(self, "_pack_hint_lbl"):
            self._pack_hint_lbl.setVisible(unit_is_piece)

    def _refresh_sale_units_summary(self):
        self._sync_pack_fields_state()

    def _default_sale_units(self) -> list[dict]:
        units = [
            {
                "name": ProductController._base_sale_unit_name(self._unit_type.currentData() or "piece"),
                "quantity": 1.0,
                "sale_price": _product_price_spin_value(self._sale_price),
                "barcode": None,
                "is_default": True,
            }
        ]

        if (
            hasattr(self, "_pack_enabled")
            and self._pack_enabled.isChecked()
            and (self._unit_type.currentData() or "piece") == "piece"
        ):
            pack_qty = int(round(float(self._pack_qty.value() or 0)))
            pack_price = _product_price_spin_value(self._pack_price)
            if pack_qty >= 2 and pack_price > 0:
                units.append(
                    {
                        "name": "Pack",
                        "quantity": float(pack_qty),
                        "sale_price": pack_price,
                        "barcode": None,
                        "is_default": False,
                    }
                )

        return units

    def _load_pack_from_units(self, units: list[dict]):
        if not hasattr(self, "_pack_enabled"):
            return

        pack_unit = None
        for unit in units or []:
            if bool(unit.get("is_default")):
                continue
            quantity = float(unit.get("quantity") or 1.0)
            unit_name = str(unit.get("name") or "").strip().casefold()
            if quantity > 1.0 or "pack" in unit_name:
                pack_unit = unit
                break

        has_pack = pack_unit is not None
        self._pack_enabled.setChecked(has_pack)
        if has_pack:
            self._pack_qty.setValue(max(2, int(round(float(pack_unit.get("quantity") or 2)))))
            self._pack_price.setValue(float(pack_unit.get("sale_price") or 0.0))
        else:
            self._pack_qty.setValue(6)
            self._pack_price.setValue(0.0)
        self._sync_pack_fields_state()

    def _edit_sale_units(self):
        self._sync_pack_fields_state()

    def _apply_quantity_mode(self):
        unit_type = self._unit_type.currentData() or "piece"
        decimals = 0 if unit_type == "piece" else 3
        placeholder = "0" if decimals == 0 else "0.000"
        configure_manual_spinbox(self._stock, decimals=decimals, placeholder=placeholder)
        configure_manual_spinbox(self._min_stock, decimals=decimals, placeholder=placeholder)
        self._stock.setSingleStep(1 if decimals == 0 else 0.001)
        self._min_stock.setSingleStep(1 if decimals == 0 else 0.001)
        if len(self._sale_units) == 1:
            self._sale_units[0]["name"] = ProductController._base_sale_unit_name(unit_type)
        if unit_type != "piece" and hasattr(self, "_pack_enabled"):
            self._pack_enabled.setChecked(False)
        self._refresh_sale_units_summary()

    def _populate(self, p: dict):
        self._name.setText(p.get("name", ""))
        self._barcode.setText(p.get("barcode") or "")
        idx = self._category.findData(p.get("category_id"))
        if idx >= 0: self._category.setCurrentIndex(idx)
        idx = self._supplier.findData(p.get("supplier_id"))
        if idx >= 0:
            self._supplier.setCurrentIndex(idx)
        else:
            default_index = self._supplier.findData(self._preset_supplier_id or ProductController.get_or_create_default_supplier_id())
            if default_index >= 0:
                self._supplier.setCurrentIndex(default_index)
        if self._preset_supplier_id:
            self._supplier.setEnabled(False)
        self._purchase_price.setValue(p.get("purchase_price", 0))
        self._sale_price.setValue(p.get("sale_price", 0))
        self._stock.setValue(p.get("stock_quantity", 0))
        self._min_stock.setValue(p.get("min_stock", 5))
        idx = self._unit_type.findData(p.get("unit_type", "piece"))
        if idx >= 0: self._unit_type.setCurrentIndex(idx)
        if p.get("expiry_date"):
            self._expiry.setDate(QDate.fromString(p["expiry_date"], "yyyy-MM-dd"))
        self._description.setPlainText(p.get("description") or "")
        self._stock.setEnabled(False)
        self._sale_units = ProductController.get_sale_units(int(p["id"])) or self._default_sale_units()
        self._load_pack_from_units(self._sale_units)
        self._refresh_sale_units_summary()
        self._update_image_preview()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Image produit",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not path:
            return
        try:
            self._image_path = _store_product_image(path)
            self._update_image_preview()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ajouter l'image : {exc}")

    def _update_image_preview(self):
        resolved_path = _resolve_product_image_path(self._image_path)
        if resolved_path:
            pix = QPixmap(resolved_path)
            if not pix.isNull():
                self._img_lbl.setPixmap(
                    pix.scaled(60, 60, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
                self._img_lbl.setText("")
                return
        self._img_lbl.setPixmap(QPixmap())
        self._img_lbl.setText("📷")

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Le nom est obligatoire.")
            return
        purchase_price = _product_price_spin_value(self._purchase_price)
        sale_price = _product_price_spin_value(self._sale_price)
        _normalize_product_price_spin(self._purchase_price)
        _normalize_product_price_spin(self._sale_price)

        if sale_price <= 0:
            QMessageBox.warning(self, "Erreur", "Le prix de vente doit être supérieur à 0.")
            return

        expiry_str = None
        if self._expiry.date() != QDate(2000, 1, 1):
            expiry_str = self._expiry.date().toString("yyyy-MM-dd")

        image_path = self._image_path
        resolved_image = _resolve_product_image_path(image_path)
        if image_path and Path(image_path).is_absolute() and resolved_image == image_path:
            try:
                image_path = _store_product_image(image_path)
            except Exception:
                image_path = self._image_path

        sale_units = self._default_sale_units()
        if hasattr(self, "_pack_enabled") and self._pack_enabled.isChecked():
            pack_qty = int(round(float(self._pack_qty.value() or 0)))
            pack_price = _product_price_spin_value(self._pack_price)
            if pack_qty < 2:
                QMessageBox.warning(self, "Erreur", "Le pack doit contenir au moins 2 pièces.")
                return
            if pack_price <= 0:
                QMessageBox.warning(self, "Erreur", "Le prix pack doit être supérieur à 0.")
                return

        if len(sale_units) == 1 and not sale_units[0].get("barcode") and self._barcode.text().strip():
            sale_units[0]["barcode"] = None

        typed_barcode = self._barcode.text().strip()
        if typed_barcode:
            existing = ProductController.get_by_barcode(typed_barcode)
            current_id = self._product["id"] if self._product else None
            if existing and int(existing["id"]) != current_id:
                QMessageBox.warning(
                    self,
                    "Code-barres déjà utilisé",
                    f"Ce code-barres est déjà attribué au produit « {existing.get('name', '')} ».\n"
                    "Utilisez un code différent ou laissez le champ vide pour en générer un automatiquement.",
                )
                self._barcode.setFocus()
                self._barcode.selectAll()
                return

        data = {
            "name":           name,
            "barcode":        self._barcode.text().strip() or None,
            "category_id":    self._category.currentData(),
            "supplier_id":    self._supplier.currentData() or self._preset_supplier_id or ProductController.get_or_create_default_supplier_id(),
            "purchase_price": purchase_price,
            "sale_price":     sale_price,
            "stock_quantity": self._stock.value(),
            "min_stock":      self._min_stock.value(),
            "unit_type":      self._unit_type.currentData(),
            "expiry_date":    expiry_str,
            "description":    self._description.toPlainText().strip() or None,
            "image_path":     image_path,
            "sale_units":     sale_units,
        }
        try:
            if self._product:
                ProductController.update(self._product["id"], data)
            else:
                pid = ProductController.create(data)
                if not data["barcode"]:
                    bc = generate_barcode_value(pid)
                    from app.database.connection import db
                    db.execute("UPDATE products SET barcode=? WHERE id=?", (bc, pid))
            self.accept()
        except Exception as e:
            message = str(e)
            if "UNIQUE constraint failed" in message and "barcode" in message:
                message = (
                    "Ce code-barres est déjà utilisé par un autre produit "
                    "(éventuellement pour une de ses unités de vente : Pièce, Pack...)."
                )
            QMessageBox.critical(self, "Erreur", message)


class SaleUnitsDialog(QDialog):
    def __init__(self, units: list[dict], *, unit_type: str, default_sale_price: float, product_barcode: str | None, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle("Unités de vente")
        self.resize(780, 460)
        self._unit_type = unit_type
        self._default_sale_price = float(default_sale_price or 0.0)
        self._product_barcode = product_barcode
        self._build_ui()
        self._load_units(units)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info = QLabel(
            "Ajoutez plusieurs unités de vente. La quantité correspond au stock réel retiré."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #64748B; font-size: 12px;")
        layout.addWidget(info)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Nom", "Qté stock", "Prix vente", "Code-barres", "Défaut"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setColumnWidth(1, 110)
        self._table.setColumnWidth(2, 110)
        self._table.setMinimumHeight(280)
        layout.addWidget(self._table, 1)

        tools = QHBoxLayout()
        btn_add = QPushButton("＋  Ajouter unité")
        btn_add.clicked.connect(self._add_row)
        btn_del = QPushButton("🗑  Supprimer ligne")
        btn_del.setObjectName("btnSecondary")
        btn_del.clicked.connect(self._remove_current_row)
        tools.addWidget(btn_add)
        tools.addWidget(btn_del)
        tools.addStretch()
        layout.addLayout(tools)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Enregistrer")
        btn_ok.clicked.connect(self._validate)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _add_row(self, unit: dict | None = None):
        row = self._table.rowCount()
        self._table.insertRow(row)

        data = unit or {
            "name": ProductController._base_sale_unit_name(self._unit_type),
            "quantity": 1.0,
            "sale_price": self._default_sale_price,
            "barcode": None,
            "is_default": row == 0,
        }

        name_item = QTableWidgetItem(str(data.get("name") or ""))
        qty_item = QTableWidgetItem(f"{float(data.get('quantity') or 1.0):g}")
        price_item = QTableWidgetItem(f"{float(data.get('sale_price') or 0.0):.3f}")
        barcode_item = QTableWidgetItem(str(data.get("barcode") or ""))

        chk = QCheckBox()
        chk.setChecked(bool(data.get("is_default")))
        chk.stateChanged.connect(lambda *_: self._enforce_single_default(chk))

        self._table.setItem(row, 0, name_item)
        self._table.setItem(row, 1, qty_item)
        self._table.setItem(row, 2, price_item)
        self._table.setItem(row, 3, barcode_item)
        self._table.setCellWidget(row, 4, chk)

    def _load_units(self, units: list[dict]):
        for unit in units or []:
            self._add_row(unit)
        if self._table.rowCount() == 0:
            self._add_row()
        self._enforce_single_default()

    def _enforce_single_default(self, checked_box: QCheckBox | None = None):
        if checked_box is not None and checked_box.isChecked():
            for row in range(self._table.rowCount()):
                chk = self._table.cellWidget(row, 4)
                if chk is not checked_box:
                    chk.blockSignals(True)
                    chk.setChecked(False)
                    chk.blockSignals(False)

        if not any((self._table.cellWidget(row, 4).isChecked() for row in range(self._table.rowCount()))):
            first = self._table.cellWidget(0, 4)
            if first is not None:
                first.blockSignals(True)
                first.setChecked(True)
                first.blockSignals(False)

    def _remove_current_row(self):
        row = self._table.currentRow()
        if row < 0:
            row = self._table.rowCount() - 1
        if row < 0:
            return
        self._table.removeRow(row)
        if self._table.rowCount() == 0:
            self._add_row()
        self._enforce_single_default()

    def _validate(self):
        try:
            units = self.get_units()
        except Exception as exc:
            QMessageBox.warning(self, "Unités invalides", str(exc))
            return
        if not units:
            QMessageBox.warning(self, "Unités invalides", "Ajoutez au moins une unité.")
            return
        self.accept()

    def get_units(self) -> list[dict]:
        units: list[dict] = []
        seen_names: set[str] = set()
        seen_barcodes: set[str] = set()

        for row in range(self._table.rowCount()):
            name = (self._table.item(row, 0).text() if self._table.item(row, 0) else "").strip()
            qty_raw = (self._table.item(row, 1).text() if self._table.item(row, 1) else "").strip().replace(",", ".")
            price_raw = (self._table.item(row, 2).text() if self._table.item(row, 2) else "").strip().replace(",", ".")
            barcode = (self._table.item(row, 3).text() if self._table.item(row, 3) else "").strip() or None
            is_default = bool(self._table.cellWidget(row, 4).isChecked())

            if not name:
                raise ValueError(f"Nom manquant sur la ligne {row + 1}.")
            try:
                quantity = float(qty_raw)
            except ValueError:
                raise ValueError(f"Quantité invalide sur la ligne {row + 1}.")
            try:
                sale_price = float(price_raw)
            except ValueError:
                raise ValueError(f"Prix invalide sur la ligne {row + 1}.")

            if quantity <= 0:
                raise ValueError(f"Quantité invalide sur la ligne {row + 1}.")
            if sale_price < 0:
                raise ValueError(f"Prix invalide sur la ligne {row + 1}.")

            key = name.casefold()
            if key in seen_names:
                raise ValueError(f"Nom dupliqué : {name}")
            seen_names.add(key)

            if barcode:
                normalized = ProductController.normalize_barcode(barcode)
                if normalized in seen_barcodes:
                    raise ValueError(f"Code-barres dupliqué : {barcode}")
                seen_barcodes.add(normalized)

            units.append(
                {
                    "name": name,
                    "quantity": int(round(quantity)) if self._unit_type == "piece" and abs(quantity - round(quantity)) < 0.001 else round(quantity, 3),
                    "sale_price": round(sale_price, 3),
                    "barcode": barcode,
                    "is_default": is_default,
                }
            )

        if not any(unit["is_default"] for unit in units):
            units[0]["is_default"] = True
        return units



# ─────────────────────────────────────────────────────────────────────────────
# Stock entry (from product card)
# ─────────────────────────────────────────────────────────────────────────────

class StockEntryDialog(QDialog):
    def __init__(self, product_id: int, product_name: str, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self._product_id = product_id
        self.setWindowTitle("Entrée de stock")
        self.setFixedWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(QLabel(f"<b>Produit :</b> {product_name}"))

        form = QFormLayout()
        self._qty = QDoubleSpinBox()
        self._qty.setMinimumHeight(42)
        self._qty.setMinimum(0.01)
        self._qty.setMaximum(99_999)
        self._qty.setDecimals(2)
        self._qty.setValue(1)
        self._qty.setLocale(QLocale(QLocale.Language.C))
        self._qty.setGroupSeparatorShown(False)

        self._ref = QLineEdit()
        self._ref.setMinimumHeight(42)
        self._ref.setPlaceholderText("N° de livraison, fournisseur...")

        self._notes = QLineEdit()
        self._notes.setMinimumHeight(42)
        self._notes.setPlaceholderText("Remarques optionnelles...")

        form.addRow("Quantité à ajouter *:", self._qty)
        form.addRow("Référence:",             self._ref)
        form.addRow("Notes:",                 self._notes)
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
        from app.controllers.stock_controller import StockController
        StockController.add_stock(
            self._product_id, self._qty.value(),
            self._notes.text(), self._ref.text()
        )
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Low stock overview dialog
# ─────────────────────────────────────────────────────────────────────────────

class LowStockDialog(QDialog):
    def __init__(self, products: list, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle("Produits en stock faible")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(QLabel(f"<b>{len(products)} produit(s) en stock insuffisant</b>"))
        tbl = DataTable(["Produit", "Catégorie", "Stock actuel", "Stock minimum"])
        tbl.set_data(products, ["name", "category_name", "stock_quantity", "min_stock"])
        layout.addWidget(tbl, 1)
        btn = QPushButton("Fermer")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, 0, Qt.AlignRight)
