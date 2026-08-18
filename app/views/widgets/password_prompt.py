"""Redemande le mot de passe de l'utilisateur connecte.

Sert a proteger les ecrans sensibles (Parametres, qui donne acces aux
sauvegardes et donc a toutes les donnees du magasin) quand la session reste
ouverte sur un poste sans surveillance : etre connecte ne suffit plus, il
faut prouver que c'est bien la bonne personne devant l'ecran.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.controllers.auth_controller import AuthController

_QSS = """
QDialog { background: #FFFFFF; }
QLabel { background: transparent; border: none; }
QLabel#pwTitle  { font-size: 16px; font-weight: 700; color: #0F172A; }
QLabel#pwReason { font-size: 12px; color: #64748B; }
QLabel#pwError  { font-size: 12px; font-weight: 700; color: #DC2626; }
QLineEdit {
    background: #F8FAFC; border: 1.5px solid #CBD5E1; border-radius: 10px;
    padding: 12px 14px; font-size: 15px; color: #0F172A;
}
QLineEdit:focus { border-color: #2563EB; background: #FFFFFF; }
QPushButton#pwOk {
    background: #2563EB; border: none; border-radius: 10px;
    color: #FFFFFF; font-size: 15px; font-weight: 700;
}
QPushButton#pwOk:hover { background: #1D4ED8; }
QPushButton#pwCancel {
    background: transparent; border: 1.5px solid #CBD5E1; border-radius: 10px;
    color: #64748B; font-size: 14px; font-weight: 700;
}
QPushButton#pwCancel:hover { border-color: #DC2626; color: #DC2626; }
"""

# Au-dela, on arrete d'accepter des essais pour cette ouverture : sans limite,
# la boite devient un outil pour deviner le mot de passe a l'infini.
_MAX_ATTEMPTS = 3


class PasswordPromptDialog(QDialog):
    def __init__(self, reason: str, parent=None):
        super().__init__(parent)
        self._attempts = 0
        self._granted = False

        self.setWindowTitle("Vérification du mot de passe")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setStyleSheet(_QSS)

        user = AuthController.current_user() or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("Accès protégé")
        title.setObjectName("pwTitle")
        layout.addWidget(title)

        info = QLabel(f"{reason}\n\nSaisissez le mot de passe de « {user.get('username', '')} ».")
        info.setObjectName("pwReason")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("Mot de passe")
        self._password.setMinimumHeight(46)
        self._password.returnPressed.connect(self._check)
        layout.addWidget(self._password)

        self._error = QLabel("")
        self._error.setObjectName("pwError")
        self._error.setWordWrap(True)
        self._error.setMinimumHeight(16)
        layout.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        cancel = QPushButton("Annuler")
        cancel.setObjectName("pwCancel")
        cancel.setMinimumHeight(46)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self._btn_ok = QPushButton("Valider")
        self._btn_ok.setObjectName("pwOk")
        self._btn_ok.setMinimumHeight(46)
        self._btn_ok.setCursor(Qt.PointingHandCursor)
        self._btn_ok.clicked.connect(self._check)
        buttons.addWidget(cancel, 1)
        buttons.addWidget(self._btn_ok, 1)
        layout.addLayout(buttons)

        self._password.setFocus()

    def _check(self) -> None:
        password = self._password.text()
        if not password:
            self._error.setText("Saisissez votre mot de passe.")
            return

        user = AuthController.current_user() or {}
        username = str(user.get("username") or "")
        # Revalide contre la base plutot que contre l'objet en memoire : un
        # mot de passe change entre-temps doit compter immediatement.
        if AuthController.verify_password(username, password):
            self._granted = True
            self.accept()
            return

        self._attempts += 1
        remaining = _MAX_ATTEMPTS - self._attempts
        AuthController.log("ACCESS_DENIED", f"Mot de passe incorrect ({username}) — accès protégé")
        self._password.clear()
        self._password.setFocus()

        if remaining <= 0:
            self._error.setText("Trop de tentatives. Accès refusé.")
            self._btn_ok.setEnabled(False)
            self._password.setEnabled(False)
            return
        self._error.setText(
            f"Mot de passe incorrect. {remaining} tentative(s) restante(s)."
        )

    def granted(self) -> bool:
        return self._granted


def require_password(parent, reason: str) -> bool:
    """Demande le mot de passe. Renvoie True seulement s'il est correct."""
    dialog = PasswordPromptDialog(reason, parent)
    return dialog.exec() == QDialog.Accepted and dialog.granted()
