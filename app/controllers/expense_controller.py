from __future__ import annotations
from app.database.connection import db
from app.controllers.auth_controller import AuthController


EXPENSE_CATEGORIES = [
    "Loyer", "Électricité", "Eau", "Internet", "Salaires",
    "Transport", "Maintenance", "Fournitures", "Publicité", "Autres",
]

RECURRENCE_UNITS = ("day", "week", "month", "year")


class ExpenseController:

    @staticmethod
    def get_all(date_from: str = None, date_to: str = None) -> list[dict]:
        conds = []
        params = []
        if date_from:
            conds.append("date(e.created_at)>=?")
            params.append(date_from)
        if date_to:
            conds.append("date(e.created_at)<=?")
            params.append(date_to)
        where = "WHERE " + " AND ".join(conds) if conds else ""
        return db.fetchall(f"""
            SELECT e.*, u.full_name AS user_name
            FROM expenses e JOIN users u ON u.id=e.user_id
            {where} ORDER BY e.created_at DESC
        """, tuple(params))

    @staticmethod
    def create(
        category: str,
        amount: float,
        description: str = "",
        recurrence_interval: int | None = None,
        recurrence_unit: str | None = None,
    ) -> int:
        if recurrence_unit is not None and recurrence_unit not in RECURRENCE_UNITS:
            raise ValueError(f"Unité de récurrence invalide : {recurrence_unit}")
        if not recurrence_interval or not recurrence_unit:
            recurrence_interval = None
            recurrence_unit = None
        cur = db.execute(
            "INSERT INTO expenses (user_id, category, amount, description, recurrence_interval, recurrence_unit) "
            "VALUES (?,?,?,?,?,?)",
            (
                AuthController.current_user()["id"],
                category,
                amount,
                description,
                recurrence_interval,
                recurrence_unit,
            ),
        )
        AuthController.log("EXPENSE_CREATE", f"Dépense: {category} - {amount}")
        return cur.lastrowid

    @staticmethod
    def delete(expense_id: int):
        db.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        AuthController.log("EXPENSE_DELETE", f"Dépense supprimée: id={expense_id}")

    @staticmethod
    def get_summary(date_from: str = None, date_to: str = None) -> dict:
        conds = []
        params = []
        if date_from:
            conds.append("date(created_at)>=?")
            params.append(date_from)
        if date_to:
            conds.append("date(created_at)<=?")
            params.append(date_to)
        where = "WHERE " + " AND ".join(conds) if conds else ""
        row = db.fetchone(f"SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expenses {where}", tuple(params))
        return row or {}
