from __future__ import annotations

from datetime import date, datetime, timedelta
import calendar
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


def _period_key_for_date(period: str, value: date) -> str:
    if period == "month":
        return value.strftime("%Y-%m")
    if period == "year":
        return value.strftime("%Y")
    return value.isoformat()


def _add_months(value: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month's length
    (so a charge recorded the 31st still lands on the 30th / 28th)."""
    total = (value.year * 12) + (value.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _recurrence_occurrences(start: date, interval: int, unit: str, until: date) -> list[date]:
    """Every due date of a recurring expense, from its own record date up to
    *until* (inclusive). Never projects before the expense was recorded and
    never past *until*, so the curve cannot invent charges outside the period
    the business actually carried them."""
    if interval <= 0 or start > until:
        return []

    occurrences: list[date] = []
    step = 0
    # Hard cap: a daily charge over a 5-year window is ~1830 points; the bound
    # keeps a corrupt interval/unit from spinning forever.
    while step < 4000:
        if unit == "day":
            current = start + timedelta(days=interval * step)
        elif unit == "week":
            current = start + timedelta(weeks=interval * step)
        elif unit == "month":
            current = _add_months(start, interval * step)
        elif unit == "year":
            current = _add_months(start, 12 * interval * step)
        else:
            return [start] if start <= until else []
        if current > until:
            break
        occurrences.append(current)
        step += 1
    return occurrences


def _expense_totals_by_period(period: str, period_keys: list[str]) -> dict[str, float]:
    """Total expenses charged to each period key.

    Every recorded expense counts in the period it was recorded. An expense
    that carries a recurrence (recurrence_interval + recurrence_unit) also
    counts in each later period it falls due, up to today — that is what makes
    a monthly rent entered once show up every month instead of only once.

    A projected occurrence is skipped when the user separately recorded an
    expense of the same category in that period: the real entry is the
    authoritative amount and must not be doubled.
    """
    wanted = set(period_keys)
    if not wanted:
        return {}

    rows = db.fetchall(
        "SELECT category, amount, recurrence_interval, recurrence_unit, created_at FROM expenses"
    )

    totals: dict[str, float] = {}
    # (period_key, normalized category) actually recorded by the user.
    recorded: set[tuple[str, str]] = set()
    parsed: list[tuple[date, str, float, int, str]] = []

    for row in rows:
        raw_created = str(row.get("created_at") or "")[:10]
        try:
            created = date.fromisoformat(raw_created)
        except ValueError:
            continue
        amount = round(float(row.get("amount") or 0.0), 3)
        category = _normalized_expense_category(row.get("category"))
        key = _period_key_for_date(period, created)
        recorded.add((key, category))
        if key in wanted:
            totals[key] = round(totals.get(key, 0.0) + amount, 3)

        interval = int(row.get("recurrence_interval") or 0)
        unit = str(row.get("recurrence_unit") or "")
        if interval > 0 and unit:
            parsed.append((created, category, amount, interval, unit))

    today = datetime.now().date()
    for created, category, amount, interval, unit in parsed:
        for occurrence in _recurrence_occurrences(created, interval, unit, today):
            if occurrence == created:
                continue  # already counted above as the recorded entry
            key = _period_key_for_date(period, occurrence)
            if key not in wanted or (key, category) in recorded:
                continue
            totals[key] = round(totals.get(key, 0.0) + amount, 3)

    return totals


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
    def _assert_stock_available(conn, normalized_items: list[dict]) -> None:
        """Refuse the sale if any line would push a product's stock negative.

        Quantities are summed per product first: the same product can appear
        on several lines (a pack line plus a loose-piece line, say), and each
        line taken alone can fit in stock while their total does not.
        """
        required: dict[int, float] = {}
        for item in normalized_items:
            if item.get("skip_stock_movement") or not item.get("product_id"):
                continue
            product_id = int(item["product_id"])
            required[product_id] = round(
                required.get(product_id, 0.0) + float(item["stock_quantity"]), 3
            )

        for product_id, needed in required.items():
            row = _fetchone(
                conn,
                "SELECT name, stock_quantity FROM products WHERE id=?",
                (product_id,),
            )
            if not row:
                raise ValueError(f"Produit introuvable (id={product_id}).")
            available = round(float(row.get("stock_quantity") or 0.0), 3)
            if needed > available + 0.0005:
                raise ValueError(
                    f"Stock insuffisant pour « {row['name']} » : "
                    f"{available:g} disponible(s), {needed:g} demandé(s)."
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
        # Whether the sale is settled right now. The timestamp itself is left
        # to the database (see paid_at_sql below) rather than stamped here:
        # created_at on this same row comes from the DB clock, so writing
        # paid_at from Python's clock would put two different time sources —
        # and under MySQL two different time zones — on one row.
        paid_now = True
        if payment_method == "credit":
            if immediate_paid <= 0:
                payment_status = "credit"
                paid_now = False
            elif immediate_paid + 0.0005 >= total:
                payment_status = "paid"
            else:
                payment_status = "partial"
                paid_now = False
        paid_at_sql = db.current_timestamp_sql() if paid_now else "NULL"

        user_id = AuthController.current_user()["id"]

        with db.transaction() as conn:
            # Re-read the stock inside the transaction rather than trusting
            # what the cart cached when the product was added: the cart can
            # sit open for minutes while a delivery, a loss or another sale
            # moves the same product. This is the only check that runs on the
            # data actually being written.
            SaleController._assert_stock_available(conn, normalized_items)

            cur = _execute(
                conn,
                f"""
                INSERT INTO sales (
                    user_id, customer_id, subtotal, discount, tax, total,
                    payment_method, payment_status, amount_paid, credit_paid, change_given, notes, paid_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,{paid_at_sql})
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

        moyen = {
            "cash": "payé en espèces",
            "credit": "à crédit",
            "card": "payé par carte",
        }.get(payment_method, payment_method)
        AuthController.log("SALE_CREATE", f"Vente #{sale_id} — {total:.3f} TND — {moyen}")
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
        with db.transaction() as conn:
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

        # Cancelling touches four things that only make sense together:
        # the sale's status, its payment rows, the customer's credit balance
        # and the stock put back on the shelf. Done as separate commits, a
        # failure halfway through left a cancelled sale whose goods were
        # never returned to stock, or a credit never given back.
        with db.transaction():
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
                if not item.get("product_id"):
                    continue
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

    # sale_payments.payment_method values that represent money moving through
    # the customer-credit ledger: a deposit taken at the moment of a credit
    # sale, or a later repayment against an outstanding balance. Everything
    # else (cash, card, ...) was paid in full on the spot.
    _CREDIT_PAYMENT_METHODS = ("credit_deposit", "credit_payment")

    @staticmethod
    def _gross_profit_by_period(period: str, start_key: str, credit_scope: str = "all") -> dict[str, float]:
        """credit_scope: "all" (default, everything) | "credit_only" | "non_credit"."""
        period_expr_payments = SaleController._period_expr(period, "sp.created_at")

        method_filter = ""
        if credit_scope == "credit_only":
            methods = ",".join(f"'{m}'" for m in SaleController._CREDIT_PAYMENT_METHODS)
            method_filter = f" AND sp.payment_method IN ({methods})"
        elif credit_scope == "non_credit":
            methods = ",".join(f"'{m}'" for m in SaleController._CREDIT_PAYMENT_METHODS)
            method_filter = f" AND sp.payment_method NOT IN ({methods})"

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
            WHERE {db.date_only_expr('sp.created_at')} >= ?{method_filter}
            GROUP BY period_key
            ORDER BY period_key
            """,
            (start_key,),
        )
        return {
            str(row["period_key"]): round(float(row.get("gross_profit") or 0.0), 3)
            for row in payment_rows
        }

    @staticmethod
    def _loss_totals_by_period(period: str, start_key: str) -> dict[str, float]:
        """Cost of stock written off in each period.

        Goods lost were paid for but will never be sold, so their purchase cost
        is a real charge against the result — without this, throwing away a
        crate of yoghurt would leave the net profit untouched. unit_cost is
        frozen on the movement, so past periods stay stable when prices change.
        """
        period_expr = SaleController._period_expr(period, "sm.created_at")
        rows = db.fetchall(
            f"""
            SELECT
                {period_expr} AS period_key,
                COALESCE(SUM(sm.quantity * COALESCE(sm.unit_cost, 0)), 0) AS loss_total
            FROM stock_movements sm
            WHERE sm.loss_reason IS NOT NULL
              AND {db.date_only_expr('sm.created_at')} >= ?
            GROUP BY period_key
            ORDER BY period_key
            """,
            (start_key,),
        )
        return {
            str(row["period_key"]): round(float(row.get("loss_total") or 0.0), 3)
            for row in rows
        }

    @staticmethod
    def get_profit_series(period: str = "day", credit_scope: str = "all") -> list[dict]:
        """credit_scope: "all" (default — every payment, current behaviour) |
        "credit_only" (only credit deposits/repayments) | "non_credit" (only
        cash/card sales paid in full on the spot). Expenses and losses are
        real operating costs regardless of how a sale was paid, so they are
        always subtracted in full in every scope — only the revenue side of
        the formula changes."""
        period = (period or "day").strip().lower()
        credit_scope = (credit_scope or "all").strip().lower()
        if credit_scope not in {"all", "credit_only", "non_credit"}:
            credit_scope = "all"

        # Every branch below is the same formula, only the bucket size changes:
        #   net = (margin on payments actually received) - (expenses due)
        if period == "month":
            month_count = 12
            now = datetime.now().replace(day=1)
            start_dt = SaleController._shift_months(now, -(month_count - 1))
            start_key = start_dt.strftime("%Y-%m-%d")
            gross_by_period = SaleController._gross_profit_by_period("month", start_key, credit_scope)
            keys = [
                SaleController._shift_months(start_dt, offset).strftime("%Y-%m")
                for offset in range(month_count)
            ]
            expenses_by_period = _expense_totals_by_period("month", keys)
            losses_by_period = SaleController._loss_totals_by_period("month", start_key)
            points: list[dict] = []
            for offset, key in enumerate(keys):
                current_dt = SaleController._shift_months(start_dt, offset)
                expense_total = expenses_by_period.get(key, 0.0)
                loss_total = losses_by_period.get(key, 0.0)
                net_profit = round(gross_by_period.get(key, 0.0) - expense_total - loss_total, 3)
                points.append(
                    {
                        "date": key,
                        "label": current_dt.strftime("%m/%Y"),
                        "profit": net_profit,
                        "expenses": expense_total,
                        "losses": loss_total,
                    }
                )
            return points

        if period == "year":
            year_count = 5
            now = datetime.now()
            start_year = now.year - (year_count - 1)
            start_key = f"{start_year}-01-01"
            gross_by_period = SaleController._gross_profit_by_period("year", start_key, credit_scope)
            keys = [str(year) for year in range(start_year, now.year + 1)]
            expenses_by_period = _expense_totals_by_period("year", keys)
            losses_by_period = SaleController._loss_totals_by_period("year", start_key)
            points: list[dict] = []
            for key in keys:
                expense_total = expenses_by_period.get(key, 0.0)
                loss_total = losses_by_period.get(key, 0.0)
                net_profit = round(gross_by_period.get(key, 0.0) - expense_total - loss_total, 3)
                points.append({
                    "date": key, "label": key, "profit": net_profit,
                    "expenses": expense_total, "losses": loss_total,
                })
            return points

        days = 30
        start_date = (datetime.now() - timedelta(days=days - 1)).date().isoformat()
        gross_by_period = SaleController._gross_profit_by_period("day", start_date, credit_scope)

        start_dt = datetime.fromisoformat(start_date)
        day_dates = [(start_dt + timedelta(days=offset)).date() for offset in range(days)]
        keys = [d.isoformat() for d in day_dates]
        expenses_by_period = _expense_totals_by_period("day", keys)
        losses_by_period = SaleController._loss_totals_by_period("day", start_date)

        points: list[dict] = []
        for current_day, key in zip(day_dates, keys):
            expense_total = expenses_by_period.get(key, 0.0)
            loss_total = losses_by_period.get(key, 0.0)
            net_profit = round(gross_by_period.get(key, 0.0) - expense_total - loss_total, 3)
            points.append(
                {
                    "date": key,
                    "label": current_day.strftime("%d/%m"),
                    "profit": net_profit,
                    "expenses": expense_total,
                    "losses": loss_total,
                }
            )
        return points

    @staticmethod
    def get_daily_profit(days: int = 30) -> list[dict]:
        points = SaleController.get_profit_series("day")
        if days and days < len(points):
            return points[-int(days):]
        return points

    # get_cash_expected_today a été retiré : il additionnait les
    # encaissements de LA JOURNÉE, si bien que deux caissiers se succédant
    # héritaient chacun de la caisse de l'autre. Voir
    # CashSessionController.compute_expected, borné par session.

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
