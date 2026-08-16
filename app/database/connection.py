from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    BACKUP_DIR,
    DATABASE_PATH,
    DB_BACKEND,
    MYSQL_CHARSET,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    ensure_dirs,
)

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None


class DatabaseConnection:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        ensure_dirs()
        self._backend = (DB_BACKEND or "sqlite").strip().lower()
        if self._backend not in {"sqlite", "mysql"}:
            raise ValueError(f"Unsupported DB_BACKEND: {self._backend}")
        self._db_path = str(DATABASE_PATH)
        self._local = threading.local()
        self._initialized = True

    @property
    def backend(self) -> str:
        return self._backend

    def is_sqlite(self) -> bool:
        return self._backend == "sqlite"

    def is_mysql(self) -> bool:
        return self._backend == "mysql"

    def current_timestamp_sql(self) -> str:
        return "NOW()" if self.is_mysql() else "datetime('now','localtime')"

    def insert_ignore_clause(self) -> str:
        return "INSERT IGNORE" if self.is_mysql() else "INSERT OR IGNORE"

    def _translate_placeholders(self, query: str) -> str:
        if not self.is_mysql():
            return query

        result: list[str] = []
        in_single = False
        in_double = False
        escaped = False

        for ch in query:
            if ch == "\\" and not escaped:
                escaped = True
                result.append(ch)
                continue

            if ch == "'" and not in_double and not escaped:
                in_single = not in_single
            elif ch == '"' and not in_single and not escaped:
                in_double = not in_double
            elif ch == "?" and not in_single and not in_double:
                result.append("%s")
                escaped = False
                continue

            result.append(ch)
            escaped = False

        return "".join(result)

    def _mysql_connect_kwargs(self, include_database: bool = True) -> dict:
        kwargs = {
            "host": MYSQL_HOST,
            "port": MYSQL_PORT,
            "user": MYSQL_USER,
            "password": MYSQL_PASSWORD,
            "charset": MYSQL_CHARSET,
            "autocommit": False,
            "cursorclass": DictCursor,
        }
        if include_database:
            kwargs["database"] = MYSQL_DATABASE
        return kwargs

    def _ensure_mysql_database(self) -> None:
        if not self.is_mysql():
            return
        if pymysql is None:
            raise RuntimeError(
                "PyMySQL is required for MySQL support. Install it with: pip install PyMySQL"
            )
        conn = pymysql.connect(**self._mysql_connect_kwargs(include_database=False))
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                    f"CHARACTER SET {MYSQL_CHARSET} COLLATE {MYSQL_CHARSET}_unicode_ci"
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _local_utc_offset() -> str:
        """Machine's current UTC offset as MySQL expects it, e.g. '+01:00'.

        Read at connection time so a DST change is picked up on the next
        launch instead of being frozen at install time.
        """
        offset = datetime.now().astimezone().utcoffset() or timedelta(0)
        total_minutes = int(offset.total_seconds()) // 60
        sign = "+" if total_minutes >= 0 else "-"
        total_minutes = abs(total_minutes)
        return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    def get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if self.is_mysql():
                self._ensure_mysql_database()
                self._local.conn = pymysql.connect(**self._mysql_connect_kwargs())
                with self._local.conn.cursor() as cursor:
                    # Store timestamps in LOCAL time, matching what SQLite does
                    # via datetime('now','localtime'). This must stay aligned
                    # with Python's datetime.now(): the daily takings query
                    # compares NOW()-written rows against a local date computed
                    # in Python, so a UTC session would file every sale made
                    # between midnight and the UTC offset under the wrong day.
                    cursor.execute("SET time_zone = %s", (self._local_utc_offset(),))
            else:
                self._local.conn = sqlite3.connect(self._db_path)
                self._local.conn.row_factory = sqlite3.Row
                self._local.conn.execute("PRAGMA journal_mode=WAL")
                self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def commit(self) -> None:
        self.get_connection().commit()

    def rollback(self) -> None:
        self.get_connection().rollback()

    def database_name(self) -> str:
        return MYSQL_DATABASE if self.is_mysql() else ""

    @property
    def in_transaction(self) -> bool:
        return getattr(self._local, "tx_depth", 0) > 0

    @contextmanager
    def transaction(self):
        """Run a block as one all-or-nothing unit of work.

            with db.transaction():
                db.execute(...)
                SomeController.helper()   # its writes join this transaction

        Everything written inside lands together or not at all. Without this,
        execute() commits on every call, so a helper called midway through a
        multi-step operation (a sale writing its lines, then deducting stock)
        would silently commit the half-finished work and leave rollback with
        nothing left to undo.

        Nesting is allowed: only the outermost block commits, so a controller
        that already runs inside a transaction can call another one safely.

        No explicit BEGIN is issued. Both backends already keep an implicit
        transaction open (pymysql with autocommit=False, sqlite3 with its
        default isolation_level), so a BEGIN here would risk committing that
        pending work as a side effect. What matters is that nothing commits
        until this block ends, which the in_transaction guard below enforces.
        """
        conn = self.get_connection()
        depth = getattr(self._local, "tx_depth", 0)
        self._local.tx_depth = depth + 1
        try:
            yield conn
        except Exception:
            self._local.tx_depth = depth
            if depth == 0:
                conn.rollback()
            raise
        else:
            self._local.tx_depth = depth
            if depth == 0:
                conn.commit()

    def execute(self, query: str, params: tuple = ()):
        conn = self.get_connection()
        cursor = conn.cursor() if self.is_mysql() else None
        translated = self._translate_placeholders(query)
        try:
            if self.is_mysql():
                cursor.execute(translated, params)
            else:
                cursor = conn.execute(translated, params)
            # Inside a transaction() block the caller owns the commit; ending
            # it here would break the block's all-or-nothing guarantee.
            if not self.in_transaction:
                conn.commit()
            return cursor
        except Exception:
            if not self.in_transaction:
                conn.rollback()
            raise

    def executemany(self, query: str, params_list: list):
        conn = self.get_connection()
        translated = self._translate_placeholders(query)
        cursor = conn.cursor() if self.is_mysql() else None
        try:
            if self.is_mysql():
                cursor.executemany(translated, params_list)
            else:
                cursor = conn.executemany(translated, params_list)
            if not self.in_transaction:
                conn.commit()
            return cursor
        except Exception:
            if not self.in_transaction:
                conn.rollback()
            raise

    def execute_script(self, script: str) -> None:
        conn = self.get_connection()
        if self.is_sqlite():
            conn.executescript(script)
            conn.commit()
            return

        statement = []
        in_single = False
        in_double = False
        escaped = False
        for ch in script:
            if ch == "\\" and not escaped:
                escaped = True
                statement.append(ch)
                continue

            if ch == "'" and not in_double and not escaped:
                in_single = not in_single
            elif ch == '"' and not in_single and not escaped:
                in_double = not in_double

            if ch == ";" and not in_single and not in_double:
                chunk = "".join(statement).strip()
                statement = []
                if chunk:
                    try:
                        self.execute(chunk)
                    except Exception as exc:
                        if not self._is_ignorable_mysql_schema_error(exc):
                            raise
                escaped = False
                continue

            statement.append(ch)
            escaped = False

        tail = "".join(statement).strip()
        if tail:
            try:
                self.execute(tail)
            except Exception as exc:
                if not self._is_ignorable_mysql_schema_error(exc):
                    raise

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        conn = self.get_connection()
        translated = self._translate_placeholders(query)
        if self.is_mysql():
            with conn.cursor() as cursor:
                cursor.execute(translated, params)
                return list(cursor.fetchall())
        cursor = conn.execute(translated, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        conn = self.get_connection()
        translated = self._translate_placeholders(query)
        if self.is_mysql():
            with conn.cursor() as cursor:
                cursor.execute(translated, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        cursor = conn.execute(translated, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def table_exists(self, table_name: str) -> bool:
        if self.is_mysql():
            row = self.fetchone(
                """
                SELECT COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_schema = ? AND table_name = ?
                """,
                (MYSQL_DATABASE, table_name),
            )
            return bool((row or {}).get("table_count"))
        row = self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return row is not None

    def table_columns(self, table_name: str) -> list[str]:
        if self.is_mysql():
            rows = self.fetchall(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                (MYSQL_DATABASE, table_name),
            )
            # MySQL 8 hands back information_schema metadata under UPPERCASE
            # keys ("COLUMN_NAME"), MySQL 5.7 under lowercase. Reading the
            # row's single value sidesteps the difference entirely — looking
            # the key up by name raised KeyError on 8.x and took every schema
            # migration down with it.
            return [str(next(iter(row.values()))) for row in rows]
        rows = self.get_connection().execute(f"PRAGMA table_info({table_name})").fetchall()
        return [str(row[1]) for row in rows]

    def mysql_date_format(self, column: str, fmt: str) -> str:
        return f"DATE_FORMAT({column}, '{fmt}')"

    def sqlite_strftime(self, fmt: str, column: str) -> str:
        return f"strftime('{fmt}', {column})"

    def date_only_expr(self, column: str) -> str:
        return f"DATE({column})"

    def _is_ignorable_mysql_schema_error(self, exc: Exception) -> bool:
        if not self.is_mysql() or pymysql is None:
            return False
        if not isinstance(exc, pymysql.MySQLError):
            return False
        code = exc.args[0] if exc.args else None
        return code in {1050, 1060, 1061, 1091, 1826}



db = DatabaseConnection()
