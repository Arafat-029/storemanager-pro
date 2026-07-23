from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QFormLayout, QComboBox, QLineEdit, QLabel,
    QMessageBox, QDateEdit, QFrame,
)
from app.views.widgets.price_input import PriceSpinBox
from app.views.dialog_theme import apply_light_dialog_theme
from PySide6.QtCore import QDate, Qt

from app.views.widgets.data_table import DataTable
from app.controllers.expense_controller import ExpenseController, EXPENSE_CATEGORIES
from app.controllers.auth_controller import AuthController
from app.utils.helpers import format_price, format_datetime


class ExpensesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

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
        btn_filter = QPushButton("🔍  Filtrer")
        btn_filter.setMinimumHeight(40)
        btn_filter.clicked.connect(self.refresh)
        btn_add = QPushButton("＋  Nouvelle dépense")
        btn_add.setMinimumHeight(40)
        btn_add.clicked.connect(self._add)

        filter_row.addWidget(lbl_from)
        filter_row.addWidget(self._date_from)
        filter_row.addWidget(lbl_to)
        filter_row.addWidget(self._date_to)
        filter_row.addWidget(btn_filter)
        filter_row.addStretch()
        filter_row.addWidget(btn_add)
        layout.addLayout(filter_row)

        # Total banner
        self._total_frame = QFrame()
        self._total_frame.setObjectName("statCard")
        self._total_frame.setFixedHeight(70)
        banner_row = QHBoxLayout(self._total_frame)
        self._total_lbl = QLabel()
        self._total_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #E53935;")
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("color: #6B7280;")
        banner_row.addWidget(QLabel("Total dépenses :"))
        banner_row.addWidget(self._total_lbl)
        banner_row.addStretch()
        banner_row.addWidget(self._count_lbl)
        layout.addWidget(self._total_frame)

        self._table = DataTable(["ID", "Date", "Catégorie", "Montant", "Description", "Utilisateur"])
        layout.addWidget(self._table, 1)

        if AuthController.is_admin():
            btn_row = QHBoxLayout()
            btn_del = QPushButton("🗑️  Supprimer")
            btn_del.setObjectName("btnDanger")
            btn_del.clicked.connect(self._delete)
            btn_row.addStretch()
            btn_row.addWidget(btn_del)
            layout.addLayout(btn_row)

    def refresh(self):
        d_from = self._date_from.date().toString("yyyy-MM-dd")
        d_to = self._date_to.date().toString("yyyy-MM-dd")
        expenses = ExpenseController.get_all(d_from, d_to)
        summary = ExpenseController.get_summary(d_from, d_to)

        self._total_lbl.setText(format_price(summary.get("total", 0)))
        self._count_lbl.setText(f"{summary.get('count', 0)} dépense(s)")

        display = []
        for e in expenses:
            d = dict(e)
            d["created_at"] = format_datetime(e["created_at"])
            d["amount"] = format_price(e["amount"])
            display.append(d)
        self._table.set_data(display, ["id", "created_at", "category", "amount", "description", "user_name"])

    def _add(self):
        dlg = ExpenseDialog(self)
        if dlg.exec():
            self.refresh()

    def _delete(self):
        data = self._table.selected_row_data()
        if not data:
            return
        reply = QMessageBox.question(self, "Supprimer", "Supprimer cette dépense ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            ExpenseController.delete(data["id"])
            self.refresh()


class ExpenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle("Nouvelle dépense")
        self.setFixedWidth(380)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        self._category = QComboBox()
        self._category.setMinimumHeight(42)
        for cat in EXPENSE_CATEGORIES:
            self._category.addItem(cat)

        self._amount = PriceSpinBox()
        self._amount.setMinimumHeight(42)
        self._amount.setMaximum(999999)
        self._amount.setSuffix("  TND")

        self._desc = QLineEdit()
        self._desc.setMinimumHeight(42)
        self._desc.setPlaceholderText("Description optionnelle...")

        form.addRow("Catégorie:", self._category)
        form.addRow("Montant *:", self._amount)
        form.addRow("Description:", self._desc)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾  Enregistrer")
        btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _save(self):
        if self._amount.value() <= 0:
            QMessageBox.warning(self, "Erreur", "Le montant doit être supérieur à 0.")
            return
        ExpenseController.create(self._category.currentText(), self._amount.value(), self._desc.text())
        self.accept()
