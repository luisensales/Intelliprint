"""Authentication, Role-Based Access Control (RBAC), User Registration & Client Approval Engine.

Supports dual database backends via db_store:
- Cloud persistent PostgreSQL (Neon) when DATABASE_URL is configured.
- Local SQLite (data/auth.db) for local execution and automated tests.

Features:
- Granular Role-Based Access Control (RBAC):
  * 'alumno': Student FP - upload PDFs, preflight, fixes, imposition, submit FP assignments.
  * 'diseñador': Designer - view jobs, upload PDFs, run preflight, submit assignments.
  * 'preimpresion': Prepress Tech - fixes, imposition, CIP3, production orders, GWG, client links.
  * 'responsable': Workshop Manager - press release, profile management, hotfolder, versions.
  * 'docente': FP Teacher - classroom management, groups, assignments, rubrics, grading & progress.
  * 'admin': Full system administration and user/role approval.
- Email + password individual registration with safe role assignment and invite codes.
- Single active session per account (prevents concurrent shared-account usage).
- Client Approval Portal via secure unguessable tokens (no client account needed).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from db_store import (
    DEFAULT_DB_PATH,
    DuplicateEntryError,
    get_connection,
    get_database_url,
    get_db_status,
    is_postgres_configured,
)


# ---------------------------------------------------------------------------
# CONFIGURACIÓN Y RUTAS
# ---------------------------------------------------------------------------

DATA_DIR = DEFAULT_DB_PATH.parent
DB_PATH = DEFAULT_DB_PATH

# Clave secreta para firma de sesiones (prioridad variable de entorno para Render/Neon)
SECRET_KEY_PATH = DATA_DIR / ".session_secret"
_env_secret = os.environ.get("INTELLIPRINT_SESSION_SECRET", "").strip()
if _env_secret:
    SESSION_SECRET = _env_secret
elif SECRET_KEY_PATH.exists():
    SESSION_SECRET = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
else:
    SESSION_SECRET = secrets.token_hex(32)
    try:
        SECRET_KEY_PATH.write_text(SESSION_SECRET, encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MATRIZ DE PERMISOS POR ROL (RBAC)
# ---------------------------------------------------------------------------

VALID_ROLES = {"alumno", "diseñador", "preimpresion", "responsable", "docente", "admin"}
SELF_SERVICE_ROLES = {"alumno", "diseñador"}
PRIVILEGED_ROLES = {"preimpresion", "responsable", "docente", "admin"}

PERMISSIONS: Dict[str, Set[str]] = {
    "alumno": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "apply_fixes",
        "run_imposition",
        "generate_cip3",
        "create_production_order",
        "validate_gwg",
        "submit_fp_assignment",
    },
    "diseñador": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "submit_fp_assignment",
    },
    "preimpresion": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "apply_fixes",
        "run_imposition",
        "generate_cip3",
        "create_production_order",
        "validate_gwg",
        "share_client_approval",
    },
    "responsable": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "apply_fixes",
        "run_imposition",
        "generate_cip3",
        "create_production_order",
        "validate_gwg",
        "share_client_approval",
        "release_production",
        "manage_profiles",
        "control_hotfolder",
        "manage_versions",
        "manage_users",
    },
    "docente": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "apply_fixes",
        "run_imposition",
        "generate_cip3",
        "create_production_order",
        "validate_gwg",
        "view_student_progress",
        "grade_submissions",
        "manage_versions",
        "submit_fp_assignment",
    },
    "admin": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
        "apply_fixes",
        "run_imposition",
        "generate_cip3",
        "create_production_order",
        "validate_gwg",
        "share_client_approval",
        "release_production",
        "manage_profiles",
        "control_hotfolder",
        "manage_versions",
        "view_student_progress",
        "grade_submissions",
        "manage_users",
        "submit_fp_assignment",
    },
}


def user_has_permission(user: Optional[Dict[str, Any]], permission: str) -> bool:
    """Return True if the authenticated user owns the requested permission."""
    if not user:
        return False
    role = user.get("role", "")
    return permission in PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# GESTIÓN DE CONEXIÓN Y ESQUEMA (POSTGRESQL / SQLITE)
# ---------------------------------------------------------------------------

_INITIALIZED_AUTH_KEYS: Set[str] = set()


def get_db_cache_key(db_path: Optional[Path] = None) -> Optional[str]:
    """Return a cache key for an already-existing DB target, or None if not yet created."""
    target_db = Path(db_path) if db_path is not None else DB_PATH
    if is_postgres_configured(target_db):
        return f"pg:{get_database_url()}"
    try:
        if not target_db.exists():
            return None
        st = target_db.stat()
        if st.st_size <= 0:
            return None
        return f"sqlite:{target_db.resolve()}:{st.st_ctime_ns}"
    except OSError:
        return None


@contextmanager
def get_db_connection(db_path: Optional[Path] = None):
    """Context manager yielding a unified connection (Neon Postgres or SQLite)."""
    target_db = db_path if db_path is not None else DB_PATH
    with get_connection(target_db) as conn:
        yield conn


def _ensure_user_columns(conn) -> None:
    """Safely add new columns to legacy SQLite/Postgres `users` tables without throwing errors."""
    if getattr(conn, "postgres", False):
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS requested_role TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status TEXT DEFAULT 'ACTIVE'")
        conn.commit()
        return

    existing_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "requested_role" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN requested_role TEXT")
    if "approval_status" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'ACTIVE'")
    conn.commit()


def init_auth_db(db_path: Optional[Path] = None, force: bool = False):
    """Inicializa las tablas de usuarios, sesiones y aprobaciones e inserta cuentas base."""
    cache_key = get_db_cache_key(db_path)
    if not force and cache_key and cache_key in _INITIALIZED_AUTH_KEYS:
        return

    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT,
                requested_role TEXT,
                approval_status TEXT DEFAULT 'ACTIVE',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        _ensure_user_columns(conn)

        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
                ON users (LOWER(email))
                WHERE email IS NOT NULL AND email != ''
            """)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_approvals (
                token TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                client_name TEXT,
                client_email TEXT,
                decision TEXT,
                notes TEXT,
                decided_at TEXT,
                client_ip TEXT
            )
        """)
        conn.commit()

        # Insertar usuarios de demostración de taller y FP si la tabla está vacía
        cursor = conn.execute("SELECT COUNT(*) AS cnt FROM users")
        row = cursor.fetchone()
        count = row["cnt"] if row else 0
        if count == 0:
            default_users = [
                ("admin", "admin123", "Administrador IntelliPrint", "admin", "admin@salesianosurnieta.com"),
                ("responsable", "taller123", "Mikel Arregi (Jefe de Taller)", "responsable", "taller@salesianosurnieta.com"),
                ("preimpresion", "preim123", "Amaia Zubeldia (Técnica CTP)", "preimpresion", "ctp@salesianosurnieta.com"),
                ("docente", "docente123", "Carlos Gómez (Profesor Artes Gráficas)", "docente", "docente@cifpmendizabala.eus"),
                ("disenador", "diseno123", "Laura Etxeberria (Diseñadora Gráfica)", "diseñador", "diseno@agencia.com"),
            ]
            now_iso = datetime.now(timezone.utc).isoformat()
            for username, pwd, full_name, role, email in default_users:
                salt, pwd_hash = hash_password(pwd)
                conn.execute("""
                    INSERT INTO users (
                        username, password_hash, salt, full_name, role, email,
                        requested_role, approval_status, is_active, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 1, ?)
                """, (username, pwd_hash, salt, full_name, role, email, role, now_iso))
            conn.commit()

    final_key = get_db_cache_key(db_path)
    if final_key:
        _INITIALIZED_AUTH_KEYS.add(final_key)


# ---------------------------------------------------------------------------
# CRIPTOGRAFÍA Y HASHING SEGURO (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Genera hash seguro PBKDF2-SHA256 con salt de 16 bytes."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations=100_000)
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verifica si la contraseña coincide de forma segura contra ataques de tiempo."""
    _, dk = hash_password(password, salt)
    return hmac.compare_digest(dk, expected_hash)


# ---------------------------------------------------------------------------
# REGISTRO INDIVIDUAL Y ASIGNACIÓN DE ROLES
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_role(role: str) -> str:
    r = (role or "alumno").strip().lower()
    if r == "disenador":
        r = "diseñador"
    return r


def _validate_invite_code(desired_role: str, invite_code: Optional[str]) -> bool:
    """Verifica códigos opcionales configurados por entorno para alta directa de docentes/taller."""
    code = (invite_code or "").strip()
    if not code:
        return False
    if desired_role == "docente":
        expected = os.environ.get("INTELLIPRINT_DOCENTE_CODE", "").strip()
        return bool(expected) and hmac.compare_digest(code, expected)
    if desired_role in ("preimpresion", "responsable"):
        expected = os.environ.get("INTELLIPRINT_TALLER_CODE", "").strip()
        return bool(expected) and hmac.compare_digest(code, expected)
    return False


def register_user(
    email: str,
    password: str,
    full_name: str,
    requested_role: str = "alumno",
    invite_code: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Registra una cuenta individual con email y contraseña y asigna rol de forma segura.

    - Roles básicos ('alumno', 'diseñador'): se activan al instante.
    - Roles sensibles ('docente', 'preimpresion', 'responsable'):
      * Si aporta el código válido de centro/taller (variables de entorno), se activa directo.
      * Si no, queda registrado con estado PENDING hasta que admin/responsable apruebe su rol,
        evitando auto-escalado de privilegios o duplicación de cuentas compartidas.
    """
    init_auth_db(db_path)

    clean_email = (email or "").strip().lower()
    clean_name = (full_name or "").strip()
    if not clean_email or not _EMAIL_RE.match(clean_email):
        raise ValueError("Introduce un correo electrónico válido.")
    if len(clean_name) < 2:
        raise ValueError("Introduce tu nombre y apellidos.")
    if not password or len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")

    desired_role = _normalize_role(requested_role)
    if desired_role not in VALID_ROLES or desired_role == "admin":
        raise ValueError("Rol solicitado no permitido en el registro público.")

    if desired_role in SELF_SERVICE_ROLES:
        assigned_role = desired_role
        approval_status = "ACTIVE"
        is_active = 1
    elif _validate_invite_code(desired_role, invite_code):
        assigned_role = desired_role
        approval_status = "ACTIVE"
        is_active = 1
    else:
        assigned_role = desired_role
        approval_status = "PENDING"
        is_active = 0

    salt, pwd_hash = hash_password(password)
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(email) = ? OR LOWER(username) = ?",
            (clean_email, clean_email),
        ).fetchone()
        if existing:
            raise ValueError("Ya existe una cuenta registrada con ese correo electrónico.")

        try:
            row = conn.execute("""
                INSERT INTO users (
                    username, password_hash, salt, full_name, role, email,
                    requested_role, approval_status, is_active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                clean_email,
                pwd_hash,
                salt,
                clean_name,
                assigned_role,
                clean_email,
                desired_role,
                approval_status,
                is_active,
                now_iso,
            )).fetchone()
            conn.commit()
        except DuplicateEntryError as exc:
            raise ValueError("Ya existe una cuenta registrada con ese correo electrónico.") from exc

    user_id = row["id"] if row else None
    return {
        "id": user_id,
        "username": clean_email,
        "email": clean_email,
        "full_name": clean_name,
        "role": assigned_role,
        "requested_role": desired_role,
        "approval_status": approval_status,
        "is_active": bool(is_active),
        "permissions": list(PERMISSIONS.get(assigned_role, set())) if is_active else [],
    }


def list_users(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lista todas las cuentas registradas con su estado y sesiones activas."""
    init_auth_db(db_path)
    now = int(time.time())
    with get_db_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT u.id, u.username, u.email, u.full_name, u.role,
                   u.requested_role, u.approval_status, u.is_active, u.created_at,
                   (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.expires_at > ?) AS active_sessions
            FROM users u
            ORDER BY
                CASE WHEN COALESCE(u.approval_status, 'ACTIVE') = 'PENDING' THEN 0 ELSE 1 END,
                u.id ASC
        """, (now,)).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["is_active"] = bool(item.get("is_active"))
            item["approval_status"] = item.get("approval_status") or ("ACTIVE" if item["is_active"] else "DISABLED")
            result.append(item)
        return result


def update_user_access(
    user_id: int,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    approval_status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Permite al administrador aprobar solicitudes, asignar roles o activar/desactivar usuarios."""
    init_auth_db(db_path)
    with get_db_connection(db_path) as conn:
        current = conn.execute(
            "SELECT id, username, email, full_name, role, requested_role, approval_status, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not current:
            raise FileNotFoundError("Usuario no encontrado.")

        new_role = _normalize_role(role) if role is not None else current["role"]
        if new_role not in VALID_ROLES:
            raise ValueError(f"Rol no válido: {new_role}")

        new_active = int(is_active) if is_active is not None else int(current["is_active"])
        if approval_status is not None:
            new_status = approval_status.strip().upper()
        elif new_active == 1:
            new_status = "ACTIVE"
        else:
            new_status = current.get("approval_status") or "DISABLED"

        conn.execute("""
            UPDATE users
            SET role = ?, is_active = ?, approval_status = ?
            WHERE id = ?
        """, (new_role, new_active, new_status, user_id))

        # Si se desactiva la cuenta, cerrar inmediatamente sus sesiones
        if not new_active:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()

    return {
        "id": user_id,
        "username": current["username"],
        "email": current["email"],
        "full_name": current["full_name"],
        "role": new_role,
        "is_active": bool(new_active),
        "approval_status": new_status,
    }


# ---------------------------------------------------------------------------
# GESTIÓN DE SESIONES (SESIÓN ÚNICA ACTIVA POR CUENTA)
# ---------------------------------------------------------------------------

SESSION_DURATION_SECONDS = 24 * 3600  # 24 horas


def create_user_session(user_id: int, db_path: Optional[Path] = None, single_session: bool = True) -> str:
    """Crea una nueva sesión para el usuario.

    Con single_session=True (por defecto), cierra cualquier sesión anterior de esa misma
    cuenta para impedir que dos personas usen simultáneamente el mismo usuario.
    """
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    expires = now + SESSION_DURATION_SECONDS

    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        if single_session:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now, expires),
        )
        conn.commit()

    return session_id


def get_user_from_session(session_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Obtiene el usuario asociado a una sesión activa válida."""
    if not session_id:
        return None

    now = int(time.time())
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT u.id, u.username, u.full_name, u.role, u.email, u.is_active, u.approval_status
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_id = ? AND s.expires_at > ? AND u.is_active = 1
        """, (session_id, now))
        row = cursor.fetchone()
        if not row:
            return None

        user_data = dict(row)
        user_data["is_active"] = bool(user_data.get("is_active"))
        user_data["permissions"] = list(PERMISSIONS.get(user_data["role"], set()))
        return user_data


def delete_session(session_id: str, db_path: Optional[Path] = None):
    """Cierra la sesión eliminándola de la base de datos."""
    if not session_id:
        return
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()


def authenticate_user_detailed(
    identifier: str,
    password: str,
    db_path: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Autentica por usuario o email, devolviendo (usuario, motivo_error)."""
    clean_id = (identifier or "").strip()
    if not clean_id or not password:
        return None, "missing_credentials"

    with get_db_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT id, username, password_hash, salt, full_name, role, email, is_active, approval_status
            FROM users
            WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
        """, (clean_id, clean_id))
        row = cursor.fetchone()
        if not row:
            return None, "invalid_credentials"

        if not verify_password(password, row["salt"], row["password_hash"]):
            return None, "invalid_credentials"

        if not row["is_active"]:
            status = (row.get("approval_status") or "").upper()
            if status == "PENDING":
                return None, "pending_approval"
            return None, "disabled"

        user = {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "role": row["role"],
            "email": row["email"],
            "approval_status": row.get("approval_status") or "ACTIVE",
            "permissions": list(PERMISSIONS.get(row["role"], set())),
        }
        return user, None


def authenticate_user(username: str, password: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Autentica un usuario por username o email. Devuelve los datos del usuario si es correcto."""
    user, _ = authenticate_user_detailed(username, password, db_path=db_path)
    return user


# ---------------------------------------------------------------------------
# GESTIÓN DE APROBACIÓN DE CLIENTE (VISTO BUENO EXTERNO)
# ---------------------------------------------------------------------------

def generate_client_approval_link(job_id: str, base_url: str = "", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Genera un token y enlace seguro único para que el cliente apruebe el PDF."""
    token = secrets.token_urlsafe(24)
    now_str = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO client_approvals (token, job_id, created_at, status)
            VALUES (?, ?, ?, 'PENDING')
        """, (token, job_id, now_str))
        conn.commit()

    rel_url = f"/api/client-approval/view/{token}"
    full_url = f"{base_url.rstrip('/')}{rel_url}" if base_url else rel_url

    return {
        "token": token,
        "job_id": job_id,
        "approval_url": full_url,
        "created_at": now_str,
        "status": "PENDING",
    }


def get_client_approval_by_token(token: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Obtiene los datos de aprobación de cliente por su token seguro."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT * FROM client_approvals WHERE token = ?", (token,))
        row = cursor.fetchone()
        return dict(row) if row else None


def submit_client_decision(
    token: str,
    decision: str,
    client_name: str,
    client_email: Optional[str] = None,
    notes: Optional[str] = None,
    client_ip: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Registra la decisión formal del cliente (APPROVED o REJECTED)."""
    if decision not in ("approved", "rejected", "approved_with_notes"):
        raise ValueError("Decisión no válida: debe ser approved o rejected.")

    now_str = datetime.now(timezone.utc).isoformat()
    status_str = "APPROVED" if decision in ("approved", "approved_with_notes") else "REJECTED"

    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT * FROM client_approvals WHERE token = ?", (token,))
        row = cursor.fetchone()
        if not row:
            raise FileNotFoundError("Token de aprobación no encontrado.")

        conn.execute("""
            UPDATE client_approvals
            SET status = ?, client_name = ?, client_email = ?, decision = ?, notes = ?, decided_at = ?, client_ip = ?
            WHERE token = ?
        """, (status_str, client_name.strip(), client_email, decision, notes or "", now_str, client_ip or "", token))
        conn.commit()

        job_id = row["job_id"]

    return {
        "token": token,
        "job_id": job_id,
        "status": status_str,
        "decision": decision,
        "client_name": client_name,
        "decided_at": now_str,
        "notes": notes,
    }


# Inicialización automática al cargar el módulo
try:
    init_auth_db()
except Exception:
    pass
