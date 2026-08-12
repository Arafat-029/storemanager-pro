from __future__ import annotations
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QMessageBox, QDialog, QComboBox,
    QFormLayout, QDoubleSpinBox, QSizePolicy, QListWidget,
    QListWidgetItem, QAbstractItemView, QToolButton, QCheckBox,
    QInputDialog,
)
from PySide6.QtCore import Qt, QSize, QLocale, QSignalBlocker, QTimer, QEvent, Signal, QRegularExpression
from PySide6.QtGui import QPixmap, QColor, QPainter, QPainterPath, QFont, QIcon, QIntValidator, QDoubleValidator, QRegularExpressionValidator, QValidator

from app.controllers.product_controller import ProductController
from app.controllers.category_controller import CategoryController
from app.controllers.customer_controller import CustomerController
from app.controllers.sale_controller import SaleController
from app.controllers.auth_controller import AuthController
from app.database.connection import db
from app.utils.helpers import format_price
from app.utils.exporter import generate_thermal_receipt
from app.views.widgets.price_input import PriceSpinBox
from app.views.widgets.quantity_input import QuantitySpinBox
from app.utils.barcode_scanner import BarcodeScannerDialog, SCANNER_AVAILABLE
from app.views.dialog_theme import (
    apply_dialog_theme,
    apply_light_dialog_theme,
    light_critical,
    light_information,
    light_question,
    light_warning,
)
from app.utils.thumbnails import load_thumbnail as _load_thumbnail
from config import PRODUCT_IMAGES_DIR, CATEGORY_IMAGES_DIR
import subprocess, sys, time

# ── Touch-first sizing system ─────────────────────────────────
# Every interactive control is at least _TOUCH_MIN tall so it can be hit
# reliably on a checkout touchscreen; _GAP is the single spacing rhythm.
_TOUCH_MIN = 44
_GAP       = 12
_PAD       = 16

_CARD_W  = 134
_CARD_MAX_W = 220  # upper bound a card can stretch to in the responsive grid
_CARD_H  = 206
_IMG_H   = 128   # the product photo is the card's main subject
_COLS    = 6

_SEARCH_H = 60   # the search field and its button share this exact height

_CAT_W   = 100   # category strip button width
_CAT_H   = 104   # category strip button height
_CAT_IMG = 66    # category image size (square) — large enough that a real
                  # photo reads clearly instead of a blurry postage stamp
_CAT_STRIP_H = _CAT_H + 16  # strip viewport: buttons + padding + h-scrollbar
_CAT_SELECTED_COLOR = "#059669"  # single accent for the selected category, regardless
                                  # of that category's own icon color (matches the app's
                                  # primary green used for the cart's main CTA)

# Rendered category icons, keyed by (label, color, image_path). Module level so
# it survives POSView being rebuilt; see POSView._make_cat_icon for the why.
_CAT_ICON_CACHE: dict[tuple, QIcon] = {}

_CART_PANEL_W = 480  # fixed cart sidebar width; the catalog absorbs the rest
_CART_HEADER_H = 52

_CART_ROW_HEIGHT = 84   # two text lines + a full 44px stepper row
_CART_ROW_ITEM_EXTRA = 0
_CART_LIST_SPACING = 8
_CART_VISIBLE_ROWS = 4
_CART_SCROLL_MIN_ROWS = 4

_CAT_EMOJI: dict[str, str] = {
    "tous":     "🏪",
    "boisson":  "🥤",
    "lait":     "🥛",
    "yaourt":   "🥛",
    "boulang":  "🍞",
    "pâtiss":   "🥐",
    "fruit":    "🍎",
    "légume":   "🥦",
    "épicerie": "🛒",
    "viande":   "🥩",
    "poisson":  "🐟",
    "fromage":  "🧀",
    "surgelé":  "🧊",
    "hygièn":   "🧴",
    "nettoy":   "🧹",
    "confis":   "🍬",
    "chocol":   "🍫",
    "café":     "☕",
    "thé":      "🍵",
    "autre":    "📦",
    "divers":   "📦",
}


def _format_quantity(value: float, unit_type: str) -> str:
    if unit_type == "piece" and abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{float(value):.3f}"


def _cart_item_height() -> int:
    return _CART_ROW_HEIGHT + _CART_ROW_ITEM_EXTRA


def _cart_visible_height() -> int:
    return (_cart_item_height() * _CART_VISIBLE_ROWS) + (_CART_LIST_SPACING * (_CART_VISIBLE_ROWS - 1)) + 22


def _cart_scroll_min_height() -> int:
    return (_cart_item_height() * _CART_SCROLL_MIN_ROWS) + (_CART_LIST_SPACING * (_CART_SCROLL_MIN_ROWS - 1)) + 20


def _grid_columns_for_width(width: int) -> int:
    """Number of product-card columns that comfortably fill the given viewport width."""
    if width <= 0:
        return 6
    return 5 if width < 650 else 6


def _normalized_text(value: str | None) -> str:
    return (value or "").strip().lower()

_WEIGHT_CATEGORY_NAMES = {
    "produits au poids",
}


_SCAN_SYMBOL_TO_DIGIT = {
    "&": "1",
    "é": "2",
    '"': "3",
    "'": "4",
    "(": "5",
    "-": "6",
    "è": "7",
    "_": "8",
    "ç": "9",
    "à": "0",
}


def _is_gram_priced_product(product: dict) -> bool:
    return (
        _normalized_text(product.get("unit_type")) == "kg"
        and _normalized_text(product.get("category_name")) in _WEIGHT_CATEGORY_NAMES
    )


def _grams_from_quantity(quantity_kg: float) -> int:
    return int(round(float(quantity_kg) * 1000))


def _format_grams(value: float | int) -> str:
    return f"{int(round(float(value)))} g"


def _cart_quantity_text(item: dict) -> str:
    if item.get("pricing_mode") == "gram":
        grams = item.get("display_weight_g")
        if grams is None:
            grams = _grams_from_quantity(item.get("quantity", 0))
        return _format_grams(grams)
    return _format_quantity(item["quantity"], item["unit_type"])


def _cart_details_text(item: dict) -> str:
    if item.get("pricing_mode") == "gram":
        grams = item.get("display_weight_g")
        if grams is None:
            grams = _grams_from_quantity(item.get("quantity", 0))
        return f"Poids {_format_grams(grams)}"

    qty = _format_quantity(item["quantity"], "piece")
    pieces_in_sale_unit = float(item.get("stock_quantity_per_unit") or 1.0)
    if pieces_in_sale_unit > 1.0:
        pieces_text = _format_quantity(pieces_in_sale_unit, "piece")
        return f"Qté {qty} • {pieces_text} pcs"
    return f"Qté {qty}"


def _cart_unit_price_text(item: dict) -> str:
    unit = "kg" if item["unit_type"] == "kg" else ("L" if item["unit_type"] == "litre" else "u")
    return f"Prix {format_price(item['unit_price'])} / {unit}"


def _spin_numeric_value(spin: QDoubleSpinBox) -> float:
    line_edit = spin.lineEdit()
    raw = line_edit.text() if line_edit else spin.text()
    raw = (raw or "").replace("\xa0", "").replace(" ", "").strip().lower()
    raw = raw.replace(",", ".")
    for suffix in ("tnd", "kg", "g", "l"):
        raw = raw.replace(suffix, "")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return float(spin.value())


def _parse_payment_amount_text(raw: str | None) -> float:
    clean = (raw or "").replace("\xa0", "").replace(" ", "").strip().lower()
    for suffix in ("tnd", "dt"):
        clean = clean.replace(suffix, "")
    if not clean:
        return 0.0
    clean = clean.replace(",", ".")
    try:
        return round(float(clean), 3)
    except ValueError:
        return 0.0


class MillimeAmountLineEdit(QLineEdit):
    """Cash-register style amount entry (Tunisian millime convention).

    Digits build the value from the smallest denomination upward, exactly
    like a real cash-register keypad: typing "5" gives 0.005, then typing
    "0","0","0" gives 5.000. No decimal point is ever typed. The field can be
    pre-filled with a suggested amount (e.g. the exact total); the first
    digit the user types clears that suggestion and starts a fresh entry
    instead of appending after it.
    """

    _MAX_MILLIMES = 999_999_999  # matches the app-wide 999999.999 TND ceiling

    def __init__(self, parent=None):
        super().__init__(parent)
        self._millimes = 0
        self._fresh = True
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setContextMenuPolicy(Qt.NoContextMenu)  # no pasting arbitrary text
        self._refresh_text()

    def set_value(self, amount: float) -> None:
        self._millimes = max(0, min(self._MAX_MILLIMES, int(round(float(amount) * 1000))))
        self._fresh = True
        self._refresh_text()

    def value(self) -> float:
        return self._millimes / 1000.0

    def mark_for_fresh_entry(self) -> None:
        """Make the next digit typed start a new value instead of appending."""
        self._fresh = True

    def _refresh_text(self) -> None:
        # setText() already emits textChanged when the value actually differs,
        # which is what PaymentDialog listens to for the live change/error update.
        self.setText(f"{self._millimes / 1000:.3f}")

    def _apply_digit(self, digit: int) -> None:
        base = 0 if self._fresh else self._millimes
        self._millimes = min(base * 10 + digit, self._MAX_MILLIMES)
        self._fresh = False
        self._refresh_text()

    def keyPressEvent(self, event):
        text = event.text()
        if text and text.isdigit():
            self._apply_digit(int(text))
            return
        key = event.key()
        if key == Qt.Key_Backspace:
            self._millimes = 0 if self._fresh else self._millimes // 10
            self._fresh = False
            self._refresh_text()
            return
        if key == Qt.Key_Delete:
            self._millimes = 0
            self._fresh = True
            self._refresh_text()
            return
        if key in (
            Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Escape,
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End,
        ):
            super().keyPressEvent(event)
            return
        # Block letters, '.', ',', and anything else: the value can only ever
        # be "digits typed so far ÷ 1000".
        event.ignore()


class POSView(QWidget):
    cash_expected_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cart: list[dict] = []
        self._active_cat_id: int | None = None
        self._default_category_applied = False
        self._cat_buttons: list[tuple[QPushButton, int | None]] = []
        self._displayed_products: list[dict] = []
        self._current_grid_columns = _COLS
        self._sale_units_cache: dict[int, list[dict]] = {}
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(140)
        self._scan_timer.timeout.connect(self._try_auto_barcode_scan)

        self._global_scan_buffer = ""
        self._global_scan_last_ts = 0
        self._global_scan_last_monotonic = 0.0
        self._global_scan_mode = False
        self._global_scan_timer = QTimer(self)
        self._global_scan_timer.setSingleShot(True)
        self._global_scan_timer.setInterval(120)
        self._global_scan_timer.timeout.connect(self._flush_global_scan_buffer)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._opening_cash_checked_key = ""
        self._catalog_restore_scheduled = False
        self._build_ui()
        self._load_categories()
        self._show_catalog()

    # ──────────────────────────────────────────── Build UI ─────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Catalog and cart sit side by side. The cart keeps a fixed width so the
        # layout — and with it the product grid's column count — stays
        # deterministic; the catalog absorbs whatever width is left over.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body)

        # ── Left: Catalog ──────────────────────────────────────
        left = QWidget()
        self._catalog_panel = left
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(_PAD, _GAP, _PAD, _GAP)
        left_layout.setSpacing(_GAP)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setSpacing(_GAP)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Nom ou code-barres…")
        self._search_input.setObjectName("searchBar")
        self._search_input.returnPressed.connect(self._on_scan)
        self._search_input.textChanged.connect(self._on_search_changed)

        btn_search = QPushButton("Rechercher")
        btn_search.setObjectName("posSearchBtn")
        btn_search.setCursor(Qt.PointingHandCursor)
        btn_search.setFixedWidth(150)
        btn_search.clicked.connect(self._on_scan)

        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(btn_search)
        left_layout.addLayout(search_row)

        # Category filter strip
        self._cat_scroll = QScrollArea()
        self._cat_scroll.setFixedHeight(_CAT_STRIP_H)
        self._cat_scroll.setWidgetResizable(False)
        self._cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cat_scroll.horizontalScrollBar().setSingleStep(24)
        self._cat_scroll.setFrameShape(QFrame.NoFrame)
        self._cat_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._cat_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:horizontal { height: 8px; background: transparent; margin: 2px 0 0 0; }"
            "QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 4px; min-width: 24px; }"
            "QScrollBar::handle:horizontal:hover { background: #94A3B8; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }"
        )

        self._cat_strip = QWidget()
        self._cat_strip_lay = QHBoxLayout(self._cat_strip)
        self._cat_strip_lay.setContentsMargins(0, 2, 8, 6)
        self._cat_strip_lay.setSpacing(10)
        self._cat_strip_lay.addStretch()
        self._cat_scroll.setWidget(self._cat_strip)
        left_layout.addWidget(self._cat_scroll)

        # Product count
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("font-size: 12px; color: #6B7280;")
        left_layout.addWidget(self._count_lbl)

        # Product grid (image cards)
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setFrameShape(QFrame.NoFrame)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setHorizontalSpacing(_GAP)
        self._grid_layout.setVerticalSpacing(_GAP)
        # Zero margins so cards align flush with the search bar and category strip.
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setAlignment(Qt.AlignTop)
        self._grid_scroll.setWidget(self._grid_widget)
        left_layout.addWidget(self._grid_scroll, 1)

        body.addWidget(left, 1)

        # ── Right: Cart ───────────────────────────────────────
        cart_panel = QFrame()
        cart_panel.setObjectName("cartPanel")
        cart_panel.setFixedWidth(_CART_PANEL_W)
        cart_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        cart_layout = QVBoxLayout(cart_panel)
        cart_layout.setContentsMargins(0, 0, 0, 0)
        cart_layout.setSpacing(0)

        # Header — the cart owns its own title bar: item count plus the
        # deliberately low-contrast clear action.
        cart_header = QFrame()
        cart_header.setObjectName("cartHeader")
        cart_header.setFixedHeight(_CART_HEADER_H)
        header_lay = QHBoxLayout(cart_header)
        header_lay.setContentsMargins(_GAP, 0, _GAP, 0)
        header_lay.setSpacing(10)

        cart_title_lbl = QLabel("Panier")
        cart_title_lbl.setObjectName("cartTitleLabel")
        header_lay.addWidget(cart_title_lbl)

        self._cart_count_lbl = QLabel()
        self._cart_count_lbl.setObjectName("cartCountLabel")
        header_lay.addWidget(self._cart_count_lbl)

        header_lay.addStretch()

        # Heights of the cart controls live in the theme (.qss): its global
        # QPushButton/QLineEdit rules carry a min-height that overrides any
        # setFixedHeight() here, so the stylesheet is the single source of truth.
        self._btn_clear_cart = QPushButton("Vider")
        self._btn_clear_cart.setObjectName("cartClearBtn")
        self._btn_clear_cart.setCursor(Qt.PointingHandCursor)
        self._btn_clear_cart.setToolTip("Vider le panier")
        self._btn_clear_cart.clicked.connect(self._clear_cart)
        header_lay.addWidget(self._btn_clear_cart)

        cart_layout.addWidget(cart_header)

        self._cart_empty_lbl = QLabel("Aucun produit dans le panier.")
        self._cart_empty_lbl.setAlignment(Qt.AlignCenter)
        self._cart_empty_lbl.setWordWrap(True)
        self._cart_empty_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600; padding: 28px 12px;")

        self._cart_list = QListWidget()
        self._cart_list.setObjectName("cartList")
        self._cart_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._cart_list.setFocusPolicy(Qt.NoFocus)
        self._cart_list.setAlternatingRowColors(False)
        self._cart_list.setSpacing(_CART_LIST_SPACING)
        self._cart_list.setUniformItemSizes(False)
        self._cart_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._cart_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._cart_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cart_list.setFrameShape(QFrame.NoFrame)
        self._cart_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cart_list.setMinimumHeight(_cart_visible_height())
        self._cart_list.verticalScrollBar().setSingleStep(max(24, _cart_item_height() // 2))
        self._cart_list.setStyleSheet(
            "QListWidget#cartList {"
            "padding: 0 6px 0 0;"
            "border: none;"
            "background: transparent;"
            "}"
            "QListWidget#cartList QScrollBar:vertical {"
            "background: #E5EAF2;"
            "width: 10px;"
            "margin: 4px 0 4px 4px;"
            "border-radius: 5px;"
            "}"
            "QListWidget#cartList QScrollBar::handle:vertical {"
            "background: #94A3B8;"
            "min-height: 34px;"
            "border-radius: 5px;"
            "}"
            "QListWidget#cartList QScrollBar::handle:vertical:hover {"
            "background: #64748B;"
            "}"
            "QListWidget#cartList QScrollBar::add-line:vertical, QListWidget#cartList QScrollBar::sub-line:vertical {"
            "height: 0;"
            "}"
            "QListWidget#cartList QScrollBar::add-page:vertical, QListWidget#cartList QScrollBar::sub-page:vertical {"
            "background: transparent;"
            "}"
        )

        cart_content = QWidget()
        cart_content_lay = QVBoxLayout(cart_content)
        cart_content_lay.setContentsMargins(_GAP, _GAP, _GAP, 8)
        cart_content_lay.setSpacing(8)
        cart_content_lay.addWidget(self._cart_empty_lbl)
        cart_content_lay.addWidget(self._cart_list, 1)

        bottom_panel = QWidget()
        bottom_panel.setObjectName("cartBottomPanel")
        bottom_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(_GAP, _GAP, _GAP, _GAP)
        bottom_layout.setSpacing(_GAP)

        self._cash_expected_lbl = QLabel()
        self._cash_expected_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #0F172A;"
            "background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 6px 8px;"
        )

        # The single summary zone for the whole POS. Deliberately minimal: no fill,
        # just a hairline frame — only the amount carries visual weight.
        total_panel = QFrame()
        total_panel.setObjectName("cartTotalPanel")
        total_lay = QHBoxLayout(total_panel)
        total_lay.setContentsMargins(_PAD, _GAP, _PAD, _GAP)
        total_lay.setSpacing(8)

        total_caption = QLabel("Total à payer")
        total_caption.setObjectName("cartTotalCaption")
        self._total_lbl = QLabel("0.000 TND")
        self._total_lbl.setObjectName("cartTotalLabel")
        self._total_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_lay.addWidget(total_caption, 0, Qt.AlignVCenter)
        total_lay.addStretch()
        total_lay.addWidget(self._total_lbl, 0, Qt.AlignVCenter)

        # Both payment methods are primary actions: same row, same width, same
        # height, same radius — only the hue separates them.
        btn_cash = QPushButton("💵   Payer en espèces")
        btn_cash.setObjectName("cartPayCashBtn")
        btn_cash.setCursor(Qt.PointingHandCursor)
        btn_cash.clicked.connect(lambda: self._checkout("cash"))

        btn_credit = QPushButton("👤   Crédit client")
        btn_credit.setObjectName("cartPayCreditBtn")
        btn_credit.setCursor(Qt.PointingHandCursor)
        btn_credit.clicked.connect(lambda: self._checkout("credit"))

        pay_row = QHBoxLayout()
        pay_row.setSpacing(_GAP)
        pay_row.addWidget(btn_cash, 1)
        pay_row.addWidget(btn_credit, 1)

        self._cash_expected_lbl.hide()
        bottom_layout.addWidget(total_panel)
        bottom_layout.addLayout(pay_row)

        cart_layout.addWidget(cart_content, 1)
        cart_layout.addWidget(bottom_panel, 0)

        body.addWidget(cart_panel, 0)

    def refresh(self):
        self._sale_units_cache.clear()
        self._ensure_opening_cash_initialized()
        self._load_categories()
        if self._search_input.text().strip():
            self._on_search_changed(self._search_input.text())
        else:
            self._show_catalog()
        self._render_cart()
        self._update_cash_expected_label()
        self._schedule_catalog_restore()


    def _setting_value(self, key: str, default: str = "") -> str:
        row = db.fetchone("SELECT value FROM settings WHERE `key`=?", (key,))
        return str((row or {}).get("value") or default)

    def _save_setting_value(self, key: str, value: str) -> None:
        if db.is_mysql():
            db.execute(
                "INSERT INTO settings (`key`, value) VALUES (?, ?) ON DUPLICATE KEY UPDATE value=VALUES(value), updated_at=NOW()",
                (key, value),
            )
        else:
            db.execute("INSERT OR REPLACE INTO settings (`key`, value) VALUES (?, ?)", (key, value))

    def _delete_setting_value(self, key: str) -> None:
        db.execute("DELETE FROM settings WHERE `key`=?", (key,))

    def _current_user_id(self) -> int:
        current_user = AuthController.current_user() or {}
        return int(current_user.get("id") or 0)

    def _is_cashier_user(self) -> bool:
        current_user = AuthController.current_user() or {}
        return str(current_user.get("role") or "").strip().lower() == "cashier"

    def _paused_cashier_user_key(self) -> str:
        return "cashier_pause_active_user_id"

    def _paused_cashier_date_key(self) -> str:
        return "cashier_pause_active_date"

    def _clear_stale_pause_state(self) -> None:
        pause_date = self._setting_value(self._paused_cashier_date_key(), "")
        today = datetime.now().date().isoformat()
        if pause_date and pause_date != today:
            self._delete_setting_value(self._paused_cashier_user_key())
            self._delete_setting_value(self._paused_cashier_date_key())

    def _paused_cashier_user_id(self) -> int | None:
        self._clear_stale_pause_state()
        raw = self._setting_value(self._paused_cashier_user_key(), "").strip()
        return int(raw) if raw.isdigit() else None

    def _resume_current_cashier_if_paused(self) -> None:
        if self._paused_cashier_user_id() == self._current_user_id():
            self._delete_setting_value(self._paused_cashier_user_key())
            self._delete_setting_value(self._paused_cashier_date_key())

    def _cash_expected_summary(self) -> dict:
        opening_cash = float(self._setting_value(self._opening_cash_setting_key(), "0") or 0.0)
        summary = SaleController.get_cash_expected_today(
            opening_cash=opening_cash,
            user_id=self._current_user_id() if self._is_cashier_user() else None,
        )
        summary["opening_cash_text"] = format_price(summary.get("opening_cash", 0))
        summary["total_received_text"] = format_price(summary.get("total_received", 0))
        summary["expected_cash_text"] = format_price(summary.get("expected_cash", 0))
        return summary

    def pause_current_shift(self) -> tuple[bool, str]:
        if not self._is_cashier_user():
            return True, ""
        paused_user_id = self._paused_cashier_user_id()
        current_user_id = self._current_user_id()
        if paused_user_id and paused_user_id != current_user_id:
            other_user = db.fetchone("SELECT full_name, username FROM users WHERE id=?", (paused_user_id,)) or {}
            other_name = other_user.get("full_name") or other_user.get("username") or f"#{paused_user_id}"
            return False, f"Le caissier « {other_name} » est déjà en pause."
        self._save_setting_value(self._paused_cashier_user_key(), str(current_user_id))
        self._save_setting_value(self._paused_cashier_date_key(), datetime.now().date().isoformat())
        return True, ""

    def finish_current_shift(self) -> dict:
        summary = self._cash_expected_summary()
        if self._paused_cashier_user_id() == self._current_user_id():
            self._delete_setting_value(self._paused_cashier_user_key())
            self._delete_setting_value(self._paused_cashier_date_key())
        self._delete_setting_value(self._opening_cash_setting_key())
        self._opening_cash_checked_key = ""
        self._update_cash_expected_label()
        return summary

    def _schedule_catalog_restore(self) -> None:
        if self._catalog_restore_scheduled:
            return
        self._catalog_restore_scheduled = True
        QTimer.singleShot(0, self._run_scheduled_catalog_restore)

    def _run_scheduled_catalog_restore(self) -> None:
        self._catalog_restore_scheduled = False
        try:
            self._ensure_category_strip_ready()
            self._ensure_catalog_visible()
        except Exception:
            pass


    def _prompt_opening_cash_amount(self) -> tuple[str, bool]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Ouverture de caisse")
        dialog.setModal(True)
        dialog.setMinimumWidth(430)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        app_stylesheet = (QApplication.instance().styleSheet() or "").lower()
        is_dark_theme = any(token in app_stylesheet for token in ("#0b1121", "#0d1525", "#111b2e", "dark"))
        apply_dialog_theme(dialog, dark=is_dark_theme)
        dialog.setStyleSheet(
            dialog.styleSheet()
            + """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:1 #F8FAFC);
                border: 1px solid #E5E7EB;
                border-radius: 18px;
            }
            QLabel#openingCashTitle {
                color: #111827;
                font-size: 17px;
                font-weight: 800;
                margin-bottom: 4px;
            }
            QLabel#openingCashSubtitle {
                color: #6B7280;
                font-size: 12px;
                font-weight: 500;
                margin-bottom: 10px;
            }
            QLineEdit {
                background: #FFFFFF;
                border: 1.5px solid #D1D5DB;
                border-radius: 10px;
                padding: 10px 12px;
                min-height: 40px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #2563EB;
                background: #F8FAFC;
            }
            QPushButton {
                min-width: 112px;
                padding: 9px 16px;
                border-radius: 10px;
                background: #2563EB;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background: #1D4ED8;
            }
            QPushButton:pressed {
                background: #1E40AF;
            }
            QPushButton#btnSecondary {
                background: transparent;
                border: 1.5px solid #D1D5DB;
                color: #6B7280;
            }
            QPushButton#btnSecondary:hover {
                background: #F9FAFB;
                color: #111827;
                border-color: #2563EB;
            }
            """
        )

        title_lbl = QLabel("Montant de départ")
        title_lbl.setObjectName("openingCashTitle")
        subtitle_lbl = QLabel("Renseignez le montant disponible au démarrage de la journée.")
        subtitle_lbl.setObjectName("openingCashSubtitle")
        subtitle_lbl.setWordWrap(True)

        amount_edit = QLineEdit("0")
        amount_edit.setPlaceholderText("12.500")
        amount_edit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        amount_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*(?:\.\d{0,3})?$"), amount_edit))
        amount_edit.setClearButtonEnabled(True)
        amount_edit.selectAll()

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setObjectName("btnSecondary")
        confirm_btn = QPushButton("Valider")
        confirm_btn.setObjectName("btnSuccess")
        cancel_btn.clicked.connect(dialog.reject)
        confirm_btn.clicked.connect(dialog.accept)
        confirm_btn.setDefault(True)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(confirm_btn)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title_lbl)
        layout.addWidget(subtitle_lbl)
        layout.addWidget(amount_edit)
        layout.addLayout(buttons_layout)

        dialog.setMinimumHeight(220)
        amount_edit.setFocus()
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        text = (amount_edit.text().strip() or "0").replace(",", ".")
        return text, accepted

    def _opening_cash_setting_key(self) -> str:
        user_id = int(AuthController.current_user().get("id") or 0)
        today = datetime.now().date().isoformat()
        return f"cash_opening:{user_id}:{today}"

    def _ensure_opening_cash_initialized(self) -> None:
        if not self._is_cashier_user():
            self._opening_cash_checked_key = ""
            self._update_cash_expected_label()
            return

        self._resume_current_cashier_if_paused()
        key = self._opening_cash_setting_key()
        if self._opening_cash_checked_key == key:
            return
        self._opening_cash_checked_key = key

        existing = self._setting_value(key, "")
        if existing != "":
            self._update_cash_expected_label()
            return

        text, ok = self._prompt_opening_cash_amount()
        if not ok:
            text = "0"
        opening_cash = _parse_payment_amount_text(text)
        self._save_setting_value(key, f"{opening_cash:.3f}")
        self._update_cash_expected_label()

    def _ensure_category_strip_ready(self) -> None:
        if not hasattr(self, "_cat_scroll"):
            return
        visible_buttons = [btn for btn, _ in getattr(self, "_cat_buttons", []) if btn is not None]
        needs_reload = (
            not visible_buttons
            or getattr(self, "_cat_strip_lay", None) is None
            or self._cat_strip_lay.count() <= 1
        )
        if needs_reload:
            self._load_categories()
        if hasattr(self, "_cat_strip"):
            self._cat_strip.show()
            self._cat_strip.adjustSize()
            self._cat_strip.setMinimumWidth(self._cat_strip.sizeHint().width() + 8)
        self._cat_scroll.show()
        self._cat_scroll.viewport().update()

    def _ensure_catalog_visible(self):
        self._ensure_category_strip_ready()
        for widget in (
            getattr(self, "_catalog_panel", None),
            getattr(self, "_cat_scroll", None),
            getattr(self, "_cat_strip", None),
            getattr(self, "_count_lbl", None),
            getattr(self, "_grid_scroll", None),
        ):
            if widget is not None:
                widget.setVisible(True)
                widget.show()
                widget.raise_()
                widget.updateGeometry()
                widget.update()
        if hasattr(self, "_cat_scroll"):
            self._cat_scroll.setVisible(True)
            self._cat_scroll.setFixedHeight(_CAT_STRIP_H)
        if hasattr(self, "_cat_strip"):
            self._cat_strip.setVisible(True)
            self._cat_strip.adjustSize()
            self._cat_strip.setMinimumWidth(self._cat_strip.sizeHint().width() + 8)
        self._restore_pos_layout()

    def _restore_pos_layout(self):
        if hasattr(self, "_cat_strip"):
            self._cat_strip.setVisible(True)
            self._cat_strip.adjustSize()
            self._cat_strip.setMinimumWidth(self._cat_strip.sizeHint().width() + 8)
            self._cat_strip.update()
        if hasattr(self, "_cat_scroll"):
            self._cat_scroll.setVisible(True)
            self._cat_scroll.setFixedHeight(_CAT_STRIP_H)
            self._cat_scroll.show()
            self._cat_scroll.viewport().update()
        if hasattr(self, "_grid_scroll"):
            self._grid_scroll.setVisible(True)
            self._grid_scroll.show()
            self._grid_scroll.viewport().update()

    def _restore_catalog_after_dialog(self):
        self._ensure_category_strip_ready()
        if hasattr(self, "_cat_strip_lay") and self._cat_strip_lay.count() <= 1:
            self._load_categories()
        self._ensure_catalog_visible()
        if hasattr(self, "_search_input") and self._search_input.text().strip():
            self._on_search_changed(self._search_input.text())
        else:
            self._show_catalog()
        self._render_cart()
        self._restore_pos_layout()
        self.updateGeometry()
        self._schedule_catalog_restore()

    def _update_cash_expected_label(self):
        if not self._is_cashier_user():
            if hasattr(self, "_cash_expected_lbl"):
                self._cash_expected_lbl.clear()
                self._cash_expected_lbl.setToolTip("")
            self.cash_expected_changed.emit("", "")
            return

        summary = self._cash_expected_summary()
        label_text = f"Caisse attendue : {summary.get('expected_cash_text', '0.000 TND')}"
        tooltip_text = (
            f"Ouverture : {summary.get('opening_cash_text', '0.000 TND')}\n"
            f"Encaissements du jour : {summary.get('total_received_text', '0.000 TND')}"
        )
        if hasattr(self, "_cash_expected_lbl"):
            self._cash_expected_lbl.setText(label_text)
            self._cash_expected_lbl.setToolTip(tooltip_text)
        self.cash_expected_changed.emit(label_text, tooltip_text)

    # ──────────────────────────────── Categories ───────────────

    def _load_categories(self):
        while self._cat_strip_lay.count():
            item = self._cat_strip_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._cat_buttons.clear()
        categories = CategoryController.get_all()

        if not self._default_category_applied:
            self._default_category_applied = True
            default_cat = next(
                (c for c in categories if (c.get("name") or "").strip().lower() == "autres"),
                None,
            )
            if default_cat is not None:
                self._active_cat_id = default_cat["id"]

        current_selection = self._active_cat_id
        self._add_cat_widget(
            "Tous",
            None,
            color="#059669",
            image_path=None,
            selected=current_selection is None,
        )
        for cat in categories:
            self._add_cat_widget(
                cat["name"], cat["id"],
                color=cat.get("color") or "#059669",
                image_path=cat.get("image_path"),
                selected=current_selection is not None and current_selection == cat["id"],
            )

        self._cat_strip_lay.addStretch()
        self._cat_strip.adjustSize()
        self._cat_strip.setMinimumWidth(self._cat_strip.sizeHint().width() + 8)
        self._cat_scroll.setVisible(True)
        self._cat_strip.setVisible(True)
        self._cat_scroll.show()
        self._cat_strip.show()
        self._schedule_catalog_restore()

    def _make_cat_icon(self, label: str, color: str, image_path: str | None) -> QIcon:
        """Return a QIcon: real image if available, else colored initial placeholder.

        Cached: _load_categories() runs on every visit to the Caisse, and
        rebuilding these icons from scratch (disk read + rescale, or QPainter
        text/emoji rendering) cost ~100 ms each — over a second of latency on
        every single page change. The cache key carries everything the icon is
        drawn from, so editing a category still produces a fresh icon.
        """
        cache_key = (label, color, image_path)
        cached = _CAT_ICON_CACHE.get(cache_key)
        if cached is not None:
            return cached
        icon = self._render_cat_icon(label, color, image_path)
        _CAT_ICON_CACHE[cache_key] = icon
        return icon

    def _render_cat_icon(self, label: str, color: str, image_path: str | None) -> QIcon:
        if image_path:
            img_file = CATEGORY_IMAGES_DIR / image_path
            if img_file.exists():
                cropped = _load_thumbnail(str(img_file), _CAT_IMG, _CAT_IMG)
                if not cropped.isNull():

                    # Round the corners to match the colored-placeholder icons
                    # and the product cards, instead of a harsh square photo.
                    rounded = QPixmap(_CAT_IMG, _CAT_IMG)
                    rounded.fill(Qt.transparent)
                    painter = QPainter(rounded)
                    painter.setRenderHint(QPainter.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, _CAT_IMG, _CAT_IMG, 12, 12)
                    painter.setClipPath(path)
                    painter.drawPixmap(0, 0, cropped)
                    painter.end()
                    return QIcon(rounded)

        # Colored background
        pix = QPixmap(_CAT_IMG, _CAT_IMG)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = QColor(color)
        bg.setAlpha(50)
        painter.setBrush(bg)
        painter.setPen(QColor(color))
        painter.drawRoundedRect(0, 0, _CAT_IMG, _CAT_IMG, 12, 12)

        # Emoji lookup — fall back to colored initial letter
        name_lc = label.lower()
        emoji = next((em for key, em in _CAT_EMOJI.items() if key in name_lc), None)

        font = QFont()
        if emoji:
            font.setPixelSize(24)
            painter.setFont(font)
            painter.setPen(QColor("#333333"))
            painter.drawText(pix.rect(), Qt.AlignCenter, emoji)
        else:
            font.setPixelSize(22)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(color))
            painter.drawText(pix.rect(), Qt.AlignCenter, label[0].upper() if label else "?")

        painter.end()
        return QIcon(pix)

    def _add_cat_widget(self, label: str, cat_id, color: str, image_path: str | None,
                        selected: bool = False):
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIcon(self._make_cat_icon(label, color, image_path))
        btn.setIconSize(QSize(_CAT_IMG, _CAT_IMG))
        display = label if len(label) <= 10 else label[:9] + "…"
        btn.setText(display)
        btn.setToolTip(label)
        btn.setCheckable(True)
        btn.setChecked(selected)
        btn.setFixedSize(_CAT_W, _CAT_H)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QToolButton {"
            "  border: 1px solid #E9EDF3; border-radius: 12px;"
            "  font-size: 10.5px; font-weight: 700; color: #374151; background: #F8FAFC;"
            "  padding: 6px 4px;"
            "}"
            f"QToolButton:checked {{ border: 1.5px solid {_CAT_SELECTED_COLOR}; "
            f"background: {_CAT_SELECTED_COLOR}1A; color: {_CAT_SELECTED_COLOR}; }}"
            "QToolButton:hover:!checked { border-color: #CBD5E1; background: #F1F5F9; }"
        )
        btn.clicked.connect(lambda _, cid=cat_id, b=btn: self._select_category(cid, b))
        # Plain append: _load_categories() clears the strip (trailing stretch
        # included) before repopulating and re-adds the stretch at the end, so
        # buttons must simply accumulate in call order. Inserting at count()-1
        # here pushed "Tous" to the far right, off the visible strip.
        self._cat_strip_lay.addWidget(btn)
        # _cat_strip may already be visible from a previous population (e.g. this is
        # not the first time the tab is opened): a widget's own show() call does not
        # cascade to children added afterwards, so newly created buttons must be shown
        # explicitly or they stay hidden and are excluded from the layout's size.
        btn.show()
        self._cat_buttons.append((btn, cat_id))

    def _select_category(self, cat_id, clicked_btn):
        self._active_cat_id = cat_id
        for btn, _ in self._cat_buttons:
            btn.setChecked(btn is clicked_btn)
        self._search_input.clear()
        self._show_catalog()

    def _show_catalog(self):
        if self._active_cat_id is not None:
            products = ProductController.get_by_category(self._active_cat_id)
        else:
            products = ProductController.get_all()
        self._display_products(products)
        self._ensure_catalog_visible()


    def _reset_global_scan_buffer(self):
        self._global_scan_buffer = ""
        self._global_scan_last_ts = 0
        self._global_scan_last_monotonic = 0.0
        self._global_scan_mode = False

    def _normalized_barcode(self, value: str) -> str:
        return ProductController.normalize_barcode(value)

    def _flush_global_scan_buffer(self):
        self._process_global_scan_buffer(show_not_found=True, show_out_of_stock=True)

    def _barcode_key_text(self, event) -> str:
        key = int(event.key())
        if 48 <= key <= 57:
            return chr(ord("0") + (key - 48))

        text_value = event.text() or ""
        if len(text_value) == 1:
            if text_value.isdigit():
                return text_value
            mapped = _SCAN_SYMBOL_TO_DIGIT.get(text_value)
            if mapped:
                return mapped

        return ""

    def _process_global_scan_buffer(self, *, show_not_found: bool = True, show_out_of_stock: bool = True) -> bool:
        code = self._normalized_barcode(self._global_scan_buffer)
        self._reset_global_scan_buffer()
        self._global_scan_timer.stop()
        if not self._looks_like_barcode(code):
            return False
        handled = self._add_product_from_barcode(
            code,
            fallback_to_search=False,
            show_not_found=show_not_found,
            show_out_of_stock=show_out_of_stock,
        )
        if handled:
            self._schedule_catalog_restore()
        return handled

    def _should_handle_global_scan(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        active_modal = app.activeModalWidget()
        if active_modal is not None:
            return False
        if not self.isVisible():
            return False
        window = self.window()
        if window is not None and not window.isActiveWindow():
            return False
        return True

    def _should_consume_global_scan_key(self, focus) -> bool:
        if focus is None:
            return True
        if focus is self._search_input:
            return False
        if isinstance(focus, (QLineEdit, QDoubleSpinBox, QuantitySpinBox, PriceSpinBox)):
            return False
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and self._should_handle_global_scan():
            focus = QApplication.focusWidget()
            if not self._should_consume_global_scan_key(focus):
                return super().eventFilter(obj, event)

            modifiers = event.modifiers()
            if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                return super().eventFilter(obj, event)

            key = event.key()

            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                if self._global_scan_buffer:
                    handled = self._process_global_scan_buffer(
                        show_not_found=True,
                        show_out_of_stock=True,
                    )
                    if handled:
                        self._clear_search_input()
                        return True
                return super().eventFilter(obj, event)

            if key == Qt.Key_Escape:
                self._reset_global_scan_buffer()
                self._global_scan_timer.stop()
                return super().eventFilter(obj, event)

            digit_text = self._barcode_key_text(event)
            if digit_text:
                now = time.monotonic()
                gap = (now - self._global_scan_last_monotonic) if self._global_scan_last_monotonic else 0.0

                if gap and gap > 0.25:
                    self._reset_global_scan_buffer()

                self._global_scan_last_monotonic = now
                self._global_scan_buffer += digit_text
                if len(self._global_scan_buffer) > 128:
                    self._global_scan_buffer = self._global_scan_buffer[-128:]

                self._global_scan_mode = bool(self._global_scan_buffer) and (gap <= 0.08 or len(self._global_scan_buffer) >= 4)
                self._global_scan_timer.start(70)

                # Never let scanner key presses or AZERTY symbols appear inside the UI.
                return True

            text_value = event.text() or ""
            if len(text_value) == 1 and text_value in _SCAN_SYMBOL_TO_DIGIT:
                return True

        return super().eventFilter(obj, event)

    # ──────────────────────────────── Search / Scan ────────────

    def _open_camera_scanner(self):
        dlg = BarcodeScannerDialog(self)
        if dlg.exec():
            code = dlg.get_result()
            if code:
                self._search_input.setText(code)
                self._on_scan()

    def _display_search_results(self, text: str) -> None:
        if not text:
            self._show_catalog()
            return

        if self._looks_like_barcode(text):
            product = ProductController.get_by_barcode(text)
            if product:
                self._display_products([product])
                self._ensure_catalog_visible()
                return

        self._display_products(ProductController.search(text))
        self._ensure_catalog_visible()

    def _on_search_changed(self, text: str):
        raw_text = text or ""
        stripped = raw_text.strip()

        normalized_barcode = ProductController.normalize_barcode(raw_text)
        scanner_like_chars = {"&", "é", '"', "'", "(", "-", "è", "_", "ç", "à"}
        if stripped and all((ch.isdigit() or ch.isspace() or ch in scanner_like_chars) for ch in raw_text):
            cleaned = normalized_barcode
            if cleaned != stripped:
                with QSignalBlocker(self._search_input):
                    self._search_input.setText(cleaned)
                stripped = cleaned

        text = stripped
        self._scan_timer.stop()

        if not text:
            self._show_catalog()
            self._ensure_catalog_visible()
            return

        self._display_search_results(text)

    def _looks_like_barcode(self, text: str) -> bool:
        code = self._normalized_barcode(text)
        return len(code) >= 3

    def _clear_search_input(self, *, reset_catalog: bool = True):
        with QSignalBlocker(self._search_input):
            self._search_input.clear()
        self._reset_global_scan_buffer()
        self._global_scan_timer.stop()
        # reset_catalog=False keeps whatever _display_products() call the caller
        # already made (e.g. showing a just-scanned product) instead of
        # reverting the grid back to the full/category listing.
        if reset_catalog:
            self._show_catalog()
        self._schedule_catalog_restore()

    def _add_product_from_barcode(
        self,
        code: str,
        *,
        fallback_to_search: bool,
        show_not_found: bool = False,
        show_out_of_stock: bool = False,
    ) -> bool:
        code = self._normalized_barcode(code)
        if not code:
            return False

        product = ProductController.get_by_barcode(code)
        if not product:
            if fallback_to_search:
                self._display_products(ProductController.search(code))
            if show_not_found:
                light_warning(self, "Produit introuvable", f"Aucun produit trouvé pour le code : {code}")
            return False

        # Show the scanned product in the catalog grid, whether it came from the
        # search bar or a hardware scanner captured by the global key filter —
        # previously only pressing Enter in the search bar did this; a physical
        # scan added the item to the cart without ever appearing on screen.
        self._display_products([product])

        stock_quantity = float(product.get("stock_quantity") or 0.0)
        if stock_quantity <= 0:
            if show_out_of_stock:
                light_warning(
                    self,
                    "Rupture de stock",
                    f"Le produit « {product.get('name', '')} » est en rupture de stock.",
                )
            return False

        selected_unit = self._default_sale_unit_for_product(product)
        required_stock = float((selected_unit or {}).get("quantity") or 1.0)
        total_required = round(self._cart_stock_usage_for_product(int(product["id"])) + required_stock, 3)
        if stock_quantity + 0.0005 < total_required:
            if show_out_of_stock:
                unit_name = (selected_unit or {}).get("name") or "unité"
                light_warning(
                    self,
                    "Stock insuffisant",
                    f"Le produit « {product.get('name', '')} » n'a pas assez de stock pour : {unit_name}.",
                )
            return False

        if product.get("selected_sale_unit_id"):
            self._add_to_cart(product, 1, sale_unit=selected_unit)
        elif product["unit_type"] in ("kg", "litre") and (not selected_unit or float(selected_unit.get("quantity") or 1.0) == 1.0):
            self._ask_weight(product)
        else:
            self._start_sale_for_product(product)

        self._clear_search_input(reset_catalog=False)
        self._ensure_catalog_visible()
        return True

    def _sale_units_for_product(self, product_id: int) -> list[dict]:
        cached = self._sale_units_cache.get(product_id)
        if cached is None:
            cached = ProductController.get_sale_units(product_id)
            self._sale_units_cache[product_id] = cached
        return cached

    def _sale_unit_of_kind(self, product: dict, kind: str) -> dict | None:
        for unit in self._sale_units_for_product(int(product["id"])):
            if str(unit.get("unit_kind") or "").strip().lower() == kind:
                return unit
        return None

    def _default_sale_unit_for_product(self, product: dict) -> dict | None:
        if product.get("selected_sale_unit_id"):
            return {
                "id": product.get("selected_sale_unit_id"),
                "name": product.get("selected_sale_unit_name"),
                "quantity": product.get("selected_sale_unit_quantity", 1.0),
                "sale_price": product.get("selected_sale_unit_price", product.get("sale_price", 0.0)),
                "barcode": product.get("selected_sale_unit_barcode"),
            }
        # "Vente à la pièce" is the inverse of pack: the normal sale is the
        # whole lot (this unit), and _piece_single_sale_unit_for_product is
        # the exception that sells just 1 piece.
        piece_lot = self._sale_unit_of_kind(product, "piece_lot")
        if piece_lot:
            return piece_lot
        units = self._sale_units_for_product(int(product["id"]))
        return units[0] if units else None

    def _pack_sale_unit_for_product(self, product: dict) -> dict | None:
        explicit = self._sale_unit_of_kind(product, "pack")
        if explicit:
            return explicit
        for unit in self._sale_units_for_product(int(product["id"])):
            if bool(unit.get("is_default")) or unit.get("unit_kind"):
                continue
            # Legacy rows created before unit_kind existed.
            quantity = float(unit.get("quantity") or 1.0)
            unit_name = str(unit.get("name") or "").strip().casefold()
            if quantity > 1.0 or "pack" in unit_name:
                return unit
        return None

    def _piece_single_sale_unit_for_product(self, product: dict) -> dict | None:
        return self._sale_unit_of_kind(product, "piece_single")

    def _add_pack_to_cart(self, product: dict) -> None:
        pack_unit = self._pack_sale_unit_for_product(product)
        if not pack_unit:
            self._start_sale_for_product(product)
            return
        self._add_to_cart(product, 1, sale_unit=pack_unit)

    def _add_piece_to_cart(self, product: dict) -> None:
        piece_unit = self._piece_single_sale_unit_for_product(product)
        if not piece_unit:
            self._start_sale_for_product(product)
            return
        self._add_to_cart(product, 1, sale_unit=piece_unit)

    def _start_sale_for_product(self, product: dict) -> None:
        selected_unit = self._default_sale_unit_for_product(product)

        if product["unit_type"] in ("kg", "litre"):
            if not selected_unit or float(selected_unit.get("quantity") or 1.0) == 1.0:
                self._ask_weight(product)
                return
            self._add_to_cart(product, 1, sale_unit=selected_unit)
            return

        self._add_to_cart(product, 1, sale_unit=selected_unit)

    def _try_auto_barcode_scan(self):
        code = self._normalized_barcode(self._search_input.text())
        handled = self._add_product_from_barcode(
            code,
            fallback_to_search=False,
            show_not_found=False,
            show_out_of_stock=True,
        )
        if handled:
            self._clear_search_input()

    def _on_scan(self):
        self._scan_timer.stop()
        self._ensure_category_strip_ready()
        raw_text = self._search_input.text().strip()
        code = self._normalized_barcode(raw_text)
        if code:
            self._display_search_results(code)
            return
        self._show_catalog()
        self._ensure_catalog_visible()

    # ──────────────────────────────── Product Grid ─────────────

    def _display_products(self, products: list):
        self._displayed_products = list(products)

        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # takeAt() only detaches the widget from the layout; it stays a
                # visible child (at its old position) until deleteLater() actually
                # runs on the next event loop turn, which can briefly show stale
                # cards behind the new ones. Hide it immediately to avoid that.
                widget.hide()
                widget.deleteLater()
        for col in range(6):  # highest possible column count from _grid_columns_for_width
            self._grid_layout.setColumnStretch(col, 0)

        self._count_lbl.setText(f"{len(products)} produit(s)")

        if not products:
            lbl = QLabel("Aucun produit trouvé")
            lbl.setStyleSheet("color: #6B7280; padding: 32px;")
            lbl.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(lbl, 0, 0)
            return

        viewport_width = self._grid_scroll.viewport().width() if hasattr(self, "_grid_scroll") else 0
        columns = _grid_columns_for_width(viewport_width or ((_CARD_W + 12) * _COLS))
        self._current_grid_columns = columns

        for col in range(columns):
            self._grid_layout.setColumnStretch(col, 1)

        for index, product in enumerate(products[:80]):
            row, col = divmod(index, columns)
            self._grid_layout.addWidget(self._make_product_card(product), row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, "_displayed_products", None):
            return
        if not hasattr(self, "_grid_scroll"):
            return

        columns = _grid_columns_for_width(self._grid_scroll.viewport().width())
        if columns != self._current_grid_columns:
            self._display_products(self._displayed_products)


    def _make_product_card(self, product: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("productCard")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedHeight(_CARD_H)
        card.setMinimumWidth(108)
        card.setMaximumWidth(220)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(5)

        # ── Image / colour placeholder ──────────────────────
        img_lbl = QLabel()
        img_lbl.setFixedHeight(_IMG_H)
        img_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        img_lbl.setAlignment(Qt.AlignCenter)

        img_loaded = False
        raw_path = product.get("image_path") or ""
        if raw_path:
            p = Path(raw_path)
            if not p.is_absolute():
                p = PRODUCT_IMAGES_DIR / raw_path
            if p.exists():
                # Pre-render at the card's max width; setScaledContents() then
                # smoothly downscales this to whatever width the card ends up
                # at once the responsive grid distributes the row's space.
                pix = _load_thumbnail(str(p), _CARD_MAX_W, _IMG_H)
                if not pix.isNull():
                    img_lbl.setPixmap(pix)
                    img_lbl.setScaledContents(True)
                    img_lbl.setStyleSheet(
                        "border-radius: 6px 6px 0 0; background: transparent;"
                    )
                    img_loaded = True

        if not img_loaded:
            # Neutral placeholder rather than a per-category tint: with a wall of
            # 6 columns, one hue per category turned the grid into noise. Slate
            # tones keep it calm while staying clearly legible.
            initial = (product["name"][0]).upper() if product["name"] else "?"
            img_lbl.setText(initial)
            img_lbl.setStyleSheet(
                "background: #F1F5F9; color: #94A3B8;"
                "font-size: 46px; font-weight: 800;"
                "border-radius: 6px 6px 0 0;"
            )

        layout.addWidget(img_lbl)

        # ── Name ────────────────────────────────────────────
        name_lbl = QLabel(product["name"])
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        name_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #111827; padding: 0 6px;"
        )
        name_lbl.setMaximumHeight(34)
        layout.addWidget(name_lbl)

        # ── Price ────────────────────────────────────────────
        # Always shows what a normal click actually charges: for a "vente à
        # la pièce" product that's the lot (piece_lot), not products.sale_price.
        piece_lot_unit = self._sale_unit_of_kind(product, "piece_lot")
        if piece_lot_unit:
            lot_qty = int(round(float(piece_lot_unit.get("quantity") or 1.0)))
            price_text = f"{format_price(float(piece_lot_unit.get('sale_price') or 0.0))} / lot de {lot_qty}"
        else:
            price_text = format_price(product["sale_price"])
            if _is_gram_priced_product(product):
                price_text = f"{price_text} / kg"
            elif product["unit_type"] == "kg":
                price_text = f"{price_text} / kg"
            elif product["unit_type"] == "litre":
                price_text = f"{price_text} / L"

        price_lbl = QLabel(price_text)
        price_lbl.setAlignment(Qt.AlignCenter)
        price_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #059669;"
        )
        layout.addWidget(price_lbl)

        # A product only ever has pack OR "à la pièce" configured, never both.
        pack_unit = self._pack_sale_unit_for_product(product)
        piece_single_unit = self._piece_single_sale_unit_for_product(product)
        badge_unit = pack_unit or piece_single_unit
        if badge_unit:
            # Anchored via a layout (not absolute .move()) so it stays pinned to the
            # top-right corner as the card's width changes with the responsive grid.
            badge_row = QHBoxLayout(img_lbl)
            badge_row.setContentsMargins(0, 6, 6, 0)
            badge_row.addStretch()

            if pack_unit:
                badge_btn = QPushButton("Pack")
                badge_btn.setToolTip(
                    f"{int(round(float(pack_unit.get('quantity') or 1.0)))} pièce(s) • "
                    f"{format_price(float(pack_unit.get('sale_price') or 0.0))}"
                )
                badge_btn.clicked.connect(lambda _, p=product: self._add_pack_to_cart(p))
            else:
                badge_btn = QPushButton("À la pièce")
                badge_btn.setToolTip(
                    f"1 pièce • {format_price(float(piece_single_unit.get('sale_price') or 0.0))}"
                )
                badge_btn.clicked.connect(lambda _, p=product: self._add_piece_to_cart(p))

            badge_btn.setCursor(Qt.PointingHandCursor)
            badge_btn.setFixedSize(60 if not pack_unit else 44, 20)
            badge_btn.setStyleSheet(
                "QPushButton { background: rgba(15, 23, 42, 0.90); color: white; border: none;"
                "border-radius: 10px; font-size: 9px; font-weight: 800; padding: 0 6px; }"
                "QPushButton:hover { background: rgba(5, 150, 105, 0.95); }"
            )
            badge_row.addWidget(badge_btn, 0, Qt.AlignTop)

        def on_click(event, p=product):
            self._start_sale_for_product(p)

        card.mousePressEvent = on_click
        return card

    # ──────────────────────────────── Cart ─────────────────────

    def _stock_required_for_cart_item(self, item: dict) -> float:
        if item.get("skip_stock_movement"):
            return 0.0
        if item.get("pricing_mode") == "gram":
            return round(float(item.get("quantity") or 0.0), 3)
        return round(
            float(item.get("quantity") or 0.0) * float(item.get("stock_quantity_per_unit") or 1.0),
            3,
        )

    def _cart_stock_usage_for_product(self, product_id: int, *, exclude_index: int | None = None) -> float:
        total = 0.0
        for index, item in enumerate(self._cart):
            if exclude_index is not None and index == exclude_index:
                continue
            if int(item.get("product_id") or 0) != int(product_id):
                continue
            total += self._stock_required_for_cart_item(item)
        return round(total, 3)

    def _add_to_cart(
        self,
        product: dict,
        quantity: float,
        *,
        sale_unit: dict | None = None,
        pricing_mode: str | None = None,
        display_weight_g: int | None = None,
    ):
        cart_pricing_mode = pricing_mode or ("gram" if _is_gram_priced_product(product) else "standard")
        resolved_sale_unit = sale_unit or self._default_sale_unit_for_product(product)

        unit_multiplier = 1.0
        resolved_unit_price = float(product.get("sale_price") or 0.0)
        sale_unit_id = None
        sale_unit_name = None
        if resolved_sale_unit and cart_pricing_mode != "gram":
            unit_multiplier = round(float(resolved_sale_unit.get("quantity") or 1.0), 3)
            resolved_unit_price = round(
                float(resolved_sale_unit.get("sale_price") or product.get("sale_price") or 0.0),
                3,
            )
            sale_unit_id = resolved_sale_unit.get("id")
            sale_unit_name = resolved_sale_unit.get("name")

        stock_required = round(float(quantity) * float(unit_multiplier), 3)
        merge_key = f"product:{product['id']}:{sale_unit_id or sale_unit_name or 'base'}:{cart_pricing_mode}"

        for item in self._cart:
            if (item.get("cart_key") or "") != merge_key:
                continue

            new_quantity = round(float(item.get("quantity", 0.0)) + float(quantity), 3)
            total_required = round(
                self._cart_stock_usage_for_product(int(product["id"]))
                - self._stock_required_for_cart_item(item)
                + (
                    new_quantity
                    if cart_pricing_mode == "gram"
                    else new_quantity * float(item.get("stock_quantity_per_unit", unit_multiplier) or 1.0)
                ),
                3,
            )
            if float(product["stock_quantity"]) + 0.0005 < total_required:
                light_warning(
                    self,
                    "Stock insuffisant",
                    f"Stock disponible : {float(product['stock_quantity']):.2f}",
                )
                return

            previous_quantity = float(item.get("quantity", 0.0))
            item["quantity"] = new_quantity

            if cart_pricing_mode == "gram":
                existing_weight_g = item.get("display_weight_g")
                if existing_weight_g is None:
                    existing_weight_g = _grams_from_quantity(previous_quantity)
                item["pricing_mode"] = "gram"
                item["display_weight_g"] = int(
                    existing_weight_g + (display_weight_g or _grams_from_quantity(quantity))
                )

            self._render_cart()
            return

        total_required = round(self._cart_stock_usage_for_product(int(product["id"])) + stock_required, 3)
        if float(product["stock_quantity"]) + 0.0005 < total_required:
            light_warning(
                self,
                "Stock insuffisant",
                f"Stock disponible : {float(product['stock_quantity']):.2f}",
            )
            return

        cart_item = {
            "cart_key": merge_key,
            "product_id": product["id"],
            "name": product["name"],
            "unit_price": resolved_unit_price,
            "quantity": quantity,
            "unit_type": product["unit_type"],
            "discount": 0.0,
            "stock": float(product["stock_quantity"]),
            "skip_stock_movement": False,
            "sale_unit_id": sale_unit_id,
            "sale_unit_name": sale_unit_name,
            "stock_quantity_per_unit": unit_multiplier,
        }
        if cart_pricing_mode == "gram":
            cart_item["pricing_mode"] = "gram"
            cart_item["display_weight_g"] = int(display_weight_g or _grams_from_quantity(quantity))
            cart_item["stock_quantity_per_unit"] = 1.0

        self._cart.append(cart_item)
        self._render_cart()

    def _ask_weight(self, product: dict):
        if _is_gram_priced_product(product):
            dlg = GramWeightDialog(product, self)
            if dlg.exec():
                self._add_to_cart(
                    product,
                    dlg.get_quantity(),
                    pricing_mode="gram",
                    display_weight_g=dlg.get_weight_grams(),
                )
            return

        dlg = WeightDialog(product, self)
        if dlg.exec():
            self._add_to_cart(product, dlg.get_quantity())

    def _render_cart(self):
        self._merge_cart_items()
        self._cart_list.clear()
        self._cart_empty_lbl.setVisible(not self._cart)
        self._cart_list.setMinimumHeight(_cart_visible_height())
        self._cart_list.updateGeometry()

        for i, item in enumerate(self._cart):
            row_widget = self._make_cart_row(i, item)
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, _cart_item_height()))
            self._cart_list.addItem(list_item)
            self._cart_list.setItemWidget(list_item, row_widget)

        self._cart_list.doItemsLayout()
        self._cart_list.updateGeometries()
        self._update_totals()
        self._schedule_catalog_restore()

    def _merge_cart_items(self):
        merged: list[dict] = []
        by_key: dict[str, dict] = {}

        for item in self._cart:
            merge_key = item.get("cart_key") or f"product:{item['product_id']}"

            existing = by_key.get(merge_key)
            if existing is None:
                cloned = dict(item)
                cloned["cart_key"] = merge_key
                if cloned.get("pricing_mode") == "gram" and cloned.get("display_weight_g") is None:
                    cloned["display_weight_g"] = _grams_from_quantity(cloned.get("quantity", 0))
                by_key[merge_key] = cloned
                merged.append(cloned)
                continue

            existing["quantity"] = round(existing["quantity"] + item["quantity"], 3)
            existing["stock"] = max(float(existing.get("stock", 0)), float(item.get("stock", 0)))
            existing["discount"] = round(existing.get("discount", 0.0) + item.get("discount", 0.0), 3)

            if item.get("pricing_mode") == "gram" or existing.get("pricing_mode") == "gram":
                existing["pricing_mode"] = "gram"
                existing["display_weight_g"] = int(
                    (existing.get("display_weight_g") or _grams_from_quantity(existing["quantity"] - item["quantity"]))
                    + (item.get("display_weight_g") or _grams_from_quantity(item.get("quantity", 0)))
                )

        self._cart = merged

    def _make_cart_row(self, idx: int, item: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("cartRow")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        frame.setFixedHeight(_cart_item_height())

        outer = QVBoxLayout(frame)
        outer.setContentsMargins(_PAD, 8, _GAP, 8)
        outer.setSpacing(6)

        # ── Top line: product name + line total ──────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        name_text = (item["name"] or "").strip()
        display_name = name_text if len(name_text) <= 38 else name_text[:37] + "…"
        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("cartItemName")
        name_lbl.setToolTip(name_text)
        name_lbl.setWordWrap(False)
        name_lbl.setMinimumWidth(0)
        top_row.addWidget(name_lbl, 1)

        total_lbl = QLabel(format_price(item["unit_price"] * item["quantity"]))
        total_lbl.setObjectName("cartItemTotal")
        total_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_lbl.setToolTip(total_lbl.text())
        top_row.addWidget(total_lbl, 0)
        outer.addLayout(top_row)

        # ── Bottom line: quantity controls / details + remove ─
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        def _make_remove_button() -> QPushButton:
            btn = QPushButton("×")
            btn.setObjectName("cartRemoveBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(_TOUCH_MIN)
            btn.setToolTip("Retirer du panier")
            btn.clicked.connect(lambda _, i=idx: self._remove_item(i))
            return btn

        details_text = _cart_details_text(item)
        details_lbl = QLabel(details_text)
        details_lbl.setObjectName("cartItemDetails")
        details_lbl.setWordWrap(False)
        details_lbl.setToolTip(details_text)
        bottom_row.addWidget(details_lbl, 1)

        if item.get("pricing_mode") == "gram":
            delta_m = -0.1
            delta_p = 0.1
        else:
            delta_m = -1 if item["unit_type"] == "piece" else -0.1
            delta_p = 1 if item["unit_type"] == "piece" else 0.1

        def _make_step_button(text: str, delta: float) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("cartQtyBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(_TOUCH_MIN)
            btn.clicked.connect(lambda _, i=idx, d=delta: self._change_qty(i, d))
            return btn

        bottom_row.addWidget(_make_step_button("−", delta_m), 0)

        qty_text = _cart_quantity_text(item)
        qty_lbl = QLabel(qty_text)
        qty_lbl.setObjectName("cartItemQty")
        qty_lbl.setAlignment(Qt.AlignCenter)
        qty_lbl.setMinimumWidth(42)
        qty_lbl.setToolTip(qty_text)
        bottom_row.addWidget(qty_lbl, 0)

        bottom_row.addWidget(_make_step_button("+", delta_p), 0)
        bottom_row.addWidget(_make_remove_button(), 0)

        outer.addLayout(bottom_row)

        return frame

    def _change_qty(self, idx: int, delta: float):
        if idx < 0 or idx >= len(self._cart):
            return

        item = self._cart[idx]
        new_qty = round(float(item.get("quantity", 0)) + float(delta), 3)

        if item.get("pricing_mode") == "gram":
            current_weight = int(item.get("display_weight_g") or _grams_from_quantity(item.get("quantity", 0)))
            new_weight = current_weight + int(round(delta * 1000))
            if new_weight <= 0 or new_qty <= 0:
                self._cart.pop(idx)
                self._render_cart()
                return
            if new_qty > float(item.get("stock", 0)):
                light_warning(self, "Stock insuffisant", f"Stock disponible : {float(item.get('stock', 0)):.3f}")
                return
            item["quantity"] = new_qty
            item["display_weight_g"] = new_weight
            self._render_cart()
            return

        if new_qty <= 0:
            self._cart.pop(idx)
            self._render_cart()
            return

        stock_required = round(float(new_qty) * float(item.get("stock_quantity_per_unit", 1.0)), 3)
        total_required = round(
            self._cart_stock_usage_for_product(int(item.get("product_id") or 0), exclude_index=idx) + stock_required,
            3,
        )
        if total_required > float(item.get("stock", 0)) + 0.0005:
            light_warning(self, "Stock insuffisant", f"Stock disponible : {float(item.get('stock', 0)):.3f}")
            return

        if item.get("unit_type") == "piece":
            item["quantity"] = int(round(new_qty))
        else:
            item["quantity"] = new_qty
        self._render_cart()

    def _remove_item(self, idx: int):
        if idx < 0 or idx >= len(self._cart):
            return
        self._cart.pop(idx)
        self._render_cart()


    def _clear_cart(self):
        if self._cart and light_question(
            self,
            "Vider le panier",
            "Vider le panier ?",
        ) == QMessageBox.Yes:
            self._cart.clear()
            self._render_cart()

    def _update_totals(self):
        total = max(0.0, sum(i["unit_price"] * i["quantity"] for i in self._cart))
        self._total_lbl.setText(format_price(total))

        count = len(self._cart)
        self._cart_count_lbl.setText(f"{count} article{'s' if count > 1 else ''}" if count else "")
        self._btn_clear_cart.setEnabled(bool(self._cart))

    # ──────────────────────────────── Checkout ─────────────────

    def _checkout(self, payment_method: str):
        self._ensure_catalog_visible()
        if not self._cart:
            light_information(self, "Panier vide", "Ajoutez des produits au panier.")
            self._ensure_catalog_visible()
            return

        subtotal = sum(i["unit_price"] * i["quantity"] for i in self._cart)
        discount = 0.0
        total    = max(0.0, subtotal)

        customer_id = None
        customer    = None
        dlg = None

        if payment_method == "credit":
            dlg = CustomerSelectDialog(self)
            if not dlg.exec():
                self._restore_catalog_after_dialog()
                QTimer.singleShot(0, self._restore_catalog_after_dialog)
                return
            customer_id = dlg.get_customer_id()
            if not customer_id:
                light_warning(self, "Aucun client", "Veuillez sélectionner un client.")
                self._restore_catalog_after_dialog()
                return
            customer = CustomerController.get_by_id(customer_id)

            dlg = CreditCheckoutDialog(total, customer, self)
            if not dlg.exec():
                self._restore_catalog_after_dialog()
                QTimer.singleShot(0, self._restore_catalog_after_dialog)
                return

            amount_paid = dlg.get_amount_paid()
            credit_amount = round(max(0.0, total - amount_paid), 3)
            reply = light_question(
                self,
                "Confirmer la vente crédit",
                f"Client : <b>{customer['name']}</b>\n\n"
                f"Total panier : {format_price(total)}\n"
                f"Payé maintenant : {format_price(amount_paid)}\n"
                f"À crédit : {format_price(credit_amount)}\n\n"
                f"Solde actuel : {format_price(customer['balance'])}\n"
                f"Nouveau solde : {format_price(customer['balance'] + credit_amount)}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self._restore_catalog_after_dialog()
                return
        else:
            dlg = PaymentDialog(total, self._cart, self)
            if not dlg.exec():
                self._restore_catalog_after_dialog()
                QTimer.singleShot(0, self._restore_catalog_after_dialog)
                return
            amount_paid = dlg.get_amount_paid()

        items = [
            {
                "product_id": i["product_id"],
                "sale_unit_id": i.get("sale_unit_id"),
                "sale_unit_name": i.get("sale_unit_name"),
                "quantity": i["quantity"],
                "stock_quantity": round(float(i["quantity"]) * float(i.get("stock_quantity_per_unit", 1.0)), 3),
                "unit_price": i["unit_price"],
                "discount": i.get("discount", 0),
                "skip_stock_movement": bool(i.get("skip_stock_movement")),
            }
            for i in self._cart
        ]
        settings = {r["key"]: r["value"]
                    for r in db.fetchall("SELECT `key` AS `key`, value FROM settings")}

        try:
            sale = SaleController.create_sale(
                items, payment_method, discount, 0, amount_paid,
                customer_id=customer_id,
            )
            self._cart.clear()
            self.refresh()
            self._restore_catalog_after_dialog()
            QTimer.singleShot(0, self._restore_catalog_after_dialog)

            refresh_pages = getattr(self.window(), "refresh_pages", None)
            if callable(refresh_pages):
                refresh_pages({"dashboard", "products", "stock", "sales", "customers"}, include_current=False)

            if payment_method == "credit":
                credit_amount = round(max(0.0, total - amount_paid), 3)
                if credit_amount > 0 and amount_paid > 0:
                    msg = (
                        f"Vente enregistrée pour {customer['name']}.\n"
                        f"Payé maintenant : {format_price(amount_paid)}\n"
                        f"Reste en crédit : {format_price(credit_amount)}"
                    )
                elif credit_amount > 0:
                    msg = f"Crédit de {format_price(credit_amount)} enregistré\npour {customer['name']}."
                else:
                    msg = f"Facture réglée complètement pour {customer['name']}."
                light_information(self, "Vente crédit", msg)
            else:
                if dlg is not None and dlg.should_print_receipt():
                    pdf_path = generate_thermal_receipt(sale, settings)
                    try:
                        if sys.platform == "linux":
                            subprocess.Popen(["xdg-open", pdf_path])
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", pdf_path])
                        else:
                            subprocess.Popen(["start", pdf_path], shell=True)
                    except Exception:
                        light_information(self, "Ticket", f"Ticket sauvegardé :\n{pdf_path}")
        except Exception as e:
            light_critical(self, "Erreur", str(e))
        finally:
            self._restore_catalog_after_dialog()
            QTimer.singleShot(0, self._restore_catalog_after_dialog)


# ─────────────────────────────────────────────────── Dialogs ──

class GramWeightDialog(QDialog):
    def __init__(self, product: dict, parent=None):
        super().__init__(parent)
        self._product = product
        self.setWindowTitle(f"Poids — {product['name']}")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(QLabel(f"<b>{product['name']}</b>"))
        layout.addWidget(QLabel(f"Prix : {format_price(product['sale_price'])} / kg"))
        layout.addWidget(QLabel(f"Soit : {format_price(product['sale_price'] / 1000)} / g"))

        form = QFormLayout()
        self._grams_input = QLineEdit()
        self._grams_input.setMinimumHeight(48)
        self._grams_input.setPlaceholderText("100")
        self._grams_input.setText("100")
        self._grams_input.setValidator(QIntValidator(1, 99999, self))
        self._grams_input.setAlignment(Qt.AlignLeft)
        self._grams_input.textChanged.connect(self._update_total_from_text)
        form.addRow("Poids (g) :", self._grams_input)
        layout.addLayout(form)

        self._total_lbl = QLabel()
        self._total_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #059669;")
        self._total_lbl.setAlignment(Qt.AlignCenter)
        self._update_total()
        layout.addWidget(self._total_lbl)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Ajouter")
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _current_grams(self) -> int:
        raw = (self._grams_input.text() or "").strip()
        if not raw:
            return 1
        try:
            value = int(raw)
        except ValueError:
            value = 1
        return max(1, value)

    def _update_total(self):
        total = (float(self._current_grams()) / 1000.0) * float(self._product["sale_price"])
        self._total_lbl.setText(f"Total : {format_price(total)}")

    def _update_total_from_text(self, _text: str):
        self._update_total()

    def accept(self):
        self._grams_input.setText(str(self._current_grams()))
        super().accept()

    def get_weight_grams(self) -> int:
        return self._current_grams()

    def get_quantity(self) -> float:
        return round(self.get_weight_grams() / 1000.0, 3)



class WeightDialog(QDialog):
    def __init__(self, product: dict, parent=None):
        super().__init__(parent)
        self._product = product
        self.setWindowTitle(f"Quantité — {product['name']}")
        self.setFixedWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        unit = "kg" if product["unit_type"] == "kg" else "L"
        layout.addWidget(QLabel(f"<b>{product['name']}</b>"))
        layout.addWidget(QLabel(f"Prix : {format_price(product['sale_price'])} / {unit}"))

        form = QFormLayout()
        self._qty = QuantitySpinBox(product["unit_type"])
        self._qty.setMinimumHeight(48)
        self._qty.setMinimum(0.001)
        self._qty.setMaximum(9999)
        self._qty.setValue(1.0)
        self._qty.setSuffix(f"  {unit}")
        self._qty.setLocale(QLocale(QLocale.Language.C))
        self._qty.setGroupSeparatorShown(False)
        self._qty.setKeyboardTracking(True)
        if self._qty.lineEdit():
            self._qty.lineEdit().textChanged.connect(self._update_total_from_text)
        form.addRow("Quantité :", self._qty)
        layout.addLayout(form)

        self._total_lbl = QLabel()
        self._total_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #059669;")
        self._total_lbl.setAlignment(Qt.AlignCenter)
        self._qty.valueChanged.connect(self._update_total)
        self._update_total()
        layout.addWidget(self._total_lbl)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Ajouter")
        btn_ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _current_qty(self) -> float:
        value = float(_spin_numeric_value(self._qty))
        minimum = 0.001 if self._product["unit_type"] in ("kg", "litre") else 1.0
        return max(minimum, value)

    def _update_total(self):
        self._total_lbl.setText(
            f"Total : {format_price(self._current_qty() * float(self._product['sale_price']))}"
        )

    def _update_total_from_text(self, _text: str):
        self._update_total()

    def accept(self):
        self._qty.setValue(self._current_qty())
        super().accept()

    def get_quantity(self) -> float:
        return self._current_qty()



class SaleUnitDialog(QDialog):
    def __init__(self, product: dict, sale_units: list[dict], parent=None):
        super().__init__(parent)
        self._product = product
        self._sale_units = sale_units or []
        self.setWindowTitle(f"Unité de vente — {product['name']}")
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel(f"<b>{product['name']}</b>")
        layout.addWidget(title)

        form = QFormLayout()

        self._unit = QComboBox()
        self._unit.setMinimumHeight(42)
        for unit in self._sale_units:
            unit_label = f"{unit['name']} — {format_price(float(unit.get('sale_price') or 0.0))}"
            qty_per_unit = round(float(unit.get('quantity') or 1.0), 3)
            if abs(qty_per_unit - 1.0) > 0.0005:
                unit_label += f" (stock -{qty_per_unit:g})"
            self._unit.addItem(unit_label, unit)
        self._unit.currentIndexChanged.connect(self._update_total)

        self._qty = QDoubleSpinBox()
        self._qty.setMinimumHeight(42)
        self._qty.setMinimum(1.0 if product.get("unit_type") == "piece" else 0.001)
        self._qty.setMaximum(9999.0)
        if product.get("unit_type") == "piece":
            self._qty.setDecimals(0)
            self._qty.setValue(1.0)
        else:
            self._qty.setDecimals(3)
            self._qty.setSingleStep(0.001)
            self._qty.setValue(1.0)
        self._qty.valueChanged.connect(self._update_total)

        form.addRow("Unité :", self._unit)
        form.addRow("Quantité :", self._qty)
        layout.addLayout(form)

        self._total_lbl = QLabel()
        self._total_lbl.setAlignment(Qt.AlignCenter)
        self._total_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #059669;")
        layout.addWidget(self._total_lbl)
        self._update_total()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Ajouter")
        btn_ok.clicked.connect(self._validate)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _current_unit(self) -> dict | None:
        data = self._unit.currentData()
        return data if isinstance(data, dict) else None

    def _current_quantity(self) -> float:
        value = float(self._qty.value())
        if self._product.get("unit_type") == "piece":
            return float(max(1, int(round(value))))
        return max(0.001, round(value, 3))

    def _update_total(self):
        unit = self._current_unit() or {}
        total = self._current_quantity() * float(unit.get("sale_price") or 0.0)
        self._total_lbl.setText(f"Total : {format_price(total)}")

    def _validate(self):
        unit = self._current_unit()
        if not unit:
            light_warning(self, "Unité requise", "Veuillez choisir une unité de vente.")
            return

        stock_required = self.get_quantity() * float(unit.get("quantity") or 1.0)
        if stock_required > float(self._product.get("stock_quantity") or 0.0) + 0.0005:
            light_warning(
                self,
                "Stock insuffisant",
                f"Stock disponible : {float(self._product.get('stock_quantity') or 0.0):.3f}",
            )
            return
        self.accept()

    def get_selected_unit(self) -> dict | None:
        return self._current_unit()

    def get_quantity(self) -> float:
        return self._current_quantity()


class PaymentDialog(QDialog):
    def __init__(self, total: float, cart: list, parent=None):
        super().__init__(parent)
        self._total = total
        self._should_print = False
        self.setWindowTitle("Paiement en espèces")
        self.setMinimumWidth(560)
        self.setMinimumHeight(660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("  Confirmation de paiement")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 800; padding: 16px 20px 12px;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setObjectName("separator")
        layout.addWidget(sep)

        body = QVBoxLayout()
        body.setContentsMargins(24, 16, 24, 16)
        body.setSpacing(12)

        n_items = sum(i["quantity"] for i in cart)
        summary = QLabel(f"{_format_quantity(n_items, 'piece')} article(s)")
        summary.setStyleSheet("color: #6B7280; font-size: 12px;")
        body.addWidget(summary)

        items_list = QListWidget()
        items_list.setMinimumHeight(180)
        items_list.setMaximumHeight(260)
        items_list.setWordWrap(True)
        items_list.setTextElideMode(Qt.ElideNone)
        items_list.setSelectionMode(QAbstractItemView.NoSelection)
        for line in cart:
            qty = _cart_quantity_text(line)
            total_line = format_price(line["unit_price"] * line["quantity"])
            label = line["name"]
            if line.get("sale_unit_name"):
                label = f"{label} [{line['sale_unit_name']}]"
            if line.get("pricing_mode") == "gram":
                text = f"{label} — {qty} × {format_price(line['unit_price'] / 1000)} / g — {total_line}"
            else:
                text = f"{qty} × {label} — {total_line}"
            row_item = QListWidgetItem(text)
            row_item.setToolTip(text)
            items_list.addItem(row_item)
        body.addWidget(items_list)

        total_lbl = QLabel(format_price(total))
        total_lbl.setStyleSheet(
            "font-size: 40px; font-weight: 800; color: #059669; letter-spacing: -1px;"
        )
        total_lbl.setAlignment(Qt.AlignCenter)
        body.addWidget(total_lbl)

        sep2 = QFrame()
        sep2.setObjectName("separator")
        body.addWidget(sep2)

        recv_lbl = QLabel("Montant reçu (TND) :")
        recv_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #6B7280; background: transparent; border: none;"
        )
        body.addWidget(recv_lbl)

        hint_lbl = QLabel("Tapez les chiffres : ils remplissent les millimes (5 → 0.005, 5000 → 5.000)")
        hint_lbl.setStyleSheet(
            "font-size: 11px; color: #94A3B8; background: transparent; border: none;"
        )
        body.addWidget(hint_lbl)

        self._paid = MillimeAmountLineEdit()
        self._paid.setMinimumHeight(54)
        self._paid.set_value(total)
        self._paid.setStyleSheet("font-size: 20px; font-weight: 800;")
        self._paid.textChanged.connect(self._update_change_from_text)
        body.addWidget(self._paid)

        self._change_lbl = QLabel()
        self._change_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #059669;"
            "background: #ECFDF5; border-radius: 8px; padding: 10px 14px;"
        )
        self._change_lbl.setAlignment(Qt.AlignCenter)
        body.addWidget(self._change_lbl)

        self._error_lbl = QLabel("")
        self._error_lbl.setVisible(False)
        self._error_lbl.setAlignment(Qt.AlignCenter)
        self._error_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 800; color: #DC2626;"
            "background: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 8px 12px;"
        )
        body.addWidget(self._error_lbl)

        self._print_chk = QCheckBox("Imprimer le ticket")
        self._print_chk.setChecked(False)
        self._print_chk.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #111827; padding-top: 2px;"
        )
        body.addWidget(self._print_chk)

        self._print_hint_lbl = QLabel("Optionnel — par défaut : non")
        self._print_hint_lbl.setStyleSheet(
            "font-size: 11px; color: #94A3B8; background: transparent; border: none;"
        )
        body.addWidget(self._print_hint_lbl)

        self._update_change()
        layout.addLayout(body)

        sep3 = QFrame()
        sep3.setObjectName("separator")
        layout.addWidget(sep3)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 14, 24, 14)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.setMinimumHeight(42)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Valider")
        btn_ok.setMinimumHeight(42)
        btn_ok.clicked.connect(self._validate)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _current_paid_value(self) -> float:
        return self._paid.value()

    def _update_change(self):
        paid_value = round(self._current_paid_value(), 3)
        total_value = round(float(self._total), 3)
        change = max(0.0, round(paid_value - total_value, 3))
        self._change_lbl.setText(f"Monnaie à rendre : {format_price(change)}")
        self._error_lbl.setVisible(False)

    def _update_change_from_text(self, text: str):
        paid_value = round(_parse_payment_amount_text(text), 3)
        total_value = round(float(self._total), 3)
        change = max(0.0, round(paid_value - total_value, 3))
        self._change_lbl.setText(f"Monnaie à rendre : {format_price(change)}")
        self._error_lbl.setVisible(False)

    def _validate(self):
        paid_value = round(self._current_paid_value(), 3)
        total_value = round(float(self._total), 3)
        if paid_value + 0.0005 < total_value:
            missing = max(0.0, round(total_value - paid_value, 3))
            self._error_lbl.setText(f"Montant insuffisant : il manque {format_price(missing)}")
            self._error_lbl.setVisible(True)
            self._paid.setFocus()
            # So the next digit the cashier types starts a corrected entry
            # instead of appending after the insufficient amount.
            self._paid.mark_for_fresh_entry()
            return
        self._error_lbl.setVisible(False)
        self._should_print = self._print_chk.isChecked()
        self._paid_value = paid_value
        self.accept()

    def get_amount_paid(self) -> float:
        return getattr(self, "_paid_value", self._current_paid_value())

    def should_print_receipt(self) -> bool:
        return self._should_print


class CreditCheckoutDialog(QDialog):
    def __init__(self, total: float, customer: dict, parent=None):
        super().__init__(parent)
        self._total = round(float(total or 0.0), 3)
        self._customer = customer or {}
        self._paid_value = 0.0
        self.setWindowTitle("Vente en crédit")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("💳  Vente client avec crédit")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #111827;")
        layout.addWidget(title)

        customer_lbl = QLabel(f"Client : <b>{self._customer.get('name', '—')}</b>")
        customer_lbl.setStyleSheet("font-size: 13px; color: #374151;")
        layout.addWidget(customer_lbl)

        bal = round(float(self._customer.get("balance") or 0.0), 3)
        balance_lbl = QLabel(f"Solde actuel : <b style='color:#DC2626'>{format_price(bal)}</b>")
        balance_lbl.setStyleSheet("font-size: 12px; color: #6B7280;")
        layout.addWidget(balance_lbl)

        total_lbl = QLabel(format_price(self._total))
        total_lbl.setAlignment(Qt.AlignCenter)
        total_lbl.setStyleSheet("font-size: 34px; font-weight: 900; color: #059669;")
        layout.addWidget(total_lbl)

        paid_lbl = QLabel("Montant payé maintenant (TND) :")
        paid_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #6B7280;")
        layout.addWidget(paid_lbl)

        hint_lbl = QLabel("Laisser 0 pour tout mettre en crédit. Exemple : 10 = 10 dinars")
        hint_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
        layout.addWidget(hint_lbl)

        self._paid = QLineEdit()
        self._paid.setMinimumHeight(46)
        self._paid.setText("0")
        self._paid.setPlaceholderText("0.000")
        self._paid.setStyleSheet("font-size: 18px; font-weight: 800;")
        validator = QDoubleValidator(0.0, 999999.999, 3, self._paid)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale(QLocale.Language.C))  # accept "." regardless of OS locale
        self._paid.setValidator(validator)
        self._paid.textChanged.connect(self._update_due_from_text)
        layout.addWidget(self._paid)

        self._due_lbl = QLabel()
        self._due_lbl.setAlignment(Qt.AlignCenter)
        self._due_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #7C3AED;"
            "background: #F5F3FF; border-radius: 8px; padding: 10px 12px;"
        )
        layout.addWidget(self._due_lbl)

        self._error_lbl = QLabel("")
        self._error_lbl.setVisible(False)
        self._error_lbl.setAlignment(Qt.AlignCenter)
        self._error_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 800; color: #DC2626;"
            "background: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 8px 12px;"
        )
        layout.addWidget(self._error_lbl)

        self._update_due()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.setMinimumHeight(40)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Valider")
        btn_ok.setMinimumHeight(40)
        btn_ok.clicked.connect(self._validate)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _current_paid_value(self) -> float:
        return _parse_payment_amount_text(self._paid.text())

    def _update_due(self):
        paid_value = min(self._total, max(0.0, round(self._current_paid_value(), 3)))
        due_value = max(0.0, round(self._total - paid_value, 3))
        self._due_lbl.setText(f"Reste en crédit : {format_price(due_value)}")
        self._error_lbl.setVisible(False)

    def _update_due_from_text(self, _text: str):
        self._update_due()

    def _validate(self):
        paid_value = max(0.0, round(self._current_paid_value(), 3))
        if paid_value > self._total + 0.0005:
            self._error_lbl.setText("Le montant payé ne peut pas dépasser le total.")
            self._error_lbl.setVisible(True)
            self._paid.setFocus()
            self._paid.selectAll()
            return
        self._paid_value = min(self._total, paid_value)
        self._paid.setText(f"{self._paid_value:.3f}")
        self.accept()

    def get_amount_paid(self) -> float:
        return round(float(self._paid_value), 3)


class ManualPriceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter un autre prix")
        self.setFixedWidth(420)
        apply_light_dialog_theme(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Ajouter une ligne libre au panier")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(title)

        form = QFormLayout()
        self._label = QLineEdit()
        self._label.setMinimumHeight(42)
        self._label.setPlaceholderText("Ex: Livraison, emballage, service...")
        self._label.setText("Autre prix")

        self._amount = PriceSpinBox()
        self._amount.setMinimumHeight(42)
        self._amount.setMaximum(999999.999)
        self._amount.setDecimals(3)
        if self._amount.lineEdit():
            self._amount.lineEdit().setPlaceholderText("0.000")

        form.addRow("Libellé :", self._label)
        form.addRow("Montant :", self._amount)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Ajouter")
        btn_ok.clicked.connect(self._validate)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _validate(self):
        if self.get_amount() <= 0:
            light_warning(self, "Montant invalide", "Le montant doit être supérieur à 0.")
            return
        self.accept()

    def get_label(self) -> str:
        return self._label.text().strip() or "Autre prix"

    def get_amount(self) -> float:
        return round(float(self._amount.value()), 3)


class CustomerSelectDialog(QDialog):
    """Select a customer for credit payment (cashier cannot add new customers)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sélectionner un client")
        self.setMinimumSize(460, 400)
        self._selected_id = None
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("👤  Choisir le client")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher par nom ou téléphone…")
        self._search.setMinimumHeight(40)
        self._search.textChanged.connect(self._refresh)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list, 1)

        # Only admins can add new customers
        if AuthController.is_admin():
            btn_new = QPushButton("＋  Nouveau client")
            btn_new.setObjectName("btnSecondary")
            btn_new.clicked.connect(self._new_customer)
            layout.addWidget(btn_new)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅  Sélectionner")
        btn_ok.clicked.connect(self._accept_selection)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        apply_light_dialog_theme(self)

    def _refresh(self):
        q = self._search.text().strip()
        customers = CustomerController.search(q) if q else CustomerController.get_all()
        self._list.clear()
        for c in customers:
            bal = f"  —  Solde : {format_price(c['balance'])}" if c["balance"] > 0 else ""
            phone = f"  {c['phone']}" if c.get("phone") else ""
            item = QListWidgetItem(f"{c['name']}{phone}{bal}")
            item.setData(Qt.UserRole, c["id"])
            self._list.addItem(item)

    def _new_customer(self):
        from app.views.customers_view import CustomerDialog
        dlg = CustomerDialog(parent=self)
        if dlg.exec():
            new_id = CustomerController.create(dlg.get_data())
            self._refresh()
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == new_id:
                    self._list.setCurrentRow(i)
                    break

    def _accept_selection(self):
        current = self._list.currentItem()
        if not current:
            light_warning(self, "Aucune sélection", "Veuillez sélectionner un client.")
            return
        self._selected_id = current.data(Qt.UserRole)
        self.accept()

    def get_customer_id(self):
        return self._selected_id
