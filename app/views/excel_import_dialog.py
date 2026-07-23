from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QAbstractItemView,
    QComboBox, QCheckBox, QWidget, QLineEdit,
)
from app.views.widgets.price_input import PriceSpinBox
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont

from app.controllers.product_controller import ProductController
from app.controllers.category_controller import CategoryController
from app.controllers.supplier_controller import SupplierController
from app.database.connection import db
from app.ui.ui_loader import embed_ui
from app.views.dialog_theme import apply_light_dialog_theme


# ── Column indices ────────────────────────────────────────────────────────────
_C_CHECK  = 0
_C_NAME   = 1
_C_BC     = 2
_C_SUPP   = 3
_C_CAT    = 4
_C_DESC   = 5
_C_SALE   = 6
_C_PURCH  = 7
_C_STATUS = 8

_QSS = """
QDialog { background: #F3F4F6; color: #111827; }
QPushButton {
    background: #059669; color: #FFFFFF; border: none;
    border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: 600;
}
QPushButton:hover { background: #10B981; }
QPushButton:pressed { background: #047857; }
QPushButton:disabled { background: #D1D5DB; color: #9CA3AF; }
QPushButton#btnSecondary, QPushButton[cssClass=\"btnSecondary\"] {
    background: transparent; border: 1.5px solid #D1D5DB;
    color: #6B7280; font-weight: 500;
}
QPushButton#btnSecondary:hover, QPushButton[cssClass=\"btnSecondary\"]:hover { border-color: #059669; color: #059669; background: #F0FDF4; }
QTableWidget {
    background: #FFFFFF; alternate-background-color: #F9FAFB;
    gridline-color: #E5E7EB; border: none; font-size: 12px; color: #111827;
    selection-background-color: #D1FAE5; selection-color: #065F46;
}
QHeaderView::section {
    background: #F9FAFB; color: #374151; font-weight: 600; font-size: 12px;
    border: none; border-right: 1px solid #E5E7EB;
    border-bottom: 1px solid #E5E7EB; padding: 8px 10px;
}
QLineEdit {
    background: #FFFFFF; border: 1px solid #D1D5DB;
    border-radius: 6px; padding: 3px 8px; font-size: 12px; color: #111827;
}
QLineEdit:focus { border-color: #059669; }
QComboBox {
    background: #FFFFFF; border: 1px solid #D1D5DB;
    border-radius: 6px; padding: 3px 8px; font-size: 12px; color: #111827;
}
QComboBox::drop-down { border: none; width: 20px; background: transparent; }
QComboBox QAbstractItemView {
    background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB;
    selection-background-color: #D1FAE5;
}
QDoubleSpinBox {
    background: #FFFFFF; border: 1px solid #D1D5DB;
    border-radius: 6px; padding: 3px 8px; font-size: 12px; color: #111827;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: 0; }
QScrollBar:vertical { background: #F9FAFB; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #D1D5DB; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #9CA3AF; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMessageBox,
QMessageBox QWidget { background: #FFFFFF; color: #111827; }
QMessageBox QLabel { color: #111827; font-size: 13px; font-weight: 600; }
QMessageBox QPushButton {
    min-width: 96px;
    min-height: 36px;
    padding: 8px 16px;
    background: #059669;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
}
QMessageBox QPushButton:hover { background: #10B981; }
QMessageBox QPushButton:pressed { background: #047857; }
"""


# ── Background worker ─────────────────────────────────────────────────────────
class _ParseWorker(QThread):
    finished = Signal(list, str)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        try:
            from app.utils.excel_catalogue_importer import parse_catalogue_xlsx
            products = parse_catalogue_xlsx(self._path)
            self.finished.emit(products, "")
        except Exception as exc:
            self.finished.emit([], str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────
class ExcelImportDialog(QDialog):
    """
    Excel catalogue import dialog.

    UI skeleton is defined in  app/ui/excel_import_dialog.ui  and loaded at
    runtime via QUiLoader — open that file in Qt Designer to edit the layout.

    To edit visually:
        pyside6-designer app/ui/excel_import_dialog.ui

    To compile (optional):
        python -m app.ui.compile_ui
    """

    _UI_FILE = Path(__file__).parent.parent / "ui" / "excel_import_dialog.ui"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importer depuis un catalogue Excel")
        self.setMinimumSize(1100, 700)
        apply_light_dialog_theme(self)
        self.setStyleSheet(self.styleSheet() + _QSS)

        self._categories: dict[str, int] = {}
        self._suppliers:  dict[str, int] = {}
        self._existing_barcodes: set[str] = set()
        self._worker: _ParseWorker | None = None
        self._xlsx_path = ""

        self._load_ui()
        self._connect_signals()
        self._load_meta()

    # ── UI loading (from .ui file) ────────────────────────────────────────────

    def _load_ui(self):
        self._ui = embed_ui(self, self._UI_FILE.name)

        # Named widget references
        self._file_lbl    = self._ui.filePath
        self._parse_btn   = self._ui.btnParse
        self._progress    = self._ui.progressBar
        self._lbl_hint    = self._ui.lblHint
        self._chip_total  = self._ui.chipTotal
        self._chip_new    = self._ui.chipNew
        self._chip_dup    = self._ui.chipDup
        self._table       = self._ui.tableWidget
        self._import_btn  = self._ui.btnImport

        # Table setup
        self._table.setHorizontalHeaderLabels([
            "", "Nom du produit", "Code-barres",
            "Fournisseur", "Catégorie", "Description",
            "Prix vente", "Prix achat", "Statut",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_C_NAME, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_C_DESC, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(_C_CHECK, 40)
        self._table.verticalHeader().setVisible(False)

        self._progress.hide()
        self._chip_total.hide()
        self._chip_new.hide()
        self._chip_dup.hide()

    def _connect_signals(self):
        self._ui.btnPick.clicked.connect(self._pick_file)
        self._parse_btn.clicked.connect(self._start_parse)
        self._ui.btnAll.clicked.connect(lambda: self._set_all_checked(True))
        self._ui.btnNone.clicked.connect(lambda: self._set_all_checked(False))
        self._ui.btnSkipDup.clicked.connect(self._uncheck_duplicates)
        self._ui.btnCancel.clicked.connect(self.reject)
        self._import_btn.clicked.connect(self._do_import)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def _load_meta(self):
        self._categories = {c["name"]: c["id"] for c in CategoryController.get_all()}
        self._suppliers  = {
            s["name"]: s["id"]
            for s in db.fetchall("SELECT id, name FROM suppliers")
        }
        self._existing_barcodes = {
            r["barcode"]
            for r in db.fetchall("SELECT barcode FROM products WHERE barcode IS NOT NULL")
        }

    # ── File picker ───────────────────────────────────────────────────────────

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un catalogue Excel",
            "",
            "Fichiers Excel (*.xlsx)",
        )
        if path:
            self._xlsx_path = path
            from pathlib import Path as _Path
            self._file_lbl.setText(_Path(path).name)
            self._file_lbl.setStyleSheet("color: #111827; font-size: 13px; font-weight: 600;")
            self._parse_btn.setEnabled(True)
            self._table.setRowCount(0)
            self._import_btn.setEnabled(False)
            self._lbl_hint.setText("Cliquez sur  Analyser  pour extraire les produits.")
            for chip in (self._chip_total, self._chip_new, self._chip_dup):
                chip.hide()

    # ── Parse ─────────────────────────────────────────────────────────────────

    def _start_parse(self):
        if not self._xlsx_path:
            return
        self._parse_btn.setEnabled(False)
        self._progress.show()
        self._table.setRowCount(0)
        self._import_btn.setEnabled(False)
        self._lbl_hint.setText("Analyse du fichier en cours…")
        for chip in (self._chip_total, self._chip_new, self._chip_dup):
            chip.hide()

        self._worker = _ParseWorker(self._xlsx_path)
        self._worker.finished.connect(self._on_parse_done)
        self._worker.start()

    def _on_parse_done(self, products: list[dict], error: str):
        self._progress.hide()
        self._parse_btn.setEnabled(True)

        if error:
            QMessageBox.critical(self, "Erreur d'analyse", error)
            self._lbl_hint.setText(f"Erreur : {error}")
            return

        if not products:
            self._lbl_hint.setText("Aucun produit trouvé dans ce fichier .xlsx.")
            return

        self._load_meta()
        self._fill_table(products)

    # ── Table population ──────────────────────────────────────────────────────

    def _fill_table(self, products: list[dict]):
        self._table.setRowCount(len(products))
        dup_count = 0

        for row, p in enumerate(products):
            barcode = p.get("barcode", "")
            is_dup  = bool(barcode) and barcode in self._existing_barcodes
            if is_dup:
                dup_count += 1

            # Checkbox
            chk = QCheckBox()
            chk.setChecked(not is_dup)
            chk_w = QWidget()
            chk_lay = QHBoxLayout(chk_w)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, _C_CHECK, chk_w)

            # Name
            self._table.setCellWidget(row, _C_NAME, QLineEdit(p.get("name", "")))

            # Barcode
            bc = QLineEdit(barcode)
            bc.setPlaceholderText("—")
            self._table.setCellWidget(row, _C_BC, bc)

            # Supplier
            supp = QLineEdit(p.get("supplier", ""))
            supp.setPlaceholderText("Fournisseur")
            self._table.setCellWidget(row, _C_SUPP, supp)

            # Category combo
            cat_combo = QComboBox()
            for cat_name in sorted(self._categories.keys()):
                cat_combo.addItem(cat_name, self._categories[cat_name])
            cat_combo.view().setStyleSheet(
                "background: #FFFFFF; color: #111827; outline: 0;"
                "QAbstractItemView::item { padding: 5px 10px; min-height: 24px; }"
                "QAbstractItemView::item:hover { background: #F0FDF4; }"
                "QAbstractItemView::item:selected { background: #D1FAE5; color: #065F46; }"
            )
            idx = cat_combo.findText(p.get("category", ""))
            if idx >= 0:
                cat_combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, _C_CAT, cat_combo)

            # Description
            desc = QLineEdit(p.get("description", ""))
            desc.setPlaceholderText("Description…")
            desc.setToolTip(p.get("description", ""))
            self._table.setCellWidget(row, _C_DESC, desc)

            # Sale price
            sale_spin = PriceSpinBox()
            sale_spin.setSuffix(" TND")
            sale_spin.setFrame(False)
            sale_spin.setValue(p.get("sale_price", 0.0))
            self._table.setCellWidget(row, _C_SALE, sale_spin)

            # Purchase price
            purch_spin = PriceSpinBox()
            purch_spin.setSuffix(" TND")
            purch_spin.setFrame(False)
            self._table.setCellWidget(row, _C_PURCH, purch_spin)

            # Status
            if is_dup:
                status = QTableWidgetItem("⚠ Doublon")
                status.setForeground(QColor("#D97706"))
                status.setBackground(QColor("#FFFBEB"))
            else:
                status = QTableWidgetItem("✓ Nouveau")
                status.setForeground(QColor("#059669"))
                status.setBackground(QColor("#F0FDF4"))
            fnt = status.font()
            fnt.setBold(True)
            fnt.setPointSize(10)
            status.setFont(fnt)
            status.setFlags(status.flags() & ~Qt.ItemIsEditable)
            status.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, _C_STATUS, status)

        self._table.resizeRowsToContents()

        total   = len(products)
        new_cnt = total - dup_count
        self._lbl_hint.setText("")
        self._chip_total.setText(f"📋  {total} produit(s)")
        self._chip_new.setText(f"✓  {new_cnt} nouveau(x)")
        self._chip_dup.setText(f"⚠  {dup_count} doublon(s)")
        for chip in (self._chip_total, self._chip_new, self._chip_dup):
            chip.show()
        self._import_btn.setEnabled(new_cnt > 0)

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _set_all_checked(self, checked: bool):
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, _C_CHECK)
            if w:
                chk = w.findChild(QCheckBox)
                if chk:
                    chk.setChecked(checked)

    def _uncheck_duplicates(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _C_STATUS)
            if item and "Doublon" in item.text():
                w = self._table.cellWidget(row, _C_CHECK)
                if w:
                    chk = w.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(False)

    # ── Import ────────────────────────────────────────────────────────────────

    def _do_import(self):
        rows_to_import = []
        for row in range(self._table.rowCount()):
            chk_w = self._table.cellWidget(row, _C_CHECK)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if not (chk and chk.isChecked()):
                continue

            name         = self._cell_text(row, _C_NAME)
            barcode      = self._cell_text(row, _C_BC) or None
            supplier_name = self._cell_text(row, _C_SUPP)
            cat_combo    = self._table.cellWidget(row, _C_CAT)
            desc         = self._cell_text(row, _C_DESC)
            sale_spin    = self._table.cellWidget(row, _C_SALE)
            purch_spin   = self._table.cellWidget(row, _C_PURCH)

            if not name:
                continue

            rows_to_import.append({
                "name":           name,
                "barcode":        barcode,
                "supplier_id":    self._get_or_create_supplier(supplier_name),
                "category_id":    cat_combo.currentData() if cat_combo else None,
                "description":    desc,
                "sale_price":     sale_spin.value()  if sale_spin  else 0.0,
                "purchase_price": purch_spin.value() if purch_spin else 0.0,
            })

        if not rows_to_import:
            QMessageBox.information(self, "Sélection vide",
                                    "Cochez au moins un produit à importer.")
            return

        reply = QMessageBox.question(
            self, "Confirmer l'import",
            f"Importer {len(rows_to_import)} produit(s) ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok = errors = 0
        for data in rows_to_import:
            try:
                ProductController.create(data)
                ok += 1
            except Exception:
                errors += 1

        msg = f"{ok} produit(s) importé(s) avec succès."
        if errors:
            msg += f"\n{errors} non importé(s) (code-barres dupliqués ou erreur)."
        QMessageBox.information(self, "Import terminé", msg)
        self.accept()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cell_text(self, row: int, col: int) -> str:
        w = self._table.cellWidget(row, col)
        if isinstance(w, QLineEdit):
            return w.text().strip()
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _get_or_create_supplier(self, name: str) -> int | None:
        if not name:
            return None
        if name in self._suppliers:
            return self._suppliers[name]
        try:
            SupplierController.create({"name": name})
            self._suppliers = {
                s["name"]: s["id"]
                for s in db.fetchall("SELECT id, name FROM suppliers")
            }
            return self._suppliers.get(name)
        except Exception:
            return None
