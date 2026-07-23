from __future__ import annotations
import bcrypt
from app.database.connection import db
from app.controllers.auth_controller import AuthController


class UserController:

    @staticmethod
    def get_all() -> list[dict]:
        return db.fetchall("SELECT id, username, full_name, role, email, is_active, created_at FROM users ORDER BY full_name")

    @staticmethod
    def get_by_id(user_id: int) -> dict | None:
        return db.fetchone(
            "SELECT id, username, full_name, role, email, is_active, created_at FROM users WHERE id=?",
            (user_id,),
        )

    @staticmethod
    def create(data: dict) -> int:
        password = data.get("password") or "admin"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cur = db.execute(
            "INSERT INTO users (username, password, full_name, role, email) VALUES (?,?,?,?,?)",
            (data["username"], hashed, data["full_name"], data.get("role", "admin"), data.get("email")),
        )
        AuthController.log("USER_CREATE", f"Utilisateur créé: {data['username']}")
        return cur.lastrowid

    @staticmethod
    def update(user_id: int, data: dict):
        db.execute(
            f"UPDATE users SET full_name=?, role=?, email=?, is_active=?, updated_at={db.current_timestamp_sql()} WHERE id=?",
            (data["full_name"], data.get("role", "admin"), data.get("email"), data.get("is_active", 1), user_id),
        )
        if data.get("password"):
            hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
            db.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
        AuthController.log("USER_UPDATE", f"Utilisateur modifié: id={user_id}")

    @staticmethod
    def delete(user_id: int):
        if user_id == AuthController.current_user()["id"]:
            raise ValueError("Impossible de supprimer votre propre compte.")
        db.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
        AuthController.log("USER_DELETE", f"Utilisateur désactivé: id={user_id}")

    @staticmethod
    def get_logs(user_id: int = None, limit: int = 100) -> list[dict]:
        if user_id:
            return db.fetchall("""
                SELECT l.*, u.full_name FROM user_logs l JOIN users u ON u.id=l.user_id
                WHERE l.user_id=? ORDER BY l.created_at DESC LIMIT ?
            """, (user_id, limit))
        return db.fetchall("""
            SELECT l.*, u.full_name FROM user_logs l JOIN users u ON u.id=l.user_id
            ORDER BY l.created_at DESC LIMIT ?
        """, (limit,))
