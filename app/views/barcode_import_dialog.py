from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QWidget, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer

from app.controllers.product_controller import ProductController
from app.utils.barcode_scanner import BarcodeScannerDialog, SCANNER_AVAILABLE


class _ScannedRow(QFrame):
    delete_requested = Signal()
    create_requested = Signal(str)

    def __init__(self, barcode: str, product: dict | None, parent=None):
        super().__init__(parent)
        self._barcode = barcode
        self._product = product
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(64)
        if self._product is None:
            self.setStyleSheet(
                "QFrame {"
                "  border: 2.5px solid #DC2626;"
                "  border-radius: 10px;"
                "  background: #FEF2F2;"
                "}"
                "QLabel { background: transparent; border: none; }"
            )
        else:
            self.setStyleSheet(
                "QFrame {"
                "  border: 1.5px solid #86EFAC;"
                "  border-radius: 10px;"
                "  background: #F0FDF4;"
                "}"
                "QLabel { background: transparent; border: none; }"
            )

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(12)

        icon = QLabel("❌" if self._product is None else "✅")
        icon.setFixedWidth(22)
        icon.setStyleSheet("background: transparent; border: none; font-size: 17px;")
        row.addWidget(icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        code_lbl = QLabel(f"<b>{self._barcode}</b>")
        code_lbl.setStyleSheet(
            "font-size: 13px; background: transparent; border: none; color: #111827;"
        )
        info_col.addWidget(code_lbl)

        if self._product:
            sub = QLabel(self._product["name"])
            sub.setStyleSheet(
                "font-size: 11px; color: #059669; background: transparent; border: none;"
            )
        else:
            sub = QLabel("Produit non trouvé dans la base de données")
            sub.setStyleSheet(
                "font-size: 11px; color: #DC2626; background: transparent; border: none;"
            )
        info_col.addWidget(sub)
        row.addLayout(info_col, 1)

        if self._product is None:
            btn_create = QPushButton("＋  Créer produit")
            btn_create.setFixedHeight(30)
            btn_create.setStyleSheet(
                "QPushButton { background: #DC2626; color: white; border: none;"
                "border-radius: 6px; font-size: 12px; font-weight: 700; padding: 0 10px; }"
                "QPushButton:hover { background: #EF4444; }"
            )
            btn_create.clicked.connect(lambda: self.create_requested.emit(self._barcode))
            row.addWidget(btn_create)

        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(30, 30)
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; color: #9CA3AF;"
            "border: 1.5px solid #E5E7EB; border-radius: 6px; font-size: 13px; }"
            "QPushButton:hover { color: #DC2626; border-color: #DC2626; background: #FEF2F2; }"
        )
        btn_del.clicked.connect(self.delete_requested.emit)
        row.addWidget(btn_del)


class BarcodeBatchImportDialog(QDialog):
    """Scan multiple barcodes. Found products show green, unknown show red border."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan codes-barres produits")
        self.setMinimumSize(660, 560)
        self._rows: list[_ScannedRow] = []
        self._scanned_codes: set[str] = set()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #059669, stop:1 #047857); }"
        )
        hdr.setFixedHeight(52)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("📷  Scan lot codes-barres / QR codes")
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: white;"
            "background: transparent; border: none;"
        )
        self._count_lbl = QLabel("0 code(s)")
        self._count_lbl.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.8);"
            "background: transparent; border: none;"
        )
        hl.addWidget(title_lbl)
        hl.addStretch()
        hl.addWidget(self._count_lbl)
        layout.addWidget(hdr)

        # ── Scan input row ─────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame { background: #F9FAFB; border-bottom: 1px solid #E5E7EB; }"
            "QLabel { background: transparent; border: none; color: #374151; }"
        )
        il = QHBoxLayout(input_frame)
        il.setContentsMargins(16, 12, 16, 12)
        il.setSpacing(8)

        lbl = QLabel("Code :")
        lbl.setFixedWidth(52)
        lbl.setStyleSheet(
            "font-weight: 600; font-size: 12px; color: #374151;"
            "background: transparent; border: none;"
        )
        il.addWidget(lbl)

        self._code_input = QLineEdit()
        self._code_input.setMinimumHeight(40)
        self._code_input.setPlaceholderText("Code-barres ou référence produit…")
        self._code_input.returnPressed.connect(self._add_manual)
        il.addWidget(self._code_input, 1)

        btn_scan = QPushButton("📷  Scanner")
        btn_scan.setMinimumHeight(40)
        btn_scan.setEnabled(SCANNER_AVAILABLE)
        if not SCANNER_AVAILABLE:
            btn_scan.setToolTip("Installer opencv-python pour activer le scanner")
        btn_scan.clicked.connect(self._open_scanner)
        il.addWidget(btn_scan)

        btn_add = QPushButton("＋  Ajouter")
        btn_add.setObjectName("btnSuccess")
        btn_add.setMinimumHeight(40)
        btn_add.clicked.connect(self._add_manual)
        il.addWidget(btn_add)

        layout.addWidget(input_frame)

        # ── Legend ─────────────────────────────────────────────────
        legend = QFrame()
        legend.setStyleSheet(
            "QFrame { background: #FFFFFF; border-bottom: 1px solid #F3F4F6; }"
        )
        ll = QHBoxLayout(legend)
        ll.setContentsMargins(16, 6, 16, 6)
        ll.setSpacing(20)

        lbl_ok = QLabel("✅  Produit trouvé en base")
        lbl_ok.setStyleSheet(
            "font-size: 11px; color: #059669; background: transparent; border: none;"
        )
        lbl_nok = QLabel("❌  Inconnu — cadre rouge — cliquer ＋ pour créer")
        lbl_nok.setStyleSheet(
            "font-size: 11px; color: #DC2626; background: transparent; border: none;"
        )
        ll.addWidget(lbl_ok)
        ll.addWidget(lbl_nok)
        ll.addStretch()
        layout.addWidget(legend)

        # ── Scrollable list ────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._scroll_widget = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_widget)
        self._list_layout.setContentsMargins(16, 12, 16, 12)
        self._list_layout.setSpacing(8)

        self._empty_lbl = QLabel(
            "Scannez ou saisissez un code-barres pour commencer"
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(
            "color: #9CA3AF; font-size: 14px; padding: 40px;"
            "background: transparent; border: none;"
        )
        self._list_layout.addWidget(self._empty_lbl)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll, 1)

        # ── Footer ─────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet(
            "QFrame { background: #FFFFFF; border-top: 1.5px solid #E5E7EB; }"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 12, 20, 12)
        fl.setSpacing(10)

        self._summary_lbl = QLabel()
        self._summary_lbl.setStyleSheet(
            "color: #6B7280; font-size: 12px; background: transparent; border: none;"
        )

        btn_clear = QPushButton("🗑  Effacer tout")
        btn_clear.setObjectName("btnDanger")
        btn_clear.setFixedHeight(38)
        btn_clear.clicked.connect(self._clear_all)

        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("btnSecondary")
        btn_close.setFixedHeight(38)
        btn_close.clicked.connect(self.accept)

        fl.addWidget(self._summary_lbl)
        fl.addStretch()
        fl.addWidget(btn_clear)
        fl.addWidget(btn_close)
        layout.addWidget(footer)

    # ── Slots ──────────────────────────────────────────────────────

    def _open_scanner(self):
        dlg = BarcodeScannerDialog(self)
        if dlg.exec():
            code = dlg.get_result().strip()
            if code:
                self._add_code(code)

    def _add_manual(self):
        code = self._code_input.text().strip()
        if not code:
            self._code_input.setFocus()
            return
        self._add_code(code)
        self._code_input.clear()
        self._code_input.setFocus()

    def _add_code(self, code: str):
        if code in self._scanned_codes:
            self._code_input.setPlaceholderText(f"'{code}' déjà dans la liste")
            return

        self._scanned_codes.add(code)
        product = ProductController.get_by_barcode(code)

        row = _ScannedRow(code, product, self._scroll_widget)
        row.delete_requested.connect(lambda r=row, c=code: self._remove_row(r, c))
        row.create_requested.connect(self._create_product)

        self._rows.append(row)
        # Insert before the trailing stretch (last item in layout)
        self._list_layout.insertWidget(self._list_layout.count() - 1, row)

        self._update_ui()
        QTimer.singleShot(
            50,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ),
        )

    def _remove_row(self, row: _ScannedRow, code: str):
        self._scanned_codes.discard(code)
        self._rows.remove(row)
        self._list_layout.removeWidget(row)
        row.deleteLater()
        self._update_ui()

    def _create_product(self, barcode: str):
        from app.views.products_view import ProductDialog
        dlg = ProductDialog(self)
        dlg._barcode.setText(barcode)
        dlg._name.setFocus()
        if dlg.exec():
            self._refresh_row(barcode)

    def _refresh_row(self, barcode: str):
        product = ProductController.get_by_barcode(barcode)
        for i, row in enumerate(self._rows):
            if row._barcode != barcode:
                continue
            new_row = _ScannedRow(barcode, product, self._scroll_widget)
            new_row.delete_requested.connect(lambda r=new_row, c=barcode: self._remove_row(r, c))
            new_row.create_requested.connect(self._create_product)
            idx = self._list_layout.indexOf(row)
            self._list_layout.removeWidget(row)
            row.deleteLater()
            self._list_layout.insertWidget(idx, new_row)
            self._rows[i] = new_row
            break
        self._update_ui()

    def _clear_all(self):
        if not self._rows:
            return
        reply = QMessageBox.question(
            self, "Effacer tout", "Effacer tous les codes scannés ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for row in self._rows:
                self._list_layout.removeWidget(row)
                row.deleteLater()
            self._rows.clear()
            self._scanned_codes.clear()
            self._update_ui()

    def _update_ui(self):
        count = len(self._rows)
        unknown = sum(1 for r in self._rows if r._product is None)
        known = count - unknown

        self._count_lbl.setText(f"{count} code(s)")
        self._empty_lbl.setVisible(count == 0)

        parts = []
        if known:
            parts.append(
                f"<span style='color:#059669; font-weight:600'>{known} trouvé(s)</span>"
            )
        if unknown:
            parts.append(
                f"<span style='color:#DC2626; font-weight:600'>{unknown} inconnu(s)</span>"
            )
        self._summary_lbl.setText("  •  ".join(parts) if parts else "")
