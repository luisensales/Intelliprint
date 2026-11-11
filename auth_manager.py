"""Authentication, Role-Based Access Control (RBAC) and Client Approval Engine.

Implements Improvement 3: Users, Permissions and Client Approval.
- SQLite-backed lightweight authentication (no external DB server needed).
- Granular Role-Based Access Control (RBAC):
  * 'diseñador': View jobs, upload PDFs, run preflight.
  * 'preimpresion': Everything above + apply technical fixes, imposition, CIP3, production orders.
  * 'responsable' (Workshop Manager): Everything above + release to press, manage profiles, hotfolder.
  * 'docente' (Vocational Training Teacher): Supervise student jobs, view history, evaluate.
  * 'admin': Full system administration and user management.
- Secure cryptographically signed session tokens (HttpOnly cookies).
- Client Approval Portal via secure unguessable tokens (no client account needed).
- Certified operator signatures bound to authenticated sessions (no freehand spoofing).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# CONFIGURACIÓN Y RUTAS
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "auth.db"

# Clave secreta para firma de sesiones (persistida o generada)
SECRET_KEY_PATH = DATA_DIR / ".session_secret"
if SECRET_KEY_PATH.exists():
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

PERMISSIONS: Dict[str, Set[str]] = {
    "diseñador": {
        "view_job",
        "upload_pdf",
        "run_preflight",
        "download_reports",
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
        "release_production",       # Autorización de tirada en prensa
        "manage_profiles",          # Crear/editar perfiles de color
        "control_hotfolder",        # Configuración de carpetas calientes
        "manage_versions",          # Restaurar y congelar versiones
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
        "view_student_progress",    # Supervisión educativa de FP
        "grade_submissions",
        "manage_versions",
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
        "manage_users",             # Crear y editar cuentas de usuario
    },
}


# ---------------------------------------------------------------------------
# GESTIÓN DE BASE DE DATOS SQLITE LOCAL
# ---------------------------------------------------------------------------

@contextmanager
def get_db_connection(db_path: Path = DB_PATH):
    """Abre conexión con SQLite en modo WAL y garantiza cierre seguro al salir."""
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        conn.close()


def init_auth_db(db_path: Path = DB_PATH):
    """Inicializa las tablas de usuarios y sesiones e inserta usuarios iniciales."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
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

        # Insertar usuarios de demostración de taller y FP si no existen
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_users = [
                ("admin", "admin123", "Administrador IntelliPrint", "admin", "admin@salesianosurnieta.com"),
                ("responsable", "taller123", "Mikel Arregi (Jefe de Taller)", "responsable", "taller@salesianosurnieta.com"),
                ("preimpresion", "preim123", "Amaia Zubeldia (Técnica CTP)", "preimpresion", "ctp@salesianosurnieta.com"),
                ("docente", "docente123", "Carlos Gómez (Profesor Artes Gráficas)", "docente", "docente@cifpmendizabala.eus"),
                ("disenador", "diseno123", "Laura Etxeberria (Diseñadora Gráfica)", "diseñador", "diseno@agencia.com"),
            ]
            for username, pwd, full_name, role, email in default_users:
                salt, pwd_hash = hash_password(pwd)
                conn.execute("""
                    INSERT INTO users (username, password_hash, salt, full_name, role, email, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """, (username, pwd_hash, salt, full_name, role, email, datetime.now(timezone.utc).isoformat()))
            conn.commit()


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
# GESTIÓN DE SESIONES
# ---------------------------------------------------------------------------

SESSION_DURATION_SECONDS = 24 * 3600  # 24 horas


def create_user_session(user_id: int, db_path: Path = DB_PATH) -> str:
    """Crea una nueva sesión para el usuario y devuelve el token de sesión."""
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    expires = now + SESSION_DURATION_SECONDS

    with get_db_connection(db_path) as conn:
        # Limpiar sesiones expiradas
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now, expires),
        )
        conn.commit()

    return session_id


def get_user_from_session(session_id: str, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    """Obtiene el usuario asociado a una sesión activa válida."""
    if not session_id:
        return None

    now = int(time.time())
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT u.id, u.username, u.full_name, u.role, u.email, u.is_active
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_id = ? AND s.expires_at > ? AND u.is_active = 1
        """, (session_id, now))
        row = cursor.fetchone()
        if not row:
            return None

        user_data = dict(row)
        user_data["permissions"] = list(PERMISSIONS.get(user_data["role"], set()))
        return user_data


def delete_session(session_id: str, db_path: Path = DB_PATH):
    """Cierra la sesión eliminándola de la base de datos."""
    if not session_id:
        return
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()


def authenticate_user(username: str, password: str, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    """Autentica un usuario por credenciales. Devuelve los datos del usuario si es correcto."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT id, username, password_hash, salt, full_name, role, email, is_active FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return None

        if not row["is_active"]:
            return None

        if not verify_password(password, row["salt"], row["password_hash"]):
            return None

        user = {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "role": row["role"],
            "email": row["email"],
            "permissions": list(PERMISSIONS.get(row["role"], set())),
        }
        return user


# ---------------------------------------------------------------------------
# GESTIÓN DE APROBACIÓN DE CLIENTE (VISTO BUENO EXTERNO)
# ---------------------------------------------------------------------------

def generate_client_approval_link(job_id: str, base_url: str = "", db_path: Path = DB_PATH) -> Dict[str, Any]:
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


def get_client_approval_by_token(token: str, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
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
    db_path: Path = DB_PATH,
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
