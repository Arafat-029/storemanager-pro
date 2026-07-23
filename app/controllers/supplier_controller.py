from __future__ import annotations

from app.controllers.auth_controller import AuthController
from app.database.connection import db


def _conn_execute(conn, query: str, params: tuple = ()):
    translated = db._translate_placeholders(query)
    if db.is_mysql():
        cursor = conn.cursor()
        cursor.execute(translated, params)
        return cursor
    return conn.execute(translated, params)


def _conn_executemany(conn, query: str, params_list: list[tuple]):
    translated = db._translate_placeholders(query)
    if db.is_mysql():
        cursor = conn.cursor()
        cursor.executemany(translated, params_list)
        return cursor
    return conn.executemany(translated, params_list)


def _conn_begin(conn):
    if db.is_mysql():
        conn.begin()
    else:
        conn.execute("BEGIN")


class SupplierController:
    @staticmethod
    def get_all() -> list[dict]:
        suppliers = db.fetchall("SELECT * FROM suppliers ORDER BY name")
        for supplier in suppliers:
            supplier.update(SupplierController.get_balance(supplier["id"]))
        return suppliers

    @staticmethod
    def get_by_id(sup_id: int) -> dict | None:
        return db.fetchone("SELECT * FROM suppliers WHERE id=?", (sup_id,))

    @staticmethod
    def create(data: dict) -> int:
        cur = db.execute(
            "INSERT INTO suppliers (name, phone, email, address, notes) VALUES (?,?,?,?,?)",
            (data["name"], data.get("phone"), data.get("email"), data.get("address"), data.get("notes")),
        )
        AuthController.log("SUPPLIER_CREATE", f"Fournisseur créé: {data['name']}")
        return cur.lastrowid

    @staticmethod
    def update(sup_id: int, data: dict):
        db.execute(
            "UPDATE suppliers SET name=?, phone=?, email=?, address=?, notes=? WHERE id=?",
            (data["name"], data.get("phone"), data.get("email"), data.get("address"), data.get("notes"), sup_id),
        )
        AuthController.log("SUPPLIER_UPDATE", f"Fournisseur modifié: id={sup_id}")

    @staticmethod
    def delete(sup_id: int):
        db.execute("DELETE FROM suppliers WHERE id=?", (sup_id,))
        AuthController.log("SUPPLIER_DELETE", f"Fournisseur supprimé: id={sup_id}")

    @staticmethod
    def get_products_for_supplier(supplier_id: int) -> list[dict]:
        return db.fetchall(
            """
            SELECT p.id,
                   p.name,
                   p.barcode,
                   p.purchase_price,
                   p.sale_price,
                   p.stock_quantity,
                   p.unit_type,
                   COALESCE(s.name, '') AS supplier_name,
                   COALESCE((
                       SELECT MAX(psu.quantity)
                       FROM product_sale_units psu
                       WHERE psu.product_id = p.id
                         AND psu.is_active=1
                         AND psu.quantity > 1
                   ), 0) AS pack_quantity
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.is_active=1 AND p.supplier_id=?
            ORDER BY p.name
            """,
            (supplier_id,),
        )

    @staticmethod
    def get_latest_invoice(supplier_id: int) -> dict | None:
        return db.fetchone(
            """
            SELECT i.*,
                   ROUND(i.amount_total - i.amount_paid, 3) AS remaining_amount,
                   COALESCE((
                       SELECT COUNT(*)
                       FROM supplier_invoice_items sii
                       WHERE sii.invoice_id = i.id
                   ), 0) AS item_count
            FROM supplier_invoices i
            WHERE i.supplier_id=?
            ORDER BY i.created_at DESC, i.id DESC
            LIMIT 1
            """
            ,
            (supplier_id,),
        )

    @staticmethod
    def _current_user_id() -> int:
        user = AuthController.current_user()
        if user and user.get("id"):
            return int(user["id"])

        fallback = db.fetchone("SELECT id FROM users ORDER BY id LIMIT 1")
        if fallback and fallback.get("id"):
            return int(fallback["id"])
        raise ValueError("Aucun utilisateur connecté.")

    @staticmethod
    def create_stock_invoice(
        supplier_id: int,
        items: list[dict] | None,
        amount_paid: float = 0.0,
        reference: str | None = None,
        notes: str | None = None,
    ) -> dict:
        normalized = SupplierController._normalize_invoice_items(supplier_id, items)
        if not normalized:
            raise ValueError("Ajoutez au moins un produit avec une quantité supérieure à 0.")

        amount_total = round(sum(float(row["line_total"]) for row in normalized), 3)
        amount_paid = round(float(amount_paid or 0.0), 3)

        if amount_total <= 0:
            raise ValueError("Le montant total de la facture doit être supérieur à 0.")
        if amount_paid < 0:
            raise ValueError("Le montant payé doit être positif.")
        if amount_paid > amount_total:
            raise ValueError("Le montant payé ne peut pas dépasser le total de la facture.")

        supplier = SupplierController.get_by_id(supplier_id)
        if not supplier:
            raise ValueError("Fournisseur introuvable.")

        user_id = SupplierController._current_user_id()
        invoice_reference = reference or None
        stock_notes = notes or f"Facture fournisseur : {supplier['name']}"

        conn = db.get_connection()

        try:
            _conn_begin(conn)

            cur = _conn_execute(conn,
                """
                INSERT INTO supplier_invoices (supplier_id, reference, amount_total, amount_paid, notes)
                VALUES (?,?,?,?,?)
                """
                ,
                (supplier_id, invoice_reference, amount_total, 0.0, notes),
            )
            invoice_id = cur.lastrowid

            _conn_executemany(conn,
                """
                INSERT INTO supplier_invoice_items
                    (invoice_id, product_id, product_name, supplier_name, quantity, unit_price, line_total)
                VALUES (?,?,?,?,?,?,?)
                """
                ,
                [
                    (
                        invoice_id,
                        row["product_id"],
                        row["product_name"],
                        row["supplier_name"],
                        row["quantity"],
                        row["unit_price"],
                        row["line_total"],
                    )
                    for row in normalized
                ],
            )

            if amount_paid > 0:
                _conn_execute(conn,
                    """
                    INSERT INTO supplier_invoice_payments (invoice_id, supplier_id, amount, reference, notes)
                    VALUES (?,?,?,?,?)
                    """
                    ,
                    (invoice_id, supplier_id, amount_paid, invoice_reference, notes),
                )
                _conn_execute(conn,
                    f"""
                    UPDATE supplier_invoices
                    SET amount_paid=?, updated_at={db.current_timestamp_sql()}
                    WHERE id=?
                    """
                    ,
                    (amount_paid, invoice_id),
                )

            for row in normalized:
                product_id = row["product_id"]
                quantity = round(float(row["quantity"]), 3)
                unit_price = round(float(row["unit_price"]), 3)

                _conn_execute(conn,
                    f"""
                    UPDATE products
                    SET stock_quantity=stock_quantity + ?,
                        purchase_price=CASE WHEN ? > 0 THEN ? ELSE purchase_price END,
                        updated_at={db.current_timestamp_sql()}
                    WHERE id=?
                    """
                    ,
                    (quantity, unit_price, unit_price, product_id),
                )
                _conn_execute(conn,
                    """
                    INSERT INTO stock_movements (product_id, user_id, movement_type, quantity, reference, notes)
                    VALUES (?,?,?,?,?,?)
                    """
                    ,
                    (product_id, user_id, "in", quantity, invoice_reference, stock_notes),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        AuthController.log("SUPPLIER_INVOICE_CREATE", f"Facture fournisseur créée: id={invoice_id}")
        if amount_paid > 0:
            AuthController.log("SUPPLIER_INVOICE_PAYMENT", f"Paiement facture fournisseur: facture={invoice_id}, montant={amount_paid}")
        AuthController.log("STOCK_IN", f"Entrée stock depuis facture fournisseur: facture={invoice_id}, lignes={len(normalized)}")

        return {
            "invoice_id": invoice_id,
            "amount_total": amount_total,
            "amount_paid": amount_paid,
            "remaining_amount": round(amount_total - amount_paid, 3),
            "item_count": len(normalized),
        }

    @staticmethod
    def _normalize_invoice_items(supplier_id: int, items: list[dict] | None) -> list[dict]:
        items = items or []
        product_map = {
            row["id"]: row
            for row in SupplierController.get_products_for_supplier(supplier_id)
        }
        normalized: list[dict] = []

        for raw in items:
            product_id = raw.get("product_id")
            product = product_map.get(product_id)
            product_name = (raw.get("product_name") or "").strip() or (product["name"] if product else "")
            supplier_name = (raw.get("supplier_name") or "").strip()
            quantity = round(float(raw.get("quantity") or 0.0), 3)
            unit_price = round(float(raw.get("unit_price") or 0.0), 3)

            if quantity <= 0 or unit_price < 0:
                continue
            if not product_name:
                raise ValueError("Chaque ligne de facture doit avoir un produit valide.")

            normalized.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "supplier_name": supplier_name or (product["supplier_name"] if product else ""),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": round(quantity * unit_price, 3),
                }
            )

        return normalized

    @staticmethod
    def _replace_invoice_items(invoice_id: int, supplier_id: int, items: list[dict] | None):
        normalized = SupplierController._normalize_invoice_items(supplier_id, items)
        db.execute("DELETE FROM supplier_invoice_items WHERE invoice_id=?", (invoice_id,))
        if normalized:
            db.executemany(
                """
                INSERT INTO supplier_invoice_items
                    (invoice_id, product_id, product_name, supplier_name, quantity, unit_price, line_total)
                VALUES (?,?,?,?,?,?,?)
                """,
                [
                    (
                        invoice_id,
                        row["product_id"],
                        row["product_name"],
                        row["supplier_name"],
                        row["quantity"],
                        row["unit_price"],
                        row["line_total"],
                    )
                    for row in normalized
                ],
            )

    @staticmethod
    def add_invoice(supplier_id: int, amount: float, reference: str = None, notes: str = None):
        return SupplierController.create_invoice(supplier_id, amount, reference=reference, notes=notes)

    @staticmethod
    def create_invoice(
        supplier_id: int,
        amount: float,
        reference: str | None = None,
        notes: str | None = None,
        items: list[dict] | None = None,
    ) -> int:
        amount = round(float(amount), 3)
        if amount <= 0:
            raise ValueError("Le montant de la facture doit être supérieur à 0.")
        cur = db.execute(
            """
            INSERT INTO supplier_invoices (supplier_id, reference, amount_total, amount_paid, notes)
            VALUES (?,?,?,?,?)
            """,
            (supplier_id, reference, amount, 0.0, notes),
        )
        invoice_id = cur.lastrowid
        SupplierController._replace_invoice_items(invoice_id, supplier_id, items)
        AuthController.log("SUPPLIER_INVOICE_CREATE", f"Facture fournisseur créée: id={invoice_id}")
        return invoice_id

    @staticmethod
    def update_invoice(invoice_id: int, data: dict):
        invoice = SupplierController.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Facture introuvable.")

        amount_total = round(float(data["amount_total"]), 3)
        if amount_total <= 0:
            raise ValueError("Le montant de la facture doit être supérieur à 0.")
        if amount_total < round(float(invoice["amount_paid"]), 3):
            raise ValueError("Le montant total ne peut pas être inférieur au montant déjà payé.")

        db.execute(
            f"""
            UPDATE supplier_invoices
            SET reference=?, amount_total=?, notes=?, updated_at={db.current_timestamp_sql()}
            WHERE id=?
            """,
            (data.get("reference"), amount_total, data.get("notes"), invoice_id),
        )

        if "items" in data:
            SupplierController._replace_invoice_items(invoice_id, invoice["supplier_id"], data.get("items"))

        AuthController.log("SUPPLIER_INVOICE_UPDATE", f"Facture fournisseur modifiée: id={invoice_id}")

    @staticmethod
    def delete_invoice(invoice_id: int):
        invoice = SupplierController.get_invoice(invoice_id)
        if not invoice:
            return
        db.execute("DELETE FROM supplier_invoices WHERE id=?", (invoice_id,))
        AuthController.log("SUPPLIER_INVOICE_DELETE", f"Facture fournisseur supprimée: id={invoice_id}")

    @staticmethod
    def get_invoice(invoice_id: int) -> dict | None:
        row = db.fetchone(
            """
            SELECT i.*,
                   s.name AS supplier_name,
                   ROUND(i.amount_total - i.amount_paid, 3) AS remaining_amount,
                   COALESCE((
                       SELECT COUNT(*)
                       FROM supplier_invoice_items sii
                       WHERE sii.invoice_id = i.id
                   ), 0) AS item_count
            FROM supplier_invoices i
            LEFT JOIN suppliers s ON s.id = i.supplier_id
            WHERE i.id=?
            """,
            (invoice_id,),
        )
        return row

    @staticmethod
    def get_invoice_items(invoice_id: int) -> list[dict]:
        return db.fetchall(
            """
            SELECT sii.*,
                   COALESCE(p.unit_type, 'piece') AS unit_type
            FROM supplier_invoice_items sii
            LEFT JOIN products p ON p.id = sii.product_id
            WHERE sii.invoice_id=?
            ORDER BY sii.product_name, sii.id
            """,
            (invoice_id,),
        )

    @staticmethod
    def get_supplier_invoices(supplier_id: int) -> list[dict]:
        invoices = db.fetchall(
            """
            SELECT i.*,
                   ROUND(i.amount_total - i.amount_paid, 3) AS remaining_amount,
                   COALESCE((
                       SELECT COUNT(*)
                       FROM supplier_invoice_items sii
                       WHERE sii.invoice_id = i.id
                   ), 0) AS item_count
            FROM supplier_invoices i
            WHERE i.supplier_id=?
            ORDER BY i.created_at DESC, i.id DESC
            """,
            (supplier_id,),
        )
        return invoices

    @staticmethod
    def record_payment(
        supplier_id: int,
        amount: float,
        reference: str = None,
        notes: str = None,
        invoice_id: int | None = None,
    ):
        amount = round(float(amount), 3)
        if amount <= 0:
            raise ValueError("Le montant payé doit être supérieur à 0.")

        if invoice_id:
            SupplierController.record_invoice_payment(invoice_id, amount, reference=reference, notes=notes)
            return

        remaining = amount
        invoices = [
            inv for inv in SupplierController.get_supplier_invoices(supplier_id)
            if float(inv["remaining_amount"]) > 0
        ]
        invoices.sort(key=lambda inv: (inv["created_at"], inv["id"]))

        for invoice in invoices:
            open_amount = round(float(invoice["remaining_amount"]), 3)
            if open_amount <= 0 or remaining <= 0:
                continue
            pay_amount = min(open_amount, remaining)
            SupplierController.record_invoice_payment(invoice["id"], pay_amount, reference=reference, notes=notes)
            remaining = round(remaining - pay_amount, 3)

        if remaining > 0:
            db.execute(
                "INSERT INTO supplier_transactions (supplier_id, type, amount, reference, notes) VALUES (?,?,?,?,?)",
                (supplier_id, "payment", remaining, reference, notes),
            )
            AuthController.log("SUPPLIER_PAYMENT_LEGACY", f"Paiement fournisseur hors facture: {remaining}")

    @staticmethod
    def record_invoice_payment(
        invoice_id: int,
        amount: float,
        reference: str = None,
        notes: str = None,
    ) -> int:
        invoice = SupplierController.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Facture introuvable.")

        amount = round(float(amount), 3)
        remaining = round(float(invoice["remaining_amount"]), 3)
        if amount <= 0:
            raise ValueError("Le montant payé doit être supérieur à 0.")
        if amount > remaining:
            raise ValueError("Le montant payé dépasse le reste à payer de la facture.")

        cur = db.execute(
            """
            INSERT INTO supplier_invoice_payments (invoice_id, supplier_id, amount, reference, notes)
            VALUES (?,?,?,?,?)
            """,
            (invoice_id, invoice["supplier_id"], amount, reference, notes),
        )
        db.execute(
            f"""
            UPDATE supplier_invoices
            SET amount_paid=ROUND(amount_paid + ?, 3),
                updated_at={db.current_timestamp_sql()}
            WHERE id=?
            """,
            (amount, invoice_id),
        )
        AuthController.log("SUPPLIER_INVOICE_PAYMENT", f"Paiement facture fournisseur: facture={invoice_id}, montant={amount}")
        return cur.lastrowid

    @staticmethod
    def get_invoice_payments(invoice_id: int) -> list[dict]:
        return db.fetchall(
            """
            SELECT *
            FROM supplier_invoice_payments
            WHERE invoice_id=?
            ORDER BY created_at DESC, id DESC
            """,
            (invoice_id,),
        )

    @staticmethod
    def get_transactions(supplier_id: int) -> list[dict]:
        legacy = db.fetchall(
            """
            SELECT id, supplier_id, type, amount, reference, notes, created_at, 'legacy' AS source
            FROM supplier_transactions
            WHERE supplier_id=?
            """,
            (supplier_id,),
        )
        invoices = db.fetchall(
            """
            SELECT i.id,
                   i.supplier_id,
                   'invoice' AS type,
                   i.amount_total AS amount,
                   i.reference,
                   CASE
                       WHEN COALESCE(i.notes, '') = '' THEN NULL
                       ELSE i.notes
                   END AS notes,
                   i.created_at,
                   'invoice' AS source
            FROM supplier_invoices i
            WHERE i.supplier_id=?
            """,
            (supplier_id,),
        )
        payments = db.fetchall(
            """
            SELECT p.id,
                   p.supplier_id,
                   'payment' AS type,
                   p.amount,
                   COALESCE(p.reference, i.reference) AS reference,
                   CASE
                       WHEN COALESCE(p.notes, '') = '' AND COALESCE(i.reference, '') = '' THEN NULL
                       WHEN COALESCE(p.notes, '') = '' THEN 'Facture : ' || i.reference
                       WHEN COALESCE(i.reference, '') = '' THEN p.notes
                       ELSE p.notes || ' • Facture : ' || i.reference
                   END AS notes,
                   p.created_at,
                   'invoice_payment' AS source
            FROM supplier_invoice_payments p
            LEFT JOIN supplier_invoices i ON i.id = p.invoice_id
            WHERE p.supplier_id=?
            """,
            (supplier_id,),
        )
        rows = legacy + invoices + payments
        return sorted(rows, key=lambda row: ((row.get("created_at") or ""), row.get("id") or 0), reverse=True)

    @staticmethod
    def get_balance(supplier_id: int) -> dict:
        legacy = db.fetchone(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type='invoice' THEN amount ELSE 0 END), 0) AS total_invoiced,
                COALESCE(SUM(CASE WHEN type='payment' THEN amount ELSE 0 END), 0) AS total_paid
            FROM supplier_transactions
            WHERE supplier_id=?
            """,
            (supplier_id,),
        ) or {"total_invoiced": 0.0, "total_paid": 0.0}

        modern = db.fetchone(
            """
            SELECT
                COALESCE(SUM(amount_total), 0) AS total_invoiced,
                COALESCE(SUM(amount_paid), 0) AS total_paid
            FROM supplier_invoices
            WHERE supplier_id=?
            """,
            (supplier_id,),
        ) or {"total_invoiced": 0.0, "total_paid": 0.0}

        total_invoiced = round(float(legacy["total_invoiced"]) + float(modern["total_invoiced"]), 3)
        total_paid = round(float(legacy["total_paid"]) + float(modern["total_paid"]), 3)
        return {
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "balance": round(total_invoiced - total_paid, 3),
        }
