from __future__ import annotations

import bcrypt

from app.database.connection import db


class AuthController:
    _current_user: dict | None = None

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @classmethod
    def _is_authenticated(cls, user: dict, password: str) -> bool:
        """Vérifie le mot de passe. Seul bcrypt fait foi.

        Une version précédente comparait le mot de passe EN CLAIR quand
        l'empreinte stockée n'était pas un bcrypt valide, puis la convertissait
        au passage. C'était un reliquat de migration : n'importe quelle valeur
        écrite directement en base devenait un mot de passe utilisable, et
        stocker un mot de passe en clair cessait d'être détectable. Désormais
        une empreinte illisible refuse la connexion — l'administrateur doit
        réinitialiser le mot de passe depuis la gestion des utilisateurs.
        """
        stored_password = (user.get("password") or "").strip()
        if not stored_password:
            return False

        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    @classmethod
    def login(cls, username: str, password: str) -> dict | None:
        user = db.fetchone(
            "SELECT * FROM users WHERE username=? AND is_active=1",
            (username.strip(),),
        )
        if not user:
            return None
        if cls._is_authenticated(user, password):
            cls._current_user = user
            cls._log_action("LOGIN", "Connexion réussie")
            return user
        return None

    @classmethod
    def verify_password(cls, username: str, password: str) -> bool:
        """Contrôle un mot de passe SANS ouvrir de session ni journaliser
        une connexion.

        Utilisé pour reconfirmer l'identité devant un écran sensible : la
        session en cours ne doit pas être modifiée, et l'événement n'est pas
        une « connexion ». L'empreinte est relue en base pour qu'un mot de
        passe changé depuis le début de session compte immédiatement.
        """
        if not username:
            return False
        user = db.fetchone(
            "SELECT id, password FROM users WHERE username=? AND is_active=1",
            (username.strip(),),
        )
        if not user:
            return False
        return cls._is_authenticated(user, password)

    @classmethod
    def logout(cls):
        if cls._current_user:
            cls._log_action("LOGOUT", "Déconnexion")
        cls._current_user = None

    @classmethod
    def current_user(cls) -> dict | None:
        return cls._current_user

    @classmethod
    def is_admin(cls) -> bool:
        return cls._current_user is not None and cls._current_user["role"] == "admin"

    @classmethod
    def _log_action(cls, action: str, details: str = ""):
        if cls._current_user:
            db.execute(
                "INSERT INTO user_logs (user_id, action, details) VALUES (?,?,?)",
                (cls._current_user["id"], action, details),
            )

    @classmethod
    def log(cls, action: str, details: str = ""):
        cls._log_action(action, details)
