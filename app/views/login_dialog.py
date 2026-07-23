from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QApplication,
)
from PySide6.QtCore import Qt
from app.controllers.auth_controller import AuthController


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connexion — StoreManager Pro")
        self.setFixedSize(440, 560)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header gradient ──────────────────────────────────
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1B2A4A, stop:1 #2C5282); }"
        )
        header.setFixedHeight(180)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 12)
        h_layout.setAlignment(Qt.AlignCenter)
        h_layout.setSpacing(6)

        # Close button top-right
        close_row = QHBoxLayout()
        close_row.setContentsMargins(0, 0, 0, 0)
        close_row.addStretch()
        btn_close_x = QPushButton("✕")
        btn_close_x.setFixedSize(28, 28)
        btn_close_x.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.2); color: white;"
            "border: none; border-radius: 14px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.4); }"
        )
        btn_close_x.clicked.connect(QApplication.quit)
        close_row.addWidget(btn_close_x)
        h_layout.addLayout(close_row)

        icon = QLabel("🏪")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")

        title = QLabel("StoreManager Pro")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: white;"
            "background: transparent; border: none; letter-spacing: 1px;"
        )

        subtitle_hdr = QLabel("Système de gestion de magasin")
        subtitle_hdr.setAlignment(Qt.AlignCenter)
        subtitle_hdr.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.75);"
            "background: transparent; border: none;"
        )

        h_layout.addWidget(icon)
        h_layout.addWidget(title)
        h_layout.addWidget(subtitle_hdr)
        layout.addWidget(header)

        # ── Form area ─────────────────────────────────────────
        form = QFrame()
        form.setStyleSheet(
            "QFrame { background: #FFFFFF; }"
            "QLabel { background: transparent; border: none; }"
        )
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(40, 32, 40, 32)
        form_layout.setSpacing(12)

        lbl_user = QLabel("Nom d'utilisateur")
        lbl_user.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600; background: transparent;")

        self._username = QLineEdit()
        self._username.setPlaceholderText("Entrez votre identifiant")
        self._username.setMinimumHeight(46)
        self._username.setText("admin")
        self._username.setStyleSheet(
            "background: #F9FAFB; border: 1.5px solid #D1D5DB; border-radius: 8px;"
            "padding: 10px 14px; color: #111827; font-size: 14px;"
        )

        lbl_pass = QLabel("Mot de passe")
        lbl_pass.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600; background: transparent;")

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("Entrez votre mot de passe")
        self._password.setMinimumHeight(46)
        self._password.setText("admin")
        self._password.setStyleSheet(
            "background: #F9FAFB; border: 1.5px solid #D1D5DB; border-radius: 8px;"
            "padding: 10px 14px; color: #111827; font-size: 14px;"
        )
        self._password.returnPressed.connect(self._do_login)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            "color: #EF4444; font-size: 12px; background: transparent; border: none;"
        )
        self._error_label.setAlignment(Qt.AlignCenter)

        btn = QPushButton("🔐   Se connecter")
        btn.setMinimumHeight(50)
        btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #1B2A4A, stop:1 #0F1D36);"
            "  color: white; border: none; border-radius: 10px;"
            "  font-size: 15px; font-weight: 700; letter-spacing: 0.5px;"
            "}"
            "QPushButton:hover { background: #2196F3; }"
            "QPushButton:pressed { background: #065F46; }"
        )
        btn.clicked.connect(self._do_login)

        hint = QLabel("Identifiants par défaut : admin / admin  •  001 / 001")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            "color: #9CA3AF; font-size: 11px; background: transparent; border: none;"
        )

        form_layout.addWidget(lbl_user)
        form_layout.addWidget(self._username)
        form_layout.addSpacing(4)
        form_layout.addWidget(lbl_pass)
        form_layout.addWidget(self._password)
        form_layout.addWidget(self._error_label)
        form_layout.addSpacing(8)
        form_layout.addWidget(btn)
        form_layout.addStretch()
        form_layout.addWidget(hint)

        layout.addWidget(form)

    def _do_login(self):
        username = self._username.text().strip()
        password = self._password.text()
        if not username or not password:
            self._error_label.setText("Veuillez remplir tous les champs.")
            return
        user = AuthController.login(username, password)
        if user:
            self.accept()
        else:
            self._error_label.setText("Identifiants incorrects. Réessayez.")
            self._password.clear()
            self._password.setFocus()
