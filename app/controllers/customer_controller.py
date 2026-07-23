from __future__ import annotations

from app.database.connection import db
from app.controllers.auth_controller import AuthController


class CustomerController:
    @staticmethod
    def get_all() -> list[dict]:
        return db.fetchall("SELECT * FROM customers ORDER BY name")

    @staticmethod
    def search(text: str) -> list[dict]:
        q = f"%{text}%"
        return db.fetchall(
            "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
            (q, q),
        )

    @staticmethod
    def get_by_id(customer_id: int) -> dict | None:
        return db.fetchone("SELECT * FROM customers WHERE id=?", (customer_id,))

    @staticmethod
    def create(data: dict) -> int:
        cur = db.execute(
            "INSERT INTO customers (name, phone, address, notes) VALUES (?,?,?,?)",
            (data["name"], data.get("phone", ""), data.get("address", ""), data.get("notes", "")),
        )
        AuthController.log("CUSTOMER_CREATE", f"Client #{cur.lastrowid} — {data['name']}")
        return cur.lastrowid

    @staticmethod
    def update(customer_id: int, data: dict):
        db.execute(
            f"""UPDATE customers
               SET name=?, phone=?, address=?, notes=?,
                   updated_at={db.current_timestamp_sql()}
               WHERE id=?""",
            (
                data["name"],
                data.get("phone", ""),
                data.get("address", ""),
                data.get("notes", ""),
                customer_id,
            ),
        )
        AuthController.log("CUSTOMER_UPDATE", f"Client #{customer_id}")

    @staticmethod
    def delete(customer_id: int):
        db.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        AuthController.log("CUSTOMER_DELETE", f"Client #{customer_id}")

    @staticmethod
    def add_credit(customer_id: int, amount: float, reason: str = "") -> float:
        customer = CustomerController.get_by_id(int(customer_id))
        if not customer:
            raise ValueError("Client introuvable.")

        amount = round(float(amount or 0.0), 3)
        if amount <= 0:
            return round(float(customer.get("balance") or 0.0), 3)

        new_balance = round(float(customer.get("balance") or 0.0) + amount, 3)
        db.execute(
            f"UPDATE customers SET balance=?, updated_at={db.current_timestamp_sql()} WHERE id=?",
            (new_balance, int(customer_id)),
        )
        AuthController.log("CUSTOMER_CREDIT", f"Client #{customer_id} +{amount:.3f} TND — {reason}")
        return new_balance

    @staticmethod
    def record_payment(customer_id: int, amount: float) -> float:
        customer = CustomerController.get_by_id(int(customer_id))
        if not customer:
            raise ValueError("Client introuvable.")

        amount = round(float(amount or 0.0), 3)
        if amount <= 0:
            return round(float(customer.get("balance") or 0.0), 3)

        from app.controllers.sale_controller import SaleController

        result = SaleController.apply_customer_credit_payment(int(customer_id), amount)
        return round(float(result.get("remaining_balance") or 0.0), 3)

    @staticmethod
    def get_sales_history(customer_id: int) -> list[dict]:
        return db.fetchall(
            """
            SELECT
                s.id,
                s.created_at,
                s.paid_at,
                s.payment_method,
                s.payment_status,
                s.total,
                s.credit_paid,
                ROUND(COALESCE(s.total, 0) - COALESCE(s.credit_paid, 0), 3) AS remaining_due,
                s.notes,
                (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id=s.id) AS item_count
            FROM sales s
            WHERE s.customer_id=?
              AND COALESCE(s.status, 'completed')='completed'
            ORDER BY s.created_at DESC, s.id DESC
            """,
            (int(customer_id),),
        )

    @staticmethod
    def get_payment_history(customer_id: int) -> list[dict]:
        payments = db.fetchall(
            """
            SELECT
                ccp.id,
                ccp.customer_id,
                ccp.amount,
                ccp.notes,
                ccp.created_at
            FROM customer_credit_payments ccp
            WHERE ccp.customer_id=?
            ORDER BY ccp.created_at DESC, ccp.id DESC
            """,
            (int(customer_id),),
        )
        for payment in payments:
            payment["allocations"] = db.fetchall(
                """
                SELECT
                    sp.sale_id,
                    sp.amount,
                    s.created_at AS sale_created_at,
                    s.total AS sale_total
                FROM sale_payments sp
                JOIN sales s ON s.id=sp.sale_id
                WHERE sp.customer_payment_id=?
                ORDER BY sp.id ASC
                """,
                (int(payment["id"]),),
            )
        return payments


    @staticmethod
    def get_sale_details(customer_id: int, sale_id: int) -> dict:
        from app.controllers.sale_controller import SaleController

        sale = SaleController.get_by_id(int(sale_id))
        if not sale or int(sale.get("customer_id") or 0) != int(customer_id):
            raise ValueError("Facture client introuvable.")

        total = round(float(sale.get("total") or 0.0), 3)
        credit_paid = round(float(sale.get("credit_paid") or 0.0), 3)
        amount_paid = round(float(sale.get("amount_paid") or 0.0), 3)
        payment_method = str(sale.get("payment_method") or "").strip().lower()

        if payment_method == "credit":
            paid_value = credit_paid
        else:
            paid_value = amount_paid if amount_paid > 0 else total

        sale["remaining_due"] = round(max(0.0, total - credit_paid), 3)
        sale["paid_value"] = round(max(0.0, paid_value), 3)
        return sale

    @staticmethod
    def get_history(customer_id: int) -> dict:
        customer = CustomerController.get_by_id(int(customer_id))
        if not customer:
            raise ValueError("Client introuvable.")

        sales = CustomerController.get_sales_history(int(customer_id))
        payments = CustomerController.get_payment_history(int(customer_id))

        total_sales = round(sum(float(s.get("total") or 0.0) for s in sales), 3)
        total_credit_sales = round(
            sum(
                float(s.get("total") or 0.0)
                for s in sales
                if str(s.get("payment_method") or "").strip().lower() == "credit"
            ),
            3,
        )
        total_paid = round(sum(float(p.get("amount") or 0.0) for p in payments), 3)
        remaining_due = round(sum(float(s.get("remaining_due") or 0.0) for s in sales), 3)

        return {
            "customer": customer,
            "sales": sales,
            "payments": payments,
            "summary": {
                "sales_count": len(sales),
                "payments_count": len(payments),
                "total_sales": total_sales,
                "total_credit_sales": total_credit_sales,
                "total_paid": total_paid,
                "remaining_due": remaining_due,
            },
        }
