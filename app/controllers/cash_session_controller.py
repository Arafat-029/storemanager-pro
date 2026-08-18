"""Sessions de caisse : ouverture, cloture, ecart constate.

Une session couvre une prise de poste. A l'ouverture on note le fond de
caisse ; a la cloture on compare ce que le tiroir DEVRAIT contenir avec ce
que le caissier a reellement compte, et on garde l'ecart.

L'ecart est le point important : sans lui, une cloture n'affiche qu'un
montant theorique et un manquant passe inapercu indefiniment.
"""
from __future__ import annotations

from app.database.connection import db
from app.controllers.auth_controller import AuthController


class CashSessionController:

    # ── Ouverture ────────────────────────────────────────────────────────

    @staticmethod
    def get_open_session(user_id: int) -> dict | None:
        """Session encore ouverte pour cet utilisateur, s'il y en a une."""
        return db.fetchone(
            "SELECT * FROM cash_sessions WHERE user_id=? AND status='open' "
            "ORDER BY opened_at DESC, id DESC LIMIT 1",
            (int(user_id),),
        )

    @staticmethod
    def open_session(user_id: int, opening_cash: float) -> dict:
        """Ouvre une session, ou renvoie celle deja ouverte.

        Ne jamais en ouvrir deux : la session ouverte sert de reference pour
        calculer les encaissements de la periode, deux sessions se
        chevauchant compteraient les memes ventes deux fois.
        """
        user_id = int(user_id)
        existing = CashSessionController.get_open_session(user_id)
        if existing:
            return existing

        opening_cash = round(float(opening_cash or 0.0), 3)
        # Repere de depart : le dernier encaissement existant. Tout ce qui
        # portera un identifiant superieur appartiendra a cette session.
        since = CashSessionController._last_payment_id()
        cur = db.execute(
            "INSERT INTO cash_sessions (user_id, opening_cash, since_payment_id, status) "
            "VALUES (?,?,?,'open')",
            (user_id, opening_cash, since),
        )
        AuthController.log(
            "CASH_SESSION_OPEN",
            f"Ouverture de caisse : fond {opening_cash:.3f} TND",
        )
        return CashSessionController.get_by_id(int(cur.lastrowid))

    @staticmethod
    def get_by_id(session_id: int) -> dict | None:
        return db.fetchone("SELECT * FROM cash_sessions WHERE id=?", (int(session_id),))

    # ── Montants ─────────────────────────────────────────────────────────

    @staticmethod
    def _last_payment_id() -> int:
        row = db.fetchone("SELECT COALESCE(MAX(id), 0) AS max_id FROM sale_payments") or {}
        return int(row.get("max_id") or 0)

    @staticmethod
    def compute_expected(session: dict) -> dict:
        """Ce que le tiroir devrait contenir pour cette session.

        Ne compte que les encaissements ENCAISSES PAR CE CAISSIER et bornes
        par les identifiants de la session : deux caissiers peuvent se
        succeder le meme jour, et chacun ne repond que de sa propre caisse.

        Les bornes sont des identifiants, pas des dates. Les horodatages
        n'ont qu'une resolution d'une seconde : une session ouverte dans la
        meme seconde qu'un encaissement s'attribuait celui du poste
        precedent, ce qui gonflait le montant attendu et faisait apparaitre
        un manquant inexistant.
        """
        opening_cash = round(float(session.get("opening_cash") or 0.0), 3)

        conditions = [
            "COALESCE(sp.receiver_user_id, s.user_id) = ?",
            "sp.id > ?",
        ]
        params: list = [int(session["user_id"]), int(session.get("since_payment_id") or 0)]
        until = session.get("until_payment_id")
        if until is not None:
            # Session close : figee sur sa periode, elle ne doit pas se
            # mettre a bouger parce que le caissier suivant encaisse.
            conditions.append("sp.id <= ?")
            params.append(int(until))

        row = db.fetchone(
            f"""
            SELECT COALESCE(SUM(sp.amount), 0) AS total_received
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        ) or {}
        total_received = round(float(row.get("total_received") or 0.0), 3)
        return {
            "opening_cash": opening_cash,
            "total_received": total_received,
            "expected_cash": round(opening_cash + total_received, 3),
        }

    # ── Cloture ──────────────────────────────────────────────────────────

    @staticmethod
    def close_session(session_id: int, counted_cash: float, notes: str = "") -> dict:
        session = CashSessionController.get_by_id(session_id)
        if not session:
            raise ValueError("Session de caisse introuvable.")
        if str(session.get("status")) != "open":
            raise ValueError("Cette session de caisse est déjà clôturée.")

        counted_cash = round(float(counted_cash or 0.0), 3)
        if counted_cash < 0:
            raise ValueError("Le montant compté ne peut pas être négatif.")

        with db.transaction():
            # La borne de fin est prise AVANT le calcul, dans la meme
            # transaction : sans elle, un encaissement arrivant entre le
            # calcul et l'ecriture serait compte dans une session deja close.
            until = CashSessionController._last_payment_id()
            session = dict(session, until_payment_id=until)
            amounts = CashSessionController.compute_expected(session)
            difference = round(counted_cash - amounts["expected_cash"], 3)

            db.execute(
                f"""
                UPDATE cash_sessions
                SET status='closed',
                    closed_at={db.current_timestamp_sql()},
                    until_payment_id=?,
                    total_received=?,
                    expected_cash=?,
                    counted_cash=?,
                    difference=?,
                    notes=?
                WHERE id=?
                """,
                (
                    until,
                    amounts["total_received"],
                    amounts["expected_cash"],
                    counted_cash,
                    difference,
                    (notes or "").strip() or None,
                    int(session_id),
                ),
            )

        etat = "conforme" if abs(difference) < 0.0005 else (
            f"excédent {difference:+.3f}" if difference > 0 else f"manquant {difference:+.3f}"
        )
        AuthController.log(
            "CASH_SESSION_CLOSE",
            f"Clôture caisse #{session_id} : attendu {amounts['expected_cash']:.3f}, "
            f"compté {counted_cash:.3f}, {etat}",
        )
        return CashSessionController.get_by_id(session_id)

    # ── Consultation (administrateur) ────────────────────────────────────

    @staticmethod
    def get_sessions(
        date_from: str | None = None,
        date_to: str | None = None,
        user_id: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if date_from:
            conditions.append(f"{db.date_only_expr('cs.opened_at')} >= ?")
            params.append(date_from)
        if date_to:
            conditions.append(f"{db.date_only_expr('cs.opened_at')} <= ?")
            params.append(date_to)
        if user_id is not None:
            conditions.append("cs.user_id = ?")
            params.append(int(user_id))
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(int(limit))
        return db.fetchall(
            f"""
            SELECT cs.*, u.full_name AS user_name, u.username
            FROM cash_sessions cs
            JOIN users u ON u.id = cs.user_id
            {where}
            ORDER BY cs.opened_at DESC, cs.id DESC
            LIMIT ?
            """,
            tuple(params),
        )

    @staticmethod
    def get_totals(date_from: str | None = None, date_to: str | None = None) -> dict:
        """Bilan des ecarts sur une periode, pour l'administrateur."""
        conditions = ["status='closed'"]
        params: list = []
        if date_from:
            conditions.append(f"{db.date_only_expr('opened_at')} >= ?")
            params.append(date_from)
        if date_to:
            conditions.append(f"{db.date_only_expr('opened_at')} <= ?")
            params.append(date_to)
        row = db.fetchone(
            f"""
            SELECT
                COUNT(*) AS sessions,
                COALESCE(SUM(difference), 0) AS ecart_total,
                COALESCE(SUM(CASE WHEN difference < -0.0005 THEN 1 ELSE 0 END), 0) AS manquants,
                COALESCE(SUM(CASE WHEN difference > 0.0005 THEN 1 ELSE 0 END), 0) AS excedents,
                COALESCE(SUM(total_received), 0) AS encaisse_total
            FROM cash_sessions
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        ) or {}
        return {
            "sessions": int(row.get("sessions") or 0),
            "ecart_total": round(float(row.get("ecart_total") or 0.0), 3),
            "manquants": int(row.get("manquants") or 0),
            "excedents": int(row.get("excedents") or 0),
            "encaisse_total": round(float(row.get("encaisse_total") or 0.0), 3),
        }
