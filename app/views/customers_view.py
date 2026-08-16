from __future__ import annotations

from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.auth_controller import AuthController
from app.controllers.customer_controller import CustomerController
from app.utils.helpers import format_date, format_datetime, format_price
from app.views.dialog_theme import (
    apply_light_dialog_theme,
    light_critical,
    light_information,
    light_question,
    light_warning,
)
from app.views.widgets.price_input import PriceSpinBox
from app.views.widgets.quantity_input import configure_manual_spinbox


def _fmt_date(value) -> str:
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value)
    return format_date(str(value or ""))


def _fmt_datetime(value) -> str:
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)
    return format_datetime(str(value or ""))


class CustomersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_refreshing = False
        self._loaded_once = False
        self._load_scheduled = False
        self._build_ui()

    def ensure_loaded(self):
        if not self._loaded_once and self.isVisible():
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # The first load is deferred so the tab switch itself paints immediately;
        # showEvent() fires synchronously inside MainWindow.navigate(), and running
        # refresh() (query + full table rebuild) right here would block that paint.
        if not self._loaded_once and not self._is_refreshing and not self._load_scheduled:
            self._load_scheduled = True
            QTimer.singleShot(0, self._run_initial_load)

    def _run_initial_load(self):
        self._load_scheduled = False
        if not self._loaded_once and not self._is_refreshing:
            self.refresh()

    def _refresh_if_loaded(self):
        if self._loaded_once:
            self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Gestion des clients")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher par nom ou téléphone…")
        self._search.setFixedHeight(40)
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self._refresh_if_loaded)

        btn_add = QPushButton("＋  Nouveau client")
        btn_add.setFixedHeight(40)
        btn_add.setVisible(AuthController.is_admin())
        btn_add.clicked.connect(self._add_customer)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._search)
        header.addWidget(btn_add)
        layout.addLayout(header)

        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet(
            "background: #ECFDF5; color: #065F46; border-radius: 8px;"
            "padding: 8px 14px; font-size: 13px;"
        )
        layout.addWidget(self._stats_lbl)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Nom", "Téléphone", "Solde dû (TND)", "Créé le", "Actions"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(4, 450)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        layout.addWidget(self._table, 1)

    def refresh(self):
        if self._is_refreshing:
            return

        self._is_refreshing = True

        try:
            q = self._search.text().strip() if hasattr(self, "_search") else ""
            customers = CustomerController.search(q) if q else CustomerController.get_all()

            total_credit = sum(float(c.get("balance") or 0.0) for c in customers)
            self._stats_lbl.setText(
                f"  {len(customers)} client(s)   •   Crédit total dû : {format_price(total_credit)}"
            )

            is_admin = AuthController.is_admin()
            self._table.setUpdatesEnabled(False)
            self._table.clearContents()
            self._table.setRowCount(len(customers))

            for row, customer in enumerate(customers):
                self._table.setItem(row, 0, QTableWidgetItem(customer["name"]))
                self._table.setItem(row, 1, QTableWidgetItem(customer.get("phone") or "—"))

                balance = round(float(customer.get("balance") or 0.0), 3)
                balance_item = QTableWidgetItem(format_price(balance))
                balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if balance > 0:
                    balance_item.setForeground(QColor("#DC2626"))
                self._table.setItem(row, 2, balance_item)

                self._table.setItem(row, 3, QTableWidgetItem(_fmt_date(customer.get("created_at"))))

                actions = QWidget(self._table)
                actions.setStyleSheet("background: transparent;")
                act_lay = QHBoxLayout(actions)
                act_lay.setContentsMargins(8, 0, 8, 0)
                act_lay.setSpacing(8)

                btn_pay = QPushButton("Payer")
                btn_pay.setFixedSize(92, 32)
                btn_pay.setStyleSheet(
                    "font-size: 11px; font-weight: 800; color: white; background: #059669; "
                    "border: none; border-radius: 7px; padding: 0 10px;"
                )
                btn_pay.setEnabled(balance > 0)
                btn_pay.clicked.connect(
                    lambda _, cid=customer["id"], cn=customer["name"], cb=balance: self._record_payment(cid, cn, cb)
                )

                btn_history = QPushButton("Historique")
                btn_history.setFixedSize(98, 32)
                btn_history.setStyleSheet(
                    "font-size: 11px; font-weight: 800; color: #1D4ED8; background: #EFF6FF; "
                    "border: 1px solid #BFDBFE; border-radius: 7px; padding: 0 10px;"
                )
                btn_history.clicked.connect(lambda _, cid=customer["id"]: self._show_history(cid))

                btn_edit = QPushButton("Modifier")
                btn_edit.setFixedSize(96, 32)
                btn_edit.setVisible(is_admin)
                btn_edit.setStyleSheet(
                    "font-size: 11px; font-weight: 800; color: #1F2937; background: #E5E7EB; "
                    "border: 1px solid #CBD5E1; border-radius: 7px; padding: 0 10px;"
                )
                btn_edit.clicked.connect(lambda _, cid=customer["id"]: self._edit_customer(cid))

                act_lay.addWidget(btn_pay)
                act_lay.addWidget(btn_history)
                act_lay.addWidget(btn_edit)

                if is_admin:
                    btn_del = QPushButton("Supprimer")
                    btn_del.setFixedSize(102, 32)
                    btn_del.setStyleSheet(
                        "font-size: 11px; font-weight: 800; color: white; background: #DC2626; "
                        "border: none; border-radius: 7px; padding: 0 10px;"
                    )
                    btn_del.clicked.connect(
                        lambda _, cid=customer["id"], cn=customer["name"]: self._delete_customer(cid, cn)
                    )
                    act_lay.addWidget(btn_del)

                act_lay.addStretch()
                actions.setMinimumWidth(430 if is_admin else 300)
                self._table.setCellWidget(row, 4, actions)
                self._table.setRowHeight(row, 52)

            self._table.setUpdatesEnabled(True)
            self._table.viewport().update()
            self._loaded_once = True
        finally:
            self._is_refreshing = False

    def _add_customer(self):
        dlg = CustomerDialog(parent=self)
        if dlg.exec():
            CustomerController.create(dlg.get_data())
            self.refresh()

    def _edit_customer(self, customer_id: int):
        customer = CustomerController.get_by_id(customer_id)
        if not customer:
            return
        dlg = CustomerDialog(data=customer, parent=self)
        if dlg.exec():
            CustomerController.update(customer_id, dlg.get_data())
            self.refresh()

    def _delete_customer(self, customer_id: int, name: str):
        reply = light_question(self, "Supprimer client", f"Supprimer le client « {name} » ?")
        if reply == QMessageBox.Yes:
            CustomerController.delete(customer_id)
            self.refresh()

    def _record_payment(self, customer_id: int, name: str, current_balance: float):
        dlg = PaymentDialog(name, current_balance, self)
        if dlg.exec():
            amount = dlg.get_amount()
            if amount > 0:
                try:
                    new_balance = CustomerController.record_payment(customer_id, amount)
                except Exception as exc:
                    light_critical(self, "Erreur", str(exc))
                    return
                self.refresh()
                light_information(
                    self,
                    "Paiement enregistré",
                    f"Paiement de {format_price(amount)} enregistré pour {name}.\n"
                    f"Nouveau solde : {format_price(new_balance)}",
                )

    def _show_history(self, customer_id: int):
        try:
            history = CustomerController.get_history(customer_id)
        except Exception as exc:
            light_critical(self, "Erreur", str(exc))
            return
        dlg = CustomerHistoryDialog(history, self)
        dlg.exec()


class CustomerDialog(QDialog):
    def __init__(self, data: dict = None, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Nouveau client" if not data else "Modifier client")
        self.setFixedWidth(380)
        self.setObjectName("CustomerDialog")
        self.setStyleSheet(self.styleSheet() + " QDialog#CustomerDialog { background: #FFFFFF; }")
        self._data = data or {}
        self._build_ui()

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background: transparent; border: none; padding: 0; margin: 0;"
            "color: #6B7280; font-size: 11px; font-weight: 600;"
        )
        return lbl

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        surface = QFrame()
        surface.setObjectName("customerDialogSurface")
        surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        surface.setStyleSheet("QFrame#customerDialogSurface { background: #FFFFFF; border: none; }")
        outer.addWidget(surface)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("Nouveau client" if not self._data else "Modifier client")
        title.setStyleSheet("font-size: 17px; font-weight: 700; padding: 20px 24px 12px; color: #111827;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(24, 12, 24, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._name = QLineEdit(self._data.get("name", ""))
        self._name.setMinimumHeight(38)
        self._name.setPlaceholderText("Nom complet")

        self._phone = QLineEdit(self._data.get("phone", ""))
        self._phone.setMinimumHeight(38)
        self._phone.setPlaceholderText("+216 XX XXX XXX")

        self._notes = QLineEdit(self._data.get("notes", ""))
        self._notes.setMinimumHeight(38)
        self._notes.setPlaceholderText("Notes (optionnel)")

        form.addRow(self._lbl("Nom *:"), self._name)
        form.addRow(self._lbl("Téléphone:"), self._phone)
        form.addRow(self._lbl("Notes:"), self._notes)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 8, 24, 20)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Enregistrer")
        btn_ok.clicked.connect(self._validate)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _validate(self):
        if not self._name.text().strip():
            light_warning(self, "Champ requis", "Le nom du client est obligatoire.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "phone": self._phone.text().strip(),
            "address": "",
            "notes": self._notes.text().strip(),
        }


class PaymentDialog(QDialog):
    def __init__(self, customer_name: str, balance: float, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle("Encaisser un règlement")
        self.setFixedWidth(360)
        self._build_ui(customer_name, balance)

    def _build_ui(self, name: str, balance: float):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        lbl_name = QLabel(f"Client : <b>{name}</b>")
        lbl_name.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl_name)

        lbl_bal = QLabel(f"Solde dû : <b style='color:#DC2626'>{format_price(balance)}</b>")
        lbl_bal.setStyleSheet("font-size: 13px;")
        layout.addWidget(lbl_bal)

        form = QFormLayout()
        self._amount = PriceSpinBox()
        self._amount.setMinimumHeight(44)
        self._amount.setMaximum(balance)
        self._amount.setValue(balance)
        self._amount.setDecimals(3)
        configure_manual_spinbox(self._amount, decimals=3, placeholder="0.000")
        form.addRow("Montant reçu :", self._amount)
        layout.addLayout(form)

        btn_row = QHBoxLayout()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Valider")
        btn_ok.clicked.connect(self._validate)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _validate(self):
        amount = round(float(self._amount.value()), 3)
        if amount <= 0:
            light_warning(self, "Montant invalide", "Le montant reçu doit être supérieur à 0.")
            return
        self.accept()

    def get_amount(self) -> float:
        return round(float(self._amount.value()), 3)



class CustomerInvoiceDetailDialog(QDialog):
    def __init__(self, sale: dict, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self._sale = sale
        self.setWindowTitle(f"Facture #{sale['id']}")
        self.resize(860, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("CustomerInvoiceDetailDialog")
        self.setStyleSheet(
            self.styleSheet()
            + " QDialog#CustomerInvoiceDetailDialog { background: #FFFFFF; }"
        )
        self._build_ui()

    def _build_ui(self):
        sale = self._sale

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        surface = QFrame()
        surface.setObjectName("customerInvoiceDetailSurface")
        surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        surface.setStyleSheet("QFrame#customerInvoiceDetailSurface { background: #FFFFFF; border: none; }")
        outer.addWidget(surface)

        root = QVBoxLayout(surface)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"Facture #{sale['id']}")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #111827;")
        root.addWidget(title)

        info = QLabel(
            f"Date : {_fmt_datetime(sale.get('created_at'))}   •   "
            f"Mode : {sale.get('payment_method') or '—'}   •   "
            f"Statut : {sale.get('payment_status') or '—'}   •   "
            f"Payée le : {_fmt_datetime(sale.get('paid_at')) if sale.get('paid_at') else '—'}"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 12px; color: #4B5563;")
        root.addWidget(info)

        if sale.get("notes"):
            notes = QLabel(f"Note : {sale.get('notes')}")
            notes.setWordWrap(True)
            notes.setStyleSheet("font-size: 12px; color: #6B7280;")
            root.addWidget(notes)

        items_title = QLabel("Produits de la facture")
        items_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #111827;")
        root.addWidget(items_title)

        self._items_table = QTableWidget(0, 5)
        self._items_table.setHorizontalHeaderLabels(["Produit", "Unité", "Qté", "Prix unit.", "Total"])
        self._items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._items_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._items_table.setAlternatingRowColors(True)
        self._items_table.verticalHeader().setVisible(False)
        root.addWidget(self._items_table, 1)

        totals = QLabel(
            f"Sous-total : {format_price(sale.get('subtotal') or sale.get('total') or 0)}   •   "
            f"Total : {format_price(sale.get('total') or 0)}   •   "
            f"Payé : {format_price(sale.get('credit_paid') if str(sale.get('payment_method') or '').lower() == 'credit' else sale.get('amount_paid') or sale.get('total') or 0)}   •   "
            f"Reste : {format_price(sale.get('remaining_due') or 0)}"
        )
        totals.setWordWrap(True)
        totals.setStyleSheet(
            "background: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 10px; "
            "padding: 10px 12px; color: #0F172A; font-size: 12px; font-weight: 700;"
        )
        root.addWidget(totals)

        payments = sale.get("payments") or []
        if payments:
            pay_title = QLabel("Règlements liés")
            pay_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #111827;")
            root.addWidget(pay_title)

            pay_table = QTableWidget(0, 3)
            pay_table.setHorizontalHeaderLabels(["Date", "Montant", "Type"])
            pay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            pay_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            pay_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            pay_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            pay_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            pay_table.setAlternatingRowColors(True)
            pay_table.verticalHeader().setVisible(False)
            pay_table.setRowCount(len(payments))
            for row, payment in enumerate(payments):
                payment_date = payment.get("customer_payment_date") or payment.get("created_at")
                pay_table.setItem(row, 0, QTableWidgetItem(_fmt_datetime(payment_date)))
                amount_item = QTableWidgetItem(format_price(payment.get("amount") or 0))
                amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                pay_table.setItem(row, 1, amount_item)
                pay_table.setItem(row, 2, QTableWidgetItem(str(payment.get("payment_method") or "—")))
            pay_table.resizeRowsToContents()
            root.addWidget(pay_table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self._fill_items()

    def _fill_items(self):
        items = self._sale.get("items") or []
        self._items_table.setRowCount(len(items))
        for row, item in enumerate(items):
            unit_name = item.get("sale_unit_name") or item.get("unit_type") or "—"
            self._items_table.setItem(row, 0, QTableWidgetItem(str(item.get("product_name") or "—")))
            self._items_table.setItem(row, 1, QTableWidgetItem(str(unit_name)))
            qty_item = QTableWidgetItem(str(item.get("quantity") or 0))
            price_item = QTableWidgetItem(format_price(item.get("unit_price") or 0))
            total_item = QTableWidgetItem(format_price(item.get("total") or 0))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._items_table.setItem(row, 2, qty_item)
            self._items_table.setItem(row, 3, price_item)
            self._items_table.setItem(row, 4, total_item)
        self._items_table.resizeRowsToContents()


class CustomerHistoryDialog(QDialog):
    def __init__(self, history: dict, parent=None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self.setWindowTitle("Historique client")
        self.resize(980, 720)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("CustomerHistoryDialog")
        self.setStyleSheet(
            self.styleSheet()
            + " QDialog#CustomerHistoryDialog { background: #FFFFFF; }"
        )
        self._history = history
        self._build_ui()

    def _build_ui(self):
        customer = self._history["customer"]
        summary = self._history["summary"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        surface = QFrame()
        surface.setObjectName("customerHistorySurface")
        surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        surface.setStyleSheet("QFrame#customerHistorySurface { background: #FFFFFF; border: none; }")
        outer.addWidget(surface)

        root = QVBoxLayout(surface)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"Historique — {customer['name']}")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #111827;")
        root.addWidget(title)

        info = QLabel(
            f"Téléphone : {customer.get('phone') or '—'}   •   "
            f"Solde actuel : {format_price(customer.get('balance') or 0)}   •   "
            f"Créé le : {_fmt_date(customer.get('created_at'))}"
        )
        info.setStyleSheet("font-size: 12px; color: #4B5563;")
        root.addWidget(info)

        stats = QLabel(
            f"Factures : {summary['sales_count']}   •   "
            f"Crédit total : {format_price(summary['total_credit_sales'])}   •   "
            f"Règlements : {format_price(summary['total_paid'])}   •   "
            f"Reste dû : {format_price(summary['remaining_due'])}"
        )
        stats.setStyleSheet(
            "background: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 10px; "
            "padding: 10px 12px; color: #0F172A; font-size: 12px; font-weight: 700;"
        )
        root.addWidget(stats)

        sales_lbl = QLabel("Factures du client")
        sales_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #111827;")
        root.addWidget(sales_lbl)

        self._sales_table = QTableWidget(0, 7)
        self._sales_table.setHorizontalHeaderLabels(
            ["Facture", "Date", "Mode", "Statut", "Total", "Payé", "Reste"]
        )
        self._sales_table.cellClicked.connect(self._open_invoice_from_cell)
        self._sales_table.cellDoubleClicked.connect(self._open_invoice_from_cell)
        self._sales_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._sales_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._sales_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._sales_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._sales_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._sales_table.setAlternatingRowColors(True)
        self._sales_table.verticalHeader().setVisible(False)
        root.addWidget(self._sales_table, 3)

        pay_lbl = QLabel("Historique des règlements")
        pay_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #111827;")
        root.addWidget(pay_lbl)

        self._payments_table = QTableWidget(0, 4)
        self._payments_table.setHorizontalHeaderLabels(["Date", "Montant", "Factures réglées", "Notes"])
        self._payments_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._payments_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._payments_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._payments_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._payments_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._payments_table.setAlternatingRowColors(True)
        self._payments_table.verticalHeader().setVisible(False)
        root.addWidget(self._payments_table, 2)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self._fill_sales()
        self._fill_payments()

    def _fill_sales(self):
        sales = self._history.get("sales", [])
        self._sales_table.setRowCount(len(sales))
        for row, sale in enumerate(sales):
            invoice_item = QTableWidgetItem(f"#{sale['id']}")
            invoice_item.setForeground(QColor("#1D4ED8"))
            invoice_item.setToolTip("Cliquer pour voir le détail de la facture")
            self._sales_table.setItem(row, 0, invoice_item)
            self._sales_table.setItem(row, 1, QTableWidgetItem(_fmt_datetime(sale.get("created_at"))))
            self._sales_table.setItem(row, 2, QTableWidgetItem(str(sale.get("payment_method") or "—")))
            self._sales_table.setItem(row, 3, QTableWidgetItem(str(sale.get("payment_status") or "—")))

            total_item = QTableWidgetItem(format_price(sale.get("total") or 0))
            paid_item = QTableWidgetItem(format_price(sale.get("credit_paid") or 0))
            due_value = float(sale.get("remaining_due") or 0.0)
            due_item = QTableWidgetItem(format_price(due_value))

            for item in (total_item, paid_item, due_item):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            if due_value > 0:
                due_item.setForeground(QColor("#DC2626"))
            else:
                due_item.setForeground(QColor("#059669"))

            self._sales_table.setItem(row, 4, total_item)
            self._sales_table.setItem(row, 5, paid_item)
            self._sales_table.setItem(row, 6, due_item)

        self._sales_table.resizeRowsToContents()

    def _open_invoice_from_cell(self, row: int, _column: int):
        sales = self._history.get("sales", [])
        if row < 0 or row >= len(sales):
            return
        sale_id = sales[row].get("id")
        try:
            sale = CustomerController.get_sale_details(int(self._history["customer"]["id"]), int(sale_id))
        except Exception as exc:
            light_critical(self, "Erreur", str(exc))
            return
        CustomerInvoiceDetailDialog(sale, self).exec()

    def _fill_payments(self):
        payments = self._history.get("payments", [])
        self._payments_table.setRowCount(len(payments))
        for row, payment in enumerate(payments):
            allocations = payment.get("allocations") or []
            allocation_text = ", ".join(
                f"#{alloc['sale_id']} ({format_price(alloc.get('amount') or 0)})"
                for alloc in allocations
            ) or "—"

            self._payments_table.setItem(row, 0, QTableWidgetItem(_fmt_datetime(payment.get("created_at"))))

            amount_item = QTableWidgetItem(format_price(payment.get("amount") or 0))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._payments_table.setItem(row, 1, amount_item)
            self._payments_table.setItem(row, 2, QTableWidgetItem(allocation_text))
            self._payments_table.setItem(row, 3, QTableWidgetItem(str(payment.get("notes") or "—")))

        self._payments_table.resizeRowsToContents()
