from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QFrame, QDialog, QMessageBox, QComboBox,
)
from PySide6.QtCore import QDate, Qt

from app.views.widgets.data_table import DataTable
from app.controllers.sale_controller import SaleController
from app.controllers.auth_controller import AuthController
from app.utils.helpers import format_price, format_datetime
from app.utils.exporter import export_to_excel, generate_receipt_pdf
from app.database.connection import db
from app.views.dialog_theme import apply_light_dialog_theme, light_information, light_question, light_warning
import subprocess, sys


class SalesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sales = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Filters
        filter_row = QHBoxLayout()

        lbl_from = QLabel("Du :")
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        self._date_from.setMinimumHeight(40)

        lbl_to = QLabel("Au :")
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setMinimumHeight(40)

        self._status_filter = QComboBox()
        self._status_filter.setMinimumHeight(40)
        self._status_filter.addItem("Tous les statuts", None)
        self._status_filter.addItem("Complétées", "completed")
        self._status_filter.addItem("Annulées", "cancelled")

        btn_filter = QPushButton("Filtrer")
        btn_filter.setMinimumHeight(40)
        btn_filter.clicked.connect(self.refresh)

        btn_today = QPushButton("Aujourd'hui")
        btn_today.setObjectName("btnSecondary")
        btn_today.setMinimumHeight(40)
        btn_today.clicked.connect(self._filter_today)

        btn_export = QPushButton("Exporter Excel")
        btn_export.setObjectName("btnSecondary")
        btn_export.setMinimumHeight(40)
        btn_export.clicked.connect(self._export)

        filter_row.addWidget(lbl_from)
        filter_row.addWidget(self._date_from)
        filter_row.addWidget(lbl_to)
        filter_row.addWidget(self._date_to)
        filter_row.addWidget(self._status_filter)
        filter_row.addWidget(btn_today)
        filter_row.addWidget(btn_filter)
        filter_row.addStretch()
        filter_row.addWidget(btn_export)
        layout.addLayout(filter_row)

        # Summary cards
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self._lbl_count = self._make_summary("0", "Ventes")
        self._lbl_revenue = self._make_summary("0.000 TND", "Chiffre d'affaires")
        self._lbl_avg = self._make_summary("0.000 TND", "Panier moyen")
        summary_row.addWidget(self._lbl_count[0])
        summary_row.addWidget(self._lbl_revenue[0])
        summary_row.addWidget(self._lbl_avg[0])
        summary_row.addStretch()
        layout.addLayout(summary_row)

        # Table
        self._table = DataTable(["#", "Date", "Caissier", "Articles", "Sous-total", "Remise", "Total", "Paiement", "Statut"])
        self._table.setMinimumHeight(560)
        self._table.setMaximumHeight(560)
        self._table.itemDoubleClicked.connect(self._view_sale)
        layout.addWidget(self._table, 0)

        # Action bar
        btn_row = QHBoxLayout()
        btn_details = QPushButton("Détails")
        btn_details.setObjectName("btnSecondary")
        btn_details.clicked.connect(self._view_sale)

        btn_cancel = QPushButton("Annuler vente")
        btn_cancel.setObjectName("btnDanger")
        btn_cancel.clicked.connect(self._cancel_sale)

        btn_reprint = QPushButton("Réimprimer ticket")
        btn_reprint.setObjectName("btnSecondary")
        btn_reprint.clicked.connect(self._reprint)

        btn_row.addStretch()
        btn_row.addWidget(btn_details)
        btn_row.addWidget(btn_reprint)
        if AuthController.is_admin():
            btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _make_summary(self, value: str, label: str):
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setFixedHeight(72)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 8, 16, 8)
        v = QLabel(value)
        v.setStyleSheet("font-size: 20px; font-weight: 700; color: #059669;")
        l = QLabel(label)
        l.setStyleSheet("font-size: 11px; color: #6B7280;")
        lay.addWidget(v)
        lay.addWidget(l)
        return frame, v

    def refresh(self):
        d_from = self._date_from.date().toString("yyyy-MM-dd")
        d_to = self._date_to.date().toString("yyyy-MM-dd")
        status = self._status_filter.currentData()
        self._sales = SaleController.get_sales(d_from, d_to, status=status)

        total_rev = sum(s["total"] for s in self._sales if s["status"] == "completed")
        completed = [s for s in self._sales if s["status"] == "completed"]
        avg = total_rev / len(completed) if completed else 0

        self._lbl_count[1].setText(str(len(self._sales)))
        self._lbl_revenue[1].setText(format_price(total_rev))
        self._lbl_avg[1].setText(format_price(avg))

        status_labels = {"completed": "Complétée", "cancelled": "Annulée", "refunded": "Remboursée"}
        method_labels = {"cash": "Espèces", "card": "Carte", "other": "Autre", "credit": "Crédit"}

        display = []
        for s in self._sales:
            d = dict(s)
            d["created_at"] = format_datetime(s["created_at"])
            d["subtotal"] = format_price(s["subtotal"])
            d["discount"] = f"-{format_price(s['discount'])}" if s["discount"] else "—"
            d["total"] = format_price(s["total"])
            payment_method = method_labels.get(s["payment_method"], s["payment_method"])
            payment_status = str(s.get("payment_status") or "").strip().lower()
            if str(s.get("payment_method") or "").strip().lower() == "credit":
                if payment_status == "paid":
                    payment_method = "Crédit réglé"
                elif payment_status == "partial":
                    payment_method = "Crédit partiel"
                else:
                    payment_method = "Crédit"
            d["payment_method"] = payment_method
            d["status"] = status_labels.get(s["status"], s["status"])
            display.append(d)

        self._table.set_data(display, ["id", "created_at", "cashier_name", "item_count", "subtotal", "discount", "total", "payment_method", "status"])

    def _filter_today(self):
        today = QDate.currentDate()
        self._date_from.setDate(today)
        self._date_to.setDate(today)
        self.refresh()

    def _view_sale(self):
        data = self._table.selected_row_data()
        if not data:
            return
        sale = SaleController.get_by_id(data["id"])
        dlg = SaleDetailDialog(sale, self)
        dlg.exec()

    def _cancel_sale(self):
        data = self._table.selected_row_data()
        if not data:
            return
        if data.get("status") != "Complétée":
            light_warning(self, "Impossible", "Seules les ventes complétées peuvent être annulées.")
            return
        reply = light_question(self, "Annuler vente", f"Annuler la vente #{data['id']} ?")
        if reply == QMessageBox.Yes:
            SaleController.cancel_sale(data["id"])
            self.refresh()

    def _reprint(self):
        data = self._table.selected_row_data()
        if not data:
            return
        sale = SaleController.get_by_id(data["id"])
        settings = {r["key"]: r["value"] for r in db.fetchall("SELECT `key` AS `key`, value FROM settings")}
        pdf = generate_receipt_pdf(sale, settings)
        try:
            if sys.platform == "linux":
                subprocess.Popen(["xdg-open", pdf])
            else:
                subprocess.Popen(["open", pdf])
        except Exception:
            light_information(self, "Ticket", f"Ticket sauvegardé :\n{pdf}")

    def _export(self):
        if not self._sales:
            return
        path = export_to_excel(self._sales, "ventes")
        light_information(self, "Export", f"Exporté :\n{path}")


class SaleDetailDialog(QDialog):
    def __init__(self, sale: dict, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle(f"Vente #{sale['id']}")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        info = f"""
        <b>Vente #{sale['id']}</b><br>
        Date : {format_datetime(sale['created_at'])}<br>
        Caissier : {sale.get('cashier_name', '—')}<br>
        Mode de paiement : {sale['payment_method']}
        """
        layout.addWidget(QLabel(info))

        sep = QFrame()
        sep.setObjectName("separator")
        layout.addWidget(sep)

        tbl = DataTable(["Produit", "Qté", "Prix unit.", "Total"])
        tbl.set_data(sale.get("items", []), ["product_name", "quantity", "unit_price", "total"])
        layout.addWidget(tbl)

        sep2 = QFrame()
        sep2.setObjectName("separator")
        layout.addWidget(sep2)

        totals = QLabel(f"""
        Sous-total : {format_price(sale['subtotal'])}<br>
        Remise : -{format_price(sale['discount'])}<br>
        TVA : {format_price(sale['tax'])}<br>
        <b>TOTAL : {format_price(sale['total'])}</b><br>
        Payé : {format_price(sale['amount_paid'])}<br>
        Monnaie : {format_price(sale['change_given'])}
        """)
        totals.setAlignment(Qt.AlignRight)
        layout.addWidget(totals)

        btn = QPushButton("Fermer")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, 0, Qt.AlignRight)
