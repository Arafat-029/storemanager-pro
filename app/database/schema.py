from __future__ import annotations

from app.database.connection import db


SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    password    TEXT    NOT NULL,
    full_name   TEXT    NOT NULL,
    role        TEXT    NOT NULL CHECK(role IN ('admin','cashier')),
    email       TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    color       TEXT    DEFAULT '#4CAF50',
    image_path  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode         TEXT    UNIQUE,
    name            TEXT    NOT NULL,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    purchase_price  REAL    NOT NULL DEFAULT 0,
    sale_price      REAL    NOT NULL DEFAULT 0,
    stock_quantity  REAL    NOT NULL DEFAULT 0,
    min_stock       REAL    NOT NULL DEFAULT 5,
    unit_type       TEXT    NOT NULL DEFAULT 'piece' CHECK(unit_type IN ('piece','kg','litre')),
    expiry_date     TEXT,
    description     TEXT,
    image_path      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT,
    address     TEXT,
    balance     REAL    NOT NULL DEFAULT 0,
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    customer_id     INTEGER REFERENCES customers(id),
    subtotal        REAL    NOT NULL DEFAULT 0,
    discount        REAL    NOT NULL DEFAULT 0,
    tax             REAL    NOT NULL DEFAULT 0,
    total           REAL    NOT NULL DEFAULT 0,
    payment_method  TEXT    NOT NULL DEFAULT 'cash',
    payment_status  TEXT    NOT NULL DEFAULT 'paid',
    amount_paid     REAL    NOT NULL DEFAULT 0,
    credit_paid     REAL    NOT NULL DEFAULT 0,
    change_given    REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'completed' CHECK(status IN ('completed','cancelled','refunded')),
    notes           TEXT,
    paid_at         TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id         INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    sale_unit_id    INTEGER REFERENCES product_sale_units(id) ON DELETE SET NULL,
    sale_unit_name  TEXT,
    quantity        REAL    NOT NULL,
    stock_quantity  REAL    NOT NULL DEFAULT 0,
    unit_price      REAL    NOT NULL,
    discount        REAL    NOT NULL DEFAULT 0,
    total           REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    movement_type   TEXT    NOT NULL CHECK(movement_type IN ('in','out','adjustment','return')),
    quantity        REAL    NOT NULL,
    reference       TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    category            TEXT    NOT NULL,
    amount              REAL    NOT NULL,
    description         TEXT,
    recurrence_interval INTEGER,
    recurrence_unit     TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS product_returns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id     INTEGER REFERENCES sales(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    quantity    REAL    NOT NULL,
    amount      REAL    NOT NULL,
    reason      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS user_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    action      TEXT    NOT NULL,
    details     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    `key`       TEXT    NOT NULL UNIQUE,
    value       TEXT,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS supplier_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL CHECK(type IN ('invoice','payment')),
    amount          REAL    NOT NULL,
    reference       TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS supplier_invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    reference       TEXT,
    amount_total    REAL    NOT NULL,
    amount_paid     REAL    NOT NULL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS supplier_invoice_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES supplier_invoices(id) ON DELETE CASCADE,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    amount          REAL    NOT NULL,
    reference       TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS supplier_invoice_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES supplier_invoices(id) ON DELETE CASCADE,
    product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name    TEXT    NOT NULL,
    supplier_name   TEXT,
    quantity        REAL    NOT NULL DEFAULT 0,
    unit_price      REAL    NOT NULL DEFAULT 0,
    line_total      REAL    NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS product_sale_units (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    quantity        REAL    NOT NULL DEFAULT 1,
    sale_price      REAL    NOT NULL DEFAULT 0,
    barcode         TEXT    UNIQUE,
    is_default      INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS customer_credit_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    amount          REAL    NOT NULL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sale_payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id             INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    customer_id         INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    customer_payment_id INTEGER REFERENCES customer_credit_payments(id) ON DELETE SET NULL,
    receiver_user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    payment_method      TEXT    NOT NULL DEFAULT 'cash',
    amount              REAL    NOT NULL DEFAULT 0,
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_stock_movements_prod ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_sup_transactions ON supplier_transactions(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_invoices_supplier ON supplier_invoices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_invoice_payments_invoice ON supplier_invoice_payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_supplier_invoice_payments_supplier ON supplier_invoice_payments(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_invoice_items_invoice ON supplier_invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_product_sale_units_product ON product_sale_units(product_id);
CREATE INDEX IF NOT EXISTS idx_product_sale_units_barcode ON product_sale_units(barcode);
CREATE INDEX IF NOT EXISTS idx_customer_credit_payments_customer ON customer_credit_payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_sale_payments_sale ON sale_payments(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_payments_created ON sale_payments(created_at);
CREATE INDEX IF NOT EXISTS idx_sale_payments_receiver ON sale_payments(receiver_user_id);
"""

MYSQL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(191) NOT NULL UNIQUE,
    password TEXT NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    email VARCHAR(255) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS categories (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(191) NOT NULL UNIQUE,
    description TEXT NULL,
    color VARCHAR(32) DEFAULT '#4CAF50',
    image_path TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS suppliers (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(64) NULL,
    email VARCHAR(255) NULL,
    address TEXT NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    barcode VARCHAR(191) NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    category_id BIGINT NULL,
    supplier_id BIGINT NULL,
    purchase_price DOUBLE NOT NULL DEFAULT 0,
    sale_price DOUBLE NOT NULL DEFAULT 0,
    stock_quantity DOUBLE NOT NULL DEFAULT 0,
    min_stock DOUBLE NOT NULL DEFAULT 5,
    unit_type VARCHAR(32) NOT NULL DEFAULT 'piece',
    expiry_date DATE NULL,
    description TEXT NULL,
    image_path TEXT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    CONSTRAINT fk_products_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS customers (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(64) NULL,
    address TEXT NULL,
    balance DOUBLE NOT NULL DEFAULT 0,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sales (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    subtotal DOUBLE NOT NULL DEFAULT 0,
    discount DOUBLE NOT NULL DEFAULT 0,
    tax DOUBLE NOT NULL DEFAULT 0,
    total DOUBLE NOT NULL DEFAULT 0,
    payment_method VARCHAR(32) NOT NULL DEFAULT 'cash',
    payment_status VARCHAR(32) NOT NULL DEFAULT 'paid',
    amount_paid DOUBLE NOT NULL DEFAULT 0,
    credit_paid DOUBLE NOT NULL DEFAULT 0,
    change_given DOUBLE NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    notes TEXT NULL,
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sales_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_sales_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sale_items (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sale_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sale_unit_id BIGINT NULL,
    sale_unit_name VARCHAR(255) NULL,
    quantity DOUBLE NOT NULL,
    stock_quantity DOUBLE NOT NULL DEFAULT 0,
    unit_price DOUBLE NOT NULL,
    discount DOUBLE NOT NULL DEFAULT 0,
    total DOUBLE NOT NULL,
    CONSTRAINT fk_sale_items_sale FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    CONSTRAINT fk_sale_items_product FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stock_movements (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    movement_type VARCHAR(32) NOT NULL,
    quantity DOUBLE NOT NULL,
    reference VARCHAR(255) NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_stock_movements_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT fk_stock_movements_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expenses (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    category VARCHAR(255) NOT NULL,
    amount DOUBLE NOT NULL,
    description TEXT NULL,
    recurrence_interval INT NULL,
    recurrence_unit VARCHAR(16) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_expenses_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS product_returns (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sale_id BIGINT NULL,
    product_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    quantity DOUBLE NOT NULL,
    amount DOUBLE NOT NULL,
    reason TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_returns_sale FOREIGN KEY (sale_id) REFERENCES sales(id),
    CONSTRAINT fk_returns_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT fk_returns_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_logs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    action VARCHAR(255) NOT NULL,
    details TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_logs_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS settings (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(191) NOT NULL UNIQUE,
    value TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_transactions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    type VARCHAR(32) NOT NULL,
    amount DOUBLE NOT NULL,
    reference VARCHAR(255) NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_supplier_transactions_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_invoices (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    reference VARCHAR(255) NULL,
    amount_total DOUBLE NOT NULL,
    amount_paid DOUBLE NOT NULL DEFAULT 0,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_supplier_invoices_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS product_sale_units (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    quantity DOUBLE NOT NULL DEFAULT 1,
    sale_price DOUBLE NOT NULL DEFAULT 0,
    barcode VARCHAR(191) NULL UNIQUE,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_product_sale_units_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS customer_credit_payments (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount DOUBLE NOT NULL DEFAULT 0,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_customer_credit_payments_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sale_payments (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sale_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    customer_payment_id BIGINT NULL,
    receiver_user_id BIGINT NULL,
    payment_method VARCHAR(32) NOT NULL DEFAULT 'cash',
    amount DOUBLE NOT NULL DEFAULT 0,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sale_payments_sale FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    CONSTRAINT fk_sale_payments_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    CONSTRAINT fk_sale_payments_customer_payment FOREIGN KEY (customer_payment_id) REFERENCES customer_credit_payments(id) ON DELETE SET NULL,
    CONSTRAINT fk_sale_payments_receiver_user FOREIGN KEY (receiver_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_products_barcode ON products(barcode);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX idx_sales_created ON sales(created_at);
CREATE INDEX idx_stock_movements_prod ON stock_movements(product_id);
CREATE INDEX idx_sup_transactions ON supplier_transactions(supplier_id);
CREATE INDEX idx_supplier_invoices_supplier ON supplier_invoices(supplier_id);
CREATE INDEX idx_product_sale_units_product ON product_sale_units(product_id);
CREATE INDEX idx_product_sale_units_barcode ON product_sale_units(barcode);
CREATE INDEX idx_customer_credit_payments_customer ON customer_credit_payments(customer_id);
CREATE INDEX idx_sale_payments_sale ON sale_payments(sale_id);
CREATE INDEX idx_sale_payments_created ON sale_payments(created_at);
CREATE INDEX idx_sale_payments_receiver ON sale_payments(receiver_user_id);
"""

WEIGHT_CATEGORY_NAME = "Produits au poids"

DEFAULT_CATEGORIES = [
    ("Produits laitiers", "Lait, fromage, beurre", "#2196F3"),
    ("Yaourts", "Yaourts et desserts", "#9C27B0"),
    ("Boulangerie", "Pain et viennoiseries", "#FF9800"),
    ("Pâtisseries", "Gâteaux et douceurs", "#E91E63"),
    ("Boissons", "Eau, jus, sodas", "#00BCD4"),
    ("Fruits et légumes", "Produits frais", "#4CAF50"),
    ("Produits ménagers", "Entretien et nettoyage", "#607D8B"),
    ("Épicerie", "Conserves et condiments", "#FF5722"),
    (WEIGHT_CATEGORY_NAME, "Épices et produits vendus au poids", "#8D6E63"),
    ("Autres", "Divers", "#9E9E9E"),
    ("Autres (Pièces uniques)", "Produits vendus à l'unité (ex: triangle de fromage)", "#FF6B35"),
]

DEFAULT_WEIGHT_PRODUCTS = [
    ("فلفل", 10.000, 18.000, 8.000),
    ("كركم", 11.000, 20.000, 8.000),
    ("كروية", 9.000, 16.000, 8.000),
    ("ملوخية", 13.000, 24.000, 8.000),
    ("كمون", 12.000, 22.000, 8.000),
]

DEFAULT_EXTRA_PRODUCTS = [
    ("Oeuf", "Produits laitiers", 0.300, 0.450, 30.000, "piece", None),
    ("Chamia", "Pâtisseries", 1.800, 2.500, 20.000, "piece", "Sweet_1783094698904.png"),
]

DEFAULT_SETTINGS = [
    ("store_name", "Mon Magasin"),
    ("store_address", "Adresse"),
    ("store_phone", "+216 XX XXX XXX"),
    ("currency", "TND"),
    ("tax_rate", "0"),
    ("theme", "light"),
    ("low_stock_threshold", "5"),
    ("receipt_footer", "Merci pour votre visite !"),
]

DEFAULT_SUPPLIER = {
    "name": "Autres",
    "notes": "Fournisseur par défaut",
}


def _execute(conn, query: str, params: tuple = ()):
    translated = db._translate_placeholders(query)
    if db.is_mysql():
        cursor = conn.cursor()
        cursor.execute(translated, params)
        return cursor
    return conn.execute(translated, params)


def _safe_mysql_schema_execute(conn, query: str, params: tuple = ()):
    try:
        return _execute(conn, query, params)
    except Exception as exc:
        if db.is_mysql() and db._is_ignorable_mysql_schema_error(exc):
            return None
        raise


def _fetchone(conn, query: str, params: tuple = ()):
    if db.is_mysql():
        cursor = _execute(conn, query, params)
        row = cursor.fetchone()
        return dict(row) if row else None
    row = _execute(conn, query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn, query: str, params: tuple = ()):
    if db.is_mysql():
        cursor = _execute(conn, query, params)
        return [dict(row) for row in cursor.fetchall()]
    return [dict(row) for row in _execute(conn, query, params).fetchall()]


def _insert_ignore_query(table: str, columns: list[str]) -> str:
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    return f"{db.insert_ignore_clause()} INTO {table} ({column_sql}) VALUES ({placeholders})"


def _ensure_default_supplier(conn=None) -> int:
    conn = conn or db.get_connection()
    row = _fetchone(
        conn,
        "SELECT id FROM suppliers WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1",
        (DEFAULT_SUPPLIER["name"],),
    )
    if row:
        return int(row["id"])
    cur = _execute(
        conn,
        "INSERT INTO suppliers (name, notes) VALUES (?, ?)",
        (DEFAULT_SUPPLIER["name"], DEFAULT_SUPPLIER["notes"]),
    )
    conn.commit()
    return int(cur.lastrowid)


def _get_category_id_by_name(category_name: str, conn=None) -> int | None:
    conn = conn or db.get_connection()
    row = _fetchone(
        conn,
        "SELECT id FROM categories WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1",
        (category_name,),
    )
    return int(row["id"]) if row else None


def _ensure_weight_products(conn=None):
    conn = conn or db.get_connection()
    supplier_id = _ensure_default_supplier(conn)

    category_row = _fetchone(
        conn,
        "SELECT id FROM categories WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1",
        (WEIGHT_CATEGORY_NAME,),
    )
    if category_row:
        weight_category_id = int(category_row["id"])
    else:
        cur = _execute(
            conn,
            "INSERT INTO categories (name, description, color) VALUES (?, ?, ?)",
            (WEIGHT_CATEGORY_NAME, "Épices et produits vendus au poids", "#8D6E63"),
        )
        weight_category_id = int(cur.lastrowid)

    for name, purchase_price, sale_price, stock_quantity in DEFAULT_WEIGHT_PRODUCTS:
        existing = _fetchone(
            conn,
            "SELECT id FROM products WHERE lower(trim(name)) = lower(trim(?)) LIMIT 1",
            (name,),
        )
        if existing:
            _execute(
                conn,
                """
                UPDATE products
                SET category_id = COALESCE(category_id, ?),
                    supplier_id = COALESCE(supplier_id, ?),
                    unit_type = CASE
                        WHEN lower(trim(COALESCE(unit_type, ''))) IN ('', 'piece') THEN 'kg'
                        ELSE unit_type
                    END,
                    min_stock = CASE WHEN COALESCE(min_stock, 0) <= 0 THEN 0.250 ELSE min_stock END,
                    description = CASE
                        WHEN COALESCE(trim(description), '') = '' THEN 'Produit vendu au poids saisi en grammes à la caisse.'
                        ELSE description
                    END,
                    is_active = 1
                WHERE id = ?
                """,
                (weight_category_id, supplier_id, int(existing["id"])),
            )
            continue

        _execute(
            conn,
            """
            INSERT INTO products (
                barcode, name, category_id, supplier_id, purchase_price, sale_price,
                stock_quantity, min_stock, unit_type, description, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"POIDS-{abs(hash(name)) % 1000000:06d}",
                name,
                weight_category_id,
                supplier_id,
                purchase_price,
                sale_price,
                stock_quantity,
                0.250,
                "kg",
                "Produit vendu au poids saisi en grammes à la caisse.",
            ),
        )
    conn.commit()


def _ensure_extra_products(conn=None):
    conn = conn or db.get_connection()
    supplier_id = _ensure_default_supplier(conn)

    for name, category_name, purchase_price, sale_price, stock_quantity, unit_type, image_path in DEFAULT_EXTRA_PRODUCTS:
        category_id = _get_category_id_by_name(category_name, conn)
        if category_id is None:
            cur = _execute(
                conn,
                "INSERT INTO categories (name, description, color) VALUES (?, ?, ?)",
                (category_name, category_name, "#9E9E9E"),
            )
            category_id = int(cur.lastrowid)

        existing = _fetchone(
            conn,
            "SELECT id FROM products WHERE lower(trim(name)) = lower(trim(?)) LIMIT 1",
            (name,),
        )
        if existing:
            _execute(
                conn,
                """
                UPDATE products
                SET category_id = COALESCE(category_id, ?),
                    supplier_id = COALESCE(supplier_id, ?),
                    unit_type = CASE
                        WHEN lower(trim(COALESCE(unit_type, ''))) IN ('', 'kg', 'litre') THEN ?
                        ELSE unit_type
                    END,
                    is_active = 1,
                    image_path = CASE
                        WHEN COALESCE(trim(image_path), '') = '' THEN ?
                        ELSE image_path
                    END
                WHERE id = ?
                """,
                (category_id, supplier_id, unit_type, image_path, int(existing["id"])),
            )
            continue

        _execute(
            conn,
            """
            INSERT INTO products (
                barcode, name, category_id, supplier_id, purchase_price, sale_price,
                stock_quantity, min_stock, unit_type, description, image_path, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"PIECE-{abs(hash(name)) % 1000000:06d}",
                name,
                category_id,
                supplier_id,
                purchase_price,
                sale_price,
                stock_quantity,
                1.000 if unit_type == "piece" else 0.250,
                unit_type,
                "Produit ajouté par défaut.",
                image_path,
            ),
        )
    conn.commit()



def _mysql_column_type(table_name: str, column_name: str, fallback: str = "BIGINT") -> str:
    row = db.fetchone(
        """
        SELECT COLUMN_TYPE
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ? AND column_name = ?
        LIMIT 1
        """,
        (db.database_name(), table_name, column_name),
    )
    return str((row or {}).get("COLUMN_TYPE") or fallback)


def _ensure_mysql_supplier_invoice_children() -> None:
    conn = db.get_connection()

    invoice_id_type = _mysql_column_type("supplier_invoices", "id", "BIGINT")
    supplier_id_type = _mysql_column_type("suppliers", "id", "BIGINT")
    product_id_type = _mysql_column_type("products", "id", "BIGINT")

    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS supplier_invoice_payments (
            id {invoice_id_type} NOT NULL AUTO_INCREMENT PRIMARY KEY,
            invoice_id {invoice_id_type} NOT NULL,
            supplier_id {supplier_id_type} NOT NULL,
            amount DOUBLE NOT NULL,
            reference VARCHAR(255) NULL,
            notes TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_supplier_invoice_payments_invoice
                FOREIGN KEY (invoice_id) REFERENCES supplier_invoices(id) ON DELETE CASCADE,
            CONSTRAINT fk_supplier_invoice_payments_supplier
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS supplier_invoice_items (
            id {invoice_id_type} NOT NULL AUTO_INCREMENT PRIMARY KEY,
            invoice_id {invoice_id_type} NOT NULL,
            product_id {product_id_type} NULL,
            product_name VARCHAR(255) NOT NULL,
            supplier_name VARCHAR(255) NULL,
            quantity DOUBLE NOT NULL DEFAULT 0,
            unit_price DOUBLE NOT NULL DEFAULT 0,
            line_total DOUBLE NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_supplier_invoice_items_invoice
                FOREIGN KEY (invoice_id) REFERENCES supplier_invoices(id) ON DELETE CASCADE,
            CONSTRAINT fk_supplier_invoice_items_product
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    _safe_mysql_schema_execute(
        conn,
        "CREATE INDEX idx_supplier_invoice_payments_invoice ON supplier_invoice_payments(invoice_id)",
    )
    _safe_mysql_schema_execute(
        conn,
        "CREATE INDEX idx_supplier_invoice_payments_supplier ON supplier_invoice_payments(supplier_id)",
    )
    _safe_mysql_schema_execute(
        conn,
        "CREATE INDEX idx_supplier_invoice_items_invoice ON supplier_invoice_items(invoice_id)",
    )
    conn.commit()



def init_schema():
    if db.is_mysql():
        db.execute_script(MYSQL_SCHEMA_SQL)
        _ensure_mysql_supplier_invoice_children()
    else:
        db.execute_script(SQLITE_SCHEMA_SQL)
    _migrate()
    _seed_defaults()
    _repair_legacy_passwords()


def _migrate():
    conn = db.get_connection()

    if "supplier_id" not in db.table_columns("products"):
        _execute(conn, "ALTER TABLE products ADD COLUMN supplier_id BIGINT NULL")
        conn.commit()

    if "image_path" not in db.table_columns("categories"):
        _execute(conn, "ALTER TABLE categories ADD COLUMN image_path TEXT NULL")
        conn.commit()

    expense_columns = db.table_columns("expenses")
    if "recurrence_interval" not in expense_columns:
        _execute(conn, "ALTER TABLE expenses ADD COLUMN recurrence_interval INTEGER NULL")
        conn.commit()
    if "recurrence_unit" not in expense_columns:
        _execute(conn, "ALTER TABLE expenses ADD COLUMN recurrence_unit VARCHAR(16) NULL")
        conn.commit()
    if "recurrence_months" in expense_columns:
        # One-off backfill from the short-lived months-only version of this
        # feature: every value there always meant "every N months".
        _execute(
            conn,
            "UPDATE expenses SET recurrence_interval=recurrence_months, recurrence_unit='month' "
            "WHERE recurrence_months IS NOT NULL AND recurrence_interval IS NULL",
        )
        conn.commit()

    _execute(
        conn,
        _insert_ignore_query("categories", ["name", "description", "color"]),
        ("Autres (Pièces uniques)", "Produits vendus à l'unité (ex: triangle de fromage)", "#FF6B35"),
    )
    default_supplier_id = _ensure_default_supplier(conn)
    _execute(
        conn,
        "UPDATE products SET supplier_id=? WHERE supplier_id IS NULL",
        (default_supplier_id,),
    )
    conn.commit()
    _migrate_sales_payment_fields(conn)



def _base_sale_unit_name(unit_type: str) -> str:
    unit_type = (unit_type or "piece").strip().lower()
    return {
        "piece": "Pièce",
        "kg": "Kg",
        "litre": "Litre",
    }.get(unit_type, "Unité")


def _ensure_product_sale_units(conn=None):
    conn = conn or db.get_connection()
    products = _fetchall(conn, "SELECT id, barcode, sale_price, unit_type FROM products")
    for product in products:
        product_id = int(product["id"])
        existing = _fetchone(
            conn,
            "SELECT id FROM product_sale_units WHERE product_id=? ORDER BY is_default DESC, id ASC LIMIT 1",
            (product_id,),
        )
        if existing:
            continue
        _execute(
            conn,
            """
            INSERT INTO product_sale_units (
                product_id, name, quantity, sale_price, barcode, is_default, is_active
            ) VALUES (?, ?, ?, ?, ?, 1, 1)
            """,
            (
                product_id,
                _base_sale_unit_name(product.get("unit_type") or "piece"),
                1.0,
                float(product.get("sale_price") or 0.0),
                None,
            ),
        )
    conn.commit()


def _seed_sale_payments(conn=None):
    conn = conn or db.get_connection()
    sales = _fetchall(
        conn,
        "SELECT id, user_id, customer_id, total, payment_method, amount_paid, credit_paid, created_at, status FROM sales",
    )
    for sale in sales:
        sale_id = int(sale["id"])
        existing_payment = _fetchone(
            conn,
            "SELECT id FROM sale_payments WHERE sale_id=? LIMIT 1",
            (sale_id,),
        )
        if existing_payment:
            continue

        if str(sale.get("status") or "") != "completed":
            continue

        amount = round(float(sale.get("amount_paid") or 0.0), 3)
        payment_method = str(sale.get("payment_method") or "cash")
        if payment_method == "credit" and amount <= 0:
            continue

        if amount <= 0:
            amount = round(float(sale.get("total") or 0.0), 3)

        if amount <= 0:
            continue

        _execute(
            conn,
            """
            INSERT INTO sale_payments (sale_id, customer_id, receiver_user_id, payment_method, amount, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_id,
                sale.get("customer_id"),
                sale.get("user_id"),
                "cash" if payment_method != "credit" else "credit_deposit",
                amount,
                "Paiement initial migré",
                sale.get("created_at"),
            ),
        )
    conn.commit()


def _migrate_sales_payment_fields(conn=None):
    conn = conn or db.get_connection()

    if "payment_status" not in db.table_columns("sales"):
        _execute(conn, "ALTER TABLE sales ADD COLUMN payment_status VARCHAR(32) NOT NULL DEFAULT 'paid'")
    if "credit_paid" not in db.table_columns("sales"):
        _execute(conn, "ALTER TABLE sales ADD COLUMN credit_paid DOUBLE NOT NULL DEFAULT 0")
    if "paid_at" not in db.table_columns("sales"):
        _execute(conn, "ALTER TABLE sales ADD COLUMN paid_at DATETIME NULL")

    if "sale_unit_id" not in db.table_columns("sale_items"):
        _execute(conn, "ALTER TABLE sale_items ADD COLUMN sale_unit_id BIGINT NULL")
    if "sale_unit_name" not in db.table_columns("sale_items"):
        _execute(conn, "ALTER TABLE sale_items ADD COLUMN sale_unit_name VARCHAR(255) NULL")
    if "stock_quantity" not in db.table_columns("sale_items"):
        _execute(conn, "ALTER TABLE sale_items ADD COLUMN stock_quantity DOUBLE NOT NULL DEFAULT 0")
    if "receiver_user_id" not in db.table_columns("sale_payments"):
        _execute(conn, "ALTER TABLE sale_payments ADD COLUMN receiver_user_id BIGINT NULL")

    _execute(conn, "UPDATE sale_items SET stock_quantity = quantity WHERE COALESCE(stock_quantity, 0) <= 0")
    _execute(
        conn,
        """
        UPDATE sale_payments
        SET receiver_user_id = (
            SELECT s.user_id
            FROM sales s
            WHERE s.id = sale_payments.sale_id
        )
        WHERE receiver_user_id IS NULL
        """,
    )
    _execute(
        conn,
        f"""
        UPDATE sales
        SET payment_status = CASE
                WHEN lower(trim(COALESCE(payment_method, ''))) = 'credit'
                     AND ROUND(COALESCE(credit_paid, 0), 3) < ROUND(COALESCE(total, 0), 3)
                    THEN CASE
                        WHEN ROUND(COALESCE(credit_paid, amount_paid, 0), 3) > 0 THEN 'partial'
                        ELSE 'credit'
                    END
                ELSE 'paid'
            END,
            credit_paid = CASE
                WHEN lower(trim(COALESCE(payment_method, ''))) = 'credit'
                    THEN ROUND(COALESCE(credit_paid, amount_paid, 0), 3)
                ELSE ROUND(COALESCE(total, 0), 3)
            END,
            paid_at = CASE
                WHEN COALESCE(paid_at, '') <> '' THEN paid_at
                WHEN lower(trim(COALESCE(payment_method, ''))) = 'credit'
                     AND ROUND(COALESCE(credit_paid, amount_paid, 0), 3) < ROUND(COALESCE(total, 0), 3)
                    THEN NULL
                ELSE created_at
            END
        """,
    )
    conn.commit()
    _ensure_product_sale_units(conn)
    _seed_sale_payments(conn)

def _repair_legacy_passwords():
    import bcrypt

    conn = db.get_connection()
    users = _fetchall(conn, "SELECT id, username, password FROM users")

    for row in users:
        user_id = int(row["id"])
        username = str(row["username"])
        stored_password = str(row["password"] or "").strip()
        if not stored_password:
            continue

        if username == "admin" and stored_password == "testhash":
            hashed = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
            _execute(
                conn,
                f"UPDATE users SET password=?, updated_at={db.current_timestamp_sql()} WHERE id=?",
                (hashed, user_id),
            )

    conn.commit()


def _seed_defaults():
    import bcrypt

    admin_pw = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
    cashier_pw = bcrypt.hashpw(b"001", bcrypt.gensalt()).decode()
    db.execute(
        _insert_ignore_query("users", ["username", "password", "full_name", "role"]),
        ("admin", admin_pw, "Administrateur", "admin"),
    )
    db.execute(
        _insert_ignore_query("users", ["username", "password", "full_name", "role"]),
        ("001", cashier_pw, "Caissier", "cashier"),
    )

    for name, desc, color in DEFAULT_CATEGORIES:
        db.execute(
            _insert_ignore_query("categories", ["name", "description", "color"]),
            (name, desc, color),
        )

    for key, value in DEFAULT_SETTINGS:
        db.execute(
            _insert_ignore_query("settings", ["`key`", "value"]),
            (key, value),
        )

    _ensure_default_supplier()
    _ensure_weight_products()
    _ensure_extra_products()
