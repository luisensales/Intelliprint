"""Dual Database Abstraction Layer: Neon PostgreSQL (Cloud) + SQLite (Local/Tests).

Automatically selects PostgreSQL when the `DATABASE_URL` environment variable is
configured (e.g. Neon PostgreSQL on Render), and falls back seamlessly to local
SQLite when running locally or inside isolated unit tests.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

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


_CLOUD_SNAPSHOT_TABLE_READY: Set[str] = set()
_MAX_CLOUD_PDF_BYTES = 18 * 1024 * 1024


def _should_use_cloud_job_snapshots(jobs_dir: Optional[Path] = None) -> bool:
    """Enable Neon job snapshots in production/default storage, skipping unit test temp dirs."""
    if not is_postgres_configured() or "unittest" in sys.modules:
        return False
    if jobs_dir is not None:
        default_jobs = (_PROJECT_ROOT / "jobs").resolve()
        if Path(jobs_dir).resolve() != default_jobs and not os.environ.get("RENDER"):
            return False
    return True


def _ensure_cloud_job_table(conn: DBConnection) -> None:
    dsn_key = get_database_url()
    if dsn_key in _CLOUD_SNAPSHOT_TABLE_READY:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cloud_job_snapshots (
            job_id TEXT PRIMARY KEY,
            filename TEXT,
            report_json TEXT NOT NULL,
            pdf_bytes BYTEA,
            updated_at BIGINT NOT NULL
        )
    """)
    conn.commit()
    _CLOUD_SNAPSHOT_TABLE_READY.add(dsn_key)


def save_cloud_job_snapshot(
    job_id: str,
    job_data: Dict[str, Any],
    pdf_path: Optional[str | Path] = None,
    jobs_dir: Optional[Path] = None,
) -> bool:
    """Persist a job JSON and its active PDF in Neon PostgreSQL so Render restarts never lose active jobs."""
    if not job_id or not _should_use_cloud_job_snapshots(jobs_dir):
        return False
    try:
        pdf_bytes: Optional[bytes] = None
        if pdf_path:
            p = Path(pdf_path)
            if p.is_file() and p.stat().st_size <= _MAX_CLOUD_PDF_BYTES:
                pdf_bytes = p.read_bytes()
        filename = (job_data.get("job_meta") or {}).get("filename") or "source.pdf"
        report_str = json.dumps(job_data, ensure_ascii=False)
        now_ts = int(time.time())
        cutoff_ts = now_ts - 86400

        with get_connection() as conn:
            _ensure_cloud_job_table(conn)
            if pdf_bytes is not None:
                conn.execute("""
                    INSERT INTO cloud_job_snapshots (job_id, filename, report_json, pdf_bytes, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (job_id) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        report_json = EXCLUDED.report_json,
                        pdf_bytes = EXCLUDED.pdf_bytes,
                        updated_at = EXCLUDED.updated_at
                """, (job_id, filename, report_str, pdf_bytes, now_ts))
            else:
                conn.execute("""
                    INSERT INTO cloud_job_snapshots (job_id, filename, report_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (job_id) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        report_json = EXCLUDED.report_json,
                        updated_at = EXCLUDED.updated_at
                """, (job_id, filename, report_str, now_ts))
            conn.execute("DELETE FROM cloud_job_snapshots WHERE updated_at < ?", (cutoff_ts,))
            conn.execute("""
                DELETE FROM cloud_job_snapshots
                WHERE job_id NOT IN (
                    SELECT job_id FROM cloud_job_snapshots ORDER BY updated_at DESC LIMIT 20
                )
            """)
            conn.commit()
        return True
    except Exception as exc:
        print(f"[db_store] Aviso guardando snapshot de job {job_id}: {exc}")
        return False


def restore_cloud_job_snapshot(
    job_id: str,
    jobs_dir: Path,
    upload_dir: Path,
) -> bool:
    """Restore a job JSON and its active PDF from Neon PostgreSQL if wiped by a container restart."""
    if not job_id or not _should_use_cloud_job_snapshots(jobs_dir):
        return False
    try:
        with get_connection() as conn:
            _ensure_cloud_job_table(conn)
            row = conn.execute(
                "SELECT filename, report_json, pdf_bytes FROM cloud_job_snapshots WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return False

        job_data = json.loads(row["report_json"])
        pdf_bytes = row.get("pdf_bytes")
        job_folder = Path(upload_dir) / job_id
        job_folder.mkdir(parents=True, exist_ok=True)
        restored_pdf = job_folder / "source.pdf"

        if pdf_bytes:
            raw_bytes = bytes(pdf_bytes)
            restored_pdf.write_bytes(raw_bytes)
            meta = job_data.setdefault("job_meta", {})
            meta["pdf_path"] = str(restored_pdf)
            for k in list(meta.keys()):
                if k.endswith("_pdf_path") and k != "pdf_path":
                    cand = meta.get(k)
                    if cand and not Path(cand).exists():
                        meta[k] = str(restored_pdf)

        Path(jobs_dir).mkdir(parents=True, exist_ok=True)
        job_json_path = Path(jobs_dir) / f"{job_id}.json"
        job_json_path.write_text(json.dumps(job_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[db_store] Aviso restaurando snapshot de job {job_id}: {exc}")
        return False

