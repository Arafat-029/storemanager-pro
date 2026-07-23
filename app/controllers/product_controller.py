from __future__ import annotations

from datetime import datetime, timedelta

from app.database.connection import db
from app.controllers.auth_controller import AuthController


class ProductController:
    _BARCODE_SYMBOL_TO_DIGIT = str.maketrans({
        "&": "1",
        "é": "2",
        '"': "3",
        "'": "4",
        "(": "5",
        "-": "6",
        "è": "7",
        "_": "8",
        "ç": "9",
        "à": "0",
    })

    @staticmethod
    def normalize_barcode(value: str | None) -> str:
        raw = "".join((value or "").split()).casefold()
        translated = raw.translate(ProductController._BARCODE_SYMBOL_TO_DIGIT)
        return "".join(ch for ch in translated if ch.isalnum())

    @staticmethod
    def _base_sale_unit_name(unit_type: str | None) -> str:
        return {
            "piece": "Pièce",
            "kg": "Kg",
            "litre": "Litre",
        }.get((unit_type or "piece").strip().lower(), "Unité")

    @staticmethod
    def get_or_create_default_supplier_id() -> int:
        row = db.fetchone(
            "SELECT id FROM suppliers WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1",
            ("Autres",),
        )
        if row:
            return int(row["id"])
        cur = db.execute(
            "INSERT INTO suppliers (name, notes) VALUES (?,?)",
            ("Autres", "Fournisseur par défaut"),
        )
        return int(cur.lastrowid)

    @staticmethod
    def get_or_create_manual_sale_product_id() -> int:
        row = db.fetchone(
            "SELECT id FROM products WHERE barcode=? ORDER BY id LIMIT 1",
            ("__MANUAL_SALE__",),
        )
        if row:
            return int(row["id"])

        supplier_id = ProductController.get_or_create_default_supplier_id()
        cur = db.execute(
            """
            INSERT INTO products (
                barcode, name, supplier_id, purchase_price, sale_price,
                stock_quantity, min_stock, unit_type, description, is_active
            ) VALUES (?,?,?,?,?,?,?,?,?,0)
            """,
            (
                "__MANUAL_SALE__",
                "Article libre caisse",
                supplier_id,
                0.0,
                0.0,
                0.0,
                0.0,
                "piece",
                "Produit technique utilisé pour les lignes libres de caisse.",
            ),
        )
        product_id = int(cur.lastrowid)
        ProductController.replace_sale_units(
            product_id,
            [
                {
                    "name": "Montant libre",
                    "quantity": 1.0,
                    "sale_price": 0.0,
                    "barcode": None,
                    "is_default": True,
                }
            ],
            product_barcode="__MANUAL_SALE__",
            default_sale_price=0.0,
            unit_type="piece",
        )
        return product_id

    @staticmethod
    def _base_product_query(where: str = "", order_sql: str = "ORDER BY p.name") -> str:
        return f"""
            SELECT p.*, c.name AS category_name, c.color AS category_color,
                   s.name AS supplier_name
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            LEFT JOIN suppliers  s ON s.id = p.supplier_id
            {where}
            {order_sql}
        """

    @staticmethod
    def get_all(include_inactive: bool = False) -> list[dict]:
        where = "" if include_inactive else "WHERE p.is_active=1"
        return db.fetchall(ProductController._base_product_query(where))

    @staticmethod
    def get_by_id(product_id: int) -> dict | None:
        product = db.fetchone(
            ProductController._base_product_query("WHERE p.id=?"),
            (product_id,),
        )
        if product:
            product["sale_units"] = ProductController.get_sale_units(int(product["id"]))
        return product

    @staticmethod
    def get_sale_units(product_id: int, active_only: bool = True) -> list[dict]:
        cond = "AND is_active=1" if active_only else ""
        return db.fetchall(
            f"""
            SELECT *
            FROM product_sale_units
            WHERE product_id=? {cond}
            ORDER BY is_default DESC, quantity ASC, id ASC
            """,
            (product_id,),
        )

    @staticmethod
    def _normalize_sale_units(
        sale_units: list[dict] | None,
        *,
        product_barcode: str | None,
        default_sale_price: float,
        unit_type: str,
    ) -> list[dict]:
        units: list[dict] = []
        seen_names: set[str] = set()
        seen_barcodes: set[str] = set()

        for index, raw in enumerate(sale_units or []):
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            quantity = round(float(raw.get("quantity") or 0.0), 3)
            sale_price = round(float(raw.get("sale_price") or 0.0), 3)
            if quantity <= 0 or sale_price < 0:
                continue

            barcode = str(raw.get("barcode") or "").strip() or None
            normalized_name = name.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"Unité dupliquée : {name}")
            seen_names.add(normalized_name)

            if barcode:
                normalized_barcode = ProductController.normalize_barcode(barcode)
                if normalized_barcode in seen_barcodes:
                    raise ValueError(f"Code-barres dupliqué : {barcode}")
                seen_barcodes.add(normalized_barcode)

            units.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "sale_price": sale_price,
                    "barcode": barcode,
                    "is_default": bool(raw.get("is_default")),
                }
            )

        if not units:
            units = [
                {
                    "name": ProductController._base_sale_unit_name(unit_type),
                    "quantity": 1.0,
                    "sale_price": round(float(default_sale_price or 0.0), 3),
                    "barcode": None,
                    "is_default": True,
                }
            ]

        if not any(unit["is_default"] for unit in units):
            units[0]["is_default"] = True

        default_found = False
        for unit in units:
            if unit["is_default"] and not default_found:
                default_found = True
                continue
            unit["is_default"] = False

        if units[0]["sale_price"] <= 0 and round(float(default_sale_price or 0.0), 3) > 0:
            units[0]["sale_price"] = round(float(default_sale_price or 0.0), 3)

        return units

    @staticmethod
    def replace_sale_units(
        product_id: int,
        sale_units: list[dict] | None,
        *,
        product_barcode: str | None = None,
        default_sale_price: float | None = None,
        unit_type: str | None = None,
    ) -> None:
        product = ProductController.get_by_id(product_id)
        unit_type = unit_type or (product or {}).get("unit_type") or "piece"
        default_sale_price = round(float(default_sale_price if default_sale_price is not None else (product or {}).get("sale_price") or 0.0), 3)
        normalized = ProductController._normalize_sale_units(
            sale_units,
            product_barcode=product_barcode or (product or {}).get("barcode"),
            default_sale_price=default_sale_price,
            unit_type=unit_type,
        )

        db.execute("DELETE FROM product_sale_units WHERE product_id=?", (product_id,))
        rows = [
            (
                product_id,
                unit["name"],
                unit["quantity"],
                unit["sale_price"],
                unit.get("barcode"),
                1 if unit["is_default"] else 0,
                1,
            )
            for unit in normalized
        ]
        db.executemany(
            """
            INSERT INTO product_sale_units (
                product_id, name, quantity, sale_price, barcode, is_default, is_active
            ) VALUES (?,?,?,?,?,?,?)
            """,
            rows,
        )

    @staticmethod
    def ensure_default_sale_unit(product_id: int) -> None:
        product = ProductController.get_by_id(product_id)
        if not product:
            return
        ProductController.replace_sale_units(
            product_id,
            product.get("sale_units") or [],
            product_barcode=product.get("barcode"),
            default_sale_price=float(product.get("sale_price") or 0.0),
            unit_type=str(product.get("unit_type") or "piece"),
        )

    @staticmethod
    def get_default_sale_unit(product_id: int) -> dict | None:
        row = db.fetchone(
            """
            SELECT *
            FROM product_sale_units
            WHERE product_id=? AND is_active=1
            ORDER BY is_default DESC, quantity ASC, id ASC
            LIMIT 1
            """,
            (product_id,),
        )
        return row

    @staticmethod
    def get_sale_unit_by_id(sale_unit_id: int) -> dict | None:
        return db.fetchone("SELECT * FROM product_sale_units WHERE id=?", (sale_unit_id,))

    @staticmethod
    def apply_sale_unit(product: dict, sale_unit: dict | None) -> dict:
        applied = dict(product)
        if not sale_unit:
            return applied
        applied["selected_sale_unit_id"] = sale_unit.get("id")
        applied["selected_sale_unit_name"] = sale_unit.get("name")
        applied["selected_sale_unit_quantity"] = float(sale_unit.get("quantity") or 1.0)
        applied["selected_sale_unit_price"] = float(sale_unit.get("sale_price") or product.get("sale_price") or 0.0)
        if sale_unit.get("barcode"):
            applied["selected_sale_unit_barcode"] = sale_unit.get("barcode")
        return applied

    @staticmethod
    def get_by_barcode(barcode: str) -> dict | None:
        normalized = ProductController.normalize_barcode(barcode)
        if not normalized:
            return None

        product = db.fetchone(
            ProductController._base_product_query(
                "WHERE lower(replace(trim(coalesce(p.barcode, '')), ' ', '')) = ? AND p.is_active=1"
            ),
            (normalized,),
        )
        if product:
            default_unit = ProductController.get_default_sale_unit(int(product["id"]))
            return ProductController.apply_sale_unit(product, default_unit)

        product_rows = db.fetchall(
            ProductController._base_product_query(
                "WHERE p.is_active=1 AND p.barcode IS NOT NULL AND trim(p.barcode) <> ''"
            )
        )
        for product in product_rows:
            product_barcode = ProductController.normalize_barcode(product.get("barcode"))
            if product_barcode and (
                product_barcode == normalized
                or normalized.endswith(product_barcode)
                or product_barcode.endswith(normalized)
            ):
                default_unit = ProductController.get_default_sale_unit(int(product["id"]))
                return ProductController.apply_sale_unit(product, default_unit)

        unit = db.fetchone(
            """
            SELECT psu.*, p.id AS product_id
            FROM product_sale_units psu
            JOIN products p ON p.id = psu.product_id
            WHERE p.is_active=1
              AND psu.is_active=1
              AND lower(replace(trim(coalesce(psu.barcode, '')), ' ', '')) = ?
            ORDER BY psu.id
            LIMIT 1
            """,
            (normalized,),
        )
        if not unit:
            units = db.fetchall(
                """
                SELECT psu.*, p.id AS product_id
                FROM product_sale_units psu
                JOIN products p ON p.id = psu.product_id
                WHERE p.is_active=1 AND psu.is_active=1
                  AND psu.barcode IS NOT NULL AND trim(psu.barcode) <> ''
                """
            )
            for row in units:
                unit_barcode = ProductController.normalize_barcode(row.get("barcode"))
                if not unit_barcode:
                    continue
                if unit_barcode == normalized or normalized.endswith(unit_barcode) or unit_barcode.endswith(normalized):
                    unit = row
                    break

        if unit:
            product = ProductController.get_by_id(int(unit["product_id"]))
            if product:
                return ProductController.apply_sale_unit(product, unit)

        return None

    @staticmethod
    def get_by_category(category_id: int) -> list[dict]:
        return db.fetchall(
            ProductController._base_product_query(
                "WHERE p.is_active=1 AND p.category_id=?",
            ),
            (category_id,),
        )

    @staticmethod
    def search(query: str) -> list[dict]:
        q = f"%{query}%"
        return db.fetchall(
            ProductController._base_product_query(
                """
                WHERE p.is_active=1
                  AND (
                    p.name LIKE ? OR p.barcode LIKE ? OR c.name LIKE ? OR s.name LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM product_sale_units psu
                        WHERE psu.product_id = p.id AND psu.is_active=1
                          AND (psu.name LIKE ? OR psu.barcode LIKE ?)
                    )
                  )
                """
            ),
            (q, q, q, q, q, q),
        )

    @staticmethod
    def create(data: dict) -> int:
        supplier_id = data.get("supplier_id") or ProductController.get_or_create_default_supplier_id()
        cur = db.execute(
            """
            INSERT INTO products
                (barcode, name, category_id, supplier_id, purchase_price, sale_price,
                 stock_quantity, min_stock, unit_type, expiry_date, description, image_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data.get("barcode"),
                data["name"],
                data.get("category_id"),
                supplier_id,
                data.get("purchase_price", 0),
                data["sale_price"],
                data.get("stock_quantity", 0),
                data.get("min_stock", 5),
                data.get("unit_type", "piece"),
                data.get("expiry_date"),
                data.get("description"),
                data.get("image_path"),
            ),
        )
        product_id = int(cur.lastrowid)
        ProductController.replace_sale_units(
            product_id,
            data.get("sale_units") or [],
            product_barcode=data.get("barcode"),
            default_sale_price=float(data.get("sale_price", 0) or 0.0),
            unit_type=str(data.get("unit_type") or "piece"),
        )
        AuthController.log("PRODUCT_CREATE", f"Produit créé: {data['name']} (id={product_id})")
        if data.get("stock_quantity", 0) > 0:
            db.execute(
                """
                INSERT INTO stock_movements (product_id, user_id, movement_type, quantity, notes)
                VALUES (?,?,?,?,?)
                """,
                (product_id, AuthController.current_user()["id"], "in", data["stock_quantity"], "Stock initial"),
            )
        return product_id

    @staticmethod
    def update(product_id: int, data: dict):
        supplier_id = data.get("supplier_id") or ProductController.get_or_create_default_supplier_id()
        db.execute(
            f"""
            UPDATE products SET
                barcode=?, name=?, category_id=?, supplier_id=?,
                purchase_price=?, sale_price=?, min_stock=?, unit_type=?,
                expiry_date=?, description=?, image_path=?,
                updated_at={db.current_timestamp_sql()}
            WHERE id=?
            """,
            (
                data.get("barcode"),
                data["name"],
                data.get("category_id"),
                supplier_id,
                data.get("purchase_price", 0),
                data["sale_price"],
                data.get("min_stock", 5),
                data.get("unit_type", "piece"),
                data.get("expiry_date"),
                data.get("description"),
                data.get("image_path"),
                product_id,
            ),
        )
        ProductController.replace_sale_units(
            product_id,
            data.get("sale_units") or ProductController.get_sale_units(product_id, active_only=False),
            product_barcode=data.get("barcode"),
            default_sale_price=float(data.get("sale_price", 0) or 0.0),
            unit_type=str(data.get("unit_type") or "piece"),
        )
        AuthController.log("PRODUCT_UPDATE", f"Produit modifié: id={product_id}")

    @staticmethod
    def delete(product_id: int):
        db.execute("UPDATE products SET is_active=0 WHERE id=?", (product_id,))
        db.execute("UPDATE product_sale_units SET is_active=0 WHERE product_id=?", (product_id,))
        AuthController.log("PRODUCT_DELETE", f"Produit supprimé: id={product_id}")

    @staticmethod
    def update_stock(product_id: int, quantity_delta: float, movement_type: str, notes: str = ""):
        db.execute(
            f"UPDATE products SET stock_quantity=stock_quantity+?, updated_at={db.current_timestamp_sql()} WHERE id=?",
            (quantity_delta, product_id),
        )
        user_id = AuthController.current_user()["id"]
        db.execute(
            """
            INSERT INTO stock_movements (product_id, user_id, movement_type, quantity, notes)
            VALUES (?,?,?,?,?)
            """,
            (product_id, user_id, movement_type, abs(quantity_delta), notes),
        )

    @staticmethod
    def get_low_stock() -> list[dict]:
        return db.fetchall(
            """
            SELECT p.*, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON c.id=p.category_id
            WHERE p.is_active=1 AND p.stock_quantity <= p.min_stock
            ORDER BY p.stock_quantity
            """
        )

    @staticmethod
    def get_expiring_soon(days: int = 7) -> list[dict]:
        deadline = (datetime.now().date() + timedelta(days=max(0, int(days)))).isoformat()
        return db.fetchall(
            """
            SELECT * FROM products
            WHERE is_active=1 AND expiry_date IS NOT NULL
              AND DATE(expiry_date) <= ?
            ORDER BY expiry_date
            """,
            (deadline,),
        )
