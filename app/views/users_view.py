from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QFormLayout, QLineEdit, QComboBox, QLabel, QMessageBox,
    QTabWidget,
)
from app.views.widgets.data_table import DataTable
from app.controllers.user_controller import UserController
from app.controllers.auth_controller import AuthController
from app.utils.helpers import format_datetime
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

        btn_refresh_logs = QPushButton("Actualiser")
        btn_refresh_logs.setObjectName("btnSecondary")
        btn_refresh_logs.clicked.connect(self._load_logs)
        logs_layout.addWidget(btn_refresh_logs, 0, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignRight)

        self._log_table = DataTable(["Date", "Utilisateur", "Action", "Détails"])
        logs_layout.addWidget(self._log_table, 1)
        tabs.addTab(logs_widget, "Journal des actions")
        tabs.currentChanged.connect(lambda i: self._load_logs() if i == 1 else None)

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
        logs = UserController.get_logs(limit=200)
        display = []
        for l in logs:
            d = dict(l)
            d["created_at"] = format_datetime(l["created_at"])
            display.append(d)
        self._log_table.set_data(display, ["created_at", "full_name", "action", "details"])

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
