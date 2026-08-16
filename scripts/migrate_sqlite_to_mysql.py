from __future__ import annotations
import sqlite3
from pathlib import Path

from app.database.connection import db
from app.database.schema import init_schema
from config import DATABASE_PATH


# Parent tables first: rows are inserted in this order and deleted in reverse,
# so every foreign key already has its target by the time it is written.
# sale_payments must trail customer_credit_payments as well as sales — it
# points at both.
TABLE_ORDER = [
    "users",
    "categories",
    "suppliers",
    "customers",
    "customer_credit_payments",
    "products",
    "product_sale_units",
    "sales",
    "sale_items",
    "sale_payments",
    "stock_movements",
    "expenses",
    "product_returns",
    "user_logs",
    "settings",
    "supplier_transactions",
    "supplier_invoices",
    "supplier_invoice_payments",
    "supplier_invoice_items",
]


def _table_exists_sqlite(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _reset_mysql_tables() -> None:
    conn = db.get_connection()
    if not db.is_mysql():
        raise RuntimeError("DB_BACKEND must be mysql to import into MySQL.")
    db.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in reversed(TABLE_ORDER):
        if db.table_exists(table):
            db.execute(f"DELETE FROM `{table}`")
    db.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()


def _sync_auto_increment(table_name: str) -> None:
    row = db.fetchone(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM `{table_name}`")
    next_id = int((row or {}).get("max_id") or 0) + 1
    db.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {max(next_id, 1)}")


def main() -> None:
    sqlite_path = Path(DATABASE_PATH)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    if not db.is_mysql():
        raise RuntimeError("Set DB_BACKEND=mysql before running this import script.")

    init_schema()
    _reset_mysql_tables()

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    try:
        for table_name in TABLE_ORDER:
            if not _table_exists_sqlite(sqlite_conn, table_name):
                continue

            rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()
            if not rows:
                continue

            columns = list(rows[0].keys())
            column_sql = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["?"] * len(columns))
            query = f"INSERT INTO `{table_name}` ({column_sql}) VALUES ({placeholders})"

            payload = [tuple(row[column] for column in columns) for row in rows]
            db.executemany(query, payload)
            _sync_auto_increment(table_name)

        print("SQLite -> MySQL import completed.")
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    main()
