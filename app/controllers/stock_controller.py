from __future__ import annotations
from app.database.connection import db
from app.controllers.auth_controller import AuthController
from app.controllers.product_controller import ProductController


class StockController:

    @staticmethod
    def adjust_stock(product_id: int, new_quantity: float, notes: str = "Ajustement inventaire"):
        product = ProductController.get_by_id(product_id)
        if not product:
            raise ValueError("Produit introuvable.")
        delta = new_quantity - product["stock_quantity"]
        ProductController.update_stock(product_id, delta, "adjustment", notes)
        AuthController.log("STOCK_ADJUST", f"Stock ajusté: produit id={product_id} | {product['stock_quantity']} -> {new_quantity}")

    @staticmethod
    def add_stock(product_id: int, quantity: float, notes: str = "", reference: str = ""):
        if quantity <= 0:
            raise ValueError("La quantité doit être positive.")
        db.execute(
            f"UPDATE products SET stock_quantity=stock_quantity+?, updated_at={db.current_timestamp_sql()} WHERE id=?",
            (quantity, product_id),
        )
        db.execute("""
            INSERT INTO stock_movements (product_id, user_id, movement_type, quantity, reference, notes)
            VALUES (?,?,?,?,?,?)
        """, (product_id, AuthController.current_user()["id"], "in", quantity, reference, notes))
        AuthController.log("STOCK_IN", f"Entrée stock: produit id={product_id}, qté={quantity}")

    @staticmethod
    def get_movements(product_id: int = None, limit: int = 100) -> list[dict]:
        if product_id:
            return db.fetchall("""
                SELECT sm.*, p.name AS product_name, u.full_name AS user_name
                FROM stock_movements sm
                JOIN products p ON p.id=sm.product_id
                JOIN users u ON u.id=sm.user_id
                WHERE sm.product_id=?
                ORDER BY sm.created_at DESC LIMIT ?
            """, (product_id, limit))
        return db.fetchall("""
            SELECT sm.*, p.name AS product_name, u.full_name AS user_name
            FROM stock_movements sm
            JOIN products p ON p.id=sm.product_id
            JOIN users u ON u.id=sm.user_id
            ORDER BY sm.created_at DESC LIMIT ?
        """, (limit,))

    @staticmethod
    def get_inventory_value() -> dict:
        row = db.fetchone("""
            SELECT
                COALESCE(SUM(stock_quantity * purchase_price), 0) AS purchase_value,
                COALESCE(SUM(stock_quantity * sale_price), 0) AS sale_value,
                COUNT(*) AS product_count,
                SUM(CASE WHEN stock_quantity <= min_stock THEN 1 ELSE 0 END) AS low_stock_count
            FROM products WHERE is_active=1
        """)
        return row or {}
