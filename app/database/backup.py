from __future__ import annotations
import os
import shutil
import sqlite3
from datetime import date, datetime
from decimal import Decimal
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

    # Écrit d'abord dans un fichier temporaire, renommé seulement une fois le
    # dump complet : une panne en cours d'écriture laisserait sinon une
    # sauvegarde tronquée que rien ne distingue d'une bonne — et on ne s'en
    # apercevrait qu'au moment de vouloir restaurer.
    dest = BACKUP_DIR / f"store_backup_{stamp}.sql"
    partial = dest.with_suffix(".sql.partiel")
    try:
        with partial.open("w", encoding="utf-8") as fh:
            fh.write("SET FOREIGN_KEY_CHECKS=0;\n")
            for table in _mysql_tables():
                create_row = db.fetchone(f"SHOW CREATE TABLE `{table}`") or {}
                create_sql = _row_value(create_row, "Create Table")
                if not create_sql:
                    raise RuntimeError(f"Structure illisible pour la table {table}")
                fh.write(f"DROP TABLE IF EXISTS `{table}`;\n")
                fh.write(f"{create_sql};\n")
                for row in db.fetchall(f"SELECT * FROM `{table}`"):
                    columns = ", ".join(f"`{key}`" for key in row.keys())
                    values = ", ".join(_sql_literal(value) for value in row.values())
                    fh.write(f"INSERT INTO `{table}` ({columns}) VALUES ({values});\n")
            fh.write("SET FOREIGN_KEY_CHECKS=1;\n")
            fh.flush()
            os.fsync(fh.fileno())
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    _cleanup_old_backups()
    return dest


def _row_value(row: dict, *preferred_keys: str):
    """Valeur d'une ligne, quelle que soit la casse de la clé.

    MySQL 8 renvoie les métadonnées en MAJUSCULES là où 5.7 les renvoie en
    minuscules ; se fier à une casse précise a déjà cassé l'application une
    fois (voir DatabaseConnection.table_columns).
    """
    for key in preferred_keys:
        for actual, value in row.items():
            if str(actual).casefold() == key.casefold():
                return value
    return None


def _mysql_tables() -> list[str]:
    """Tables de la base courante, sans dépendre du nom de colonne renvoyé.

    `SHOW TABLES` nomme sa colonne « Tables_in_<base> » : la lire par ce nom
    obligeait à reconstruire le nom de la base à la main. On prend la seule
    valeur de chaque ligne, ce qui marche quel que soit le nom.
    """
    return [str(next(iter(row.values()))) for row in db.fetchall("SHOW TABLES")]


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return f"'{value.isoformat(sep=' ')}'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex() if value else "''"
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f"'{escaped}'"


def _cleanup_old_backups(keep: int = 30):
    backups = sorted(
        list(BACKUP_DIR.glob("store_backup_*.db")) + list(BACKUP_DIR.glob("store_backup_*.sql")),
        key=lambda p: p.stat().st_mtime,
    )
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)


def format_backup_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} Go"


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
            "size_label": format_backup_size(p.stat().st_size),
            "date": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
        }
        for p in backups
    ]


def restore_backup(backup_path: str):
    src = Path(backup_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    if db.is_sqlite():
        # The live database runs in WAL mode, so overwriting store.db while a
        # connection is still open (or while stale -wal/-shm sidecar files
        # from the OLD file are still sitting next to it) risks corruption:
        # the WAL holds page references keyed to that specific file's
        # layout, not the one we're about to drop in. Closing first lets
        # SQLite checkpoint and release its handle cleanly; deleting the
        # sidecars after that removes any that a prior crash left behind.
        db.close()
        for suffix in ("-wal", "-shm"):
            Path(str(DATABASE_PATH) + suffix).unlink(missing_ok=True)
        shutil.copy2(src, DATABASE_PATH)
        return

    script = src.read_text(encoding="utf-8")
    db.execute_script(script)
