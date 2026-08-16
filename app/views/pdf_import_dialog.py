from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QFileDialog, QMessageBox, QProgressBar, QAbstractItemView,
    QComboBox, QCheckBox, QWidget,
)
from app.views.widgets.price_input import PriceSpinBox
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont

from app.controllers.product_controller import ProductController
from app.controllers.category_controller import CategoryController
from app.database.connection import db
from app.views.widgets.screen_fit import clamp_min_size


# ── Background worker ─────────────────────────────────────────────
class _ParseWorker(QThread):
    finished = Signal(list, str)   # (products, error_msg)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        try:
            from app.utils.pdf_catalogue_importer import parse_catalogue_pdf
            products = parse_catalogue_pdf(self._path)
            self.finished.emit(products, "")
        except Exception as exc:
            self.finished.emit([], str(exc))


# ── Column indices ────────────────────────────────────────────────
_C_CHECK  = 0
_C_NAME   = 1
_C_BC     = 2
_C_CAT    = 3
_C_SALE   = 4
_C_PURCH  = 5
_C_STATUS = 6


class PDFImportDialog(QDialog):
    """
    Preview and confirm import of products from a PDF catalogue.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importer depuis un catalogue PDF")
        clamp_min_size(self, 1000, 680)
        self._categories: dict[str, int] = {}
        self._existing_barcodes: set[str] = set()
        self._worker: _ParseWorker | None = None
        self._build_ui()
        self._load_meta()

    # ── Build UI ─────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #059669, stop:1 #047857); }"
        )
        header.setFixedHeight(72)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)
        title = QLabel("Importer des produits depuis un catalogue PDF")
        title.setStyleSheet("color: white; font-size: 17px; font-weight: 700; background: transparent;")
        h_lay.addWidget(title)

        layout.addWidget(header)

        # File picker row
        file_row = QFrame()
        file_row.setStyleSheet("QFrame { background: #F9FAFB; border-bottom: 1px solid #E5E7EB; }")
        fr_lay = QHBoxLayout(file_row)
        fr_lay.setContentsMargins(20, 12, 20, 12)
        fr_lay.setSpacing(12)

        self._file_lbl = QLabel("Aucun fichier sélectionné")
        self._file_lbl.setStyleSheet("color: #6B7280; font-size: 13px;")

        btn_pick = QPushButton("Choisir un PDF")
        btn_pick.setFixedHeight(38)
        btn_pick.setMinimumWidth(160)
        btn_pick.clicked.connect(self._pick_file)

        self._parse_btn = QPushButton("Analyser")
        self._parse_btn.setFixedHeight(38)
        self._parse_btn.setMinimumWidth(120)
        self._parse_btn.setEnabled(False)
        self._parse_btn.clicked.connect(self._start_parse)

        fr_lay.addWidget(QLabel("Fichier PDF :"))
        fr_lay.addWidget(self._file_lbl, 1)
        fr_lay.addWidget(btn_pick)
        fr_lay.addWidget(self._parse_btn)
        layout.addWidget(file_row)

        # Progress bar (hidden until parsing)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setStyleSheet(
            "QProgressBar { background: #E5E7EB; border: none; }"
            "QProgressBar::chunk { background: #059669; }"
        )
        self._progress.hide()
        layout.addWidget(self._progress)

        # Table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "", "Nom du produit", "Code-barres",
            "Catégorie", "Prix vente (TND)", "Prix achat (TND)", "Statut",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_C_NAME, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(_C_CHECK, 36)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        # Summary bar
        self._summary = QLabel("Sélectionnez un fichier PDF pour commencer.")
        self._summary.setStyleSheet(
            "background: #F9FAFB; color: #374151; font-size: 12px;"
            "padding: 8px 20px; border-top: 1px solid #E5E7EB;"
        )
        layout.addWidget(self._summary)

        # Bottom buttons
        btn_row = QFrame()
        btn_row.setStyleSheet("QFrame { background: #FFFFFF; border-top: 1px solid #E5E7EB; }")
        br_lay = QHBoxLayout(btn_row)
        br_lay.setContentsMargins(20, 14, 20, 14)
        br_lay.setSpacing(10)

        btn_all = QPushButton("Tout sélectionner")
        btn_all.setObjectName("btnSecondary")
        btn_all.setFixedHeight(36)
        btn_all.clicked.connect(lambda: self._set_all_checked(True))

        btn_none = QPushButton("Tout désélectionner")
        btn_none.setObjectName("btnSecondary")
        btn_none.setFixedHeight(36)
        btn_none.clicked.connect(lambda: self._set_all_checked(False))

        btn_skip_dup = QPushButton("Ignorer les doublons")
        btn_skip_dup.setObjectName("btnSecondary")
        btn_skip_dup.setFixedHeight(36)
        btn_skip_dup.clicked.connect(self._uncheck_duplicates)

        btn_cancel = QPushButton("Fermer")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(self.reject)

        self._import_btn = QPushButton("Importer la sélection")
        self._import_btn.setFixedHeight(38)
        self._import_btn.setMinimumWidth(200)
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._do_import)

        br_lay.addWidget(btn_all)
        br_lay.addWidget(btn_none)
        br_lay.addWidget(btn_skip_dup)
        br_lay.addStretch()
        br_lay.addWidget(btn_cancel)
        br_lay.addWidget(self._import_btn)
        layout.addWidget(btn_row)

        self._pdf_path = ""

    # ── Metadata ──────────────────────────────────────────────────
    def _load_meta(self):
        self._categories = {c["name"]: c["id"] for c in CategoryController.get_all()}
        self._existing_barcodes = {
            r["barcode"] for r in
            db.fetchall("SELECT barcode FROM products WHERE barcode IS NOT NULL")
        }

    # ── File picker ───────────────────────────────────────────────
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un catalogue PDF", "", "Fichiers PDF (*.pdf)"
        )
        if path:
            self._pdf_path = path
            self._file_lbl.setText(Path(path).name)
            self._parse_btn.setEnabled(True)
            self._table.setRowCount(0)
            self._import_btn.setEnabled(False)
            self._summary.setText("Cliquez sur Analyser pour extraire les produits.")

    # ── Parse ─────────────────────────────────────────────────────
    def _start_parse(self):
        if not self._pdf_path:
            return
        self._parse_btn.setEnabled(False)
        self._progress.show()
        self._table.setRowCount(0)
        self._summary.setText("Analyse du PDF en cours…")

        self._worker = _ParseWorker(self._pdf_path)
        self._worker.finished.connect(self._on_parse_done)
        self._worker.start()

    def _on_parse_done(self, products: list[dict], error: str):
        self._progress.hide()
        self._parse_btn.setEnabled(True)

        if error:
            QMessageBox.critical(self, "Erreur d'analyse", error)
            self._summary.setText(f"Erreur : {error}")
            return

        if not products:
            self._summary.setText("Aucun produit trouvé dans ce PDF.")
            return

        self._fill_table(products)

    def _fill_table(self, products: list[dict]):
        self._load_meta()  # refresh existing barcodes
        self._table.setRowCount(len(products))

        dup_count = 0
        for row, p in enumerate(products):
            barcode = p.get('barcode', '')
            is_dup = barcode in self._existing_barcodes

            if is_dup:
                dup_count += 1

            # Check column
            chk = QCheckBox()
            chk.setChecked(not is_dup)
            chk.setStyleSheet("margin-left: 10px;")
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, _C_CHECK, chk_widget)

            # Name (editable)
            name_item = QTableWidgetItem(p.get('name', ''))
            self._table.setItem(row, _C_NAME, name_item)

            # Barcode (editable)
            bc_item = QTableWidgetItem(barcode)
            self._table.setItem(row, _C_BC, bc_item)

            # Category (combo)
            cat_combo = QComboBox()
            for cat_name in sorted(self._categories.keys()):
                cat_combo.addItem(cat_name, self._categories[cat_name])
            default_cat = p.get('category', '')
            idx = cat_combo.findText(default_cat)
            if idx >= 0:
                cat_combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, _C_CAT, cat_combo)

            # Sale price
            sale_spin = PriceSpinBox()
            sale_spin.setMaximum(99999.999)
            sale_spin.setSuffix(" TND")
            sale_spin.setFrame(False)
            self._table.setCellWidget(row, _C_SALE, sale_spin)

            # Purchase price
            purch_spin = PriceSpinBox()
            purch_spin.setMaximum(99999.999)
            purch_spin.setSuffix(" TND")
            purch_spin.setFrame(False)
            self._table.setCellWidget(row, _C_PURCH, purch_spin)

            # Status
            if is_dup:
                status = QTableWidgetItem("Déjà en base")
                status.setForeground(QColor("#D97706"))
            else:
                status = QTableWidgetItem("Nouveau")
                status.setForeground(QColor("#059669"))
            status.setFlags(status.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, _C_STATUS, status)

        total = len(products)
        new_count = total - dup_count
        self._summary.setText(
            f"  {total} produit(s) trouvé(s)  •  "
            f"{new_count} nouveau(x)  •  "
            f"{dup_count} déjà présent(s) en base"
        )
        self._import_btn.setEnabled(True)
        self._table.resizeRowsToContents()

    # ── Selection helpers ─────────────────────────────────────────
    def _set_all_checked(self, checked: bool):
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, _C_CHECK)
            if w:
                chk = w.findChild(QCheckBox)
                if chk:
                    chk.setChecked(checked)

    def _uncheck_duplicates(self):
        for row in range(self._table.rowCount()):
            status_item = self._table.item(row, _C_STATUS)
            if status_item and "Déjà" in status_item.text():
                w = self._table.cellWidget(row, _C_CHECK)
                if w:
                    chk = w.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(False)

    # ── Import ────────────────────────────────────────────────────
    def _do_import(self):
        rows_to_import = []
        for row in range(self._table.rowCount()):
            chk_w = self._table.cellWidget(row, _C_CHECK)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if not (chk and chk.isChecked()):
                continue

            name = (self._table.item(row, _C_NAME) or QTableWidgetItem()).text().strip()
            barcode = (self._table.item(row, _C_BC) or QTableWidgetItem()).text().strip()
            cat_combo = self._table.cellWidget(row, _C_CAT)
            sale_spin = self._table.cellWidget(row, _C_SALE)
            purch_spin = self._table.cellWidget(row, _C_PURCH)

            if not name:
                continue

            rows_to_import.append({
                'name': name,
                'barcode': barcode or None,
                'category_id': cat_combo.currentData() if cat_combo else None,
                'sale_price': sale_spin.value() if sale_spin else 0.0,
                'purchase_price': purch_spin.value() if purch_spin else 0.0,
            })

        if not rows_to_import:
            QMessageBox.information(self, "Sélection vide",
                                    "Cochez au moins un produit à importer.")
            return

        reply = QMessageBox.question(
            self, "Confirmer l'import",
            f"Importer {len(rows_to_import)} produit(s) dans la base de données ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok = 0
        errors = 0
        for data in rows_to_import:
            try:
                ProductController.create(data)
                ok += 1
            except Exception:
                errors += 1

        msg = f"{ok} produit(s) importé(s) avec succès."
        if errors:
            msg += f"\n{errors} erreur(s) (doublons de code-barres ignorés)."

        QMessageBox.information(self, "Import terminé", msg)
        self._summary.setText(f"{ok} produit(s) importé(s). {errors} erreur(s).")
        self._import_btn.setEnabled(False)
        self.accept()
