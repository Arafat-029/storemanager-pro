from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QFormLayout, QLineEdit, QComboBox, QLabel, QMessageBox,
    QTabWidget,
)
from PySide6.QtCore import Qt

from app.views.widgets.data_table import DataTable
from app.controllers.user_controller import UserController
from app.controllers.auth_controller import AuthController
from app.controllers.cash_session_controller import CashSessionController
from app.utils import action_labels
from app.utils.helpers import format_datetime, format_price
from app.views.dialog_theme import apply_light_dialog_theme


class UsersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Users tab
        users_widget = QWidget()
        users_layout = QVBoxLayout(users_widget)
        users_layout.setContentsMargins(0, 16, 0, 0)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("＋  Nouvel utilisateur")
        btn_add.clicked.connect(self._add)
        toolbar.addStretch()
        toolbar.addWidget(btn_add)
        users_layout.addLayout(toolbar)

        self._table = DataTable(["ID", "Identifiant", "Nom complet", "Rôle", "Email", "Statut", "Créé le"])
        self._table.itemDoubleClicked.connect(self._edit)
        users_layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_edit = QPushButton("Modifier")
        btn_edit.setObjectName("btnSecondary")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("Désactiver")
        btn_del.setObjectName("btnDanger")
        btn_del.clicked.connect(self._delete)
        btn_row.addStretch()
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        users_layout.addLayout(btn_row)
        tabs.addTab(users_widget, "Utilisateurs")

        # Logs tab
        logs_widget = QWidget()
        logs_layout = QVBoxLayout(logs_widget)
        logs_layout.setContentsMargins(0, 16, 0, 0)

        logs_help = QLabel(
            "Qui a fait quoi, et quand. Utile pour retrouver l'origine d'une "
            "vente annulée, d'une perte de stock ou d'un écart de caisse."
        )
        logs_help.setWordWrap(True)
        logs_help.setStyleSheet("color: #6B7280; font-size: 12px;")
        logs_layout.addWidget(logs_help)

        logs_toolbar = QHBoxLayout()
        logs_toolbar.setSpacing(10)
        logs_toolbar.addWidget(QLabel("Afficher :"))
        self._log_filter = QComboBox()
        self._log_filter.setMinimumHeight(38)
        self._log_filter.setMinimumWidth(200)
        self._log_filter.addItem("Tout", None)
        self._log_filter.addItem("Seulement les actions sensibles", "__sensibles__")
        for domaine in action_labels.DOMAINES:
            self._log_filter.addItem(domaine, domaine)
        self._log_filter.currentIndexChanged.connect(self._load_logs)
        logs_toolbar.addWidget(self._log_filter)
        logs_toolbar.addStretch()
        btn_refresh_logs = QPushButton("Actualiser")
        btn_refresh_logs.setObjectName("btnSecondary")
        btn_refresh_logs.setMinimumHeight(38)
        btn_refresh_logs.clicked.connect(self._load_logs)
        logs_toolbar.addWidget(btn_refresh_logs)
        logs_layout.addLayout(logs_toolbar)

        self._log_table = DataTable(["Date", "Utilisateur", "Action", "Détails"])
        logs_layout.addWidget(self._log_table, 1)
        tabs.addTab(logs_widget, "Journal des actions")

        # ── Clôtures de caisse ────────────────────────────────────────────
        cash_widget = QWidget()
        cash_layout = QVBoxLayout(cash_widget)
        cash_layout.setContentsMargins(0, 16, 0, 0)
        cash_layout.setSpacing(12)

        cash_toolbar = QHBoxLayout()
        self._cash_summary = QLabel("Chargement…")
        self._cash_summary.setWordWrap(True)
        self._cash_summary.setStyleSheet(
            "background: #F8FAFC; border: 1.5px solid #E2E8F0; border-radius: 10px;"
            "padding: 10px 14px; font-size: 13px; color: #334155;"
        )
        btn_refresh_cash = QPushButton("Actualiser")
        btn_refresh_cash.setObjectName("btnSecondary")
        btn_refresh_cash.clicked.connect(self._load_cash_sessions)
        cash_toolbar.addWidget(self._cash_summary, 1)
        cash_toolbar.addWidget(btn_refresh_cash, 0, Qt.AlignTop)
        cash_layout.addLayout(cash_toolbar)

        self._cash_table = DataTable(
            ["Ouverture", "Caissier", "Fond", "Encaissé", "Attendu", "Compté", "Écart", "État", "Remarque"]
        )
        cash_layout.addWidget(self._cash_table, 1)
        tabs.addTab(cash_widget, "Clôtures de caisse")

        def _on_tab(index: int) -> None:
            if index == 1:
                self._load_logs()
            elif index == 2:
                self._load_cash_sessions()

        tabs.currentChanged.connect(_on_tab)

    def refresh(self):
        users = UserController.get_all()
        role_labels = {"admin": "Administrateur", "cashier": "Caissier"}
        display = []
        for u in users:
            d = dict(u)
            d["role"] = role_labels.get(u["role"], u["role"])
            d["is_active"] = "Actif" if u["is_active"] else "Inactif"
            d["created_at"] = format_datetime(u["created_at"])
            display.append(d)
        self._table.set_data(display, ["id", "username", "full_name", "role", "email", "is_active", "created_at"])

    def _load_logs(self):
        """Journal traduit en français, filtrable par domaine.

        Les codes techniques (SALE_CANCEL…) restent stockés tels quels — ils
        sont stables et filtrables — mais ne sont jamais montrés : la
        traduction se fait ici, ce qui vaut aussi pour l'historique déjà
        enregistré.
        """
        choix = self._log_filter.currentData()
        logs = UserController.get_logs(limit=400)

        display = []
        for l in logs:
            action = l.get("action") or ""
            if choix == "__sensibles__" and not action_labels.is_sensitive(action):
                continue
            if choix not in (None, "__sensibles__") and action_labels.domain_for(action) != choix:
                continue
            display.append({
                **l,
                "created_at": format_datetime(l["created_at"]),
                "action": action_labels.label_for(action),
                "details": action_labels.humanize_details(l.get("details")),
            })

        self._log_table.set_data(display[:200], ["created_at", "full_name", "action", "details"])

    def _load_cash_sessions(self):
        sessions = CashSessionController.get_sessions()
        display = []
        for s in sessions:
            ouverte = str(s.get("status")) != "closed"
            ecart = s.get("difference")
            if ouverte:
                etat = "En cours"
                ecart_txt = "—"
            elif ecart is None:
                etat = "Clôturée"
                ecart_txt = "—"
            else:
                ecart = round(float(ecart), 3)
                if abs(ecart) < 0.0005:
                    etat, ecart_txt = "Juste", "—"
                elif ecart < 0:
                    etat, ecart_txt = "Manquant", f"-{format_price(abs(ecart))}"
                else:
                    etat, ecart_txt = "Excédent", f"+{format_price(ecart)}"

            display.append({
                **s,
                "opened_at": format_datetime(s.get("opened_at")),
                "user_name": s.get("user_name") or s.get("username") or "",
                "opening_cash": format_price(s.get("opening_cash") or 0),
                "total_received": format_price(s.get("total_received") or 0) if not ouverte else "—",
                "expected_cash": format_price(s.get("expected_cash") or 0) if not ouverte else "—",
                "counted_cash": format_price(s.get("counted_cash") or 0) if not ouverte else "—",
                "_ecart": ecart_txt,
                "_etat": etat,
                "notes": s.get("notes") or "",
            })

        self._cash_table.set_data(display, [
            "opened_at", "user_name", "opening_cash", "total_received",
            "expected_cash", "counted_cash", "_ecart", "_etat", "notes",
        ])

        t = CashSessionController.get_totals()
        if t["sessions"] == 0:
            self._cash_summary.setText("Aucune clôture de caisse enregistrée pour le moment.")
            return
        ecart_total = t["ecart_total"]
        if abs(ecart_total) < 0.0005:
            bilan = "aucun écart cumulé"
        elif ecart_total < 0:
            bilan = f"manquant cumulé de {format_price(abs(ecart_total))}"
        else:
            bilan = f"excédent cumulé de {format_price(ecart_total)}"
        self._cash_summary.setText(
            f"{t['sessions']} clôture(s)  •  encaissé {format_price(t['encaisse_total'])}  •  "
            f"{t['manquants']} manquant(s), {t['excedents']} excédent(s)  •  {bilan}"
        )

    def _add(self):
        dlg = UserDialog(self)
        if dlg.exec():
            self.refresh()

    def _edit(self):
        data = self._table.selected_row_data()
        if not data:
            return
        user = UserController.get_by_id(data["id"])
        dlg = UserDialog(self, user)
        if dlg.exec():
            self.refresh()

    def _delete(self):
        data = self._table.selected_row_data()
        if not data:
            return
        try:
            reply = QMessageBox.question(self, "Désactiver", f"Désactiver «{data['username']}» ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                UserController.delete(data["id"])
                self.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "Impossible", str(e))


class UserDialog(QDialog):
    def __init__(self, parent=None, user: dict = None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self._user = user
        self.setWindowTitle("Modifier l'utilisateur" if user else "Nouvel utilisateur")
        self.setFixedWidth(400)
        self._build_ui()
        if user:
            self._username.setText(user.get("username", ""))
            self._username.setReadOnly(True)
            self._full_name.setText(user.get("full_name", ""))
            self._email.setText(user.get("email") or "")
            idx = self._role.findData(user.get("role", "admin"))
            if idx >= 0:
                self._role.setCurrentIndex(idx)
            self._password.setPlaceholderText("Laisser vide pour ne pas changer")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        self._username = QLineEdit()
        self._username.setMinimumHeight(42)
        self._full_name = QLineEdit()
        self._full_name.setMinimumHeight(42)
        self._email = QLineEdit()
        self._email.setMinimumHeight(42)
        self._role = QComboBox()
        self._role.setMinimumHeight(42)
        self._role.addItem("Administrateur", "admin")
        self._role.addItem("Caissier", "cashier")
        self._role.view().setMinimumWidth(180)
        self._role.setMaxVisibleItems(6)
        self._role.setCurrentIndex(0)
        self._password = QLineEdit()
        self._password.setMinimumHeight(42)
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("Au moins 6 caractères")

        form.addRow("Identifiant *:", self._username)
        form.addRow("Nom complet *:", self._full_name)
        form.addRow("Email:", self._email)
        form.addRow("Rôle:", self._role)
        form.addRow("Mot de passe:", self._password)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _save(self):
        username = self._username.text().strip()
        full_name = self._full_name.text().strip()
        password = self._password.text()

        if not username or not full_name:
            QMessageBox.warning(self, "Erreur", "Identifiant et nom sont obligatoires.")
            return
        if not self._user and not password:
            QMessageBox.warning(self, "Erreur", "Le mot de passe est obligatoire pour un nouvel utilisateur.")
            return
        # Empty on an edit means "keep the current password"; anything the
        # user does type has to clear the minimum length.
        if password and len(password) < 6:
            QMessageBox.warning(self, "Erreur", "Le mot de passe doit contenir au moins 6 caractères.")
            return

        data = {
            "username": username,
            "full_name": full_name,
            "email": self._email.text().strip() or None,
            "role": self._role.currentData(),
            "password": password or None,
            "is_active": 1,
        }
        try:
            if self._user:
                UserController.update(self._user["id"], data)
            else:
                UserController.create(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
