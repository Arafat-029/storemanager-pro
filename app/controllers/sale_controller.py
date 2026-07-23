from __future__ import annotations

from datetime import datetime, timedelta
import unicodedata

from app.database.connection import db
from app.controllers.auth_controller import AuthController
from app.controllers.product_controller import ProductController


def _execute(conn, query: str, params: tuple = ()):
    translated = db._translate_placeholders(query)
    if db.is_mysql():
        cursor = conn.cursor()
        cursor.execute(translated, params)
        return cursor
    return conn.execute(translated, params)


def _fetchone(conn, query: str, params: tuple = ()):
    row = _execute(conn, query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn, query: str, params: tuple = ()):
    rows = _execute(conn, query, params).fetchall()
    return [dict(row) for row in rows]


def _normalized_expense_category(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.strip().casefold()


_EXCLUDED_PROFIT_EXPENSE_CATEGORIES = {"loyer", "electricite", "eau"}


def _periodic_category_meta() -> dict[str, dict]:
    return {
        "loyer": {"months_interval": 1},
        "electricite": {"months_interval": 2},
        "eau": {"months_interval": 2},
    }


def _latest_periodic_expense_templates() -> dict[str, dict]:
    rows = db.fetchall(
        f"""
        SELECT category, amount, created_at
        FROM expenses
        WHERE LOWER(category) IN ('loyer', 'electricite', 'eau', 'électricité')
        ORDER BY created_at DESC
        """
    )
    templates: dict[str, dict] = {}
    for row in rows:
        key = _normalized_expense_category(row.get("category"))
        if key == "electricite" or key == "eau" or key == "loyer":
            if key not in templates:
                templates[key] = {
                    "amount": round(float(row.get("amount") or 0.0), 3),
                    "created_at": str(row.get("created_at") or ""),
                }
    return templates


def _month_distance(start_month: str, current_month: str) -> int:
    start_year, start_m = [int(x) for x in start_month.split("-")]
    current_year, current_m = [int(x) for x in current_month.split("-")]
    return (current_year - start_year) * 12 + (current_m - start_m)


def _periodic_expenses_for_month(month_key: str, templates: dict[str, dict]) -> float:
    total = 0.0
    meta = _periodic_category_meta()
    for category_key, template in templates.items():
        amount = round(float(template.get("amount") or 0.0), 3)
        if amount <= 0:
            continue
        created_at = str(template.get("created_at") or "")[:7]
        if not created_at or len(created_at) != 7:
            continue
        interval = int(meta.get(category_key, {}).get("months_interval", 1))
        if _month_distance(created_at, month_key) % interval == 0:
            total = round(total + amount, 3)
    return total


class SaleController:
    @staticmethod
    def _normalize_items(items: list[dict]) -> list[dict]:
        normalized_items: list[dict] = []
        for raw in items or []:
            quantity = round(float(raw.get("quantity") or 0.0), 3)
            stock_quantity = round(float(raw.get("stock_quantity") or quantity or 0.0), 3)
            unit_price = round(float(raw.get("unit_price") or 0.0), 3)
            discount_value = round(float(raw.get("discount") or 0.0), 3)
            if quantity <= 0 or stock_quantity <= 0:
                continue
            normalized_items.append(
                {
                    "product_id": raw.get("product_id"),
                    "sale_unit_id": raw.get("sale_unit_id"),
                    "sale_unit_name": raw.get("sale_unit_name"),
                    "quantity": quantity,
                    "stock_quantity": stock_quantity,
                    "unit_price": unit_price,
                    "discount": discount_value,
                    "skip_stock_movement": bool(raw.get("skip_stock_movement")),
                }
            )
        return normalized_items

    @staticmethod
    def _insert_sale_payment(
        conn,
        *,
        sale_id: int,
        amount: float,
        payment_method: str,
        customer_id: int | None = None,
        customer_payment_id: int | None = None,
        receiver_user_id: int | None = None,
        created_at: str | None = None,
        notes: str = "",
    ) -> None:
        amount = round(float(amount or 0.0), 3)
        if amount <= 0:
            return
        if receiver_user_id is None:
            current_user = AuthController.current_user() or {}
            receiver_user_id = current_user.get("id")
        if created_at:
            _execute(
                conn,
                """
                INSERT INTO sale_payments (
                    sale_id, customer_id, customer_payment_id, receiver_user_id, payment_method, amount, notes, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (sale_id, customer_id, customer_payment_id, receiver_user_id, payment_method, amount, notes or None, created_at),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO sale_payments (
                sale_id, customer_id, customer_payment_id, receiver_user_id, payment_method, amount, notes
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (sale_id, customer_id, customer_payment_id, receiver_user_id, payment_method, amount, notes or None),
        )

    @staticmethod
    def _sync_credit_payment_status(conn, sale_id: int) -> None:
        sale = _fetchone(
            conn,
            "SELECT id, total, payment_method, credit_paid FROM sales WHERE id=?",
            (sale_id,),
        )
        if not sale:
            return

        total = round(float(sale.get("total") or 0.0), 3)
        credit_paid = round(float(sale.get("credit_paid") or 0.0), 3)
        payment_method = str(sale.get("payment_method") or "cash").strip().lower()

        if payment_method != "credit":
            _execute(
                conn,
                f"""
                UPDATE sales
                SET payment_status='paid',
                    credit_paid=?,
                    paid_at=COALESCE(paid_at, created_at)
                WHERE id=?
                """,
                (total, sale_id),
            )
            return

        if credit_paid <= 0:
            _execute(
                conn,
                "UPDATE sales SET payment_status='credit', paid_at=NULL WHERE id=?",
                (sale_id,),
            )
            return

        if credit_paid + 0.0005 >= total:
            _execute(
                conn,
                f"""
                UPDATE sales
                SET payment_status='paid',
                    credit_paid=?,
                    paid_at={db.current_timestamp_sql()}
                WHERE id=?
                """,
                (total, sale_id),
            )
            return

        _execute(
            conn,
            "UPDATE sales SET payment_status='partial' WHERE id=?",
            (sale_id,),
        )

    @staticmethod
    def create_sale(
        items: list[dict],
        payment_method: str = "cash",
        discount: float = 0,
        tax_rate: float = 0,
        amount_paid: float = 0,
        notes: str = "",
        customer_id: int = None,
    ) -> dict:
        """
        items: [{
            "product_id": int,
            "sale_unit_id": int | None,
            "sale_unit_name": str | None,
            "quantity": float,
            "stock_quantity": float,
            "unit_price": float,
            "discount": float,
        }]
        """
        from app.controllers.customer_controller import CustomerController

        payment_method = (payment_method or "cash").strip().lower()
        amount_paid = round(float(amount_paid or 0.0), 3)

        normalized_items = SaleController._normalize_items(items)
        if not normalized_items:
            raise ValueError("Ajoutez au moins une ligne de vente valide.")

        subtotal = round(sum(it["quantity"] * it["unit_price"] - it.get("discount", 0.0) for it in normalized_items), 3)
        tax = round(subtotal * tax_rate / 100, 3)
        total = round(subtotal - float(discount or 0.0) + tax, 3)
        if total <= 0:
            raise ValueError("Le total de la vente doit être supérieur à 0.")

        if payment_method != "credit" and amount_paid + 0.0005 < total:
            raise ValueError("Le montant payé est insuffisant.")

        immediate_paid = min(total, amount_paid if payment_method == "credit" else total)
        change = round(max(0.0, amount_paid - total), 3)
        payment_status = "paid"
        paid_at_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if payment_method == "credit":
            if immediate_paid <= 0:
                payment_status = "credit"
                paid_at_value = None
            elif immediate_paid + 0.0005 >= total:
                payment_status = "paid"
            else:
                payment_status = "partial"
                paid_at_value = None

        user_id = AuthController.current_user()["id"]
        conn = db.get_connection()
        try:
            cur = _execute(
                conn,
                """
                INSERT INTO sales (
                    user_id, customer_id, subtotal, discount, tax, total,
                    payment_method, payment_status, amount_paid, credit_paid, change_given, notes, paid_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    user_id,
                    customer_id,
                    subtotal,
                    float(discount or 0.0),
                    tax,
                    total,
                    payment_method,
                    payment_status,
                    amount_paid,
                    immediate_paid if payment_method == "credit" else total,
                    change,
                    notes or None,
                    paid_at_value,
                ),
            )
            sale_id = int(cur.lastrowid)

            for it in normalized_items:
                item_total = round(it["quantity"] * it["unit_price"] - it.get("discount", 0.0), 3)
                _execute(
                    conn,
                    """
                    INSERT INTO sale_items (
                        sale_id, product_id, sale_unit_id, sale_unit_name, quantity,
                        stock_quantity, unit_price, discount, total
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        sale_id,
                        it["product_id"],
                        it.get("sale_unit_id"),
                        it.get("sale_unit_name"),
                        it["quantity"],
                        it["stock_quantity"],
                        it["unit_price"],
                        it.get("discount", 0.0),
                        item_total,
                    ),
                )

                if it.get("skip_stock_movement") or not it.get("product_id"):
                    continue

                ProductController.update_stock(
                    int(it["product_id"]),
                    -float(it["stock_quantity"]),
                    "out",
                    f"Vente #{sale_id}",
                )

            if payment_method == "credit":
                credit_amount = round(max(0.0, total - immediate_paid), 3)
                if credit_amount > 0:
                    CustomerController.add_credit(customer_id, credit_amount, f"Vente #{sale_id}")
                if immediate_paid > 0:
                    SaleController._insert_sale_payment(
                        conn,
                        sale_id=sale_id,
                        amount=immediate_paid,
                        payment_method="credit_deposit",
                        customer_id=customer_id,
                        notes="Acompte vente crédit",
                    )
            else:
                SaleController._insert_sale_payment(
                    conn,
                    sale_id=sale_id,
                    amount=total,
                    payment_method=payment_method,
                    customer_id=customer_id,
                    notes="Paiement immédiat",
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        AuthController.log("SALE_CREATE", f"Vente #{sale_id} | Total: {total:.3f} | Méthode: {payment_method}")
        return SaleController.get_by_id(sale_id)

    @staticmethod
    def apply_customer_credit_payment(customer_id: int, amount: float, notes: str = "") -> dict:
        from app.controllers.customer_controller import CustomerController

        customer = CustomerController.get_by_id(int(customer_id))
        if not customer:
            raise ValueError("Client introuvable.")

        amount = round(float(amount or 0.0), 3)
        if amount <= 0:
            raise ValueError("Le montant doit être supérieur à 0.")

        current_balance = round(float(customer.get("balance") or 0.0), 3)
        if current_balance <= 0:
            raise ValueError("Ce client n'a aucun crédit en attente.")

        open_sales = SaleController.get_open_credit_sales(int(customer_id))
        if not open_sales:
            raise ValueError("Aucune facture crédit ouverte pour ce client.")

        remaining = min(amount, current_balance)
        conn = db.get_connection()
        try:
            batch_cur = _execute(
                conn,
                """
                INSERT INTO customer_credit_payments (customer_id, amount, notes)
                VALUES (?,?,?)
                """,
                (int(customer_id), remaining, notes or None),
            )
            batch_id = int(batch_cur.lastrowid)

            allocations: list[dict] = []
            total_allocated = 0.0

            for sale in open_sales:
                due = round(float(sale.get("remaining_due") or 0.0), 3)
                if due <= 0 or remaining <= 0:
                    continue

                allocated = round(min(due, remaining), 3)
                if allocated <= 0:
                    continue

                new_credit_paid = round(float(sale.get("credit_paid") or 0.0) + allocated, 3)
                _execute(
                    conn,
                    "UPDATE sales SET credit_paid=? WHERE id=?",
                    (new_credit_paid, int(sale["id"])),
                )
                SaleController._sync_credit_payment_status(conn, int(sale["id"]))
                SaleController._insert_sale_payment(
                    conn,
                    sale_id=int(sale["id"]),
                    amount=allocated,
                    payment_method="credit_payment",
                    customer_id=int(customer_id),
                    customer_payment_id=batch_id,
                    notes=notes or "Règlement crédit client",
                )

                remaining = round(remaining - allocated, 3)
                total_allocated = round(total_allocated + allocated, 3)
                allocations.append(
                    {
                        "sale_id": int(sale["id"]),
                        "allocated": allocated,
                    }
                )

                if remaining <= 0:
                    break

            if total_allocated <= 0:
                raise ValueError("Aucune facture crédit n'a pu être réglée.")

            new_balance = round(max(0.0, current_balance - total_allocated), 3)
            _execute(
                conn,
                f"UPDATE customers SET balance=?, updated_at={db.current_timestamp_sql()} WHERE id=?",
                (new_balance, int(customer_id)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        AuthController.log(
            "CUSTOMER_PAYMENT",
            f"Client #{customer_id} -{total_allocated:.3f} TND réparti sur {len(allocations)} facture(s)",
        )
        return {
            "payment_id": batch_id,
            "allocated_total": total_allocated,
            "remaining_balance": new_balance,
            "allocations": allocations,
        }

    @staticmethod
    def get_open_credit_sales(customer_id: int) -> list[dict]:
        return db.fetchall(
            """
            SELECT
                s.*,
                ROUND(COALESCE(s.total, 0) - COALESCE(s.credit_paid, 0), 3) AS remaining_due
            FROM sales s
            WHERE s.customer_id=?
              AND s.status='completed'
              AND lower(trim(COALESCE(s.payment_method, '')))='credit'
              AND ROUND(COALESCE(s.total, 0) - COALESCE(s.credit_paid, 0), 3) > 0
            ORDER BY s.created_at ASC, s.id ASC
            """,
            (customer_id,),
        )

    @staticmethod
    def get_by_id(sale_id: int) -> dict | None:
        sale = db.fetchone(
            """
            SELECT s.*, u.full_name AS cashier_name, c.name AS customer_name
            FROM sales s
            JOIN users u ON u.id=s.user_id
            LEFT JOIN customers c ON c.id=s.customer_id
            WHERE s.id=?
            """,
            (sale_id,),
        )
        if sale:
            sale["items"] = db.fetchall(
                """
                SELECT
                    si.*,
                    p.name AS product_name,
                    p.unit_type
                FROM sale_items si
                JOIN products p ON p.id=si.product_id
                WHERE si.sale_id=?
                ORDER BY si.id
                """,
                (sale_id,),
            )
            sale["payments"] = db.fetchall(
                """
                SELECT sp.*, ccp.created_at AS customer_payment_date
                FROM sale_payments sp
                LEFT JOIN customer_credit_payments ccp ON ccp.id = sp.customer_payment_id
                WHERE sp.sale_id=?
                ORDER BY sp.created_at ASC, sp.id ASC
                """,
                (sale_id,),
            )
        return sale

    @staticmethod
    def get_sales(date_from: str = None, date_to: str = None, user_id: int = None, status: str = None) -> list[dict]:
        conds = []
        params = []
        if date_from:
            conds.append(f"{db.date_only_expr('s.created_at')} >= ?")
            params.append(date_from)
        if date_to:
            conds.append(f"{db.date_only_expr('s.created_at')} <= ?")
            params.append(date_to)
        if user_id:
            conds.append("s.user_id=?")
            params.append(user_id)
        if status:
            conds.append("s.status=?")
            params.append(status)
        where = "WHERE " + " AND ".join(conds) if conds else ""
        return db.fetchall(
            f"""
            SELECT
                s.*,
                u.full_name AS cashier_name,
                (SELECT COUNT(*) FROM sale_items WHERE sale_id=s.id) AS item_count,
                ROUND(COALESCE(s.total, 0) - COALESCE(s.credit_paid, 0), 3) AS remaining_due
            FROM sales s
            JOIN users u ON u.id=s.user_id
            {where}
            ORDER BY s.created_at DESC
            """,
            tuple(params),
        )

    @staticmethod
    def cancel_sale(sale_id: int, reason: str = ""):
        sale = SaleController.get_by_id(sale_id)
        if not sale or sale["status"] != "completed":
            raise ValueError("Vente introuvable ou déjà annulée.")

        db.execute("UPDATE sales SET status='cancelled' WHERE id=?", (sale_id,))
        db.execute("DELETE FROM sale_payments WHERE sale_id=?", (sale_id,))

        if sale.get("payment_method") == "credit" and sale.get("customer_id"):
            remaining_due = round(float(sale.get("total") or 0.0) - float(sale.get("credit_paid") or 0.0), 3)
            if remaining_due > 0:
                db.execute(
                    f"""
                    UPDATE customers
                    SET balance = CASE
                        WHEN balance - ? < 0 THEN 0
                        ELSE balance - ?
                    END,
                    updated_at={db.current_timestamp_sql()}
                    WHERE id=?
                    """,
                    (remaining_due, remaining_due, int(sale["customer_id"])),
                )

        for item in sale["items"]:
            ProductController.update_stock(
                int(item["product_id"]),
                float(item.get("stock_quantity") or item["quantity"]),
                "return",
                f"Annulation vente #{sale_id}",
            )
        AuthController.log("SALE_CANCEL", f"Vente #{sale_id} annulée. Raison: {reason}")

    @staticmethod
    def get_daily_summary(date: str = None) -> dict:
        target_date = date or datetime.now().date().isoformat()
        revenue_row = db.fetchone(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS revenue
            FROM sale_payments
            WHERE {db.date_only_expr('created_at')} = ?
            """,
            (target_date,),
        ) or {"revenue": 0}

        sale_row = db.fetchone(
            f"""
            SELECT
                COUNT(*) AS total_sales,
                COALESCE(SUM(discount), 0) AS total_discounts,
                COALESCE(SUM(tax), 0) AS total_taxes
            FROM sales
            WHERE {db.date_only_expr('created_at')} = ?
              AND status='completed'
            """,
            (target_date,),
        ) or {}
        sale_row["revenue"] = round(float(revenue_row.get("revenue") or 0.0), 3)
        return sale_row

    @staticmethod
    def get_top_products(limit: int = 10, date_from: str = None, date_to: str = None) -> list[dict]:
        conds = ["s.status='completed'", "(p.barcode IS NULL OR p.barcode <> '__MANUAL_SALE__')"]
        params = []
        if date_from:
            conds.append(f"{db.date_only_expr('s.created_at')}>=?")
            params.append(date_from)
        if date_to:
            conds.append(f"{db.date_only_expr('s.created_at')}<=?")
            params.append(date_to)
        where = "WHERE " + " AND ".join(conds)
        return db.fetchall(
            f"""
            SELECT
                p.name,
                p.unit_type,
                SUM(COALESCE(si.stock_quantity, si.quantity)) AS total_qty,
                SUM(si.total) AS total_revenue
            FROM sale_items si
            JOIN sales s ON s.id=si.sale_id
            JOIN products p ON p.id=si.product_id
            {where}
            GROUP BY si.product_id
            ORDER BY total_qty DESC, total_revenue DESC, p.name ASC
            LIMIT {limit}
            """,
            tuple(params),
        )

    @staticmethod
    def _month_key(dt: datetime) -> str:
        return dt.strftime("%Y-%m")

    @staticmethod
    def _shift_months(dt: datetime, months: int) -> datetime:
        year = dt.year + ((dt.month - 1 + months) // 12)
        month = ((dt.month - 1 + months) % 12) + 1
        return dt.replace(year=year, month=month, day=1)

    @staticmethod
    def _period_expr(period: str, column: str) -> str:
        if period == "month":
            return db.mysql_date_format(column, "%Y-%m") if db.is_mysql() else db.sqlite_strftime("%Y-%m", column)
        if period == "year":
            return db.mysql_date_format(column, "%Y") if db.is_mysql() else db.sqlite_strftime("%Y", column)
        if period == "week":
            return "CONCAT('Sem ', DATE_FORMAT(created_at, '%v'))" if db.is_mysql() else db.sqlite_strftime("Sem %W", column)
        if period == "day":
            return db.date_only_expr(column)
        raise ValueError(f"Unsupported period: {period}")

    @staticmethod
    def _label_expr(period: str, column: str) -> str:
        if period == "day":
            return db.mysql_date_format(column, "%d/%m") if db.is_mysql() else db.sqlite_strftime("%d/%m", column)
        if period == "week":
            return "CONCAT('Sem ', DATE_FORMAT(created_at, '%v'))" if db.is_mysql() else db.sqlite_strftime("Sem %W", column)
        if period == "month":
            return db.mysql_date_format(column, "%m/%Y") if db.is_mysql() else db.sqlite_strftime("%m/%Y", column)
        return db.mysql_date_format(column, "%d/%m") if db.is_mysql() else db.sqlite_strftime("%d/%m", column)

    @staticmethod
    def _profit_rows_for_period(period: str, start_key: str) -> tuple[dict[str, float], dict[str, float]]:
        period_expr_payments = SaleController._period_expr(period, "sp.created_at")
        period_expr_expenses = SaleController._period_expr(period, "created_at")

        payment_rows = db.fetchall(
            f"""
            SELECT
                {period_expr_payments} AS period_key,
                COALESCE(SUM(
                    sp.amount * (
                        CASE
                            WHEN sale_fin.total > 0 THEN sale_fin.gross_profit / sale_fin.total
                            ELSE 0
                        END
                    )
                ), 0) AS gross_profit
            FROM sale_payments sp
            JOIN (
                SELECT
                    s.id,
                    s.total,
                    COALESCE(SUM(si.total - (COALESCE(si.stock_quantity, si.quantity) * COALESCE(p.purchase_price, 0))), 0) AS gross_profit
                FROM sales s
                LEFT JOIN sale_items si ON si.sale_id = s.id
                LEFT JOIN products p ON p.id = si.product_id
                WHERE s.status='completed'
                GROUP BY s.id, s.total
            ) AS sale_fin ON sale_fin.id = sp.sale_id
            WHERE {db.date_only_expr('sp.created_at')} >= ?
            GROUP BY period_key
            ORDER BY period_key
            """,
            (start_key,),
        )
        expense_rows = db.fetchall(
            f"""
            SELECT
                {period_expr_expenses} AS period_key,
                category,
                COALESCE(SUM(amount), 0) AS total_expenses
            FROM expenses
            WHERE {db.date_only_expr('created_at')} >= ?
            GROUP BY period_key, category
            ORDER BY period_key, category
            """,
            (start_key,),
        )
        sales_by_period = {str(row["period_key"]): round(float(row.get("gross_profit") or 0.0), 3) for row in payment_rows}
        expenses_by_period: dict[str, float] = {}
        for row in expense_rows:
            category_key = _normalized_expense_category(row.get("category"))
            if category_key in _EXCLUDED_PROFIT_EXPENSE_CATEGORIES:
                continue
            period_key = str(row.get("period_key") or "")
            expenses_by_period[period_key] = round(
                expenses_by_period.get(period_key, 0.0) + float(row.get("total_expenses") or 0.0),
                3,
            )
        return sales_by_period, expenses_by_period

    @staticmethod
    def get_profit_series(period: str = "day") -> list[dict]:
        period = (period or "day").strip().lower()

        if period == "month":
            month_count = 12
            now = datetime.now().replace(day=1)
            start_dt = SaleController._shift_months(now, -(month_count - 1))
            start_key = start_dt.strftime("%Y-%m-%d")
            sales_by_period, expenses_by_period = SaleController._profit_rows_for_period("month", start_key)
            periodic_templates = _latest_periodic_expense_templates()
            points: list[dict] = []
            for offset in range(month_count):
                current_dt = SaleController._shift_months(start_dt, offset)
                key = current_dt.strftime("%Y-%m")
                periodic_expense = _periodic_expenses_for_month(key, periodic_templates)
                net_profit = round(
                    sales_by_period.get(key, 0.0)
                    - expenses_by_period.get(key, 0.0)
                    - periodic_expense,
                    3,
                )
                points.append(
                    {
                        "date": key,
                        "label": current_dt.strftime("%m/%Y"),
                        "profit": net_profit,
                        "periodic_expense": periodic_expense,
                    }
                )
            return points

        if period == "year":
            year_count = 5
            now = datetime.now()
            start_year = now.year - (year_count - 1)
            start_key = f"{start_year}-01-01"
            sales_by_period, expenses_by_period = SaleController._profit_rows_for_period("year", start_key)
            points: list[dict] = []
            for year in range(start_year, now.year + 1):
                key = str(year)
                net_profit = round(sales_by_period.get(key, 0.0) - expenses_by_period.get(key, 0.0), 3)
                points.append({"date": key, "label": key, "profit": net_profit})
            return points

        days = 30
        start_date = (datetime.now() - timedelta(days=days - 1)).date().isoformat()
        sales_by_period, expenses_by_period = SaleController._profit_rows_for_period("day", start_date)

        points: list[dict] = []
        start_dt = datetime.fromisoformat(start_date)
        for offset in range(days):
            current_day = (start_dt + timedelta(days=offset)).date()
            key = current_day.isoformat()
            net_profit = round(sales_by_period.get(key, 0.0) - expenses_by_period.get(key, 0.0), 3)
            points.append({"date": key, "label": current_day.strftime("%d/%m"), "profit": net_profit})
        return points

    @staticmethod
    def get_daily_profit(days: int = 30) -> list[dict]:
        points = SaleController.get_profit_series("day")
        if days and days < len(points):
            return points[-int(days):]
        return points

    @staticmethod
    def get_cash_expected_today(date: str = None, opening_cash: float = 0.0, user_id: int | None = None) -> dict:
        target_date = date or datetime.now().date().isoformat()
        where_sql = [f"{db.date_only_expr('sp.created_at')} = ?"]
        params: list = [target_date]

        if user_id is not None:
            where_sql.append("COALESCE(sp.receiver_user_id, s.user_id) = ?")
            params.append(int(user_id))

        received_row = db.fetchone(
            f"""
            SELECT COALESCE(SUM(sp.amount), 0) AS total_received
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE {' AND '.join(where_sql)}
            """,
            tuple(params),
        ) or {"total_received": 0}
        total_received = round(float(received_row.get("total_received") or 0.0), 3)
        opening_cash = round(float(opening_cash or 0.0), 3)
        return {
            "date": target_date,
            "opening_cash": opening_cash,
            "total_received": total_received,
            "expected_cash": round(opening_cash + total_received, 3),
        }

    @staticmethod
    def get_revenue_by_period(period: str = "day", days: int = 30) -> list[dict]:
        start_date = (datetime.now() - timedelta(days=max(0, int(days)))).date().isoformat()
        label_expr = SaleController._label_expr(period, "created_at")
        return db.fetchall(
            f"""
            SELECT
                {label_expr} AS period,
                SUM(amount) AS revenue,
                COUNT(*) AS payment_count
            FROM sale_payments
            WHERE {db.date_only_expr('created_at')} >= ?
            GROUP BY period
            ORDER BY MIN(created_at)
            """,
            (start_date,),
        )
