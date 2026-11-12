"""FP Classroom & Teacher Evaluation Panel for IntelliPrint.

Supports dual persistence (Neon PostgreSQL in cloud via DATABASE_URL, SQLite in local/tests).
Provides:
- Groups / courses with join codes
- Assignments linked to existing didactic scenarios OR real student PDFs
- Weighted FP rubrics with automated pre-scoring
- Forensic comparison: Initial Diagnosis -> Decisions & Fixes Timeline -> Final Result
- Student evolution analytics, quiz score integration, CSV gradebook & A4 PDF evaluation reports
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import html as html_lib
import io
import json
from pathlib import Path
import secrets
import string
from typing import Any, Dict, List, Optional, Set

import pymupdf

from auth_manager import get_db_cache_key, get_db_connection, init_auth_db

_INITIALIZED_FP_KEYS: Set[str] = set()


# ---------------------------------------------------------------------------
# RÚBRICAS PREDEFINIDAS DE ARTES GRÁFICAS (FP)
# ---------------------------------------------------------------------------

DEFAULT_RUBRICS = [
    {
        "title": "Rúbrica Estándar Preimpresión Offset (PDF/X y Correcciones)",
        "description": "Evalúa diagnóstico inicial, criterio técnico en correcciones, conformidad final PDF/X y preparación para máquina.",
        "criteria": [
            {
                "id": "diagnostico",
                "name": "Diagnóstico Técnico Inicial",
                "weight": 20,
                "max_score": 10,
                "description": "Identificación de perfil destino, color, resolución, sangrado y fuentes de partida.",
            },
            {
                "id": "decisiones",
                "name": "Criterio en Correcciones y Trazabilidad",
                "weight": 30,
                "max_score": 10,
                "description": "Selección adecuada de herramientas y revisión sin degradar el arte original.",
            },
            {
                "id": "resultado_final",
                "name": "Conformidad Técnica y Calidad Final",
                "weight": 30,
                "max_score": 10,
                "description": "Resolución de errores críticos (CMYK, TAC, sangres, fuentes) y validación GWG/PDF/X.",
            },
            {
                "id": "taller_teoria",
                "name": "Preparación Taller / Imposición / Cuestionario",
                "weight": 20,
                "max_score": 10,
                "description": "Orden de producción, marcas de corte, imposición o cuestionario teórico.",
            },
        ],
    },
    {
        "title": "Rúbrica Iniciación Preflight y Colorimetría (1º GM / 1º GS)",
        "description": "Enfocada en detección de imágenes RGB, resolución mínima, sangrado 3 mm y conversión CMYK.",
        "criteria": [
            {
                "id": "deteccion",
                "name": "Detección de Errores Básicos",
                "weight": 35,
                "max_score": 10,
                "description": "Localización de RGB, baja resolución y falta de sangrado.",
            },
            {
                "id": "correccion",
                "name": "Conversión Color y Sangrado Correctos",
                "weight": 40,
                "max_score": 10,
                "description": "Aplicación de perfil ISO Coated v2 / FOGRA39 y sangrado de 3 mm.",
            },
            {
                "id": "verificacion",
                "name": "Verificación Final sin Errores Críticos",
                "weight": 25,
                "max_score": 10,
                "description": "Comprobación posterior del PDF corregido y generación de informe.",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# INICIALIZACIÓN DE TABLAS
# ---------------------------------------------------------------------------

def _ensure_fp_assignment_columns(conn) -> None:
    """Safely add new pedagogy columns on legacy SQLite/Postgres `fp_assignments` tables."""
    if getattr(conn, "postgres", False):
        conn.execute("ALTER TABLE fp_assignments ADD COLUMN IF NOT EXISTS exam_mode INTEGER DEFAULT 0")
        conn.commit()
        return

    existing = {row["name"] for row in conn.execute("PRAGMA table_info(fp_assignments)").fetchall()}
    if "exam_mode" not in existing:
        conn.execute("ALTER TABLE fp_assignments ADD COLUMN exam_mode INTEGER DEFAULT 0")
        conn.commit()


def init_fp_db(db_path: Optional[Path] = None, force: bool = False) -> None:
    """Inicializa tablas del Panel Docente FP e inserta rúbricas por defecto."""
    cache_key = get_db_cache_key(db_path)
    if not force and cache_key and cache_key in _INITIALIZED_FP_KEYS:
        return
    init_auth_db(db_path, force=force)
    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                center TEXT NOT NULL,
                module_name TEXT NOT NULL,
                join_code TEXT UNIQUE NOT NULL,
                teacher_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                UNIQUE (group_id, student_id),
                FOREIGN KEY (group_id) REFERENCES fp_groups (id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_rubrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                criteria_json TEXT NOT NULL,
                teacher_id INTEGER,
                is_default INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                assignment_type TEXT NOT NULL DEFAULT 'pdf_real',
                scenario_id TEXT,
                target_profile TEXT DEFAULT 'OFFSET_300',
                rubric_id INTEGER,
                due_date TEXT,
                is_open INTEGER DEFAULT 1,
                exam_mode INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES fp_groups (id) ON DELETE CASCADE,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (rubric_id) REFERENCES fp_rubrics (id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                job_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                status TEXT DEFAULT 'SUBMITTED',
                comparison_json TEXT NOT NULL,
                rubric_scores_json TEXT,
                final_grade REAL,
                teacher_feedback TEXT,
                graded_by INTEGER,
                graded_at TEXT,
                FOREIGN KEY (assignment_id) REFERENCES fp_assignments (id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (graded_by) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                assignment_id INTEGER,
                topic TEXT NOT NULL,
                score_pct REAL NOT NULL,
                correct_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fp_custom_challenges (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL DEFAULT 'docente',
                level TEXT NOT NULL DEFAULT 'Reto Docente FP',
                module TEXT NOT NULL DEFAULT 'Preimpresión y Arte Final',
                doc_type TEXT NOT NULL DEFAULT 'PDF Personalizado',
                target_profile TEXT NOT NULL DEFAULT 'OFFSET_300',
                iso_norm TEXT NOT NULL DEFAULT 'ISO 12647-2 / PDF/X',
                target_errors_json TEXT NOT NULL DEFAULT '[]',
                learning_goals_json TEXT NOT NULL DEFAULT '[]',
                filename TEXT NOT NULL,
                pdf_sha256 TEXT,
                teacher_id INTEGER,
                teacher_name TEXT,
                is_published INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        conn.commit()
        _ensure_fp_assignment_columns(conn)

        row = conn.execute("SELECT COUNT(*) AS cnt FROM fp_rubrics").fetchone()
        if (row["cnt"] if row else 0) == 0:
            now_iso = datetime.now(timezone.utc).isoformat()
            for rb in DEFAULT_RUBRICS:
                conn.execute("""
                    INSERT INTO fp_rubrics (title, description, criteria_json, teacher_id, is_default, created_at)
                    VALUES (?, ?, ?, NULL, 1, ?)
                """, (rb["title"], rb["description"], json.dumps(rb["criteria"], ensure_ascii=False), now_iso))
            conn.commit()

    final_key = get_db_cache_key(db_path)
    if final_key:
        _INITIALIZED_FP_KEYS.add(final_key)


# ---------------------------------------------------------------------------
# ANÁLISIS COMPARATIVO FORENSE (INICIAL -> DECISIONES -> FINAL)
# ---------------------------------------------------------------------------

def _summarize_findings(findings: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    """Resume los hallazgos técnicos de un análisis en métricas comparables."""
    critical = 0
    warnings = 0
    infos = 0
    categories: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []

    for f in findings or []:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", f.get("type", ""))).lower()
        if sev in ("error", "critical", "fatal"):
            critical += 1
            norm_sev = "CRITICAL"
        elif sev in ("warning", "warn"):
            warnings += 1
            norm_sev = "WARNING"
        else:
            infos += 1
            norm_sev = "INFO"

        cat = str(f.get("category") or f.get("rule_id") or f.get("code") or "General")
        categories[cat] = categories.get(cat, 0) + 1
        items.append({
            "severity": norm_sev,
            "category": cat,
            "message": str(f.get("message") or f.get("description") or f.get("title") or "")[:180],
            "page": f.get("page"),
        })

    return {
        "critical_count": critical,
        "warning_count": warnings,
        "info_count": infos,
        "total_issues": critical + warnings,
        "categories": categories,
        "items": items[:25],
        "page_count": summary.get("page_count", 1) if isinstance(summary, dict) else 1,
        "tac_max": summary.get("max_tac") if isinstance(summary, dict) else None,
        "color_spaces": summary.get("color_spaces", []) if isinstance(summary, dict) else [],
    }


def _collect_decisions_timeline(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Recopila la trazabilidad cronológica de decisiones tomadas sobre el trabajo."""
    meta = job_data.get("job_meta", {}) if isinstance(job_data.get("job_meta"), dict) else {}
    fixes = list(meta.get("applied_fixes_history") or [])
    batch_steps = list(meta.get("batch_steps_applied") or [])

    flag_labels = {
        "has_icc_fix": "Conversión / Incrustación de Perfil ICC",
        "has_icc_fixed": "Conversión / Incrustación de Perfil ICC",
        "has_cmyk_images": "Conversión de imágenes RGB a CMYK",
        "has_cmyk_converted": "Conversión de imágenes RGB a CMYK",
        "has_tac_fix": "Reducción de Cobertura Total de Tinta (TAC)",
        "has_tac_limited": "Reducción de Cobertura Total de Tinta (TAC)",
        "has_overprint_fix": "Corrección de Sobreimpresión / Knockout",
        "has_overprint_fixed": "Corrección de Sobreimpresión / Knockout",
        "has_varnish_overprint": "Sobreimpresión de Barniz Reserva / Troquel",
        "has_bleed_fix": "Generación / Ajuste de Sangrado y Cajas PDF",
        "has_bleed_fixed": "Generación / Ajuste de Sangrado y Cajas PDF",
        "has_mirror_bleed": "Generación de Sangrado por Espejo (Mirror Bleed)",
        "has_outline_fix": "Trazado de Fuentes a Curvas / Incrustación",
        "has_fonts_outlined": "Trazado de Fuentes a Curvas / Incrustación",
        "has_hairline_fix": "Engrosamiento de Líneas Finas (Hairlines)",
        "has_hairline_fixed": "Engrosamiento de Líneas Finas (Hairlines)",
        "has_spot_fix": "Conversión de Tintas Planas (Spot -> CMYK)",
        "has_spot_converted": "Conversión de Tintas Planas (Spot -> CMYK)",
        "has_barcode_fix": "Optimización de Código de Barras (100% K)",
        "has_barcode_fixed": "Optimización de Código de Barras (100% K)",
        "has_marks_fix": "Marcas de Corte / Tira de Control",
        "has_printer_marks": "Marcas de Corte / Tira de Control",
    }
    inferred_actions: List[str] = []
    for k, label in flag_labels.items():
        if meta.get(k) and label not in inferred_actions:
            inferred_actions.append(label)

    versions = job_data.get("version_history_summary") or []
    gwg = (
        job_data.get("production_validation")
        or job_data.get("gwg_validation_report")
        or meta.get("production_validation")
        or meta.get("gwg_validation_report")
    )
    prod_order = job_data.get("production_order") or meta.get("production_order")
    client_approval = job_data.get("client_approval_record") or job_data.get("client_approval")

    steps: List[Dict[str, Any]] = []
    for item in fixes:
        if isinstance(item, dict):
            steps.append({
                "type": "fix",
                "action": item.get("action") or item.get("fix") or item.get("label") or "Corrección aplicada",
                "timestamp": item.get("timestamp") or item.get("applied_at") or "",
                "detail": item.get("detail") or "",
            })
        else:
            steps.append({"type": "fix", "action": str(item), "timestamp": "", "detail": ""})

    if not steps and batch_steps:
        for b in batch_steps:
            steps.append({"type": "batch", "action": f"Lote 1-Clic: {b}", "timestamp": "", "detail": ""})

    if not steps and inferred_actions:
        for act in inferred_actions:
            steps.append({"type": "fix", "action": act, "timestamp": "", "detail": ""})

    if prod_order:
        steps.append({"type": "order", "action": "Orden de Producción / Imposición configurada", "timestamp": "", "detail": ""})
    gwg_verdict = (
        (gwg.get("overall_verdict") or gwg.get("overall_status") or gwg.get("status"))
        if isinstance(gwg, dict)
        else None
    )
    if gwg:
        gwg_status = gwg_verdict or "EJECUTADA"
        steps.append({"type": "gwg", "action": f"Validación Pericial GWG ({gwg_status})", "timestamp": "", "detail": ""})
    if client_approval:
        steps.append({"type": "client", "action": "Enlace de Visto Bueno de Cliente generado", "timestamp": "", "detail": ""})

    return {
        "steps": steps,
        "fixes_count": len(fixes) + len(inferred_actions) if not fixes else len(fixes),
        "batch_steps_count": len(batch_steps),
        "versions_count": len(versions),
        "used_gwg_validation": bool(gwg),
        "gwg_status": gwg_verdict,
        "used_production_order": bool(prod_order),
        "used_client_approval": bool(client_approval),
        "used_batch_fix": bool(batch_steps),
    }


def build_submission_comparison(
    job_data: Dict[str, Any],
    rubric_criteria: Optional[List[Dict[str, Any]]] = None,
    exam_mode: bool = False,
) -> Dict[str, Any]:
    """Genera el informe comparativo Inicial -> Decisiones -> Final y propone pre-calificación."""
    orig = job_data.get("original_analysis")
    if isinstance(orig, dict) and orig.get("findings") is not None:
        initial_summary = _summarize_findings(orig.get("findings", []), orig.get("job_summary", {}))
        initial_source = "original_analysis"
    else:
        initial_summary = _summarize_findings(job_data.get("findings", []), job_data.get("job_summary", {}))
        initial_source = "current_only"

    final_summary = _summarize_findings(job_data.get("findings", []), job_data.get("job_summary", {}))
    decisions = _collect_decisions_timeline(job_data)

    resolved_critical = max(0, initial_summary["critical_count"] - final_summary["critical_count"])
    resolved_warnings = max(0, initial_summary["warning_count"] - final_summary["warning_count"])
    introduced_critical = max(0, final_summary["critical_count"] - initial_summary["critical_count"])

    if initial_summary["critical_count"] > 0:
        critical_resolution_pct = round((resolved_critical / initial_summary["critical_count"]) * 100.0, 1)
    else:
        critical_resolution_pct = 100.0 if final_summary["critical_count"] == 0 else 0.0

    # Detección de puntos clave pedagógicos para el docente
    observations: List[str] = []
    if initial_summary["critical_count"] > 0 and final_summary["critical_count"] == 0:
        observations.append("El alumno ha resuelto el 100% de los errores críticos iniciales.")
    elif resolved_critical > 0:
        observations.append(
            f"Resolvió {resolved_critical} de {initial_summary['critical_count']} errores críticos, "
            f"pero permanecen {final_summary['critical_count']} sin subsanar."
        )
    elif final_summary["critical_count"] > 0:
        observations.append(f"Mantiene {final_summary['critical_count']} errores críticos sin corregir.")

    if introduced_critical > 0:
        observations.append(f"Atención: aparecieron {introduced_critical} errores críticos nuevos respecto al original.")

    if decisions["fixes_count"] == 0 and decisions["batch_steps_count"] == 0 and initial_summary["critical_count"] > 0:
        observations.append("Entregó el PDF sin aplicar correcciones técnicas en la aplicación.")
    elif decisions["batch_steps_count"] > 0 and decisions["fixes_count"] <= 1:
        observations.append("Aplicó corrección automática en lote; conviene revisar si ajustó parámetros.")

    if decisions["used_gwg_validation"]:
        observations.append(f"Verificó el resultado final con Validación GWG ({decisions['gwg_status']}).")
    if decisions["used_production_order"]:
        observations.append("Completó la Orden de Producción técnica / selección de máquina.")
    if exam_mode:
        if decisions.get("used_batch_fix"):
            observations.append("Aviso Modo Examen: utilizó corrección automática en lote (1 Clic).")
        elif decisions["fixes_count"] > 0:
            observations.append("Modo Examen cumplido: aplicó las correcciones paso a paso sin automatismo en 1 Clic.")

    # Pre-calificación orientativa por criterio (escala 0..10)
    diag_score = 9.0 if initial_source == "original_analysis" else 7.0
    if decisions["fixes_count"] > 0 or decisions["used_gwg_validation"]:
        decision_score = 8.5 if introduced_critical == 0 else 5.5
    elif initial_summary["critical_count"] == 0:
        decision_score = 8.5
    else:
        decision_score = 3.5

    if final_summary["critical_count"] == 0 and final_summary["warning_count"] == 0:
        final_score = 10.0
    elif final_summary["critical_count"] == 0:
        final_score = max(7.0, 9.5 - min(2.5, final_summary["warning_count"] * 0.5))
    else:
        final_score = max(2.0, round((critical_resolution_pct / 100.0) * 7.5, 1))

    taller_score = 5.0
    if decisions["used_production_order"]:
        taller_score += 2.5
    if decisions["used_gwg_validation"]:
        taller_score += 2.0
    if decisions["versions_count"] >= 2:
        taller_score += 0.5
    taller_score = min(10.0, round(taller_score, 1))

    suggested_scores: Dict[str, float] = {}
    for c in (rubric_criteria or DEFAULT_RUBRICS[0]["criteria"]):
        cid = c["id"]
        if "diag" in cid or "detec" in cid:
            suggested_scores[cid] = round(diag_score, 1)
        elif "decis" in cid or "correc" in cid:
            suggested_scores[cid] = round(decision_score, 1)
        elif "final" in cid or "verif" in cid or "calidad" in cid:
            suggested_scores[cid] = round(final_score, 1)
        else:
            suggested_scores[cid] = round(taller_score, 1)

    return {
        "initial_source": initial_source,
        "initial": initial_summary,
        "decisions": decisions,
        "final": final_summary,
        "delta": {
            "resolved_critical": resolved_critical,
            "resolved_warnings": resolved_warnings,
            "introduced_critical": introduced_critical,
            "critical_resolution_pct": critical_resolution_pct,
        },
        "observations": observations,
        "suggested_scores": suggested_scores,
        "suggested_final_grade": _compute_weighted_grade(suggested_scores, rubric_criteria or DEFAULT_RUBRICS[0]["criteria"]),
    }


def _compute_weighted_grade(scores: Dict[str, float], criteria: List[Dict[str, Any]]) -> float:
    """Calcula la nota final ponderada sobre 10."""
    total_weight = sum(float(c.get("weight", 0)) for c in criteria) or 100.0
    weighted = 0.0
    for c in criteria:
        cid = c["id"]
        w = float(c.get("weight", 0))
        max_s = float(c.get("max_score", 10)) or 10.0
        val = float(scores.get(cid, 0.0))
        val = max(0.0, min(max_s, val))
        weighted += (val / max_s) * 10.0 * (w / total_weight)
    return round(weighted, 2)


# ---------------------------------------------------------------------------
# GESTIÓN DOCENTE: GRUPOS, RÚBRICAS, PRÁCTICAS Y CALIFICACIONES
# ---------------------------------------------------------------------------

def _generate_join_code(prefix: str = "FP") -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{prefix}-{suffix}"


def create_group(
    name: str,
    center: str,
    module_name: str,
    teacher_id: int,
    join_code: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_fp_db(db_path)
    clean_name = (name or "").strip()
    if len(clean_name) < 2:
        raise ValueError("El nombre del grupo es obligatorio.")
    code = (join_code or _generate_join_code()).strip().upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        row = conn.execute("""
            INSERT INTO fp_groups (name, center, module_name, join_code, teacher_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (clean_name, (center or "CPIFP Artes Gráficas").strip(), (module_name or "Preimpresión Digital").strip(), code, teacher_id, now_iso)).fetchone()
        conn.commit()
    return {
        "id": row["id"],
        "name": clean_name,
        "center": center,
        "module_name": module_name,
        "join_code": code,
        "teacher_id": teacher_id,
        "created_at": now_iso,
    }


def list_groups(teacher_id: Optional[int] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        sql = """
            SELECT g.*, u.full_name AS teacher_name,
                   (SELECT COUNT(*) FROM fp_enrollments e WHERE e.group_id = g.id) AS student_count,
                   (SELECT COUNT(*) FROM fp_assignments a WHERE a.group_id = g.id) AS assignment_count
            FROM fp_groups g
            LEFT JOIN users u ON g.teacher_id = u.id
        """
        params: Tuple[Any, ...] = ()
        if teacher_id is not None:
            sql += " WHERE g.teacher_id = ?"
            params = (teacher_id,)
        sql += " ORDER BY g.id DESC"
        return conn.execute(sql, params).fetchall()


def list_rubrics(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM fp_rubrics ORDER BY is_default DESC, id ASC").fetchall()
        for r in rows:
            try:
                r["criteria"] = json.loads(r["criteria_json"])
            except Exception:
                r["criteria"] = []
        return rows


def create_rubric(
    title: str,
    description: str,
    criteria: List[Dict[str, Any]],
    teacher_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_fp_db(db_path)
    if not title or not criteria:
        raise ValueError("Título y criterios de rúbrica obligatorios.")
    now_iso = datetime.now(timezone.utc).isoformat()
    c_json = json.dumps(criteria, ensure_ascii=False)
    with get_db_connection(db_path) as conn:
        row = conn.execute("""
            INSERT INTO fp_rubrics (title, description, criteria_json, teacher_id, is_default, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            RETURNING id
        """, (title.strip(), (description or "").strip(), c_json, teacher_id, now_iso)).fetchone()
        conn.commit()
    return {"id": row["id"], "title": title.strip(), "description": description, "criteria": criteria}


def create_assignment(
    group_id: int,
    teacher_id: int,
    title: str,
    description: str = "",
    assignment_type: str = "pdf_real",
    scenario_id: Optional[str] = None,
    target_profile: str = "OFFSET_300",
    rubric_id: Optional[int] = None,
    due_date: Optional[str] = None,
    exam_mode: bool = False,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_fp_db(db_path)
    clean_title = (title or "").strip()
    if len(clean_title) < 2:
        raise ValueError("El título de la práctica es obligatorio.")
    if assignment_type not in ("reto", "pdf_real", "libre"):
        assignment_type = "pdf_real"

    exam_flag = 1 if exam_mode else 0
    with get_db_connection(db_path) as conn:
        grp = conn.execute("SELECT id FROM fp_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise FileNotFoundError("Grupo no encontrado.")

        if rubric_id is None:
            rb = conn.execute("SELECT id FROM fp_rubrics ORDER BY is_default DESC, id ASC LIMIT 1").fetchone()
            rubric_id = rb["id"] if rb else None

        now_iso = datetime.now(timezone.utc).isoformat()
        row = conn.execute("""
            INSERT INTO fp_assignments (
                group_id, teacher_id, title, description, assignment_type,
                scenario_id, target_profile, rubric_id, due_date, is_open, exam_mode, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            RETURNING id
        """, (
            group_id,
            teacher_id,
            clean_title,
            (description or "").strip(),
            assignment_type,
            scenario_id or None,
            target_profile or "OFFSET_300",
            rubric_id,
            due_date or None,
            exam_flag,
            now_iso,
        )).fetchone()
        conn.commit()

    return {
        "id": row["id"],
        "group_id": group_id,
        "title": clean_title,
        "assignment_type": assignment_type,
        "scenario_id": scenario_id,
        "target_profile": target_profile,
        "rubric_id": rubric_id,
        "due_date": due_date,
        "exam_mode": bool(exam_flag),
        "created_at": now_iso,
    }


def list_assignments(group_id: Optional[int] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        sql = """
            SELECT a.*, g.name AS group_name, g.join_code, r.title AS rubric_title,
                   (SELECT COUNT(*) FROM fp_submissions s WHERE s.assignment_id = a.id) AS submission_count
            FROM fp_assignments a
            JOIN fp_groups g ON a.group_id = g.id
            LEFT JOIN fp_rubrics r ON a.rubric_id = r.id
        """
        params: Tuple[Any, ...] = ()
        if group_id is not None:
            sql += " WHERE a.group_id = ?"
            params = (group_id,)
        sql += " ORDER BY a.id DESC"
        rows = conn.execute(sql, params).fetchall()
        for r in rows:
            r["exam_mode"] = bool(r.get("exam_mode"))
        return rows


def join_group_by_code(student_id: int, join_code: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    init_fp_db(db_path)
    code = (join_code or "").strip().upper()
    if not code:
        raise ValueError("Introduce un código de clase válido.")
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        grp = conn.execute("SELECT * FROM fp_groups WHERE UPPER(join_code) = ?", (code,)).fetchone()
        if not grp:
            raise FileNotFoundError("No existe ningún grupo con ese código de clase.")
        existing = conn.execute(
            "SELECT id FROM fp_enrollments WHERE group_id = ? AND student_id = ?",
            (grp["id"], student_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO fp_enrollments (group_id, student_id, joined_at) VALUES (?, ?, ?)",
                (grp["id"], student_id, now_iso),
            )
            conn.commit()
    return {"group": grp, "joined_at": now_iso}


def submit_job_for_assignment(
    student_id: int,
    assignment_id: int,
    job_id: str,
    job_data: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Registra la entrega de un PDF real/corregido con instantánea comparativa."""
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        asg = conn.execute("SELECT * FROM fp_assignments WHERE id = ?", (assignment_id,)).fetchone()
        if not asg:
            raise FileNotFoundError("Práctica no encontrada.")

        # Auto-matricular si aún no estaba inscrito y la práctica está abierta
        enrolled = conn.execute(
            "SELECT id FROM fp_enrollments WHERE group_id = ? AND student_id = ?",
            (asg["group_id"], student_id),
        ).fetchone()
        if not enrolled:
            conn.execute(
                "INSERT INTO fp_enrollments (group_id, student_id, joined_at) VALUES (?, ?, ?)",
                (asg["group_id"], student_id, datetime.now(timezone.utc).isoformat()),
            )

        criteria = DEFAULT_RUBRICS[0]["criteria"]
        if asg.get("rubric_id"):
            rb = conn.execute("SELECT criteria_json FROM fp_rubrics WHERE id = ?", (asg["rubric_id"],)).fetchone()
            if rb:
                criteria = json.loads(rb["criteria_json"])

        comparison = build_submission_comparison(
            job_data,
            rubric_criteria=criteria,
            exam_mode=bool(asg.get("exam_mode")),
        )
        meta = job_data.get("job_meta", {}) if isinstance(job_data.get("job_meta"), dict) else {}
        filename = meta.get("filename") or f"{job_id}.pdf"
        now_iso = datetime.now(timezone.utc).isoformat()

        row = conn.execute("""
            INSERT INTO fp_submissions (
                assignment_id, student_id, job_id, filename, submitted_at,
                status, comparison_json
            )
            VALUES (?, ?, ?, ?, ?, 'SUBMITTED', ?)
            RETURNING id
        """, (
            assignment_id,
            student_id,
            job_id,
            filename,
            now_iso,
            json.dumps(comparison, ensure_ascii=False),
        )).fetchone()
        conn.commit()

    return {
        "id": row["id"],
        "assignment_id": assignment_id,
        "student_id": student_id,
        "job_id": job_id,
        "filename": filename,
        "submitted_at": now_iso,
        "status": "SUBMITTED",
        "comparison": comparison,
    }


def list_submissions(
    group_id: Optional[int] = None,
    assignment_id: Optional[int] = None,
    student_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        sql = """
            SELECT s.*, a.title AS assignment_title, a.group_id, a.rubric_id, a.target_profile,
                   a.exam_mode AS assignment_exam_mode,
                   g.name AS group_name, u.full_name AS student_name, u.email AS student_email,
                   r.criteria_json
            FROM fp_submissions s
            JOIN fp_assignments a ON s.assignment_id = a.id
            JOIN fp_groups g ON a.group_id = g.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN fp_rubrics r ON a.rubric_id = r.id
            WHERE 1=1
        """
        params: List[Any] = []
        if group_id is not None:
            sql += " AND a.group_id = ?"
            params.append(group_id)
        if assignment_id is not None:
            sql += " AND s.assignment_id = ?"
            params.append(assignment_id)
        if student_id is not None:
            sql += " AND s.student_id = ?"
            params.append(student_id)
        sql += " ORDER BY s.id DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
        for item in rows:
            try:
                item["comparison"] = json.loads(item.get("comparison_json") or "{}")
            except Exception:
                item["comparison"] = {}
            try:
                item["rubric_scores"] = json.loads(item.get("rubric_scores_json") or "{}") if item.get("rubric_scores_json") else None
            except Exception:
                item["rubric_scores"] = None
            try:
                item["rubric_criteria"] = json.loads(item.get("criteria_json") or "[]") if item.get("criteria_json") else DEFAULT_RUBRICS[0]["criteria"]
            except Exception:
                item["rubric_criteria"] = DEFAULT_RUBRICS[0]["criteria"]
        return rows


def get_submission_detail(submission_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        row = conn.execute("""
            SELECT s.*, a.title AS assignment_title, a.description AS assignment_description,
                   a.group_id, a.rubric_id, a.target_profile, a.exam_mode AS assignment_exam_mode,
                   g.name AS group_name, g.center, g.module_name,
                   u.full_name AS student_name, u.email AS student_email,
                   r.title AS rubric_title, r.criteria_json,
                   t.full_name AS grader_name
            FROM fp_submissions s
            JOIN fp_assignments a ON s.assignment_id = a.id
            JOIN fp_groups g ON a.group_id = g.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN fp_rubrics r ON a.rubric_id = r.id
            LEFT JOIN users t ON s.graded_by = t.id
            WHERE s.id = ?
        """, (submission_id,)).fetchone()
        if not row:
            return None
        row["comparison"] = json.loads(row.get("comparison_json") or "{}")
        row["rubric_scores"] = json.loads(row.get("rubric_scores_json") or "{}") if row.get("rubric_scores_json") else None
        row["rubric_criteria"] = json.loads(row.get("criteria_json") or "[]") if row.get("criteria_json") else DEFAULT_RUBRICS[0]["criteria"]
        return row


def grade_submission(
    submission_id: int,
    teacher_id: int,
    rubric_scores: Dict[str, float],
    final_grade: Optional[float] = None,
    teacher_feedback: str = "",
    status: str = "GRADED",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_fp_db(db_path)
    detail = get_submission_detail(submission_id, db_path=db_path)
    if not detail:
        raise FileNotFoundError("Entrega no encontrada.")

    criteria = detail.get("rubric_criteria") or DEFAULT_RUBRICS[0]["criteria"]
    computed = _compute_weighted_grade(rubric_scores, criteria)
    grade_val = round(float(final_grade), 2) if final_grade is not None else computed
    grade_val = max(0.0, min(10.0, grade_val))
    norm_status = status if status in ("GRADED", "NEEDS_REVISION", "REVIEWED", "SUBMITTED") else "GRADED"
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        conn.execute("""
            UPDATE fp_submissions
            SET status = ?, rubric_scores_json = ?, final_grade = ?,
                teacher_feedback = ?, graded_by = ?, graded_at = ?
            WHERE id = ?
        """, (
            norm_status,
            json.dumps(rubric_scores, ensure_ascii=False),
            grade_val,
            (teacher_feedback or "").strip(),
            teacher_id,
            now_iso,
            submission_id,
        ))
        conn.commit()

    return get_submission_detail(submission_id, db_path=db_path) or {}


def record_quiz_attempt(
    student_id: int,
    topic: str,
    score_pct: float,
    correct_count: int,
    total_count: int,
    assignment_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_fp_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        row = conn.execute("""
            INSERT INTO fp_quiz_attempts (
                student_id, assignment_id, topic, score_pct, correct_count, total_count, details_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (
            student_id,
            assignment_id,
            topic or "general",
            float(score_pct),
            int(correct_count),
            int(total_count),
            json.dumps(details or {}, ensure_ascii=False),
            now_iso,
        )).fetchone()
        conn.commit()
    return {
        "id": row["id"],
        "student_id": student_id,
        "topic": topic,
        "score_pct": float(score_pct),
        "created_at": now_iso,
    }


_COMPETENCY_META = (
    ("color", "Colorimetría, CMYK y TAC", ("cmyk", "tac", "spot", "icc", "rgb")),
    ("geometria", "Geometría, Cajas y Sangrado", ("bleed", "sangr", "geometr", "cajas", "margin", "trim", "marca")),
    ("tipografia", "Tipografía, Trazos y Overprint", ("overprint", "sobreimpr", "hairline", "filete", "fuente", "font", "traz", "blanco")),
    ("normativa", "Normativa PDF/X, GWG y Taller", ("gwg", "orden", "producc", "imposic", "norma", "barcode")),
)


def compute_competency_profile(
    submissions: List[Dict[str, Any]],
    quiz_attempts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Calcula perfil competencial FP (color, geometría, tipografía, normativa) desde entregas y cuestionarios."""
    buckets: Dict[str, List[float]] = {cid: [] for cid, _lbl, _kw in _COMPETENCY_META}

    for sub in submissions:
        comp = sub.get("comparison") or {}
        delta = comp.get("delta") or {}
        decs = comp.get("decisions") or {}
        res_pct = delta.get("critical_resolution_pct")
        step_actions = " ".join(str(st.get("action") or "").lower() for st in (decs.get("steps") or []))

        if decs.get("used_gwg_validation"):
            buckets["normativa"].append(100.0 if decs.get("gwg_status") == "PASS" else 75.0)
        if decs.get("used_production_order"):
            buckets["normativa"].append(95.0)
        if res_pct is not None:
            buckets["normativa"].append(float(res_pct))

        for cid, _lbl, keywords in _COMPETENCY_META:
            if any(kw in step_actions for kw in keywords):
                score_val = float(res_pct) if res_pct is not None else 80.0
                buckets[cid].append(max(50.0, score_val))

    for q in quiz_attempts:
        details_raw = q.get("details_json")
        details = {}
        if isinstance(details_raw, str) and details_raw:
            try:
                details = json.loads(details_raw)
            except Exception:
                details = {}
        elif isinstance(q.get("details"), dict):
            details = q["details"]

        breakdown = details.get("competency_breakdown") or []
        if isinstance(breakdown, list) and breakdown:
            for item in breakdown:
                cid = item.get("topic")
                if cid in buckets and item.get("total", 0) > 0:
                    buckets[cid].append(float(item.get("pct", 0.0)))
        else:
            q_topic = str(q.get("topic") or "").lower()
            if q_topic in buckets and q.get("score_pct") is not None:
                buckets[q_topic].append(float(q["score_pct"]))

    profile: List[Dict[str, Any]] = []
    for cid, label, _kw in _COMPETENCY_META:
        vals = buckets[cid]
        pct = round(sum(vals) / len(vals), 1) if vals else None
        profile.append({
            "id": cid,
            "label": label,
            "score_pct": pct,
            "evidences": len(vals),
        })
    return profile


def list_student_dashboard(student_id: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        groups = conn.execute("""
            SELECT g.*, u.full_name AS teacher_name, e.joined_at
            FROM fp_enrollments e
            JOIN fp_groups g ON e.group_id = g.id
            LEFT JOIN users u ON g.teacher_id = u.id
            WHERE e.student_id = ?
            ORDER BY g.id DESC
        """, (student_id,)).fetchall()

        assignments = conn.execute("""
            SELECT a.*, g.name AS group_name, r.title AS rubric_title
            FROM fp_assignments a
            JOIN fp_groups g ON a.group_id = g.id
            JOIN fp_enrollments e ON e.group_id = g.id
            LEFT JOIN fp_rubrics r ON a.rubric_id = r.id
            WHERE e.student_id = ? AND a.is_open = 1
            ORDER BY a.id DESC
        """, (student_id,)).fetchall()

        quizzes = conn.execute("""
            SELECT * FROM fp_quiz_attempts WHERE student_id = ? ORDER BY id DESC LIMIT 20
        """, (student_id,)).fetchall()

    enriched_quizzes: List[Dict[str, Any]] = []
    for q in quizzes:
        item = dict(q)
        try:
            details = json.loads(item.get("details_json") or "{}")
            if not isinstance(details, dict):
                details = {}
        except Exception:
            details = {}
        item["profile"] = item.get("topic") or "General"
        item["level"] = details.get("level") or ""
        enriched_quizzes.append(item)

    for a in assignments:
        a["exam_mode"] = bool(a.get("exam_mode"))

    submissions = list_submissions(student_id=student_id, db_path=db_path)
    return {
        "groups": groups,
        "assignments": assignments,
        "submissions": submissions,
        "quiz_attempts": enriched_quizzes,
        "competencies": compute_competency_profile(submissions, enriched_quizzes),
    }


def get_student_evolution(
    group_id: Optional[int] = None,
    student_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Calcula evolución individual y grupal: media prácticas, cuestionarios y tasa de resolución."""
    submissions = list_submissions(group_id=group_id, student_id=student_id, db_path=db_path)
    with get_db_connection(db_path) as conn:
        quiz_rows = conn.execute("SELECT * FROM fp_quiz_attempts ORDER BY id ASC").fetchall()
        if group_id is not None:
            students = conn.execute("""
                SELECT u.id, u.full_name, u.email
                FROM fp_enrollments e
                JOIN users u ON e.student_id = u.id
                WHERE e.group_id = ?
                ORDER BY u.full_name ASC
            """, (group_id,)).fetchall()
        else:
            students = conn.execute("""
                SELECT DISTINCT u.id, u.full_name, u.email
                FROM users u
                WHERE u.role = 'alumno'
                   OR u.id IN (SELECT student_id FROM fp_submissions)
                   OR u.id IN (SELECT student_id FROM fp_enrollments)
                ORDER BY u.full_name ASC
            """).fetchall()

    quizzes_by_student: Dict[int, List[Dict[str, Any]]] = {}
    for q in quiz_rows:
        quizzes_by_student.setdefault(q["student_id"], []).append(q)

    subs_by_student: Dict[int, List[Dict[str, Any]]] = {}
    for s in submissions:
        subs_by_student.setdefault(s["student_id"], []).append(s)

    evolution_list: List[Dict[str, Any]] = []
    for st in students:
        sid = st["id"]
        if student_id is not None and sid != student_id:
            continue
        st_subs = sorted(subs_by_student.get(sid, []), key=lambda x: x["id"])
        st_quizzes = quizzes_by_student.get(sid, [])

        graded_vals = [float(s["final_grade"]) for s in st_subs if s.get("final_grade") is not None]
        avg_practice = round(sum(graded_vals) / len(graded_vals), 2) if graded_vals else None

        quiz_vals = [round(float(q["score_pct"]) / 10.0, 2) for q in st_quizzes]
        avg_quiz = round(sum(quiz_vals) / len(quiz_vals), 2) if quiz_vals else None

        res_rates: List[float] = []
        remaining_cats: Dict[str, int] = {}
        timeline: List[Dict[str, Any]] = []
        for s in st_subs:
            comp = s.get("comparison") or {}
            delta = comp.get("delta") or {}
            pct = delta.get("critical_resolution_pct")
            if pct is not None:
                res_rates.append(float(pct))
            rem_cats = (comp.get("final") or {}).get("categories") or {}
            for cat_name, cnt in rem_cats.items():
                remaining_cats[cat_name] = remaining_cats.get(cat_name, 0) + int(cnt)
            timeline.append({
                "submission_id": s["id"],
                "assignment_title": s["assignment_title"],
                "submitted_at": s["submitted_at"],
                "final_grade": s.get("final_grade"),
                "resolution_pct": pct,
                "initial_critical": (comp.get("initial") or {}).get("critical_count", 0),
                "final_critical": (comp.get("final") or {}).get("critical_count", 0),
            })

        avg_resolution = round(sum(res_rates) / len(res_rates), 1) if res_rates else None
        top_pitfalls = sorted(remaining_cats.items(), key=lambda x: x[1], reverse=True)[:3]

        evolution_list.append({
            "student_id": sid,
            "full_name": st["full_name"],
            "email": st["email"],
            "submissions_count": len(st_subs),
            "graded_count": len(graded_vals),
            "avg_practice_grade": avg_practice,
            "quiz_attempts_count": len(st_quizzes),
            "avg_quiz_grade": avg_quiz,
            "avg_error_resolution_pct": avg_resolution,
            "recurring_pitfalls": [{"category": k, "count": v} for k, v in top_pitfalls],
            "competencies": compute_competency_profile(st_subs, st_quizzes),
            "timeline": timeline,
        })

    return {
        "students": evolution_list,
        "total_submissions": len(submissions),
    }


def export_grades_csv(group_id: Optional[int] = None, db_path: Optional[Path] = None) -> str:
    """Exporta las actas de entregas y notas en CSV (UTF-8 con BOM para Excel)."""
    subs = list_submissions(group_id=group_id, db_path=db_path)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "ID Entrega",
        "Grupo",
        "Práctica",
        "Alumno",
        "Email",
        "Archivo PDF",
        "Fecha Entrega",
        "Errores Críticos Iniciales",
        "Errores Críticos Finales",
        "% Resolución",
        "Nota Final (/10)",
        "Estado",
        "Observaciones Docente",
    ])
    for s in subs:
        comp = s.get("comparison") or {}
        init_c = (comp.get("initial") or {}).get("critical_count", 0)
        fin_c = (comp.get("final") or {}).get("critical_count", 0)
        pct = (comp.get("delta") or {}).get("critical_resolution_pct", 0)
        writer.writerow([
            s["id"],
            s.get("group_name", ""),
            s.get("assignment_title", ""),
            s.get("student_name", ""),
            s.get("student_email", ""),
            s.get("filename", ""),
            (s.get("submitted_at") or "")[:19].replace("T", " "),
            init_c,
            fin_c,
            f"{pct}%",
            s["final_grade"] if s.get("final_grade") is not None else "Pendiente",
            s.get("status", ""),
            (s.get("teacher_feedback") or "").replace("\n", " "),
        ])
    return "\ufeff" + buf.getvalue()


def generate_evaluation_pdf_report(submission_id: int, db_path: Optional[Path] = None) -> bytes:
    """Genera el Boletín Oficial de Evaluación Práctica FP en PDF A4 usando PyMuPDF."""
    detail = get_submission_detail(submission_id, db_path=db_path)
    if not detail:
        raise FileNotFoundError("Entrega no encontrada.")

    comp = detail.get("comparison") or {}
    init_s = comp.get("initial") or {}
    fin_s = comp.get("final") or {}
    dec_s = comp.get("decisions") or {}
    delta = comp.get("delta") or {}

    criteria = detail.get("rubric_criteria") or DEFAULT_RUBRICS[0]["criteria"]
    scores = detail.get("rubric_scores") or comp.get("suggested_scores") or {}
    grade_str = f"{detail['final_grade']} / 10" if detail.get("final_grade") is not None else "Pendiente"

    esc = html_lib.escape
    criteria_rows_html = "".join(
        f"<tr><td>{esc(str(c['name']))}</td><td class='c'>{esc(str(c['weight']))}%</td>"
        f"<td class='c'><b>{esc(str(scores.get(c['id'], '-')))} / {esc(str(c.get('max_score', 10)))}</b></td></tr>"
        for c in criteria
    )

    if detail.get("teacher_feedback"):
        obs_block = (
            "<h2>3. Observaciones del Docente</h2>"
            f"<div class='box'>{esc(detail['teacher_feedback']).replace(chr(10), '<br/>')}</div>"
        )
    elif comp.get("observations"):
        obs_items = "".join(f"<li>{esc(str(obs))}</li>" for obs in comp["observations"])
        obs_block = f"<h2>3. Diagnóstico Automático de Trazabilidad</h2><ul>{obs_items}</ul>"
    else:
        obs_block = ""

    report_html = f"""
    <style>
      body {{ font-family: sans-serif; color: #1e293b; font-size: 9.5pt; line-height: 1.4; }}
      h1 {{ font-size: 15pt; color: #0f172a; margin: 0 0 4pt 0; }}
      .sub {{ color: #475569; font-size: 9pt; margin-bottom: 12pt; }}
      h2 {{ font-size: 11pt; color: #1e3a8a; margin: 12pt 0 5pt 0; border-bottom: 1px solid #cbd5e1; padding-bottom: 2pt; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 10pt; }}
      th, td {{ border: 0.6pt solid #cbd5e1; padding: 5pt 6pt; text-align: left; font-size: 8.8pt; }}
      th {{ background: #1e293b; color: #ffffff; font-weight: bold; }}
      th.blue {{ background: #1e3a8a; }}
      td.lbl {{ background: #f1f5f9; font-weight: bold; width: 20%; }}
      td.c {{ text-align: center; }}
      .box {{ border: 0.6pt solid #cbd5e1; background: #f8fafc; padding: 8pt; border-radius: 4pt; }}
      ul {{ margin: 4pt 0 0 14pt; padding: 0; }}
    </style>
    <h1>IntelliPrint FP · Informe de Evaluación Técnica de Práctica</h1>
    <div class="sub">{esc(str(detail.get('center', 'FP Artes Gráficas')))} · {esc(str(detail.get('module_name', '')))} · Grupo: {esc(str(detail.get('group_name', '')))}</div>
    <table>
      <tr><td class="lbl">Alumno/a:</td><td>{esc(str(detail.get('student_name', '')))}</td><td class="lbl">Email:</td><td>{esc(str(detail.get('student_email') or '-'))}</td></tr>
      <tr><td class="lbl">Práctica:</td><td>{esc(str(detail.get('assignment_title', '')))}</td><td class="lbl">Perfil Preflight:</td><td>{esc(str(detail.get('target_profile', 'OFFSET_300')))}</td></tr>
      <tr><td class="lbl">Archivo PDF:</td><td>{esc(str(detail.get('filename', '')))}</td><td class="lbl">Fecha Entrega:</td><td>{esc(str((detail.get('submitted_at') or '')[:19].replace('T', ' ')))}</td></tr>
      <tr><td class="lbl">Estado:</td><td>{esc(str(detail.get('status', '')))}</td><td class="lbl">Calificación Final:</td><td><b>{esc(grade_str)}</b></td></tr>
    </table>
    <h2>1. Comparativa Forense: Diagnóstico Inicial vs. Resultado Final</h2>
    <table>
      <tr><th>Métrica Técnica</th><th class="c">Estado Inicial</th><th class="c">Estado Final</th><th>Evolución</th></tr>
      <tr><td>Errores Críticos</td><td class="c">{init_s.get('critical_count', 0)}</td><td class="c">{fin_s.get('critical_count', 0)}</td><td>{delta.get('critical_resolution_pct', 0)}% resueltos</td></tr>
      <tr><td>Avisos (Warnings)</td><td class="c">{init_s.get('warning_count', 0)}</td><td class="c">{fin_s.get('warning_count', 0)}</td><td>-{delta.get('resolved_warnings', 0)}</td></tr>
      <tr><td>Decisiones / Correcciones</td><td class="c">-</td><td class="c">{dec_s.get('fixes_count', 0)}</td><td>{dec_s.get('versions_count', 0)} versiones</td></tr>
      <tr><td>Validación GWG / PDF/X</td><td class="c">-</td><td class="c">{esc(str(dec_s.get('gwg_status') or 'No ejecutada'))}</td><td>Orden Prod.: {'Sí' if dec_s.get('used_production_order') else 'No'}</td></tr>
    </table>
    <h2>2. Desglose de Rúbrica de Evaluación</h2>
    <table>
      <tr><th class="blue">Criterio Evaluado</th><th class="blue c">Peso</th><th class="blue c">Puntuación</th></tr>
      {criteria_rows_html}
    </table>
    {obs_block}
    """

    story = pymupdf.Story(html=report_html)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (42, 42, -42, -42)
    out_buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(out_buf)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev, None)
        writer.end_page()
    writer.close()
    return out_buf.getvalue()


# ---------------------------------------------------------------------------
# RETOS PROPIOS SUBIDOS POR EL DOCENTE (PLANTILLAS REUTILIZABLES FP)
# ---------------------------------------------------------------------------

def _normalize_custom_challenge_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a database row from `fp_custom_challenges` to scenario-compatible dict."""
    try:
        target_errors = json.loads(row.get("target_errors_json") or "[]")
        if not isinstance(target_errors, list):
            target_errors = []
    except Exception:
        target_errors = []
    try:
        learning_goals = json.loads(row.get("learning_goals_json") or "[]")
        if not isinstance(learning_goals, list):
            learning_goals = []
    except Exception:
        learning_goals = []

    return {
        "id": row["id"],
        "category": row.get("category") or "docente",
        "title": row["title"],
        "description": row.get("description") or "",
        "level": row.get("level") or "Reto Docente FP",
        "difficulty": row.get("level") or "Reto Docente FP",
        "module": row.get("module") or "Preimpresión y Arte Final",
        "doc_type": row.get("doc_type") or "PDF Personalizado",
        "target_profile": row.get("target_profile") or "OFFSET_300",
        "iso_norm": row.get("iso_norm") or "ISO 12647-2 / PDF/X",
        "target_errors": target_errors,
        "learning_goals": learning_goals,
        "filename": row.get("filename") or f"{row['id']}.pdf",
        "pdf_sha256": row.get("pdf_sha256"),
        "teacher_id": row.get("teacher_id"),
        "teacher_name": row.get("teacher_name") or "Docente FP",
        "is_published": bool(row.get("is_published", 1)),
        "is_custom": True,
        "created_at": row.get("created_at"),
    }


def create_custom_challenge(
    title: str,
    filename: str,
    pdf_sha256: str,
    teacher_id: Optional[int],
    teacher_name: str = "Docente FP",
    description: str = "",
    level: str = "Reto Docente FP",
    module: str = "Preimpresión y Arte Final",
    doc_type: str = "PDF Personalizado",
    target_profile: str = "OFFSET_300",
    iso_norm: str = "ISO 12647-2 / PDF/X",
    target_errors: Optional[List[str]] = None,
    learning_goals: Optional[List[str]] = None,
    challenge_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist a teacher-uploaded PDF challenge template so groups can reuse it."""
    init_fp_db(db_path)
    clean_title = (title or "").strip()
    if len(clean_title) < 2:
        raise ValueError("El título del reto propio debe tener al menos 2 caracteres.")

    cid = (challenge_id or f"custom_{secrets.token_hex(6)}").strip().lower()
    errors_list = [str(e).strip() for e in (target_errors or []) if str(e).strip()]
    goals_list = [str(g).strip() for g in (learning_goals or []) if str(g).strip()]
    if not goals_list:
        goals_list = [
            "Diagnosticar todas las incidencias del PDF original del docente antes de producir.",
            f"Ajustar el arte final al perfil objetivo ({target_profile or 'OFFSET_300'}).",
        ]

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO fp_custom_challenges (
                id, title, description, category, level, module, doc_type,
                target_profile, iso_norm, target_errors_json, learning_goals_json,
                filename, pdf_sha256, teacher_id, teacher_name, is_published, created_at
            )
            VALUES (?, ?, ?, 'docente', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            cid,
            clean_title,
            (description or "").strip() or "Caso práctico preparado por el profesorado a partir de un PDF real de taller.",
            (level or "").strip() or "Reto Docente FP",
            (module or "").strip() or "Preimpresión y Arte Final",
            (doc_type or "").strip() or "PDF Personalizado",
            (target_profile or "").strip() or "OFFSET_300",
            (iso_norm or "").strip() or "ISO 12647-2 / PDF/X",
            json.dumps(errors_list, ensure_ascii=False),
            json.dumps(goals_list, ensure_ascii=False),
            filename or f"{cid}.pdf",
            pdf_sha256,
            teacher_id,
            (teacher_name or "").strip() or "Docente FP",
            now_iso,
        ))
        conn.commit()
        row = conn.execute("SELECT * FROM fp_custom_challenges WHERE id = ?", (cid,)).fetchone()
    return _normalize_custom_challenge_row(row)


def list_custom_challenges(
    teacher_id: Optional[int] = None,
    only_published: bool = True,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return teacher-uploaded custom challenges formatted for the scenarios catalog & classroom."""
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        clauses = []
        params: List[Any] = []
        if only_published:
            clauses.append("is_published = 1")
        if teacher_id is not None:
            clauses.append("teacher_id = ?")
            params.append(teacher_id)
        sql = "SELECT * FROM fp_custom_challenges"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_normalize_custom_challenge_row(r) for r in rows]


def get_custom_challenge(challenge_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Fetch a single teacher-uploaded challenge by id."""
    if not challenge_id:
        return None
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM fp_custom_challenges WHERE id = ?", (challenge_id,)).fetchone()
    return _normalize_custom_challenge_row(row) if row else None


def delete_custom_challenge(
    challenge_id: str,
    requester_id: int,
    requester_role: str = "teacher",
    db_path: Optional[Path] = None,
) -> bool:
    """Delete a teacher-uploaded challenge if the requester is its owner or admin."""
    init_fp_db(db_path)
    with get_db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM fp_custom_challenges WHERE id = ?", (challenge_id,)).fetchone()
        if not row:
            raise FileNotFoundError("Reto docente no encontrado.")
        if requester_role != "admin" and row.get("teacher_id") not in (None, requester_id):
            raise PermissionError("Solo el docente autor o un administrador puede eliminar este reto.")
        conn.execute("DELETE FROM fp_custom_challenges WHERE id = ?", (challenge_id,))
        conn.commit()
    return True


# Inicialización automática segura
try:
    init_fp_db()
except Exception:
    pass
