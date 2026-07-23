from __future__ import annotations
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BACKUP_DIR, DATABASE_PATH
from app.database.connection import db


def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if db.is_sqlite():
        dest = BACKUP_DIR / f"store_backup_{stamp}.db"
        src_conn = sqlite3.connect(str(DATABASE_PATH))
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()
        _cleanup_old_backups()
        return dest

    dest = BACKUP_DIR / f"store_backup_{stamp}.sql"
    conn = db.get_connection()
    with dest.open("w", encoding="utf-8") as fh:
        fh.write("SET FOREIGN_KEY_CHECKS=0;\n")
        tables = [row[f"Tables_in_{conn.db.decode() if isinstance(conn.db, bytes) else conn.db}"] for row in db.fetchall("SHOW TABLES")]
        for table in tables:
            create_row = db.fetchone(f"SHOW CREATE TABLE `{table}`")
            create_sql = create_row.get("Create Table") or create_row.get(f"Create Table `{table}`")
            fh.write(f"DROP TABLE IF EXISTS `{table}`;\n")
            fh.write(f"{create_sql};\n")
            rows = db.fetchall(f"SELECT * FROM `{table}`")
            for row in rows:
                columns = ", ".join(f"`{key}`" for key in row.keys())
                values = ", ".join(_sql_literal(value) for value in row.values())
                fh.write(f"INSERT INTO `{table}` ({columns}) VALUES ({values});\n")
        fh.write("SET FOREIGN_KEY_CHECKS=1;\n")
    _cleanup_old_backups()
    return dest


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _cleanup_old_backups(keep: int = 30):
    backups = sorted(
        list(BACKUP_DIR.glob("store_backup_*.db")) + list(BACKUP_DIR.glob("store_backup_*.sql")),
        key=lambda p: p.stat().st_mtime,
    )
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)


def list_backups() -> list[dict]:
    backups = sorted(
        list(BACKUP_DIR.glob("store_backup_*.db")) + list(BACKUP_DIR.glob("store_backup_*.sql")),
        reverse=True,
    )
    return [
        {
            "name": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "date": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
        }
        for p in backups
    ]


def restore_backup(backup_path: str):
    src = Path(backup_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    if db.is_sqlite():
        shutil.copy2(src, DATABASE_PATH)
        return

    script = src.read_text(encoding="utf-8")
    db.execute_script(script)
