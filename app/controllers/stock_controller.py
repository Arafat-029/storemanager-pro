from __future__ import annotations
from datetime import date, datetime, timedelta

from app.database.connection import db
from app.controllers.auth_controller import AuthController
from app.controllers.product_controller import ProductController

# Reasons a product can leave the stock without being sold. Stored as the key
# in stock_movements.loss_reason so totals stay groupable; the label is what
# the admin sees.
LOSS_REASONS: list[tuple[str, str]] = [
    ("expired", "Périmé"),
    ("broken", "Cassé"),
    ("damaged", "Endommagé"),
    ("destroyed", "Détruit"),
    ("lost", "Perdu"),
    ("other", "Autre"),
]
LOSS_REASON_LABELS = dict(LOSS_REASONS)

# A product expiring within this many days is worth flagging on arrival.
EXPIRY_WARNING_DAYS = 15
# "Short shelf life" threshold for a category, in days.
SHORT_SHELF_LIFE_DAYS = 15
# Only for sensitive categories: receiving more than this multiple of what is
# already in stock is worth a second look. Applied to sensitive goods only —
# on shelf-stable products a large restock is routine, and an alert that fires
# on routine events stops being read.
OVERSTOCK_FACTOR = 3.0


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:len(fmt) + 2].strip(), fmt).date()
        except ValueError:
            continue
    return None


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
        # The quantity and its movement record must land together, or the
        # stock history stops explaining the stock figure.
        with db.transaction():
            db.execute(
                f"UPDATE products SET stock_quantity=stock_quantity+?, updated_at={db.current_timestamp_sql()} WHERE id=?",
                (quantity, product_id),
            )
            db.execute("""
                INSERT INTO stock_movements (product_id, user_id, movement_type, quantity, reference, notes)
                VALUES (?,?,?,?,?,?)
            """, (product_id, AuthController.current_user()["id"], "in", quantity, reference, notes))
        AuthController.log("STOCK_IN", f"Entrée stock: produit id={product_id}, qté={quantity}")

    # ── Reception checks ──────────────────────────────────────────────────

    @staticmethod
    def check_reception(items: list[dict] | None) -> list[dict]:
        """Warnings worth showing before a delivery is added to the stock.

        Purely informative — this reads nothing but the products being
        received and never changes anything. `items` uses the same shape the
        supplier-invoice code already passes around: product_id + quantity.

        Each warning is {product_name, messages, suggested_expiry}, where
        suggested_expiry is filled only when the category declares a shelf
        life, so the caller can offer to set the product's expiry date.
        """
        warnings: list[dict] = []
        today = date.today()

        for raw in items or []:
            product_id = raw.get("product_id")
            if not product_id:
                continue
            quantity = float(raw.get("quantity") or 0.0)
            if quantity <= 0:
                continue

            product = db.fetchone(
                """
                SELECT p.name, p.stock_quantity, p.expiry_date, p.unit_type,
                       c.name AS category_name, c.is_sensitive, c.shelf_life_days
                FROM products p
                LEFT JOIN categories c ON c.id = p.category_id
                WHERE p.id = ?
                """,
                (product_id,),
            )
            if not product:
                continue

            is_sensitive = bool(product.get("is_sensitive"))
            shelf_life = product.get("shelf_life_days")
            shelf_life = int(shelf_life) if shelf_life else None
            messages: list[str] = []

            if is_sensitive:
                messages.append(
                    f"Catégorie sensible ({product.get('category_name') or 'sans catégorie'}) "
                    "— vérifier l'état et les conditions de conservation."
                )

            if shelf_life and shelf_life <= SHORT_SHELF_LIFE_DAYS:
                messages.append(f"Conservation courte : {shelf_life} jours après réception.")

            expiry = _parse_date(product.get("expiry_date"))
            if expiry:
                days_left = (expiry - today).days
                if days_left < 0:
                    messages.append(
                        f"Date d'expiration dépassée depuis {abs(days_left)} jour(s) "
                        f"({expiry.strftime('%d/%m/%Y')})."
                    )
                elif days_left <= EXPIRY_WARNING_DAYS:
                    messages.append(
                        f"Expiration proche : dans {days_left} jour(s) ({expiry.strftime('%d/%m/%Y')})."
                    )

            # Overstock, sensitive categories only (see OVERSTOCK_FACTOR).
            current_stock = float(product.get("stock_quantity") or 0.0)
            if is_sensitive and current_stock > 0 and quantity > current_stock * OVERSTOCK_FACTOR:
                messages.append(
                    f"Quantité élevée : {quantity:g} reçus pour {current_stock:g} en stock "
                    "— risque de perte avant écoulement."
                )

            if not messages:
                continue

            warnings.append(
                {
                    "product_id": product_id,
                    "product_name": product["name"],
                    "quantity": quantity,
                    "messages": messages,
                    "suggested_expiry": (
                        (today + timedelta(days=shelf_life)).strftime("%Y-%m-%d")
                        if shelf_life else None
                    ),
                }
            )

        return warnings

    @staticmethod
    def apply_suggested_expiry(warnings: list[dict] | None) -> int:
        """Set each product's expiry date to the one its category implies.

        The app stores a single expiry date per product (there is no per-batch
        tracking), so this overwrites it with the incoming delivery's date.
        Called only when the admin explicitly accepts the suggestion.
        """
        updated = 0
        for warning in warnings or []:
            suggested = warning.get("suggested_expiry")
            if not suggested:
                continue
            db.execute(
                f"UPDATE products SET expiry_date=?, updated_at={db.current_timestamp_sql()} WHERE id=?",
                (suggested, warning["product_id"]),
            )
            updated += 1
        if updated:
            AuthController.log("STOCK_EXPIRY_UPDATE", f"Dates d'expiration mises à jour: {updated} produit(s)")
        return updated

    # ── Losses ────────────────────────────────────────────────────────────

    @staticmethod
    def record_loss(product_id: int, quantity: float, reason: str, notes: str = "") -> dict:
        """Remove stock that will never be sold, with a reason, and trace it.

        Recorded as an 'out' movement carrying a loss_reason, so it shows up in
        the existing movement history for free. unit_cost freezes the purchase
        price now, so the loss keeps costing what it cost even if the product's
        price changes later.
        """
        quantity = round(float(quantity or 0.0), 3)
        if quantity <= 0:
            raise ValueError("La quantité doit être supérieure à 0.")
        if reason not in LOSS_REASON_LABELS:
            raise ValueError("Motif de perte invalide.")

        product = ProductController.get_by_id(product_id)
        if not product:
            raise ValueError("Produit introuvable.")

        available = round(float(product["stock_quantity"] or 0.0), 3)
        if quantity > available + 0.0005:
            raise ValueError(
                f"Stock insuffisant : {available:g} en stock, {quantity:g} déclarés en perte."
            )

        unit_cost = round(float(product.get("purchase_price") or 0.0), 3)
        total_cost = round(unit_cost * quantity, 3)
        label = LOSS_REASON_LABELS[reason]

        with db.transaction():
            db.execute(
                f"UPDATE products SET stock_quantity=stock_quantity-?, updated_at={db.current_timestamp_sql()} WHERE id=?",
                (quantity, product_id),
            )
            db.execute(
                """
                INSERT INTO stock_movements
                    (product_id, user_id, movement_type, quantity, reference, notes, loss_reason, unit_cost)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    product_id,
                    AuthController.current_user()["id"],
                    "out",
                    quantity,
                    f"Perte : {label}",
                    notes or None,
                    reason,
                    unit_cost,
                ),
            )

        AuthController.log(
            "STOCK_LOSS",
            f"Perte enregistrée: produit id={product_id}, qté={quantity}, motif={label}, coût={total_cost}",
        )
        return {
            "product_name": product["name"],
            "quantity": quantity,
            "reason_label": label,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "remaining_stock": round(available - quantity, 3),
        }

    @staticmethod
    def get_losses(limit: int = 200) -> list[dict]:
        return db.fetchall(
            """
            SELECT sm.*, p.name AS product_name, u.full_name AS user_name,
                   (sm.quantity * COALESCE(sm.unit_cost, 0)) AS total_cost
            FROM stock_movements sm
            JOIN products p ON p.id = sm.product_id
            JOIN users u ON u.id = sm.user_id
            WHERE sm.loss_reason IS NOT NULL
            ORDER BY sm.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    @staticmethod
    def get_losses_total(start: str | None = None, end: str | None = None) -> float:
        """Cost of everything lost in a period, for the profit calculation."""
        query = (
            "SELECT COALESCE(SUM(quantity * COALESCE(unit_cost, 0)), 0) AS total "
            "FROM stock_movements WHERE loss_reason IS NOT NULL"
        )
        params: list = []
        if start:
            query += " AND created_at >= ?"
            params.append(start)
        if end:
            query += " AND created_at < ?"
            params.append(end)
        row = db.fetchone(query, tuple(params))
        return round(float((row or {}).get("total") or 0.0), 3)

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
