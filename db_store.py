"""Dual Database Abstraction Layer: Neon PostgreSQL (Cloud) + SQLite (Local/Tests).

Automatically selects PostgreSQL when the `DATABASE_URL` environment variable is
configured (e.g. Neon PostgreSQL on Render), and falls back seamlessly to local
SQLite when running locally or inside isolated unit tests.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None
    PSYCOPG_AVAILABLE = False


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = DATA_DIR / "auth.db"
_PROJECT_ROOT = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Load variables from .env.local / .env when not already set in environment."""
    for fname in (".env.local", ".env"):
        env_path = _PROJECT_ROOT / fname
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)
        except OSError:
            pass


_load_local_env()


class DuplicateEntryError(Exception):
    """Raised when inserting/updating violates a UNIQUE constraint."""


def get_database_url() -> str:
    """Return normalized PostgreSQL URL from environment, or empty string."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    return raw


def is_postgres_configured(db_path: Optional[Path] = None) -> bool:
    """Use Postgres only when DATABASE_URL is set and no custom test db_path is forced."""
    if db_path is not None and Path(db_path).resolve() != DEFAULT_DB_PATH.resolve():
        return False
    return bool(get_database_url()) and PSYCOPG_AVAILABLE


def get_db_status(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return non-sensitive metadata about the active storage backend."""
    pg = is_postgres_configured(db_path)
    url = get_database_url()
    provider = "sqlite_local"
    if pg:
        provider = "neon_postgresql" if "neon.tech" in url else "postgresql"
    return {
        "backend": "postgresql" if pg else "sqlite",
        "provider": provider,
        "persistent": pg,
        "psycopg_installed": PSYCOPG_AVAILABLE,
    }


def _translate_sql(sql: str, postgres: bool) -> str:
    """Translate standard SQLite-style `?` placeholders & DDL to PostgreSQL safely."""
    if not postgres:
        return sql

    out = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    # Replace '?' placeholders outside single-quoted string literals
    chars: List[str] = []
    in_single = False
    i = 0
    n = len(out)
    while i < n:
        ch = out[i]
        if ch == "'":
            chars.append(ch)
            if in_single and i + 1 < n and out[i + 1] == "'":
                chars.append("'")
                i += 2
                continue
            in_single = not in_single
        elif ch == "?" and not in_single:
            chars.append("%s")
        else:
            chars.append(ch)
        i += 1
    return "".join(chars)


class _CursorAdapter:
    """Unifies SQLite and Psycopg cursor rows into plain dicts."""

    def __init__(self, cursor: Any, postgres: bool):
        self._cursor = cursor
        self._postgres = postgres

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> List[Dict[str, Any]]:
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", -1))

    @property
    def lastrowid(self) -> Optional[int]:
        return getattr(self._cursor, "lastrowid", None)


class DBConnection:
    """Unified connection wrapper over psycopg (Postgres) and sqlite3."""

    def __init__(self, raw_conn: Any, postgres: bool):
        self._conn = raw_conn
        self.postgres = postgres

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _CursorAdapter:
        translated = _translate_sql(sql, self.postgres)
        try:
            if self.postgres:
                cur = self._conn.execute(translated, tuple(params))
            else:
                cur = self._conn.execute(translated, tuple(params))
            return _CursorAdapter(cur, self.postgres)
        except sqlite3.IntegrityError as exc:
            raise DuplicateEntryError(str(exc)) from exc
        except Exception as exc:
            if PSYCOPG_AVAILABLE and isinstance(exc, psycopg.errors.UniqueViolation):
                raise DuplicateEntryError(str(exc)) from exc
            if PSYCOPG_AVAILABLE and isinstance(exc, psycopg.IntegrityError):
                raise DuplicateEntryError(str(exc)) from exc
            raise

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def get_connection(db_path: Optional[Path] = None):
    """Context manager yielding a unified DBConnection for Postgres or SQLite."""
    use_pg = is_postgres_configured(db_path)
    if use_pg:
        url = get_database_url()
        raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)
        conn = DBConnection(raw, postgres=True)
    else:
        target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(target), timeout=10.0)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode = WAL")
        raw.execute("PRAGMA foreign_keys = ON")
        conn = DBConnection(raw, postgres=False)
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

