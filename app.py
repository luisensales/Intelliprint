import os
import io
import html
import zipfile
import shutil
import hashlib
from document_identity import update_pdf_identity, clear_pdf_authorization
from analysis_history import capture_original_analysis, ensure_original_analysis
import json
import uuid
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Query, Body
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pymupdf
from pdf_utils import copy_pdf
from artifact_retention import cleanup_expired_artifacts, artifact_storage_bytes
from upload_security import validate_pdf_filename, discard_failed_upload, save_bounded_upload, read_bounded_upload
from manual_content import MANUAL_SOURCE, MANUAL_EDITION, MANUAL_UPDATED, MANUAL_TITLE, render_manual_page

from preflight_engine import IntelliPrintEngine
from icc_manager import get_available_icc_profiles, detect_pdf_output_intent, apply_icc_to_pdf, resolve_icc_profile, ICC_DIR
from spellcheck_engine import save_word_to_glossary
from report_generator import generate_preflight_certificate_pdf
from client_report_generator import generate_client_educational_report_pdf
from issue_viewer import inspect_finding, render_issue_page, StaleIssueAnalysis
from color_converter import convert_rgb_images_to_cmyk, extract_embedded_icc_to_tempfile
from separations_viewer import render_page_separation
from overprint_fixer import apply_overprint_to_dark_text, apply_overprint_to_technical_inks, fix_white_overprint, fix_rich_black_small_text
from spot_converter import convert_spot_colors_to_cmyk
from hairline_fixer import fix_hairlines
from geometry_fixer import fix_pdf_boxes_and_bleed
from font_vectorizer import outline_fonts_in_pdf
from mirror_bleed_generator import generate_mirror_bleed
from printer_marks_generator import add_printer_marks_to_pdf
from tac_limiter import limit_pdf_tac
from imposition_engine import (
    validate_sheet_size,
    calculate_imposition_plan,
    generate_imposed_pdf,
    render_imposition_preview_image,
    STANDARD_SHEET_SIZES_MM,
)
from cip3_engine import (
    calculate_ink_zone_coverage,
    generate_cip3_ppf,
    is_current_ppf,
    generate_cip3_pdf_sheet,
)
from barcode_engine import (
    inspect_barcodes_in_pdf,
    fix_barcodes_in_pdf,
    render_barcode_preview_image,
)
from hotfolder_engine import (
    hotfolder_service,
    process_batch_upload,
    batch_fix_jobs,
    create_batch_zip,
    IN_DIR,
    APPROVED_DIR,
    REJECTED_DIR,
)
from safety_margin_engine import (
    inspect_safety_margins,
    render_safety_margin_preview,
)
from traceability_engine import (
    generate_traceability_qr_bytes,
    get_press_operator_data,
    render_press_operator_html,
)
from didactic_engine import (
    SCENARIOS_CATALOG,
    QUESTIONS_FP,
    generate_scenario_pdf,
    simulate_register_misalignment,
    simulate_setoff_stain,
    simulate_guillotine_shift,
    simulate_ctp_hairline,
    evaluate_student_quiz,
    generate_student_worksheet_pdf,
)
from profile_manager import (
    import_custom_profiles,
    get_all_profiles,
    get_profile_by_id,
    create_custom_profile,
    update_custom_profile,
    delete_custom_profile,
    load_custom_profiles,
    save_custom_profiles_to_disk,
)
from version_history import (
    capture_version,
    select_version,
    public_history,
    version_path,
    compare_versions,
    render_version_page_image,
    render_version_diff_image,
    VersionHistoryError,
    VersionQuotaError,
)
from job_manager import (
    JOB_TTL_HOURS,
    JobManagerError,
    calculate_job_expiration,
    list_managed_jobs,
    get_job_data_for_recovery,
    build_production_package,
)
from production_order import (
    get_production_catalogs,
    propose_production_recipe,
    validate_pdf_against_order,
    generate_job_ticket_pdf,
)
from gwg_validator import (
    get_available_standards,
    validate_pdf_gwg,
    generate_gwg_certificate_pdf,
)
from auth_manager import (
    authenticate_user,
    authenticate_user_detailed,
    register_user,
    list_users,
    update_user_access,
    user_has_permission,
    create_user_session,
    get_user_from_session,
    delete_session,
    generate_client_approval_link,
    get_client_approval_by_token,
    submit_client_decision,
    get_db_status,
)
from fp_classroom import (
    create_group as fp_create_group,
    list_groups as fp_list_groups,
    list_rubrics as fp_list_rubrics,
    create_rubric as fp_create_rubric,
    create_assignment as fp_create_assignment,
    list_assignments as fp_list_assignments,
    join_group_by_code as fp_join_group,
    submit_job_for_assignment as fp_submit_job,
    list_submissions as fp_list_submissions,
    get_submission_detail as fp_get_submission_detail,
    grade_submission as fp_grade_submission,
    record_quiz_attempt as fp_record_quiz_attempt,
    list_student_dashboard as fp_student_dashboard,
    get_student_evolution as fp_student_evolution,
    export_grades_csv as fp_export_grades_csv,
    generate_evaluation_pdf_report as fp_generate_eval_pdf,
)

from security_limits import (
    RequestLimitsMiddleware, ResourceLimitError, MAX_FILE_BYTES, MAX_BATCH_BYTES,
    MAX_BATCH_FILES, MAX_PREVIEW_DPI, validate_job_id, contained_job_path,
    validate_pdf_resources, bounded_render_dpi,
    pdf_processing_slot, release_pdf_memory,
)


def safe_job_id(value):
    try:
        return validate_job_id(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def job_output_path(filename):
    try:
        return contained_job_path(JOBS_DIR, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def checked_sheet_size(value):
    try:
        return validate_sheet_size(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def imposition_options(body):
    result = dict(sheet_size=checked_sheet_size(body.get('sheet_size', 'SRA3')),
                  orientation=body.get('orientation', 'auto'), mode=body.get('mode', 'step_and_repeat'))
    if result['orientation'] not in ('auto', 'portrait', 'landscape') or result['mode'] not in ('step_and_repeat', 'booklet', '2up', '4up'):
        raise HTTPException(status_code=422, detail='Modo u orientación de imposición no válidos.')
    import math
    for key, default, maximum in [('gap_mm', 4, 100), ('gap_x_mm', body.get('gap_mm', 4), 100),
                                  ('gap_y_mm', body.get('gap_mm', 4), 100), ('bleed_mm', 2, 20),
                                  ('sheet_margin_mm', 10, 200)]:
        try:
            value = float(body.get(key, default))
            if not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(status_code=422, detail=f'Valor no válido para {key}.')
        result[key] = value
    return result


BASE_DIR = Path(__file__).parent
PERSISTENT_DATA_DIR = os.environ.get("INTELLIPRINT_DATA_DIR") or os.environ.get("RENDER_DISK_PATH")
DATA_DIR = Path(PERSISTENT_DATA_DIR) if PERSISTENT_DATA_DIR else BASE_DIR
UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"
DIDACTIC_SCENARIOS_DIR = BASE_DIR / "didactic_scenarios"
WORKSHEETS_DIR = DATA_DIR / "worksheets"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
DIDACTIC_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
WORKSHEETS_DIR.mkdir(parents=True, exist_ok=True)

def rehydrate_didactic_job(job_id: str, scenario_id: str) -> Optional[dict]:
    """
    Reconstruye un trabajo didáctico FP a partir de los PDFs reales pre-generados
    cuando un trabajo se consulta y no está en la memoria del contenedor (ej. reinicios de Render).
    """
    scenario = next((s for s in SCENARIOS_CATALOG if s["id"] == scenario_id), None)
    if not scenario:
        return None

    job_folder = UPLOAD_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)
    filename = f"{scenario_id}.pdf"
    file_path = job_folder / filename

    src_pdf = DIDACTIC_SCENARIOS_DIR / filename
    if src_pdf.exists():
        shutil.copyfile(src_pdf, file_path)
    else:
        generate_scenario_pdf(scenario_id, file_path)

    file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
    with open(file_path, "rb") as f:
        pdf_sha256 = hashlib.sha256(f.read()).hexdigest()

    try:
        report = engine.run_preflight(
            pdf_path=str(file_path),
            profile_id="OFFSET_300",
            icc_choice="preserve"
        )
    except Exception as e:
        print(f"[rehydrate] Error en preflight de {scenario_id}: {e}")
        return None

    report["job_meta"] = {
        "job_id": job_id,
        "filename": filename,
        "file_size_mb": file_size_mb,
        "sha256": pdf_sha256,
        "profile_id": "OFFSET_300",
        "icc_option": "preserve",
        "selected_icc": None,
        "pdf_path": str(file_path),
        "is_didactic_scenario": True,
        "scenario_id": scenario_id,
        "scenario_title": scenario["title"]
    }
    update_pdf_identity(report, file_path, original_sha256=pdf_sha256)
    capture_original_analysis(report)

    job_json_path = JOBS_DIR / f"{job_id}.json"
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def get_job_json_path(job_id: str) -> Path:
    """
    Obtiene la ruta al archivo JSON del trabajo, asegurando que si se trata de un reto
    didáctico FP y el contenedor ha sido reiniciado (como en Render), el trabajo se
    rehidrate al vuelo a partir de los PDFs reales pre-generados.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = JOBS_DIR / f"{safe_id}.json"
    if not job_json_path.exists():
        sc_id = None
        if safe_id.startswith("fp_"):
            cand = safe_id[3:]
            matched = next((s["id"] for s in SCENARIOS_CATALOG if s["id"] == cand or cand.startswith(s["id"])), None)
            if matched:
                sc_id = matched
            else:
                up_dir = UPLOAD_DIR / safe_id
                if up_dir.exists():
                    for f in up_dir.glob("*.pdf"):
                        if any(s["id"] == f.stem for s in SCENARIOS_CATALOG):
                            sc_id = f.stem
                            break
                if not sc_id:
                    sc_id = "reto_tarjeta_richblack"
        elif any(s["id"] == safe_id for s in SCENARIOS_CATALOG):
            sc_id = safe_id

        if sc_id:
            try:
                rehydrate_didactic_job(safe_id, sc_id)
            except Exception as e:
                print(f"[rehydrate] Error rehidratando reto {sc_id}: {e}")

    return job_json_path

app = FastAPI(
    title="IntelliPrint Preflight Web",
    description="Sistema Avanzado de Preflight mediante Redes Neuronales y Verificación de PDF",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLimitsMiddleware)

engine = IntelliPrintEngine()

# ---------------------------------------------------------------------------
# Limpieza automática de jobs antiguos
# ---------------------------------------------------------------------------
JOB_TTL_HOURS = 24         # Conservar trabajos 24 horas desde su última modificación
CLEANUP_INTERVAL_SEC = 3600  # Ejecutar limpieza cada hora

def _cleanup_old_jobs():
    """Retira artefactos vencidos sin interferir con el procesamiento de PDF."""
    cutoff = time.time() - JOB_TTL_HOURS * 3600
    with pdf_processing_slot():
        result = cleanup_expired_artifacts(
            JOBS_DIR, UPLOAD_DIR, WORKSHEETS_DIR, (APPROVED_DIR, REJECTED_DIR), cutoff)
    for error in result["errors"]:
        print(f"[cleanup] {error}")
    if result["deleted_files"]:
        print(f"[cleanup] {result['deleted_jobs']} jobs eliminados · {result['freed_bytes'] // 1024} KB liberados")
    return result

def _cleanup_loop():
    """Hilo de limpieza periódica."""
    while True:
        time.sleep(CLEANUP_INTERVAL_SEC)
        try:
            _cleanup_old_jobs()
        except Exception as e:
            print(f"[cleanup] Error en limpieza periódica: {e}")

# Arrancar hilo de limpieza en background al iniciar la app
_cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
_cleanup_thread.start()

# Mount static and assets folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
    app.mount("/asset", StaticFiles(directory=str(ASSETS_DIR)), name="asset")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>IntelliPrint Web en preparación...</h1>")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/favicon.ico", include_in_schema=False)
def favicon_endpoint():
    ico_path = STATIC_DIR / "favicon.ico"
    if ico_path.exists():
        return FileResponse(ico_path, media_type="image/x-icon")
    return Response(status_code=404)

@app.get("/api/profiles")
def get_profiles():
    """Devuelve la lista unificada de perfiles estándar y personalizados."""
    all_profiles = get_all_profiles()
    return {
        "version": "1.2.0",
        "profiles": all_profiles
    }


@app.post("/api/profiles/custom")
def create_profile_endpoint(payload: dict):
    """Crea un nuevo perfil personalizado de preflight."""
    try:
        new_p = create_custom_profile(payload)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "success", "profile": new_p}


@app.put("/api/profiles/custom/{profile_id}")
def update_profile_endpoint(profile_id: str, payload: dict):
    """Actualiza un perfil personalizado de preflight."""
    try:
        updated = update_custom_profile(profile_id, payload)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Perfil no encontrado o no modificable.")
    return {"status": "success", "profile": updated}


@app.delete("/api/profiles/custom/{profile_id}")
def delete_profile_endpoint(profile_id: str):
    """Elimina un perfil personalizado de preflight."""
    ok = delete_custom_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Perfil no encontrado o no se puede eliminar.")
    return {"status": "success", "deleted_id": profile_id}


@app.get("/api/profiles/export")
def export_profiles_endpoint():
    """Exporta los perfiles personalizados en formato JSON."""
    custom = load_custom_profiles()
    return {"version": "1.2.0", "custom_profiles": custom}


@app.post("/api/profiles/import")
def import_profiles_endpoint(payload: dict):
    """Importa perfiles personalizados desde un JSON."""
    try:
        return import_custom_profiles(payload.get("custom_profiles", []))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/icc-catalog")
def get_icc_catalog():
    return {
        "profiles": get_available_icc_profiles()
    }

@app.post("/api/inspect-pdf")
def inspect_pdf(file: UploadFile = File(...)):
    """
    Lightweight instant inspection of uploaded PDF:
    Returns page count, file size, dimensions, and embedded OutputIntent / ICC profile.
    """
    try:
        validate_pdf_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    temp_id = uuid.uuid4().hex[:8]
    temp_path = UPLOAD_DIR / f"inspect_{temp_id}.pdf"
    try:
        file_size, _ = save_bounded_upload(file, temp_path)
        validate_pdf_resources(temp_path)

        # 1. Detect OutputIntent & ICC
        icc_info = detect_pdf_output_intent(temp_path)

        # 2. Page count, dimensions & basic images count
        doc = pymupdf.open(temp_path)
        page_count = len(doc)
        p0 = doc[0] if page_count > 0 else None
        w_mm = round(p0.rect.width * 25.4 / 72.0, 1) if p0 else 0
        h_mm = round(p0.rect.height * 25.4 / 72.0, 1) if p0 else 0
        total_images = sum(len(p.get_images()) for p in doc)
        doc.close()

        file_size_mb = round(file_size / (1024 * 1024), 2)

        return {
            "filename": file.filename,
            "file_size_mb": file_size_mb,
            "pages": page_count,
            "page_size_mm": f"{w_mm} × {h_mm} mm",
            "total_images": total_images,
            "output_intent": icc_info
        }
    except ResourceLimitError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=422, detail="No se pudo abrir un PDF valido y sin cifrado.") from e
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

@app.post("/api/check")
def check_pdf(
    file: UploadFile = File(...),
    profile_id: str = Form("OFFSET_300"),
    icc_option: str = Form("preserve"),
    selected_icc: Optional[str] = Form(None)
):
    try:
        validate_pdf_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job_id = str(uuid.uuid4())[:8]
    job_folder = UPLOAD_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)
    
    file_path = job_folder / "source.pdf"
    try:
        file_size, pdf_sha256 = save_bounded_upload(file, file_path)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        report = engine.run_preflight(
            pdf_path=str(file_path), profile_id=profile_id,
            icc_choice=icc_option, selected_icc=selected_icc,
        )
    except ResourceLimitError as exc:
        discard_failed_upload(job_folder, UPLOAD_DIR)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        discard_failed_upload(job_folder, UPLOAD_DIR)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        discard_failed_upload(job_folder, UPLOAD_DIR)
        raise HTTPException(status_code=500, detail="No se pudo analizar el PDF.") from exc

    # Attach Job Metadata
    report["job_meta"] = {
        "job_id": job_id,
        "filename": file.filename,
        "file_size_mb": file_size_mb,
        "sha256": pdf_sha256,
        "profile_id": profile_id,
        "icc_option": icc_option,
        "selected_icc": selected_icc,
        "pdf_path": str(file_path)
    }
    update_pdf_identity(report, file_path, original_sha256=pdf_sha256)
    capture_original_analysis(report)
    try:
        capture_version(report, file_path, JOBS_DIR, label="PDF original recibido")
        report["version_history_summary"] = public_history(report, JOBS_DIR)
    except Exception as exc:
        print(f"[check_pdf] Aviso versión: {exc}")

    try:
        report["expiration_info"] = calculate_job_expiration(report, ttl_hours=JOB_TTL_HOURS)
    except Exception as exc:
        print(f"[check_pdf] Aviso caducidad: {exc}")

    # Persist Job JSON
    job_json_path = get_job_json_path(job_id)
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report

@app.post("/api/proofreading/action")
def handle_proofreading_action(
    job_id: str = Form(...),
    suggestion_id: str = Form(...),
    action: str = Form(...), # accept, ignore, add_to_glossary
    word: str = Form(...)
):
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    if action == "add_to_glossary":
        save_word_to_glossary(word)

    for item in job_data.get("spell_suggestions", []):
        if item.get("id") == suggestion_id:
            item["status"] = action

    # Re-evaluate content result
    pending_count = sum(1 for item in job_data.get("spell_suggestions", []) if item.get("status") == "pending")
    if pending_count == 0:
        job_data["triple_result"]["content"]["status"] = "RESOLVED"
        job_data["triple_result"]["content"]["label"] = "Revisión editorial completada"
    else:
        job_data["triple_result"]["content"]["label"] = f"Revisión editorial pendiente ({pending_count} restantes)"

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "pending_count": pending_count,
        "content_result": job_data["triple_result"]["content"]
    }

@app.post("/api/release")
def release_production(
    request: Request,
    job_id: str = Form(...),
    operator_name: str = Form(...),
    decision: str = Form(...), # approved, approved_with_warnings, rejected
    notes: Optional[str] = Form("")
):
    job_id = safe_job_id(job_id)
    if decision not in ("approved", "approved_with_warnings", "rejected"):
        raise HTTPException(status_code=422, detail="Decisión no válida: usa approved, approved_with_warnings o rejected.")
    is_approved = decision in ("approved", "approved_with_warnings")
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    # Si hay sesión de usuario autenticado, su identidad y rol firman oficialmente
    auth_user = get_authenticated_user(request)
    if auth_user:
        effective_operator = auth_user["full_name"]
        auth_username = auth_user["username"]
        auth_role = auth_user["role"]
    else:
        effective_operator = operator_name.strip()
        auth_username = None
        auth_role = "invitado"

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    current_pdf = get_latest_cumulative_pdf(job_data.get("job_meta", {}))
    if not current_pdf:
        raise HTTPException(status_code=404, detail="PDF de producción no encontrado.")
    current_sha256 = update_pdf_identity(job_data, current_pdf)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    job_data["triple_result"]["release"] = {
        "status": "AUTHORIZED" if is_approved else "REJECTED",
        "label": f"Autorizado por {effective_operator}" if is_approved else f"Rechazado por {effective_operator}",
        "decision": decision,
        "operator": effective_operator,
        "authenticated_username": auth_username,
        "operator_role": auth_role,
        "is_certified_signature": bool(auth_user),
        "notes": notes,
        "signed_at": now_str,
        "sha256": current_sha256,
    }

    if job_data["triple_result"]["release"]["status"] == "AUTHORIZED":
        job_data["job_meta"]["authorized_sha256"] = current_sha256
        try:
            capture_version(job_data, current_pdf, JOBS_DIR, label=f"Versión aprobada ({effective_operator})", is_approved=True)
            job_data["version_history_summary"] = public_history(job_data, JOBS_DIR)
        except Exception as exc:
            print(f"[release_production] Aviso versión: {exc}")
    else:
        job_data["job_meta"].pop("authorized_sha256", None)

    # Generate Official Preflight Certificate PDF
    cert_path = job_output_path(f"{job_id}_ficha_tecnica.pdf")
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
        job_data["job_meta"]["certificate_pdf_path"] = str(cert_path)
    except Exception as e:
        print(f"Error generando certificado PDF: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "release_result": job_data["triple_result"]["release"],
        "certificate_url": f"/api/download-certificate/{job_id}",
        "client_report_url": f"/api/download-client-report/{job_id}",
        "production_pdf_url": f"/api/download-pdf/{job_id}",
        "json_report_url": f"/api/report/{job_id}",
        "saved_location": f"jobs/{job_id}.json"
    }

@app.get("/api/download-certificate/{job_id}")
def download_certificate_pdf(job_id: str):
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    
    cert_path = job_output_path(f"{job_id}_ficha_tecnica.pdf")
    meta = job_data.get("job_meta", {})
    current_pdf = get_latest_cumulative_pdf(meta)
    if current_pdf:
        update_pdf_identity(job_data, current_pdf)
    history_changed = ensure_original_analysis(
        job_data, engine.run_preflight, (UPLOAD_DIR, APPROVED_DIR, REJECTED_DIR))
    if (not cert_path.exists() or meta.get("certificate_identity_version") != 3 or history_changed
            or meta.get("certificate_sha256") != meta.get("current_sha256")):
        generate_preflight_certificate_pdf(job_data, cert_path)
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=str(cert_path),
        media_type="application/pdf",
        filename=f"Ficha_Tecnica_IntelliPrint_{clean_name}_{job_id}.pdf"
    )


@app.get("/api/download-client-report/{job_id}")
def download_client_report_pdf(job_id: str):
    """
    Descarga la guía A4 completa para cliente y diseñador, con estado e historial.
    Explica en lenguaje constructivo y claro qué incidencias existen y cómo resolverlas en InDesign / Illustrator.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    if ensure_original_analysis(job_data, engine.run_preflight, (UPLOAD_DIR, APPROVED_DIR, REJECTED_DIR)):
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

    report_path = JOBS_DIR / f"{safe_id}_guia_cliente.pdf"
    try:
        generate_client_educational_report_pdf(
            job_data, report_path, pdf_path=get_latest_cumulative_pdf(job_data.get("job_meta", {})))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando informe pedagógico para el cliente: {e}")

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    stem = Path(filename).stem
    download_filename = f"Guia_Cliente_IntelliPrint_{stem}_{safe_id[:8]}.pdf"

    return FileResponse(
        path=str(report_path),
        media_type="application/pdf",
        filename=download_filename
    )

@app.get("/api/report/{job_id}")
def download_json_report(job_id: str):
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    return FileResponse(
        path=str(job_json_path),
        media_type="application/json",
        filename=f"Informe_IntelliPrint_{job_id}.json"
    )


@app.get("/api/storage-status")
def storage_status():
    """Estado del almacenamiento: número de jobs y espacio usado."""
    uploads_bytes = artifact_storage_bytes(UPLOAD_DIR)
    jobs_bytes = artifact_storage_bytes(JOBS_DIR)
    worksheets_bytes = artifact_storage_bytes(WORKSHEETS_DIR)
    hotfolder_bytes = sum(artifact_storage_bytes(root) for root in (APPROVED_DIR, REJECTED_DIR))
    total_bytes = uploads_bytes + jobs_bytes + worksheets_bytes + hotfolder_bytes

    job_count = len(list(JOBS_DIR.glob("*.json")))

    # Antigüedad del job más viejo
    json_files = sorted(JOBS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime)
    oldest_age_h = None
    if json_files:
        oldest_age_h = round((time.time() - json_files[0].stat().st_mtime) / 3600, 1)

    return {
        "jobs_count": job_count,
        "uploads_mb": round(uploads_bytes / 1024 / 1024, 2),
        "jobs_mb":    round(jobs_bytes    / 1024 / 1024, 2),
        "worksheets_mb": round(worksheets_bytes / 1024 / 1024, 2),
        "hotfolder_mb": round(hotfolder_bytes / 1024 / 1024, 2),
        "total_mb":   round(total_bytes   / 1024 / 1024, 2),
        "oldest_job_hours": oldest_age_h,
        "ttl_hours": JOB_TTL_HOURS,
        "note": f"Los jobs se eliminan automáticamente después de {JOB_TTL_HOURS} horas."
    }


@app.post("/api/cleanup-now")
def cleanup_now():
    """Fuerza la limpieza inmediata de jobs antiguos."""
    result = _cleanup_old_jobs()
    return {
        "status": "ok",
        "freed_mb": round(result["freed_bytes"] / 1024 / 1024, 2),
        "deleted_jobs": result["deleted_jobs"],
        "deleted_files": result["deleted_files"],
        "errors": result["errors"],
        "remaining_jobs": len(list(JOBS_DIR.glob("*.json")))
    }


# =============================================================================
# GESTIÓN DE TRABAJOS, CADUCIDAD Y PAQUETE COMPLETO DE PRODUCCIÓN
# =============================================================================

@app.get("/api/jobs")
def list_jobs_endpoint(
    q: Optional[str] = Query(None, description="Búsqueda por texto (nombre, ID, perfil, operador)"),
    status: Optional[str] = Query("all", description="Filtro de estado: all, approved, rejected, pending, errors"),
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados"),
):
    """Búsqueda y listado filtrado de trabajos almacenados con estado de caducidad."""
    return list_managed_jobs(JOBS_DIR, query=q, status_filter=status, limit=limit, ttl_hours=JOB_TTL_HOURS)


@app.get("/api/jobs/{job_id}/expiration")
def get_job_expiration_endpoint(job_id: str):
    """Devuelve los datos de caducidad y tiempo restante de retención (24 h)."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    return calculate_job_expiration(job_data, manifest_path=job_json_path, ttl_hours=JOB_TTL_HOURS)


@app.get("/api/jobs/{job_id}/load")
def load_job_endpoint(job_id: str):
    """Recupera y rehidrata completamente un trabajo para su carga inmediata en la interfaz."""
    safe_id = safe_job_id(job_id)
    try:
        return get_job_data_for_recovery(safe_id, JOBS_DIR, ttl_hours=JOB_TTL_HOURS)
    except JobManagerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/production-package")
@app.get("/api/production-package/{job_id}")
def download_production_package_endpoint(job_id: str):
    """Descarga el paquete completo de producción (.zip) con PDF final, certificados, informes, CIP3 e historial."""
    safe_id = safe_job_id(job_id)
    try:
        zip_bytes, zip_filename = build_production_package(safe_id, JOBS_DIR, upload_dir=UPLOAD_DIR, engine=engine)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
        )
    except JobManagerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando el paquete de producción: {exc}") from exc


# =============================================================================
# ORDEN DE PRODUCCIÓN, RECETAS Y HOJA DE RUTA DE TALLER (JOB TICKET)
# =============================================================================

@app.get("/api/production-orders/catalogs")
def get_production_catalogs_endpoint():
    """Devuelve los catálogos de productos, máquinas, papeles y acabados."""
    return get_production_catalogs()


@app.post("/api/production-orders/calculate")
def calculate_production_recipe_endpoint(body: dict = Body(default={})):
    """Calcula la receta propuesta de preflight, imposición y consumo de pliegos."""
    product_id = body.get("product_id", "catalogo_grapado")
    machine_id = body.get("machine_id", "digital_sra3")
    paper_id = body.get("paper_id", "estucado_mate")
    quantity = body.get("quantity", 500)
    finishings = body.get("finishings", [])
    page_count = body.get("page_count")
    trim_w = body.get("trim_width_mm")
    trim_h = body.get("trim_height_mm")

    try:
        recipe = propose_production_recipe(
            product_id=product_id,
            machine_id=machine_id,
            paper_id=paper_id,
            quantity=quantity,
            finishings=finishings,
            page_count=page_count,
            trim_width_mm=trim_w,
            trim_height_mm=trim_h,
        )
        return recipe
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/production-orders/apply/{job_id}")
def apply_production_order_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """
    Aplica la orden de producción seleccionada al trabajo:
    - Asigna perfil recomendado
    - Ejecuta y genera el pliego de imposición correspondiente
    - Valida conformidad contra el PDF
    - Genera la Hoja de Ruta de Taller (Job Ticket PDF)
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    meta = job_data.get("job_meta") or {}
    pdf_pages = (job_data.get("paginas") or {}).get("total_paginas") or meta.get("page_count") or 1

    product_id = body.get("product_id", "catalogo_grapado")
    machine_id = body.get("machine_id", "digital_sra3")
    paper_id = body.get("paper_id", "estucado_mate")
    quantity = body.get("quantity", 500)
    finishings = body.get("finishings", [])

    recipe = propose_production_recipe(
        product_id=product_id,
        machine_id=machine_id,
        paper_id=paper_id,
        quantity=quantity,
        finishings=finishings,
        page_count=pdf_pages,
    )

    # Validar coherencia del PDF contra la orden
    findings = validate_pdf_against_order(job_data, recipe)

    # Generar Hoja de Ruta (Job Ticket PDF)
    ticket_path = JOBS_DIR / f"{safe_id}_job_ticket.pdf"
    try:
        generate_job_ticket_pdf(recipe, job_data, ticket_path)
    except Exception as exc:
        print(f"[production_order] Aviso generación Job Ticket: {exc}")

    # Guardar la orden en el trabajo
    job_data["production_order"] = recipe
    job_data["production_order_findings"] = findings
    job_data["job_ticket_generated"] = ticket_path.exists()

    # Si hay PDF objetivo, generar automáticamente el pliego de imposición según la receta
    target_pdf = get_latest_cumulative_pdf(meta) or meta.get("file_path")
    if target_pdf and Path(target_pdf).exists():
        imp = recipe["imposition"]
        output_imposed_pdf = job_output_path(f"{safe_id}_pliego_imposicion_{imp['sheet_size'].lower()}.pdf")
        try:
            imp_result = generate_imposed_pdf(
                pdf_path=target_pdf,
                output_path=output_imposed_pdf,
                sheet_size=imp["sheet_size"],
                orientation=imp["orientation"],
                mode=imp["mode"],
                gap_mm=imp.get("gutter_x_mm", 4.0),
                bleed_mm=imp.get("bleed_mm", 3.0),
                sheet_margin_mm=imp.get("sheet_margin_mm", 10.0),
                add_marks=True,
                add_reg_crosses=True,
                add_color_bar=True,
                add_slug=True,
                job_id=safe_id,
                base_url=str(request.base_url),
                gap_x_mm=imp.get("gutter_x_mm"),
                gap_y_mm=imp.get("gutter_y_mm"),
            )
            meta["imposed_pdf_path"] = str(output_imposed_pdf)
            meta["imposition_source_sha256"] = meta.get("current_sha256") or meta.get("sha256")
            meta["last_imposition_plan"] = imp_result
        except Exception as exc:
            print(f"[production_order] Aviso generación imposición: {exc}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "ok",
        "order": recipe,
        "compliance_findings": findings,
        "job_ticket_url": f"/api/production-orders/job-ticket/{safe_id}",
    }


@app.get("/api/production-orders/job-ticket/{job_id}")
def download_job_ticket_endpoint(job_id: str):
    """Descarga la Hoja de Ruta de Taller (Job Ticket A4 PDF) para seguimiento en imprenta."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    ticket_path = JOBS_DIR / f"{safe_id}_job_ticket.pdf"
    if not ticket_path.exists():
        # Generar sobre la marcha si no existe
        with open(job_json_path, "r", encoding="utf-8") as f:
            job_data = json.load(f)
        order = job_data.get("production_order")
        if not order:
            order = propose_production_recipe("catalogo_grapado", "digital_sra3", "estucado_mate")
        generate_job_ticket_pdf(order, job_data, ticket_path)

    return FileResponse(
        path=str(ticket_path),
        media_type="application/pdf",
        filename=f"Hoja_de_Ruta_IntelliPrint_{safe_id[:8]}.pdf",
    )


# =============================================================================
# VALIDACIÓN DE PRODUCCIÓN CON EVIDENCIA (GWG 2015 / ISO 15930 PDF/X)
# =============================================================================

@app.get("/api/validation/standards")
def validation_standards_endpoint():
    """Devuelve el catálogo de estándares de producción industrial GWG y PDF/X."""
    return {"standards": get_available_standards()}


@app.post("/api/validation/verify/{job_id}")
def verify_production_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """Ejecuta una auditoría pericial contra la norma GWG o PDF/X elegida con evidencias exactas."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(meta) or meta.get("file_path")
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF de origen no encontrado.")

    standard_id = body.get("standard_id", "gwg_2015_sheetfed")
    try:
        report = validate_pdf_gwg(target_pdf, standard_id=standard_id, job_data=job_data)

        # Generar certificado PDF de conformidad
        cert_path = JOBS_DIR / f"{safe_id}_certificado_gwg.pdf"
        generate_gwg_certificate_pdf(job_data, report, cert_path)

        job_data["production_validation"] = report
        job_data["production_validation_certificate_path"] = str(cert_path)
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

        report["certificate_url"] = f"/api/validation/certificate/{job_id}"
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error validando contra norma GWG: {exc}")


@app.get("/api/validation/certificate/{job_id}")
def download_validation_certificate_endpoint(job_id: str):
    """Descarga el Certificado Oficial de Producción pericial en PDF firmado digitalmente."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    cert_path = JOBS_DIR / f"{safe_id}_certificado_gwg.pdf"
    if not cert_path.exists():
        with open(job_json_path, "r", encoding="utf-8") as f:
            job_data = json.load(f)
        meta = job_data.get("job_meta", {})
        target_pdf = get_latest_cumulative_pdf(meta) or meta.get("file_path")
        report = job_data.get("production_validation") or validate_pdf_gwg(target_pdf, "gwg_2015_sheetfed", job_data)
        generate_gwg_certificate_pdf(job_data, report, cert_path)

    return FileResponse(
        path=str(cert_path),
        media_type="application/pdf",
        filename=f"Certificado_Conformidad_GWG_{safe_id[:8]}.pdf",
    )


def get_authenticated_user(request: Request) -> Optional[Dict[str, Any]]:
    """Extrae el usuario autenticado a partir de la cookie de sesión HttpOnly o encabezado Bearer."""
    session_id = request.cookies.get("intelliprint_session")
    if not session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:].strip()
    if session_id:
        return get_user_from_session(session_id)
    return None


def _require_auth(request: Request) -> Dict[str, Any]:
    user = get_authenticated_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión para realizar esta operación.")
    return user


def _require_permission(request: Request, permission: str) -> Dict[str, Any]:
    user = _require_auth(request)
    if not user_has_permission(user, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Tu rol ({user.get('role')}) no tiene permiso para esta operación ({permission}).",
        )
    return user


# =============================================================================
# AUTENTICACIÓN, REGISTRO INDIVIDUAL, SESIONES ÚNICAS Y ROLES (RBAC)
# =============================================================================

@app.post("/api/auth/login")
def auth_login_endpoint(request: Request, response: Response, body: dict = Body(default={})):
    """Inicia sesión por email o usuario con sesión única activa (cierra sesiones previas)."""
    username = (body.get("username") or body.get("email") or "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Correo/usuario y contraseña obligatorios.")

    user, err_reason = authenticate_user_detailed(username, password)
    if not user:
        if err_reason == "pending_approval":
            raise HTTPException(
                status_code=403,
                detail="Tu cuenta fue creada, pero la asignación del rol solicitado está pendiente de aprobación por el administrador.",
            )
        if err_reason == "disabled":
            raise HTTPException(status_code=403, detail="Esta cuenta está desactivada.")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas.")

    session_id = create_user_session(user["id"], single_session=True)
    response.set_cookie(
        key="intelliprint_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400,  # 24h
        path="/",
    )
    return {
        "status": "ok",
        "user": user,
        "session_id": session_id,
        "db_status": get_db_status(),
    }


@app.post("/api/auth/register")
def auth_register_endpoint(request: Request, response: Response, body: dict = Body(default={})):
    """Registra una cuenta individual con email, contraseña y asignación segura de rol."""
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    full_name = (body.get("full_name") or "").strip()
    requested_role = (body.get("role") or "alumno").strip()
    invite_code = (body.get("invite_code") or "").strip() or None
    class_code = (body.get("class_code") or "").strip() or None

    try:
        user = register_user(
            email=email,
            password=password,
            full_name=full_name,
            requested_role=requested_role,
            invite_code=invite_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    joined_group = None
    if user.get("is_active"):
        if class_code:
            try:
                joined_group = fp_join_group(user["id"], class_code).get("group")
            except Exception as exc:
                # No abortar el alta si el código de grupo no existe, pero avisar
                joined_group = {"error": str(exc)}

        session_id = create_user_session(user["id"], single_session=True)
        response.set_cookie(
            key="intelliprint_session",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=86400,
            path="/",
        )
        return {
            "status": "ok",
            "user": user,
            "session_id": session_id,
            "joined_group": joined_group,
            "db_status": get_db_status(),
        }

    return {
        "status": "pending",
        "message": (
            f"Cuenta registrada para {user['email']}. "
            f"El rol '{user['requested_role']}' requiere aprobación del administrador o código de centro."
        ),
        "user": user,
        "db_status": get_db_status(),
    }


@app.post("/api/auth/logout")
def auth_logout_endpoint(request: Request, response: Response):
    """Cierra la sesión activa y elimina la cookie de sesión."""
    session_id = request.cookies.get("intelliprint_session")
    if session_id:
        delete_session(session_id)
    response.delete_cookie("intelliprint_session", path="/")
    return {"status": "ok"}


@app.get("/api/auth/me")
def auth_me_endpoint(request: Request):
    """Devuelve los datos del usuario autenticado actual, permisos RBAC y estado BD."""
    user = get_authenticated_user(request)
    db_st = get_db_status()
    if not user:
        return {"authenticated": False, "user": None, "db_status": db_st}
    return {
        "authenticated": True,
        "user": user,
        "db_status": db_st,
    }


@app.get("/api/admin/users")
def admin_list_users_endpoint(request: Request):
    """Lista todas las cuentas registradas para gestión de roles y aprobaciones."""
    _require_permission(request, "manage_users")
    return {"users": list_users(), "db_status": get_db_status()}


@app.post("/api/admin/users/{user_id}/access")
def admin_update_user_access_endpoint(user_id: int, request: Request, body: dict = Body(default={})):
    """Aprueba solicitudes de rol, cambia roles o activa/desactiva cuentas."""
    _require_permission(request, "manage_users")
    role = body.get("role")
    is_active = body.get("is_active")
    approval_status = body.get("approval_status")
    try:
        updated = update_user_access(
            user_id=user_id,
            role=role,
            is_active=is_active,
            approval_status=approval_status,
        )
        return {"status": "ok", "user": updated}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# PANEL DOCENTE FP: GRUPOS, PRÁCTICAS, RÚBRICAS, ENTREGAS Y EVOLUCIÓN
# =============================================================================

@app.get("/api/fp/teacher/overview")
def fp_teacher_overview_endpoint(request: Request, group_id: Optional[int] = None):
    """Panel completo del docente FP: grupos, prácticas, entregas, rúbricas y evolución."""
    _require_permission(request, "view_student_progress")
    return {
        "groups": fp_list_groups(),
        "rubrics": fp_list_rubrics(),
        "assignments": fp_list_assignments(group_id=group_id),
        "submissions": fp_list_submissions(group_id=group_id),
        "evolution": fp_student_evolution(group_id=group_id),
        "scenarios": [
            {"id": s["id"], "title": s["title"], "level": s["level"], "module": s["module"]}
            for s in SCENARIOS_CATALOG
        ],
        "db_status": get_db_status(),
    }


@app.post("/api/fp/teacher/groups")
def fp_teacher_create_group_endpoint(request: Request, body: dict = Body(default={})):
    """Crea un nuevo grupo FP con código de matrícula."""
    user = _require_permission(request, "grade_submissions")
    try:
        group = fp_create_group(
            name=body.get("name", ""),
            center=body.get("center", "CPIFP Salesianos Urnieta"),
            module_name=body.get("module_name", "Preimpresión Digital"),
            teacher_id=user["id"],
            join_code=body.get("join_code"),
        )
        return {"status": "ok", "group": group}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/fp/teacher/rubrics")
def fp_teacher_create_rubric_endpoint(request: Request, body: dict = Body(default={})):
    """Crea una nueva rúbrica ponderada."""
    user = _require_permission(request, "grade_submissions")
    try:
        rubric = fp_create_rubric(
            title=body.get("title", ""),
            description=body.get("description", ""),
            criteria=body.get("criteria", []),
            teacher_id=user["id"],
        )
        return {"status": "ok", "rubric": rubric}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/fp/teacher/assignments")
def fp_teacher_create_assignment_endpoint(request: Request, body: dict = Body(default={})):
    """Crea una práctica evaluable asociada a un grupo y rúbrica."""
    user = _require_permission(request, "grade_submissions")
    try:
        assignment = fp_create_assignment(
            group_id=int(body["group_id"]),
            teacher_id=user["id"],
            title=body.get("title", ""),
            description=body.get("description", ""),
            assignment_type=body.get("assignment_type", "pdf_real"),
            scenario_id=body.get("scenario_id"),
            target_profile=body.get("target_profile", "OFFSET_300"),
            rubric_id=int(body["rubric_id"]) if body.get("rubric_id") else None,
            due_date=body.get("due_date"),
        )
        return {"status": "ok", "assignment": assignment}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/fp/teacher/submissions/{submission_id}")
def fp_teacher_submission_detail_endpoint(submission_id: int, request: Request):
    """Obtiene el análisis comparativo Inicial -> Decisiones -> Final de una entrega."""
    user = _require_auth(request)
    detail = fp_get_submission_detail(submission_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Entrega no encontrada.")
    if not user_has_permission(user, "view_student_progress") and detail["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta entrega.")
    return {"submission": detail}


@app.post("/api/fp/teacher/submissions/{submission_id}/grade")
def fp_teacher_grade_submission_endpoint(submission_id: int, request: Request, body: dict = Body(default={})):
    """Guarda la calificación por rúbrica y observaciones del docente."""
    user = _require_permission(request, "grade_submissions")
    try:
        graded = fp_grade_submission(
            submission_id=submission_id,
            teacher_id=user["id"],
            rubric_scores=body.get("rubric_scores", {}),
            final_grade=body.get("final_grade"),
            teacher_feedback=body.get("teacher_feedback", ""),
            status=body.get("status", "GRADED"),
        )
        return {"status": "ok", "submission": graded}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/fp/teacher/export-csv")
def fp_teacher_export_csv_endpoint(request: Request, group_id: Optional[int] = None):
    """Descarga el acta de entregas y calificaciones en formato CSV para Excel."""
    _require_permission(request, "view_student_progress")
    csv_text = fp_export_grades_csv(group_id=group_id)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="IntelliPrint_Actas_FP.csv"'},
    )


@app.get("/api/fp/teacher/submissions/{submission_id}/report-pdf")
def fp_submission_report_pdf_endpoint(submission_id: int, request: Request):
    """Descarga el Boletín Oficial de Evaluación Práctica FP en PDF A4."""
    user = _require_auth(request)
    detail = fp_get_submission_detail(submission_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Entrega no encontrada.")
    if not user_has_permission(user, "view_student_progress") and detail["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Sin permiso para descargar este boletín.")
    pdf_bytes = fp_generate_eval_pdf(submission_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Evaluacion_FP_Entrega_{submission_id}.pdf"'},
    )


@app.get("/api/fp/student/dashboard")
def fp_student_dashboard_endpoint(request: Request):
    """Panel del alumno: grupos inscritos, prácticas abiertas, entregas y cuestionarios."""
    user = _require_auth(request)
    return {
        "dashboard": fp_student_dashboard(user["id"]),
        "db_status": get_db_status(),
    }


@app.post("/api/fp/student/join-group")
def fp_student_join_group_endpoint(request: Request, body: dict = Body(default={})):
    """Matricula al usuario autenticado en un grupo FP mediante código de clase."""
    user = _require_auth(request)
    try:
        res = fp_join_group(user["id"], body.get("join_code", ""))
        return {"status": "ok", **res}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/fp/student/submit")
def fp_student_submit_endpoint(request: Request, body: dict = Body(default={})):
    """Entrega un trabajo PDF analizado/corregido (job_id) a una práctica FP."""
    user = _require_permission(request, "submit_fp_assignment")
    assignment_id = body.get("assignment_id")
    raw_job_id = body.get("job_id")
    if not assignment_id or not raw_job_id:
        raise HTTPException(status_code=400, detail="assignment_id y job_id son obligatorios.")

    safe_id = safe_job_id(str(raw_job_id))
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo PDF no encontrado en el servidor.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    try:
        sub = fp_submit_job(
            student_id=user["id"],
            assignment_id=int(assignment_id),
            job_id=safe_id,
            job_data=job_data,
        )
        return {"status": "ok", "submission": sub}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# PORTAL DE APROBACIÓN DE CLIENTE (VISTO BUENO EXTERNO)
# =============================================================================

@app.post("/api/client-approval/create/{job_id}")
def create_client_approval_endpoint(job_id: str, request: Request):
    """Genera un enlace y token protegido para enviar al cliente para Visto Bueno."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    base_url = str(request.base_url).rstrip("/")
    approval_data = generate_client_approval_link(safe_id, base_url=base_url)

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_data["client_approval"] = approval_data
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return approval_data


@app.get("/api/client-approval/info/{token}")
def get_client_approval_info_endpoint(token: str):
    """Devuelve la información del trabajo para la vista del cliente."""
    approval = get_client_approval_by_token(token)
    if not approval:
        raise HTTPException(status_code=404, detail="Token de aprobación no encontrado o caducado.")

    safe_id = safe_job_id(approval["job_id"])
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    meta = job_data.get("job_meta", {})
    return {
        "token": token,
        "job_id": safe_id,
        "filename": meta.get("filename", "documento.pdf"),
        "page_count": meta.get("page_count", 1),
        "status": approval.get("status", "PENDING"),
        "created_at": approval.get("created_at"),
        "client_name": approval.get("client_name"),
        "decision": approval.get("decision"),
        "notes": approval.get("notes"),
        "decided_at": approval.get("decided_at"),
        "preview_pdf_url": f"/api/download-pdf/{safe_id}",
    }


@app.get("/api/client-approval/view/{token}", response_class=HTMLResponse)
def client_approval_view_endpoint(token: str):
    """Página web pública para que el cliente examine el PDF corregido y emita su Visto Bueno."""
    approval = get_client_approval_by_token(token)
    if not approval:
        raise HTTPException(status_code=404, detail="Token de aprobación no encontrado o caducado.")

    safe_id = safe_job_id(approval["job_id"])
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    meta = job_data.get("job_meta", {})
    filename = html.escape(meta.get("filename", "documento.pdf"))
    pages = meta.get("page_count", 1)
    status = approval.get("status", "PENDING")
    client_name = html.escape(approval.get("client_name") or "")
    notes = html.escape(approval.get("notes") or "")
    decided_at = approval.get("decided_at") or ""

    status_banner = ""
    if status == "APPROVED":
        status_banner = f"""
        <div class="p-6 bg-emerald-50 border-2 border-emerald-500 rounded-2xl text-emerald-900 space-y-2 mb-6 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-lg">✓</div>
            <div>
              <h2 class="text-base font-extrabold text-emerald-950 uppercase tracking-wide">Visto Bueno Aprobado para Tirada (OK Plancha)</h2>
              <p class="text-xs text-emerald-800">Aprobado formalmente por: <strong>{client_name}</strong> el {decided_at[:19].replace('T', ' ')} UTC.</p>
            </div>
          </div>
          {f'<p class="text-xs text-emerald-900 bg-white/60 p-2.5 rounded-lg border border-emerald-200 mt-2 font-medium">Observaciones: {notes}</p>' if notes else ''}
          <p class="text-xs font-semibold text-emerald-800 pt-1">El taller de preimpresión ha recibido la conformidad y procederá a la filmación de planchas y tiro en máquina.</p>
        </div>
        """
    elif status == "REJECTED":
        status_banner = f"""
        <div class="p-6 bg-red-50 border-2 border-red-500 rounded-2xl text-red-900 space-y-2 mb-6 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-red-600 text-white flex items-center justify-center font-bold text-lg">✕</div>
            <div>
              <h2 class="text-base font-extrabold text-red-950 uppercase tracking-wide">Solicitud de Cambios Notificada al Taller</h2>
              <p class="text-xs text-red-800">Rechazado por: <strong>{client_name}</strong> el {decided_at[:19].replace('T', ' ')} UTC.</p>
            </div>
          </div>
          {f'<p class="text-xs text-red-900 bg-white/60 p-2.5 rounded-lg border border-red-200 mt-2 font-medium">Motivo: {notes}</p>' if notes else ''}
          <p class="text-xs font-semibold text-red-800 pt-1">El técnico de preimpresión revisará las anotaciones antes de preparar una nueva versión.</p>
        </div>
        """

    form_section = ""
    if status == "PENDING":
        form_section = f"""
        <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h3 class="text-sm font-extrabold text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-sky-500"></span> Formulario de Visto Bueno del Cliente
          </h3>
          <p class="text-xs text-slate-500">Por favor, revisa el PDF final en el visor inferior. Si estás de acuerdo con los textos, colores y maquetación, confirma tu Visto Bueno para entrar a máquina.</p>

          <form id="approvalForm" onsubmit="submitApproval(event)" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Nombre y Apellidos / Empresa: *</label>
                <input type="text" id="clientNameInput" required placeholder="Ej. Ana García - Dpto. Marketing" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 focus:ring-2 focus:ring-sky-500 outline-none">
              </div>
              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Correo Electrónico (para justificante):</label>
                <input type="email" id="clientEmailInput" placeholder="ana.garcia@empresa.com" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 focus:ring-2 focus:ring-sky-500 outline-none">
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Observaciones o Instrucciones Especiales:</label>
              <textarea id="clientNotesInput" rows="2" placeholder="Ej. Revisado texto legal y precios. Aprobado para tirada de 1.000 ejemplares." class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 focus:ring-2 focus:ring-sky-500 outline-none"></textarea>
            </div>

            <div class="flex flex-col sm:flex-row items-center gap-3 pt-2">
              <button type="button" onclick="sendDecision('approved')" class="w-full sm:w-auto px-6 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white rounded-xl text-xs font-bold shadow-md transition flex items-center justify-center gap-2 cursor-pointer">
                ✓ Dar Visto Bueno (OK para Imprimir)
              </button>
              <button type="button" onclick="sendDecision('rejected')" class="w-full sm:w-auto px-5 py-3 bg-white border border-rose-300 text-rose-700 hover:bg-rose-50 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 cursor-pointer">
                ✕ Solicitar Cambios / Rechazar
              </button>
            </div>
          </form>
        </div>
        """

    page_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Visto Bueno de Cliente · {filename} · IntelliPrint</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 antialiased flex flex-col">
  <header class="bg-slate-900 text-white border-b border-slate-800 py-4 px-6 shadow-md">
    <div class="max-w-5xl mx-auto flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-sky-500/20 text-sky-400 flex items-center justify-center border border-sky-400/30 font-bold">IP</div>
        <div>
          <h1 class="text-sm font-extrabold tracking-wide">IntelliPrint · Portal de Aprobación de Clientes</h1>
          <p class="text-xs text-slate-400">CPIFP Salesianos Urnieta · CIFP Mendizabala LHII</p>
        </div>
      </div>
      <div class="text-right text-xs text-slate-400 hidden sm:block">
        <span class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">Token: {token[:12]}...</span>
      </div>
    </div>
  </header>

  <main class="max-w-5xl mx-auto p-4 sm:p-6 w-full flex-1 space-y-6">
    <!-- Header del trabajo -->
    <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div>
        <span class="text-[10px] font-bold text-sky-600 uppercase tracking-wider block">Revisión de Producción</span>
        <h2 class="text-lg font-black text-slate-900">{filename}</h2>
        <p class="text-xs text-slate-500 mt-0.5">Documento preparado para imprenta · {pages} página(s)</p>
      </div>
      <div class="flex items-center gap-3">
        <a href="/api/download-pdf/{safe_id}" target="_blank" download class="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition flex items-center gap-1.5 border border-slate-200">
          📥 Descargar PDF
        </a>
      </div>
    </div>

    {status_banner}
    {form_section}

    <!-- Visor del PDF -->
    <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-3">
      <div class="flex items-center justify-between border-b border-slate-100 pb-2">
        <h3 class="text-xs font-extrabold uppercase tracking-wider text-slate-700">Previsualización del PDF de Producción</h3>
        <span class="text-xs text-slate-400 font-mono">ID: {safe_id[:8]}</span>
      </div>
      <div class="w-full bg-slate-900 rounded-xl overflow-hidden border border-slate-300 min-h-[600px] flex items-center justify-center">
        <iframe src="/api/download-pdf/{safe_id}#toolbar=0" class="w-full h-[650px] border-0" title="Visor de PDF"></iframe>
      </div>
    </div>
  </main>

  <footer class="bg-white border-t border-slate-200 py-4 text-center text-xs text-slate-400">
    IntelliPrint v2.0 · Plataforma de Preimpresión Profesional y Formación Profesional
  </footer>

  <script>
    async function sendDecision(decision) {{
      const nameInput = document.getElementById('clientNameInput');
      const emailInput = document.getElementById('clientEmailInput');
      const notesInput = document.getElementById('clientNotesInput');

      const name = nameInput ? nameInput.value.trim() : '';
      if (!name) {{
        alert('Por favor, indica tu nombre o empresa antes de emitir tu decisión.');
        if (nameInput) nameInput.focus();
        return;
      }}

      const actionText = decision === 'approved' ? 'dar tu Visto Bueno para imprimir' : 'solicitar cambios';
      if (!confirm(`¿Confirmas que deseas ${{actionText}}?`)) return;

      try {{
        const resp = await fetch('/api/client-approval/submit/{token}', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            client_name: name,
            client_email: emailInput ? emailInput.value.trim() : '',
            decision: decision,
            notes: notesInput ? notesInput.value.trim() : ''
          }})
        }});

        if (!resp.ok) throw new Error('Error al registrar la decisión');
        alert('¡Tu decisión ha sido registrada con éxito y comunicada al taller de imprenta!');
        window.location.reload();
      }} catch (err) {{
        alert(`Error: ${{err.message}}`);
      }}
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=page_html)


@app.post("/api/client-approval/submit/{token}")
def submit_client_approval_decision_endpoint(token: str, request: Request, body: dict = Body(default={})):
    """Registra formalmente el visto bueno o rechazo del cliente."""
    client_name = body.get("client_name", "").strip()
    decision = body.get("decision", "").strip().lower()
    notes = body.get("notes", "").strip()
    client_email = body.get("client_email", "").strip() or None

    if not client_name:
        raise HTTPException(status_code=400, detail="El nombre del cliente o empresa es obligatorio.")
    if decision not in ("approved", "rejected", "approved_with_notes"):
        raise HTTPException(status_code=422, detail="Decisión no válida: debe ser approved o rejected.")

    client_ip = request.client.host if request.client else "desconocido"
    try:
        result = submit_client_decision(
            token=token,
            decision=decision,
            client_name=client_name,
            client_email=client_email,
            notes=notes,
            client_ip=client_ip,
        )

        # Actualizar el trabajo correspondiente
        job_id = result["job_id"]
        job_json_path = get_job_json_path(job_id)
        if job_json_path.exists():
            with open(job_json_path, "r", encoding="utf-8") as f:
                job_data = json.load(f)

            job_data["client_approval_record"] = result
            if decision in ("approved", "approved_with_notes"):
                current_pdf = get_latest_cumulative_pdf(job_data.get("job_meta", {}))
                if current_pdf:
                    try:
                        capture_version(
                            job_data,
                            current_pdf,
                            JOBS_DIR,
                            label=f"Visto Bueno Cliente ({client_name})",
                            is_approved=True,
                        )
                        job_data["version_history_summary"] = public_history(job_data, JOBS_DIR)
                    except Exception as exc:
                        print(f"[client_approval] Aviso version: {exc}")

            with open(job_json_path, "w", encoding="utf-8") as f:
                json.dump(job_data, f, ensure_ascii=False, indent=2)

        return {"status": "ok", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error registrando aprobación: {exc}")



def get_latest_cumulative_pdf(job_meta: dict) -> Optional[str]:
    """
    Devuelve siempre la ruta absoluta al PDF de trabajo más reciente con todas
    las correcciones acumuladas. Garantiza una cadena estrictamente acumulativa
    para que cada corrección técnica herede y preserve todas las anteriores.
    """
    if not job_meta:
        return None
    candidates = [
        job_meta.get("last_fixed_pdf_path"),
        job_meta.get("batch_fixed_pdf_path"),
        job_meta.get("barcode_fixed_pdf_path"),
        job_meta.get("tac_limited_pdf_path"),
        job_meta.get("printer_marks_pdf_path"),
        job_meta.get("mirror_bleed_pdf_path"),
        job_meta.get("fonts_outlined_pdf_path"),
        job_meta.get("bleed_fixed_pdf_path"),
        job_meta.get("hairline_fixed_pdf_path"),
        job_meta.get("icc_fixed_pdf_path"),
        job_meta.get("overprint_fixed_pdf_path"),
        job_meta.get("spot_converted_pdf_path"),
        job_meta.get("varnish_overprint_pdf_path"),
        job_meta.get("cmyk_converted_pdf_path"),
        job_meta.get("pdf_path")
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def register_cumulative_fix(job_data: dict, output_path: str | Path, fix_name: str) -> None:
    """
    Registra de forma centralizada la nueva versión del PDF acumulado, actualizando
    'last_fixed_pdf_path' y el historial cronológico de correcciones acumulativas.
    """
    ensure_original_analysis(job_data, engine.run_preflight, (UPLOAD_DIR, APPROVED_DIR, REJECTED_DIR))
    job_meta = job_data.setdefault("job_meta", {})
    clear_pdf_authorization(job_data)
    current_sha256 = update_pdf_identity(job_data, output_path)
    job_meta["last_fixed_pdf_path"] = str(output_path)
    job_meta[f"has_{fix_name}"] = True
    history = job_meta.setdefault("applied_fixes_history", [])
    history.append({
        "fix": fix_name,
        "path": str(output_path),
        "sha256": current_sha256,
        "timestamp": datetime.now().isoformat()
    })
    FIX_LABELS = {
        "cmyk_converted": "Conversión de imágenes a CMYK",
        "spot_converted": "Conversión de tintas planas a CMYK",
        "overprint_fixed": "Sobreimpresión 100% K y calado",
        "varnish_overprint": "Sobreimpresión de barnices y tintas técnicas",
        "hairline_fixed": "Engrosado de filetes finos (< 0,25 pt)",
        "icc_fixed": "Incrustación de perfil ICC de salida",
        "bleed_fixed": "Ajuste de cajas ISO y sangrado 3 mm",
        "mirror_bleed": "Sangrado sintético por reflejo (Mirror Bleed)",
        "fonts_outlined": "Trazado de fuentes a curvas vectoriales",
        "tac_limited": "Limitación de cobertura total de tinta (TAC)",
        "printer_marks": "Marcas de imprenta, corte y registro",
        "batch_fixed": "Corrección integral en lote (1 Clic)",
        "barcode_fixed": "Corrección de códigos de barras",
    }
    label = FIX_LABELS.get(fix_name, f"Corrección: {fix_name}")
    try:
        capture_version(job_data, output_path, JOBS_DIR, label=label)
        job_data["version_history_summary"] = public_history(job_data, JOBS_DIR)
    except Exception as exc:
        print(f"[register_cumulative_fix] Aviso versión: {exc}")


def refresh_job_analysis(job_data: dict, pdf_path: str | Path) -> None:
    """El dictamen se obtiene del PDF resultante, nunca borrando avisos a mano."""
    report = engine.run_preflight(
        pdf_path=str(pdf_path),
        profile_id=job_data.get("job_meta", {}).get("profile_id", "OFFSET_300"),
        icc_choice="preserve",
    )
    technical = report.get("triple_result", {}).get("technical")
    if report.get("error") or not technical:
        raise HTTPException(status_code=500, detail="No se pudo verificar el PDF corregido.")
    ensure_original_analysis(job_data, engine.run_preflight, (UPLOAD_DIR, APPROVED_DIR, REJECTED_DIR))
    job_data["job_summary"] = report["job_summary"]
    job_data["findings"] = report["findings"]
    job_data.setdefault("triple_result", {})["technical"] = technical


@app.get("/api/download-pdf/{job_id}")
def download_pdf_file(job_id: str):
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    meta = job_data.get("job_meta", {})
    pdf_p = get_latest_cumulative_pdf(meta)
    filename = meta.get("filename", "documento.pdf")
    if not pdf_p or not os.path.exists(pdf_p):
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado en el servidor.")
    return FileResponse(
        path=pdf_p,
        media_type="application/pdf",
        filename=f"IntelliPrint_{filename}"
    )

@app.post("/api/convert-to-cmyk/{job_id}")
async def convert_images_to_cmyk(
    job_id: str,
    request: Request,
    use_embedded_icc: bool = True,
    custom_icc: Optional[str] = None,
):
    """
    Convierte las imágenes RGB del PDF a CMYK usando perfiles ICC.
    - use_embedded_icc=true  → usa el OutputIntent embebido en el PDF (o fallback FOGRA39)
    - use_embedded_icc=false → usa custom_icc (nombre de archivo en icc_profiles/)
    """
    # The web selector posts FormData; keep query parameters for API clients.
    form = await request.form()
    if "use_embedded_icc" in form:
        choice = str(form["use_embedded_icc"]).lower()
        if choice not in ("true", "false"):
            raise HTTPException(status_code=400, detail="Selección ICC no válida.")
        use_embedded_icc = choice == "true"
    if "custom_icc" in form:
        custom_icc = str(form["custom_icc"])
    return await run_in_threadpool(_convert_images_to_cmyk_sync, job_id, use_embedded_icc, custom_icc)


def _convert_images_to_cmyk_sync(job_id, use_embedded_icc, custom_icc):
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})

    # Usar el PDF más reciente en la cadena acumulativa
    pdf_path = get_latest_cumulative_pdf(job_meta)

    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF de origen no encontrado en el servidor.")

    ICC_PROFILES_DIR = BASE_DIR / "icc_profiles"
    dst_icc_path = None
    temp_icc_file = None

    if use_embedded_icc:
        # Intentar extraer el ICC embebido en el PDF
        temp_icc_file = extract_embedded_icc_to_tempfile(pdf_path)
        if temp_icc_file:
            dst_icc_path = temp_icc_file
        else:
            # Si no hay ICC embebido, usar el seleccionado en el job o el predeterminado
            fallback_name = job_data.get("job_meta", {}).get("selected_icc") or "ISOcoated_v2_eci.icc"
            fallback_path = ICC_PROFILES_DIR / fallback_name
            if not fallback_path.exists():
                fallback_path = ICC_PROFILES_DIR / "ISOcoated_v2_300_bas.icc"
            dst_icc_path = str(fallback_path)
    else:
        if not custom_icc:
            raise HTTPException(status_code=400, detail="Se requiere un perfil ICC personalizado.")
        try:
            selected_path, family = resolve_icc_profile(custom_icc)
            if family != "CMYK":
                raise ValueError("Selecciona un perfil ICC CMYK para convertir las imágenes.")
            dst_icc_path = str(selected_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    output_path = JOBS_DIR / f"{safe_id}_cmyk_converted.pdf"

    try:
        conv_result = convert_rgb_images_to_cmyk(
            pdf_path=pdf_path,
            dst_icc_path=dst_icc_path,
            output_path=str(output_path),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la conversión: {e}")
    finally:
        # Limpiar el archivo temporal del ICC extraído
        if temp_icc_file and os.path.exists(temp_icc_file):
            try:
                os.unlink(temp_icc_file)
            except Exception:
                pass

    if not conv_result.get("success") or conv_result.get("errors"):
        errors = conv_result.get("errors", [])
        raise HTTPException(status_code=500, detail=f"La conversión falló: {'; '.join(errors)}")

    # Guardar en metadatos del job de forma acumulativa
    job_meta["has_cmyk_converted"] = True
    job_meta["cmyk_converted_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "cmyk_converted")

    refresh_job_analysis(job_data, output_path)

    # Regenerar el certificado PDF técnico
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[convert-to-cmyk] Aviso: no se pudo regenerar el certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "job_id": safe_id,
        "images_converted": conv_result["images_converted"],
        "images_skipped": conv_result["images_skipped"],
        "errors": conv_result.get("errors", []),
        "download_url": f"/api/download-cmyk/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
        "report": job_data,
        "target_icc": Path(dst_icc_path).name if dst_icc_path else "ISO Coated v2"
    }


@app.get("/api/download-cmyk/{job_id}")
def download_cmyk_pdf(job_id: str):
    """Descarga el PDF con imágenes convertidas a CMYK."""
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    converted_path = JOBS_DIR / f"{job_id}_cmyk_converted.pdf"
    if not converted_path.exists():
        raise HTTPException(status_code=404, detail="PDF convertido no encontrado. Ejecuta la conversión primero.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")

    return FileResponse(
        path=str(converted_path),
        media_type="application/pdf",
        filename=f"IntelliPrint_CMYK_{clean_name}.pdf",
    )


# ---------------------------------------------------------------------------
# Conversión de Tintas Planas / Directas a CMYK (Cuatricromía)
# ---------------------------------------------------------------------------

@app.post("/api/convert-spots-to-cmyk/{job_id}")
def convert_spots_to_cmyk_endpoint(job_id: str, target_spots: Optional[str] = Form(None)):
    """
    Convierte tintas planas / directas (Pantone, directas) a cuatricromía (CMYK de proceso).
    Preserva intactas las tintas técnicas como barnices, lacas y troqueles.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_spots_converted.pdf"

    target_list = None
    if target_spots:
        target_list = [s.strip() for s in target_spots.split(",") if s.strip()]

    conv_result = convert_spot_colors_to_cmyk(
        pdf_path=source_pdf,
        output_path=output_path,
        target_spots=target_list,
        convert_technical=False
    )

    if not conv_result.get("success"):
        errors = conv_result.get("errors", [])
        raise HTTPException(status_code=500, detail=f"Fallo al convertir tintas planas: {'; '.join(errors)}")

    # Guardar paths en job_meta de forma acumulativa
    job_data["job_meta"]["spot_converted_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "spot_converted")

    converted_names = {s["name"] for s in conv_result.get("spots_converted", [])}

    # Actualizar la lista de spot_colors en el job summary
    spots_remaining = [
        s for s in job_data.get("job_summary", {}).get("spot_colors", [])
        if s.get("name") not in converted_names
    ]
    job_data["job_summary"]["spot_colors"] = spots_remaining

    # Eliminar de findings los avisos relacionados con las tintas convertidas (ej. sobreimpresion de Pantone)
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if not any(name.lower() in f.get("title", "").lower() or name.lower() in f.get("message", "").lower() for name in converted_names)
    ]

    # Recalcular resultado técnico
    all_findings = job_data.get("findings", [])
    errs = sum(1 for f in all_findings if f.get("severity") == "ERROR")
    warns = sum(1 for f in all_findings if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    tech["status"] = "FAIL" if errs > 0 else ("PASS_WITH_WARNINGS" if warns > 0 else "PASS")
    tech["label"] = "NO CUMPLE" if errs > 0 else ("CUMPLE CON AVISOS" if warns > 0 else "CUMPLE")

    # Regenerar el certificado oficial en PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    spots_remaining = job_data["job_summary"]["spot_colors"]
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[convert-spots] Aviso: no se pudo regenerar certificado PDF: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "spots_converted": conv_result.get("spots_converted", []),
        "pages_modified": conv_result.get("pages_modified", 0),
        "remaining_spots": spots_remaining,
        "download_url": f"/api/download-pdf/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
    }


# ---------------------------------------------------------------------------
# Auto-Trapping: Corrección automática de sobreimpresión en textos negros
# ---------------------------------------------------------------------------

@app.post("/api/apply-overprint/{job_id}")
def apply_overprint_fix(job_id: str, mode: str = "k100"):
    """
    Aplica sobreimpresión automática exclusivamente a textos negros 100% K en calado.
    """
    # Validar job_id para evitar path traversal
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(
            status_code=400,
            detail="PDF de origen no encontrado en el servidor."
        )

    output_path = JOBS_DIR / f"{safe_id}_overprint_fixed.pdf"

    # ── PASO 1 (silencioso): White Overprint Killer ──────────────────────────
    # Corregir blanco en sobreimpresión ANTES del auto-trapping de negros.
    # Si hay blancos que sobreimprimen los forzamos a calado; si no hay, el PDF
    # pasa sin modificar. Usamos un fichero temporal intermedio para no pisar source_pdf.
    white_fix_tmp = JOBS_DIR / f"{safe_id}_white_fixed_tmp.pdf"
    white_result = fix_white_overprint(str(source_pdf), str(white_fix_tmp))
    white_objects_fixed = 0
    if white_result.get("success"):
        white_objects_fixed = white_result.get("objects_fixed", 0)
        if white_objects_fixed > 0:
            # Usar el PDF con blancos ya corregidos como fuente del auto-trapping
            overprint_source = str(white_fix_tmp)
            # Limpiar la incidencia WHITE_OVERPRINT de findings
            job_data["findings"] = [
                f for f in job_data.get("findings", [])
                if f.get("rule_id") != "WHITE_OVERPRINT"
                and "blanco" not in f.get("title", "").lower()
            ]
            stats = job_data.get("job_summary", {}).get("overprint_stats", {})
            stats["white_overprint"] = 0
        else:
            overprint_source = str(source_pdf)
            # Limpiar tmp si no se modificó nada
            if white_fix_tmp.exists():
                white_fix_tmp.unlink(missing_ok=True)
    else:
        overprint_source = str(source_pdf)
        if white_fix_tmp.exists():
            white_fix_tmp.unlink(missing_ok=True)

    # ── PASO 2 (silencioso): Rich Black Killer ───────────────────────────────
    # Convierte negro enriquecido en texto < 12 pt a negro puro 0/0/0/100.
    rich_fix_tmp = JOBS_DIR / f"{safe_id}_rich_black_tmp.pdf"
    rich_result = fix_rich_black_small_text(overprint_source, str(rich_fix_tmp))
    rich_texts_fixed = 0
    if rich_result.get("success") and rich_result.get("texts_fixed", 0) > 0:
        rich_texts_fixed = rich_result["texts_fixed"]
        overprint_source = str(rich_fix_tmp)
        # Limpiar incidencias RICH_BLACK_SMALL_TEXT de findings
        job_data["findings"] = [
            f for f in job_data.get("findings", [])
            if f.get("rule_id") != "RICH_BLACK_SMALL_TEXT"
        ]
        stats = job_data.get("job_summary", {}).get("overprint_stats", {})
        stats["rich_black_small_text"] = 0
    else:
        if rich_fix_tmp.exists():
            rich_fix_tmp.unlink(missing_ok=True)

    # ── PASO 3: Auto-trapping de textos en negro puro 100% K ─────────────────
    result = apply_overprint_to_dark_text(overprint_source, str(output_path), dark_k_threshold=0.99)

    # Limpiar tmps intermedios
    if white_fix_tmp.exists():
        white_fix_tmp.unlink(missing_ok=True)
    if rich_fix_tmp.exists():
        rich_fix_tmp.unlink(missing_ok=True)

    if not result.get("success"):
        errors = result.get("errors", [])
        raise HTTPException(
            status_code=500,
            detail=f"La corrección de sobreimpresión falló: {'; '.join(errors)}"
        )

    # Guardar la ruta en el job para el endpoint de descarga de forma acumulativa
    job_data["job_meta"]["overprint_fixed_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "overprint_fixed")

    # Actualizar estadisticas y limpiar incidencias resueltas de la ficha tecnica
    stats = job_data.get("job_summary", {}).get("overprint_stats", {})
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") not in ("BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100")
        and not (("calado" in f.get("title", "").lower() or "knockout" in f.get("title", "").lower()) and "barniz" not in f.get("title", "").lower())
    ]
    stats["black_100_overprint"] = stats.get("black_100_overprint", 0) + stats.get("black_100_knockout", 0)
    stats["black_100_knockout"] = 0
    stats["dark_80_overprint"] = 0
    stats["dark_80_knockout"] = 0
    stats["black_text_overprint"] = stats["black_100_overprint"]
    stats["black_text_knockout"] = 0

    # Recalcular resultado tecnico general
    all_findings = job_data.get("findings", [])
    errs = sum(1 for f in all_findings if f.get("severity") == "ERROR")
    warns = sum(1 for f in all_findings if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar el PDF de la Ficha Tecnica oficial para que el Dictamen no muestre el error resuelto
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[apply-overprint] Aviso: no se pudo regenerar certificado PDF: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "mode": mode,
        "pages_modified": result["pages_modified"],
        "text_ops_fixed": result["text_ops_fixed"],
        "text_100_fixed": result.get("text_100_fixed", 0),
        "white_objects_fixed": white_objects_fixed,
        "rich_texts_fixed": rich_texts_fixed,
        "errors": result.get("errors", []),
        "download_url": f"/api/download-overprint/{safe_id}",
        "overprint_stats": stats,
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
    }


@app.post("/api/fix-hairlines/{job_id}")
def fix_hairlines_endpoint(job_id: str, target_width: float = 0.30):
    """
    Fase 2: Engrosa trazos finos (< 0.25 pt / hairline) a un grosor seguro (0.30 pt).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    minimum_width = get_profile_by_id(job_meta.get("profile_id", "OFFSET_300"))["min_hairline_pt"]
    target_width = max(target_width, minimum_width)
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_hairline_fixed.pdf"

    result = fix_hairlines(
        pdf_path=source_pdf,
        output_path=output_path,
        hairline_threshold=minimum_width,
        target_width=target_width
    )

    if not result.get("success"):
        errors = result.get("errors", [])
        raise HTTPException(status_code=500, detail=f"Fallo al engrosar líneas finas: {'; '.join(errors)}")

    # Guardar ruta acumulada
    job_data["job_meta"]["hairline_fixed_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "hairline_fixed")

    # Limpiar incidencias de HAIRLINE_DETECTED
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") != "HAIRLINE_DETECTED"
    ]

    # Recalcular dictamen técnico
    all_findings = job_data.get("findings", [])
    errs = sum(1 for f in all_findings if f.get("severity") == "ERROR")
    warns = sum(1 for f in all_findings if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar certificado
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[fix-hairlines] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "lines_fixed": result.get("lines_fixed", 0),
        "pages_modified": result.get("pages_modified", 0),
        "download_url": f"/api/download-hairline/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
    }


@app.get("/api/download-hairline/{job_id}")
def download_hairline_pdf(job_id: str):
    """Descarga el PDF con líneas finas engrosadas."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("hairline_fixed_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con líneas corregidas no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_Hairline_OK.pdf"
    )


@app.post("/api/fix-output-intent/{job_id}")
def fix_output_intent_endpoint(job_id: str, icc_profile: Optional[str] = None):
    """
    Fase 2: Incrusta un OutputIntent estándar (FOGRA39 / ISO Coated v2) para certificar la condición de impresión.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_icc_fixed.pdf"
    # Copiar source_pdf a output_path para no pisar el anterior
    import shutil
    copy_pdf(source_pdf, output_path)

    # Determinar el perfil según el perfil del trabajo si no se especificó
    target_icc = icc_profile or "ISOcoated_v2_eci.icc"
    profile_id = job_meta.get("profile_id", "OFFSET_300")
    if not icc_profile:
        if profile_id == "DIGITAL_200":
            target_icc = "PSOcoated_v3.icc" if (ICC_DIR / "PSOcoated_v3.icc").exists() else "ISOcoated_v2_300_bas.icc"
        elif profile_id in ("SCREEN_RGB", "PANTALLA_RGB"):
            target_icc = "sRGB2014.icc"
        else:
            target_icc = "ISOcoated_v2_eci.icc" if (ICC_DIR / "ISOcoated_v2_eci.icc").exists() else "ISOcoated_v2_300_bas.icc"

    try:
        applied_info = apply_icc_to_pdf(output_path, target_icc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not applied_info:
        raise HTTPException(status_code=500, detail="Fallo al incrustar el OutputIntent en el PDF.")

    # Guardar ruta acumulada
    job_data["job_meta"]["icc_fixed_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "icc_fixed")
    job_data["job_meta"]["applied_icc_info"] = applied_info

    # Actualizar información del ICC detectado en el job_summary
    job_summary = job_data.setdefault("job_summary", {})
    job_summary["icc_detected"] = applied_info

    # Limpiar incidencias de DOCUMENT_OUTPUT_ICC
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") != "DOCUMENT_OUTPUT_ICC"
    ]

    # Recalcular dictamen técnico
    all_findings = job_data.get("findings", [])
    errs = sum(1 for f in all_findings if f.get("severity") == "ERROR")
    warns = sum(1 for f in all_findings if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar certificado
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[fix-output-intent] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "applied_icc": applied_info,
        "download_url": f"/api/download-icc/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
        "icc_detected": applied_info
    }


@app.get("/api/download-icc/{job_id}")
def download_icc_pdf(job_id: str):
    """Descarga el PDF con OutputIntent formal incrustado."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("icc_fixed_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con OutputIntent no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_ICC_OK.pdf"
    )


@app.post("/api/fix-bleed-geometry/{job_id}")
def fix_bleed_geometry_endpoint(job_id: str, bleed_mm: float = 3.0):
    """
    Fase 2: Ajuste de Cajas (TrimBox y BleedBox) y normalización de sangrado a 3 mm.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_bleed_fixed.pdf"
    result = fix_pdf_boxes_and_bleed(source_pdf, str(output_path), target_bleed_mm=bleed_mm)

    job_meta["has_bleed_fixed"] = True
    job_meta["bleed_fixed_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "bleed_fixed")

    # Actualizar resumen de trabajo
    job_summary = job_data.setdefault("job_summary", {})
    job_summary["bleed_status"] = "PASS"
    job_summary["bleed_detected_mm"] = bleed_mm

    # Filtrar incidencias de BLEED_GEOMETRY_3MM y sangrado
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") != "BLEED_GEOMETRY_3MM"
        and "sangrado" not in f.get("title", "").lower()
    ]

    # Recalcular resultado técnico
    errs = sum(1 for f in job_data["findings"] if f.get("severity") == "ERROR")
    warns = sum(1 for f in job_data["findings"] if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar certificado técnico PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[fix-bleed-geometry] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "pages_modified": result.get("pages_modified", 0),
        "bleed_mm": result.get("bleed_mm", 3.0),
        "details": result.get("details", []),
        "download_url": f"/api/download-bleed/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"]
    }


@app.get("/api/download-bleed/{job_id}")
def download_bleed_pdf(job_id: str):
    """Descarga el PDF con TrimBox y BleedBox a 3 mm ajustados."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("bleed_fixed_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con cajas corregidas no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_Bleed_OK.pdf"
    )


@app.post("/api/outline-fonts/{job_id}")
def outline_fonts_endpoint(job_id: str, pages: Optional[str] = None):
    """
    Fase 2: Traza tipografías no incrustadas a curvas vectoriales directas (<path>).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    target_page_list = None
    if pages:
        try:
            target_page_list = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
        except Exception:
            target_page_list = None

    output_path = JOBS_DIR / f"{safe_id}_fonts_outlined.pdf"
    try:
        result = outline_fonts_in_pdf(source_pdf, str(output_path), target_pages=target_page_list)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_meta["has_fonts_outlined"] = True
    job_meta["fonts_outlined_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "fonts_outlined")

    # Filtrar incidencias de fuentes no incrustadas
    if target_page_list:
        job_data["findings"] = [
            f for f in job_data.get("findings", [])
            if not (f.get("rule_id") == "USED_FONTS_EMBEDDED" and f.get("page") in target_page_list)
        ]
    else:
        job_data["findings"] = [
            f for f in job_data.get("findings", [])
            if f.get("rule_id") != "USED_FONTS_EMBEDDED"
            and "no incrustada" not in f.get("title", "").lower()
        ]

    # Recalcular dictamen técnico
    errs = sum(1 for f in job_data["findings"] if f.get("severity") == "ERROR")
    warns = sum(1 for f in job_data["findings"] if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar certificado técnico PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[outline-fonts] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "pages_vectorized": result.get("pages_vectorized", 0),
        "total_pages": result.get("total_pages", 0),
        "download_url": f"/api/download-outlined-fonts/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"]
    }


@app.get("/api/download-outlined-fonts/{job_id}")
def download_outlined_fonts_pdf(job_id: str):
    """Descarga el PDF con textos trazados a curvas."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("fonts_outlined_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con tipografías trazadas no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_Curvas_OK.pdf"
    )


@app.post("/api/generate-mirror-bleed/{job_id}")
def generate_mirror_bleed_endpoint(job_id: str, bleed_mm: float = 3.0):
    """
    Fase 3: Genera sangrado sintético por reflejo de 3.0 mm en los bordes de la página.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_mirror_bleed.pdf"
    result = generate_mirror_bleed(source_pdf, str(output_path), bleed_mm=bleed_mm)

    job_meta["has_mirror_bleed"] = True
    job_meta["has_bleed_fixed"] = True
    job_meta["mirror_bleed_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "mirror_bleed")

    # Actualizar resumen de trabajo
    job_summary = job_data.setdefault("job_summary", {})
    job_summary["bleed_status"] = "PASS"
    job_summary["bleed_detected_mm"] = bleed_mm

    # Filtrar incidencias de BLEED_GEOMETRY_3MM y sangrado
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") != "BLEED_GEOMETRY_3MM"
        and "sangrado" not in f.get("title", "").lower()
    ]

    # Recalcular resultado técnico
    errs = sum(1 for f in job_data["findings"] if f.get("severity") == "ERROR")
    warns = sum(1 for f in job_data["findings"] if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    if errs > 0:
        tech["status"] = "FAIL"
        tech["label"] = "NO CUMPLE"
    elif warns > 0:
        tech["status"] = "PASS_WITH_WARNINGS"
        tech["label"] = "CUMPLE CON AVISOS"
    else:
        tech["status"] = "PASS"
        tech["label"] = "CUMPLE"

    # Regenerar certificado técnico PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[generate-mirror-bleed] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "pages_processed": result.get("pages_processed", 0),
        "bleed_mm": result.get("bleed_mm", 3.0),
        "download_url": f"/api/download-mirror-bleed/{safe_id}",
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"]
    }


@app.get("/api/download-mirror-bleed/{job_id}")
def download_mirror_bleed_pdf(job_id: str):
    """Descarga el PDF con sangrado sintético por reflejo generado.
    Si no existe todavía, lo genera al vuelo desde el PDF de origen."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    fixed_path = job_meta.get("mirror_bleed_pdf_path")

    # Si no existe en el JSON o el archivo fue eliminado (Render reinicio), generar al vuelo
    if not fixed_path or not Path(fixed_path).exists():
        source_pdf = get_latest_cumulative_pdf(job_meta)
        if not source_pdf or not Path(source_pdf).exists():
            raise HTTPException(
                status_code=404,
                detail="PDF con sangrado por reflejo no encontrado y no se pudo regenerar."
            )
        output_path = JOBS_DIR / f"{safe_id}_mirror_bleed.pdf"
        generate_mirror_bleed(source_pdf, str(output_path), bleed_mm=3.0)
        job_meta["mirror_bleed_pdf_path"] = str(output_path)
        register_cumulative_fix(job_data, output_path, "mirror_bleed")
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)
        fixed_path = str(output_path)

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_Sangre_Reflejo.pdf"
    )


@app.post("/api/add-printer-marks/{job_id}")
def add_printer_marks_endpoint(
    job_id: str,
    request: Request,
    slug_margin_mm: float = 10.0,
    bleed_mm: float = 3.0
):
    """
    Fase 3: Añade marcas de imprenta profesionales (corte, registro, tiras CMYK e información).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    filename = job_meta.get("filename", "documento.pdf")
    output_path = JOBS_DIR / f"{safe_id}_printer_marks.pdf"
    result = add_printer_marks_to_pdf(
        source_pdf,
        str(output_path),
        slug_margin_mm=slug_margin_mm,
        bleed_mm=bleed_mm,
        job_filename=filename,
        job_id=safe_id,
        base_url=str(request.base_url)
    )

    job_meta["has_printer_marks"] = True
    job_meta["printer_marks_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "printer_marks")

    # Regenerar certificado técnico PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[add-printer-marks] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "pages_processed": result.get("pages_processed", 0),
        "slug_margin_mm": slug_margin_mm,
        "bleed_mm": bleed_mm,
        "download_url": f"/api/download-printer-marks/{safe_id}",
        "findings": job_data.get("findings", []),
        "triple_result": job_data.get("triple_result", {})
    }


@app.get("/api/download-printer-marks/{job_id}")
def download_printer_marks_pdf(job_id: str):
    """Descarga el PDF con marcas de imprenta profesionales añadidas."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("printer_marks_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con marcas de imprenta no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_Marcas.pdf"
    )


@app.post("/api/limit-tac/{job_id}")
def limit_tac_endpoint(
    job_id: str,
    max_tac: Optional[float] = None
):
    """
    Limita las imágenes CMYK al máximo del perfil o al indicado y reanaliza el PDF.
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    if max_tac is None:
        max_tac = get_profile_by_id(job_meta.get("profile_id", "OFFSET_300"))["max_tac"]
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_tac_limited.pdf"
    try:
        result = limit_pdf_tac(source_pdf, str(output_path), max_tac_percent=max_tac)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result.get("success"):
        raise HTTPException(status_code=422, detail="No se pudo limitar la tinta de todas las imagenes.")

    job_meta["has_tac_limited"] = True
    job_meta["tac_limited_max_percent"] = max_tac
    job_meta["tac_limited_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "tac_limited")

    # Regenerar certificado técnico PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[limit-tac] Error regenerando certificado: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "job_id": safe_id,
        "images_inspected": result.get("images_inspected", 0),
        "images_clamped": result.get("images_clamped", 0),
        "peak_tac_before": result.get("peak_tac_before", 0.0),
        "target_max_tac": max_tac,
        "download_url": f"/api/download-tac/{safe_id}",
        "findings": job_data.get("findings", []),
        "triple_result": job_data.get("triple_result", {})
    }


@app.get("/api/download-tac/{job_id}")
def download_tac_pdf(job_id: str):
    """Descarga el PDF tratado con el límite de imágenes CMYK elegido."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("tac_limited_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF con TAC limitado no encontrado."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    limit = job_data.get("job_meta", {}).get("tac_limited_max_percent")
    suffix = f"TAC{float(limit):g}" if limit is not None else "TAC_limitado"
    return FileResponse(
        path=fixed_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_{clean_name}_{suffix}.pdf"
    )


@app.get("/api/download-overprint/{job_id}")
def download_overprint_pdf(job_id: str):
    """Descarga el PDF con sobreimpresión corregida automáticamente."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    fixed_path = job_data.get("job_meta", {}).get("overprint_fixed_pdf_path")
    if not fixed_path or not Path(fixed_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF corregido no encontrado. Aplica la corrección primero."
        )

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")

    return FileResponse(
        path=str(fixed_path),
        media_type="application/pdf",
        filename=f"IntelliPrint_Overprint_{clean_name}.pdf",
    )


# ---------------------------------------------------------------------------
# Sobreimpresión de Tintas Técnicas (Barnices, Troqueles, UV)
# ---------------------------------------------------------------------------

@app.post("/api/apply-varnish-overprint/{job_id}")
def apply_varnish_overprint_endpoint(job_id: str, target_spots: Optional[str] = Form(None)):
    """
    Aplica sobreimpresión obligatoria (/IP_OP) a las capas técnicas (barnices UV,
    brillos, troqueles) que se encuentren en calado (knockout).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    source_pdf = get_latest_cumulative_pdf(job_meta)
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(status_code=400, detail="PDF de origen no encontrado en el servidor.")

    output_path = JOBS_DIR / f"{safe_id}_overprint_fixed.pdf"

    target_list = None
    if target_spots:
        target_list = [s.strip() for s in target_spots.split(",") if s.strip()]

    result = apply_overprint_to_technical_inks(
        pdf_path=source_pdf,
        output_path=output_path,
        target_spots=target_list
    )

    if not result.get("success"):
        errors = result.get("errors", [])
        raise HTTPException(status_code=500, detail=f"Fallo al sobreimprimir tintas técnicas: {'; '.join(errors)}")

    # Guardar ruta en job_meta de forma acumulativa
    job_data["job_meta"]["varnish_overprint_pdf_path"] = str(output_path)
    register_cumulative_fix(job_data, output_path, "varnish_overprint")

    # Actualizar estadísticas de sobreimpresión
    stats = job_data.get("job_summary", {}).get("overprint_stats", {})
    ko_count = stats.get("varnish_knockout", 0)
    stats["varnish_overprint"] = stats.get("varnish_overprint", 0) + ko_count
    stats["varnish_knockout"] = 0

    # Eliminar incidencias de calado de barniz de findings
    job_data["findings"] = [
        f for f in job_data.get("findings", [])
        if f.get("rule_id") != "VARNISH_KNOCKOUT" and "barniz" not in f.get("title", "").lower()
    ]

    # Recalcular resultado técnico general (puede pasar de FAIL a PASS/PASS_WITH_WARNINGS)
    all_findings = job_data.get("findings", [])
    errs = sum(1 for f in all_findings if f.get("severity") == "ERROR")
    warns = sum(1 for f in all_findings if f.get("severity") == "WARNING")
    tech = job_data.setdefault("triple_result", {}).setdefault("technical", {})
    tech["errors_count"] = errs
    tech["warnings_count"] = warns
    tech["status"] = "FAIL" if errs > 0 else ("PASS_WITH_WARNINGS" if warns > 0 else "PASS")
    tech["label"] = "NO CUMPLE" if errs > 0 else ("CUMPLE CON AVISOS" if warns > 0 else "CUMPLE")

    # Regenerar el certificado oficial en PDF
    refresh_job_analysis(job_data, get_latest_cumulative_pdf(job_meta))
    cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
    try:
        generate_preflight_certificate_pdf(job_data, cert_path)
    except Exception as e:
        print(f"[apply-varnish-overprint] Aviso: no se pudo regenerar certificado PDF: {e}")

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "report": job_data,
        "status": "success",
        "pages_modified": result.get("pages_modified", 0),
        "ops_fixed": result.get("ops_fixed", 0),
        "technical_spots_fixed": result.get("technical_spots_fixed", []),
        "overprint_stats": stats,
        "findings": job_data["findings"],
        "triple_result": job_data["triple_result"],
        "download_url": f"/api/download-overprint/{safe_id}",
    }


@app.get("/api/spot-colors/{job_id}")
def get_job_spot_colors(job_id: str):
    """Devuelve las tintas planas detectadas en el documento del trabajo."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    spots = job_data.get("job_summary", {}).get("spot_colors")
    if spots is not None:
        return {"spot_colors": spots}

    target_pdf = job_data.get("job_meta", {}).get("pdf_path")
    if not target_pdf or not Path(target_pdf).exists():
        return {"spot_colors": []}

    try:
        import pikepdf
        from preflight_engine import extract_pdf_spot_colors
        pdf = pikepdf.open(str(target_pdf))
        spots = extract_pdf_spot_colors(pdf)
        pdf.close()
        job_data.setdefault("job_summary", {})["spot_colors"] = spots
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)
    except Exception:
        spots = []

    return {"spot_colors": spots}


@app.get("/api/separations/{job_id}")
def get_page_separation(
    job_id: str,
    page: int = 1,
    c: bool = True,
    m: bool = True,
    y: bool = True,
    k: bool = True,
    disabled_spots: Optional[str] = None,
    mode: str = "color",
    dpi: int = Query(110, ge=36, le=MAX_PREVIEW_DPI),
    use_converted: bool = True,
    icc: Optional[str] = None,
    simulate_paper: bool = False,
    paper_type: str = "coated",
    simulate_black: bool = True,
):
    """
    Renderiza la simulación de separaciones de color CMYK para la página seleccionada.
    Permite activar/desactivar individualmente planchas de Cian, Magenta, Amarillo y Negro
    para verificar visualmente sobreimpresiones y calados como en Adobe Acrobat Output Preview.
    Aplica el perfil de simulación ICC escogido y soporta Soft Proofing (simulación de papel y tinta).
    """
    job_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(job_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = None
    if use_converted:
        target_pdf = get_latest_cumulative_pdf(job_meta)
    elif job_meta.get("pdf_path") and os.path.exists(job_meta.get("pdf_path")):
        target_pdf = job_meta.get("pdf_path")

    if not target_pdf:
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado en el servidor.")

    temp_extracted_icc = None
    icc_cmyk_path = None

    # 1. Si se especificó un perfil en la llamada al endpoint (distinto de 'default'/'job_initial')
    if icc and icc not in ("default", "job_initial"):
        safe_name = Path(icc).name
        custom_path = BASE_DIR / "icc_profiles" / safe_name
        if custom_path.exists():
            icc_cmyk_path = str(custom_path)

    # 2. Si no se especificó, usar la selección realizada en la página inicial
    if not icc_cmyk_path:
        icc_option = job_data.get("job_meta", {}).get("icc_option", "preserve")
        selected_icc = job_data.get("job_meta", {}).get("selected_icc")

        if icc_option == "custom_selection" and selected_icc:
            safe_name = Path(selected_icc).name
            custom_path = BASE_DIR / "icc_profiles" / safe_name
            if custom_path.exists():
                icc_cmyk_path = str(custom_path)

    # 3. Si la opción era conservar perfil o no se resolvió arriba, extraer el ICC embebido del PDF
    if not icc_cmyk_path:
        temp_extracted_icc = extract_embedded_icc_to_tempfile(target_pdf)
        if temp_extracted_icc:
            icc_cmyk_path = temp_extracted_icc
        else:
            # Fallback inteligente según el OutputIntent detectado
            orig_info = (
                job_data.get("job_summary", {}).get("original_icc_detected", {})
                or job_data.get("job_summary", {}).get("icc_detected", {})
            )
            orig_id = str(orig_info.get("identifier", "")).lower()
            orig_desc = str(orig_info.get("friendly_description", "")).lower()
            combined = orig_id + " " + orig_desc
            if "fogra52" in combined or "uncoated" in combined:
                icc_cmyk_path = str(BASE_DIR / "icc_profiles" / "PSOuncoated_v3_FOGRA52.icc")
            elif "fogra51" in combined or "psocoated" in combined:
                icc_cmyk_path = str(BASE_DIR / "icc_profiles" / "PSOcoated_v3.icc")
            elif "eci" in combined:
                icc_cmyk_path = str(BASE_DIR / "icc_profiles" / "ISOcoated_v2_eci.icc")
            else:
                icc_cmyk_path = str(BASE_DIR / "icc_profiles" / "ISOcoated_v2_300_bas.icc")

    disabled_spots_list = None
    if disabled_spots:
        disabled_spots_list = [s.strip() for s in disabled_spots.split(",") if s.strip()]

    try:
        img_bytes = render_page_separation(
            pdf_path=target_pdf,
            page_index=max(0, page - 1),
            show_c=c,
            show_m=m,
            show_y=y,
            show_k=k,
            disabled_spots=disabled_spots_list,
            view_mode=mode,
            dpi=min(200, max(60, dpi)),
            icc_cmyk_path=icc_cmyk_path,
            simulate_paper=simulate_paper,
            paper_type=paper_type,
            simulate_black_ink=simulate_black,
        )
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renderizando separación: {e}")
    finally:
        if temp_extracted_icc and os.path.exists(temp_extracted_icc):
            try:
                os.unlink(temp_extracted_icc)
            except Exception:
                pass


def _load_issue_viewer_job(job_id):
    safe_id = safe_job_id(job_id)
    manifest = get_job_json_path(safe_id)
    try:
        manifest = contained_job_path(JOBS_DIR, manifest.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Ruta del trabajo no válida.") from exc
    if not manifest.is_file():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    try:
        with open(manifest, encoding="utf-8") as source:
            job_data = json.load(source)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="No se pudo leer el análisis del trabajo.") from exc
    target = get_latest_cumulative_pdf(job_data.get("job_meta", {}))
    if not target:
        raise HTTPException(status_code=404, detail="PDF actual no encontrado.")
    target = Path(target).resolve()
    roots = (UPLOAD_DIR, JOBS_DIR, APPROVED_DIR, REJECTED_DIR, DIDACTIC_SCENARIOS_DIR)
    if not any(target.is_relative_to(Path(root).resolve()) for root in roots):
        raise HTTPException(status_code=422, detail="El PDF queda fuera de las carpetas del trabajo.")
    return safe_id, job_data, target


@app.get("/api/issue-viewer/{job_id}")
def inspect_issue_endpoint(
    job_id: str,
    finding_index: int = Query(0, ge=0),
    sha256: Optional[str] = Query(None, pattern=r"^[a-fA-F0-9]{64}$"),
):
    """Locate a current finding on the exact PDF version used for its analysis."""
    safe_id, job_data, target = _load_issue_viewer_job(job_id)
    try:
        data = inspect_finding(target, job_data, finding_index, sha256)
    except StaleIssueAnalysis as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail="No se pudo localizar la incidencia en este PDF.") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="PDF actual no encontrado.") from exc
    data["job_id"] = safe_id
    data["render_url"] = (f"/api/issue-viewer/{safe_id}/render?page={data['page']}"
                          f"&sha256={data['sha256']}&dpi=130")
    return JSONResponse(data, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.get("/api/issue-viewer/{job_id}/render")
def render_issue_page_endpoint(
    job_id: str,
    page: int = Query(1, ge=1),
    sha256: str = Query(..., pattern=r"^[a-fA-F0-9]{64}$"),
    dpi: int = Query(130, ge=36, le=MAX_PREVIEW_DPI),
):
    """Render a bounded page; reject stale overlays instead of showing another PDF."""
    _, job_data, target = _load_issue_viewer_job(job_id)
    try:
        rendered = render_issue_page(target, job_data, page, sha256, dpi)
    except StaleIssueAnalysis as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail="No se pudo previsualizar esta página.") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="PDF actual no encontrado.") from exc
    return Response(rendered, media_type="image/png", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "X-PDF-SHA256": sha256.lower(),
    })


@app.get("/api/render-comparison/{job_id}")
def render_comparison_endpoint(
    job_id: str,
    page: int = 1,
    side: str = "after",
    dpi: int = Query(130, ge=36, le=MAX_PREVIEW_DPI)
):
    """
    Fase 3: Renderiza la vista 'before' (original) o 'after' (corregido)
    para el comparador interactivo con cortinilla (Split View Slider).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    orig_path = job_meta.get("pdf_path")
    fixed_path = get_latest_cumulative_pdf(job_meta) or orig_path

    target_path = orig_path if side == "before" else fixed_path
    if not target_path or not Path(target_path).exists():
        target_path = orig_path

    if not target_path or not Path(target_path).exists():
        raise HTTPException(status_code=404, detail="PDF no encontrado.")

    has_fixed = bool(
        fixed_path
        and Path(fixed_path).exists()
        and orig_path
        and Path(orig_path).exists()
        and Path(fixed_path).resolve() != Path(orig_path).resolve()
    )

    try:
        doc = pymupdf.open(target_path)
        p_idx = max(0, min(len(doc) - 1, page - 1))
        page_obj = doc[p_idx]
        pix = page_obj.get_pixmap(dpi=bounded_render_dpi(page_obj.rect, dpi))
        img_bytes = pix.tobytes("jpeg")
        del pix
        doc.close()
        release_pdf_memory()
        return Response(
            content=img_bytes,
            media_type="image/jpeg",
            headers={"X-Has-Fixes": "1" if has_fixed else "0"}
        )
    except Exception as e:
        release_pdf_memory()
        raise HTTPException(status_code=500, detail=f"Error renderizando página para comparación: {e}")


@app.post("/api/batch-fix/{job_id}")
def batch_fix_endpoint(
    job_id: str,
    trapping: bool = True,
    hairlines: bool = True,
    icc: bool = True,
    geometry: bool = True,
    mirror_bleed: bool = True,
    cmyk_images: bool = True,
    spot_colors: bool = False,
    fonts: bool = True,
    tac: bool = True,
    printer_marks: bool = True
):
    """
    Fase 3: Lote de Acciones en 1 Clic (One-Click Batch Fixer).
    Ejecuta secuencial y acumulativamente las correcciones estándar seleccionadas.
    """
    try:
        safe_id = safe_job_id(job_id)
        job_json_path = get_job_json_path(safe_id)
        if not job_json_path.exists():
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

        with open(job_json_path, "r", encoding="utf-8") as f:
            job_data = json.load(f)

        job_meta = job_data.get("job_meta", {}) or {}
        profile = get_profile_by_id(job_meta.get("profile_id", "OFFSET_300"))
        source_pdf = get_latest_cumulative_pdf(job_meta)
        if not source_pdf or not Path(source_pdf).exists():
            raise HTTPException(status_code=400, detail="PDF original no encontrado.")

        final_batch_path = JOBS_DIR / f"{safe_id}_batch_fixed.pdf"
        current_in = Path(source_pdf)
        steps_applied = []
        temp_files = []

        try:
            # 1. Trapping & Overprint Killer
            if trapping:
                step1_out = JOBS_DIR / f"{safe_id}_bstep1_trapping.pdf"
                temp_files.append(step1_out)
                w_out = JOBS_DIR / f"{safe_id}_bw_tmp.pdf"
                temp_files.append(w_out)
                w_res = fix_white_overprint(str(current_in), str(w_out))
                cur_trap_src = str(w_out) if (w_res.get("success") and w_res.get("objects_fixed", 0) > 0) else str(current_in)

                rb_out = JOBS_DIR / f"{safe_id}_brb_tmp.pdf"
                temp_files.append(rb_out)
                rb_res = fix_rich_black_small_text(cur_trap_src, str(rb_out))
                cur_trap_src2 = str(rb_out) if (rb_res.get("success") and rb_res.get("texts_fixed", 0) > 0) else cur_trap_src

                # Sobreimpresión de capas técnicas y barnices en calado
                varnish_out = JOBS_DIR / f"{safe_id}_bvarnish_tmp.pdf"
                temp_files.append(varnish_out)
                varnish_res = apply_overprint_to_technical_inks(cur_trap_src2, str(varnish_out))
                cur_trap_src3 = str(varnish_out) if (varnish_res.get("success") and varnish_res.get("ops_fixed", 0) > 0) else cur_trap_src2

                trap_res = apply_overprint_to_dark_text(cur_trap_src3, str(step1_out), dark_k_threshold=0.99)
                if trap_res.get("success") and step1_out.exists():
                    current_in = step1_out
                    steps_applied.append({
                        "action": "trapping",
                        "title": "Auto-Trapping y Sobreimpresión 100% K / Barnices",
                        "details": {
                            "text_overprint": trap_res,
                            "varnish_fixed": varnish_res.get("ops_fixed", 0) if varnish_res.get("success") else 0
                        }
                    })
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") not in ("WHITE_OVERPRINT", "RICH_BLACK_SMALL_TEXT", "BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100", "VARNISH_KNOCKOUT")
                        and "blanco" not in (f.get("title") or "").lower()
                        and "barniz" not in (f.get("title") or "").lower()
                        and not ("calado" in (f.get("title") or "").lower() or "knockout" in (f.get("title") or "").lower())
                    ]
                    job_summary = job_data.setdefault("job_summary", {}) or {}
                    if not isinstance(job_summary, dict):
                        job_summary = {}
                        job_data["job_summary"] = job_summary
                    stats = job_summary.setdefault("overprint_stats", {}) or {}
                    if not isinstance(stats, dict):
                        stats = {}
                        job_summary["overprint_stats"] = stats
                    stats["white_overprint"] = 0
                    stats["rich_black_small_text"] = 0
                    stats["black_100_overprint"] = stats.get("black_100_overprint", 0) + stats.get("black_100_knockout", 0)
                    stats["black_100_knockout"] = 0
                    stats["varnish_overprint"] = stats.get("varnish_overprint", 0) + stats.get("varnish_knockout", 0)
                    stats["varnish_knockout"] = 0
                release_pdf_memory()

            # 2. Corrector de Hairlines (< 0.25 pt)
            if hairlines:
                step2_out = JOBS_DIR / f"{safe_id}_bstep2_hairlines.pdf"
                temp_files.append(step2_out)
                hl_res = fix_hairlines(str(current_in), str(step2_out), hairline_threshold=profile["min_hairline_pt"], target_width=max(0.30, profile["min_hairline_pt"]))
                if hl_res.get("success") and step2_out.exists():
                    current_in = step2_out
                    steps_applied.append({
                        "action": "hairlines",
                        "title": "Engrosado de Filetes Finos (Hairlines)",
                        "details": hl_res
                    })
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") not in ("HAIRLINE_WIDTH", "HAIRLINE_STROKE")
                        and "hairline" not in (f.get("title") or "").lower()
                        and "línea fina" not in (f.get("title") or "").lower()
                    ]
                release_pdf_memory()

            # 3. Trazado de tipografías a curvas
            if fonts:
                font_error_pages = [
                    f.get("page") for f in job_data.get("findings", [])
                    if (f.get("rule_id") == "USED_FONTS_EMBEDDED"
                        or "no incrustada" in (f.get("title") or "").lower()
                        or "incrustada" in (f.get("title") or "").lower())
                    and f.get("page") is not None
                ]
                has_general_font_issue = any(
                    f.get("rule_id") == "USED_FONTS_EMBEDDED" or "no incrustada" in (f.get("title") or "").lower()
                    for f in job_data.get("findings", [])
                )

                # Omitir el trazado si no hay incidencias de fuentes.
                if not has_general_font_issue and not font_error_pages:
                    steps_applied.append({
                        "action": "fonts",
                        "title": "Tipografías Vectoriales (Fuentes 100% incrustadas y conformes)",
                        "details": {"status": "success", "pages_vectorized": 0}
                    })
                else:
                    step3_out = JOBS_DIR / f"{safe_id}_bstep3_fonts.pdf"
                    temp_files.append(step3_out)
                    target_pages = list(set(font_error_pages)) if font_error_pages else None
                    font_res = outline_fonts_in_pdf(str(current_in), str(step3_out), target_pages=target_pages)
                    if (font_res.get("success") or font_res.get("status") == "success") and step3_out.exists():
                        current_in = step3_out
                        steps_applied.append({
                            "action": "fonts",
                            "title": f"Tipografías Trazadas a Curvas ({font_res.get('pages_vectorized', 0)} págs)",
                            "details": font_res
                        })
                        job_data["findings"] = [
                            f for f in job_data.get("findings", [])
                            if f.get("rule_id") != "USED_FONTS_EMBEDDED"
                            and "incrustada" not in (f.get("title") or "").lower()
                            and "fuente" not in (f.get("title") or "").lower()
                        ]
                    release_pdf_memory()

            # 4. Normalización de Cajas de Página y Sangrado 3 mm
            if geometry:
                step4_out = JOBS_DIR / f"{safe_id}_bstep4_geometry.pdf"
                temp_files.append(step4_out)
                geom_res = fix_pdf_boxes_and_bleed(str(current_in), str(step4_out), target_bleed_mm=profile["min_bleed_mm"])
                if (geom_res.get("success") or geom_res.get("status") == "success") and step4_out.exists():
                    current_in = step4_out
                    steps_applied.append({
                        "action": "geometry",
                        "title": "Cajas ISO y Sangrado 3 mm",
                        "details": geom_res
                    })
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "BLEED_GEOMETRY_3MM"
                        and "sangrado" not in (f.get("title") or "").lower()
                        and "bleed" not in (f.get("title") or "").lower()
                    ]
                release_pdf_memory()

            # 4b. Sangrado Sintético por Reflejo perimetral de píxeles (Mirror Bleed)
            if mirror_bleed and profile["min_bleed_mm"] > 0:
                step_mb_out = JOBS_DIR / f"{safe_id}_bstep_mirrorbleed.pdf"
                temp_files.append(step_mb_out)
                mb_res = generate_mirror_bleed(str(current_in), str(step_mb_out), bleed_mm=profile["min_bleed_mm"])
                if mb_res.get("success") and step_mb_out.exists():
                    current_in = step_mb_out
                    steps_applied.append({
                        "action": "mirror_bleed",
                        "title": "Sangrado Sintético por Reflejo 3 mm (Mirror Bleed)",
                        "details": mb_res
                    })
                    job_summary = job_data.setdefault("job_summary", {}) or {}
                    if not isinstance(job_summary, dict):
                        job_summary = {}
                        job_data["job_summary"] = job_summary
                    job_summary["bleed_status"] = "PASS"
                    job_summary["bleed_detected_mm"] = 3.0
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "BLEED_GEOMETRY_3MM"
                        and "sangrado" not in (f.get("title") or "").lower()
                        and "bleed" not in (f.get("title") or "").lower()
                    ]
                release_pdf_memory()

            # 4c. Conversión de imágenes RGB a CMYK (ISO Coated v2 / FOGRA39)
            if cmyk_images and profile["color_family"] == "CMYK":
                step_cmyk_out = JOBS_DIR / f"{safe_id}_bstep_cmyk.pdf"
                temp_files.append(step_cmyk_out)
                dst_icc = ICC_DIR / "ISOcoated_v2_eci.icc"
                if not dst_icc.exists():
                    dst_icc = ICC_DIR / "ISOcoated_v2_300_bas.icc"

                cmyk_res = convert_rgb_images_to_cmyk(
                    pdf_path=str(current_in),
                    dst_icc_path=str(dst_icc),
                    output_path=str(step_cmyk_out)
                )
                if cmyk_res.get("success") and step_cmyk_out.exists():
                    current_in = step_cmyk_out
                    n_conv = cmyk_res.get("images_converted", 0)
                    title_txt = f"Conversión a CMYK ({n_conv} imágenes RGB convertidas)" if n_conv > 0 else "Espacio de Color CMYK (0 imágenes RGB)"
                    steps_applied.append({
                        "action": "cmyk_images",
                        "title": title_txt,
                        "details": cmyk_res
                    })
                    if n_conv > 0:
                        job_meta["has_cmyk_converted"] = True
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "SOURCE_COLOR_DIAGNOSTIC"
                        and "rgb" not in (f.get("title") or "").lower()
                        and "rgb" not in (f.get("message") or "").lower()
                    ]

            # 4d. Descomposición de Tintas Planas / Pantone a CMYK
            if spot_colors:
                step_spots_out = JOBS_DIR / f"{safe_id}_bstep_spots.pdf"
                temp_files.append(step_spots_out)
                spots_res = convert_spot_colors_to_cmyk(
                    pdf_path=str(current_in),
                    output_path=str(step_spots_out),
                    target_spots=None,
                    convert_technical=False
                )
                if spots_res.get("success") and step_spots_out.exists():
                    current_in = step_spots_out
                    n_spots = len(spots_res.get("spots_converted", []))
                    title_txt = f"Conversión de Tintas Planas a CMYK ({n_spots} tintas convertidas)" if n_spots > 0 else "Tintas Planas a CMYK (0 tintas comerciales)"
                    steps_applied.append({
                        "action": "spot_colors",
                        "title": title_txt,
                        "details": spots_res
                    })
                    if n_spots > 0:
                        job_meta["has_spot_converted"] = True
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "SPOT_COLOR_FOUND"
                        and not (("pantone" in (f.get("title") or "").lower() or "tinta plana" in (f.get("title") or "").lower()) and "barniz" not in (f.get("title") or "").lower() and "troquel" not in (f.get("title") or "").lower())
                    ]

            # 5. OutputIntent ICC
            if icc:
                step5_out = JOBS_DIR / f"{safe_id}_bstep5_icc.pdf"
                temp_files.append(step5_out)
                shutil.copyfile(str(current_in), str(step5_out))
                target_icc = "ISOcoated_v2_eci.icc" if (ICC_DIR / "ISOcoated_v2_eci.icc").exists() else "ISOcoated_v2_300_bas.icc"
                if profile["color_family"] == "RGB":
                    target_icc = "sRGB2014.icc"
                applied_info = apply_icc_to_pdf(step5_out, target_icc)
                if applied_info and step5_out.exists():
                    current_in = step5_out
                    steps_applied.append({
                        "action": "icc",
                        "title": "OutputIntent ICC ISO Coated v2 (FOGRA39)",
                        "details": applied_info
                    })
                    job_summary = job_data.setdefault("job_summary", {}) or {}
                    if not isinstance(job_summary, dict):
                        job_summary = {}
                        job_data["job_summary"] = job_summary
                    job_summary["icc_detected"] = applied_info
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "DOCUMENT_OUTPUT_ICC"
                        and "outputintent" not in (f.get("title") or "").lower()
                    ]

            # 6. Limitador de Cobertura Total de Tinta (TAC <= 300%)
            if tac and profile["color_family"] == "CMYK":
                step6_out = JOBS_DIR / f"{safe_id}_bstep6_tac.pdf"
                temp_files.append(step6_out)
                tac_res = limit_pdf_tac(str(current_in), str(step6_out), max_tac_percent=profile["max_tac"])
                if (tac_res.get("success") or tac_res.get("status") == "success") and step6_out.exists():
                    current_in = step6_out
                    steps_applied.append({
                        "action": "tac",
                        "title": "Limitación de Cobertura de Tinta (TAC 300%)",
                        "details": tac_res
                    })
                    job_data["findings"] = [
                        f for f in job_data.get("findings", [])
                        if f.get("rule_id") != "MAX_INK_COVERAGE"
                        and "cobertura" not in (f.get("title") or "").lower()
                        and "tac" not in (f.get("title") or "").lower()
                    ]

            # 7. Marcas de Imprenta (Opcional)
            if printer_marks and profile["color_family"] == "CMYK":
                step7_out = JOBS_DIR / f"{safe_id}_bstep7_marks.pdf"
                temp_files.append(step7_out)
                orig_filename = job_meta.get("filename", "documento.pdf")
                pm_res = add_printer_marks_to_pdf(str(current_in), str(step7_out), slug_margin_mm=10.0, bleed_mm=profile["min_bleed_mm"], job_filename=orig_filename)
                if pm_res.get("success") and step7_out.exists():
                    current_in = step7_out
                    steps_applied.append({
                        "action": "printer_marks",
                        "title": "Marcas de Imprenta y Registro (+10 mm)",
                        "details": pm_res
                    })

            # Copiar el resultado final acumulativo a final_batch_path
            if str(current_in) != str(final_batch_path):
                shutil.copyfile(str(current_in), str(final_batch_path))

        finally:
            for tmp in temp_files:
                if tmp.exists() and tmp != final_batch_path:
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
            release_pdf_memory()

        # Registrar en job_meta de manera acumulativa
        job_meta = job_data.setdefault("job_meta", {}) or {}
        job_meta["batch_fixed_pdf_path"] = str(final_batch_path)
        job_meta["batch_steps_applied"] = steps_applied
        register_cumulative_fix(job_data, final_batch_path, "batch_fixed")

        # Verify every rule against the final cumulative PDF.
        refresh_job_analysis(job_data, final_batch_path)
        all_findings = job_data["findings"]
        tech = job_data["triple_result"]["technical"]
        errs = tech["errors_count"]
        warns = tech["warnings_count"]
        tech["verdict"] = "RECHAZADO" if errs else ("CON OBSERVACIONES" if warns else "CORRECTO")
        cert_path = JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf"
        generate_preflight_certificate_pdf(job_data, cert_path)

        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

        pending_errors = [
            {
                "page": f.get("page"),
                "category": f.get("category", "General"),
                "title": f.get("title") or "Error crítico",
                "message": f.get("message") or ""
            }
            for f in all_findings if f.get("severity") == "ERROR"
        ]
        pending_warnings = [
            {
                "page": f.get("page"),
                "category": f.get("category", "Aviso"),
                "title": f.get("title") or "Advertencia",
                "message": f.get("message") or ""
            }
            for f in all_findings if f.get("severity") == "WARNING"
        ]

        return {
            "success": True,
            "message": f"Se aplicaron {len(steps_applied)} acciones de corrección en lote con éxito.",
            "steps_applied": steps_applied,
            "errors_count": errs,
            "warnings_count": warns,
            "pending_errors": pending_errors,
            "pending_warnings": pending_warnings,
            "verdict": tech["verdict"],
            "report": job_data,
            "download_url": f"/api/download-batch/{job_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[batch_fix_endpoint] ERROR: {err_msg}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "detail": f"Error al procesar el lote ({err_msg}). Revisa los logs o prueba con correcciones individuales.",
                "traceback": traceback.format_exc()
            }
        )


@app.get("/api/download-batch/{job_id}")
def download_batch_endpoint(job_id: str):
    """Descarga el PDF con las correcciones integrales del lote."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    batch_path = job_data.get("job_meta", {}).get("batch_fixed_pdf_path")
    if not batch_path or not Path(batch_path).exists():
        batch_path = job_data.get("job_meta", {}).get("last_fixed_pdf_path")

    if not batch_path or not Path(batch_path).exists():
        raise HTTPException(status_code=404, detail="PDF corregido en lote no encontrado.")

    orig_filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    stem = Path(orig_filename).stem
    download_filename = f"{stem}_lote_corregido.pdf"

    return FileResponse(
        path=batch_path,
        media_type="application/pdf",
        filename=download_filename
    )


# =============================================================================
# HISTORIAL DE VERSIONES, TIMELINE, DESHACER / REHACER Y COMPARACIÓN
# =============================================================================

@app.get("/api/history/{job_id}")
def get_job_history_endpoint(job_id: str):
    """Devuelve la línea temporal completa del trabajo (versiones inmutables)."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        return public_history(job_data, JOBS_DIR)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _navigate_history(job_id: str, operation: str, version_id: str = None):
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        selected = select_version(job_data, JOBS_DIR, version_id=version_id, operation=operation)
        new_pdf = version_path(job_data, JOBS_DIR, selected["id"])
    except (VersionHistoryError, VersionQuotaError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_meta = job_data.setdefault("job_meta", {})
    job_meta["last_fixed_pdf_path"] = str(new_pdf)
    current_sha256 = update_pdf_identity(job_data, new_pdf)

    # Identificación y protección de versión aprobada
    auth_sha = job_meta.get("authorized_sha256")
    if auth_sha and auth_sha == current_sha256:
        job_data.setdefault("triple_result", {}).setdefault("release", {})["status"] = "AUTHORIZED"
        operator = job_data["triple_result"]["release"].get("operator", "taller")
        job_data["triple_result"]["release"]["label"] = f"Autorizado por {operator}"
    else:
        clear_pdf_authorization(job_data)

    refresh_job_analysis(job_data, new_pdf)

    hist = public_history(job_data, JOBS_DIR)
    job_data["version_history_summary"] = hist

    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "active_version": selected,
        "report": job_data,
        "history": hist
    }


@app.post("/api/history/{job_id}/undo")
def undo_job_version_endpoint(job_id: str):
    """Deshace la última corrección y vuelve a la versión previa."""
    return _navigate_history(job_id, operation="undo")


@app.post("/api/history/{job_id}/redo")
def redo_job_version_endpoint(job_id: str):
    """Rehace la corrección deshecha."""
    return _navigate_history(job_id, operation="redo")


@app.post("/api/history/{job_id}/restore/{version_id}")
def restore_job_version_endpoint(job_id: str, version_id: str):
    """Restaura cualquier versión histórica del PDF y re-evalúa el perfil."""
    return _navigate_history(job_id, operation="restore", version_id=version_id)


@app.get("/api/history/{job_id}/compare")
def compare_job_versions_endpoint(job_id: str, version_a: str, version_b: str, page: int = 1):
    """Compara técnicamente dos versiones del trabajo (dimensiones, páginas, peso)."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        return compare_versions(job_data, JOBS_DIR, version_a, version_b, page_num=page)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/history/{job_id}/preview/{version_id}")
def preview_version_page_endpoint(job_id: str, version_id: str, page: int = 1):
    """Renderiza la página indicada de una versión específica a imagen JPEG."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        img_bytes = render_version_page_image(job_data, JOBS_DIR, version_id, page_num=page)
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/history/{job_id}/diff")
def diff_versions_endpoint(job_id: str, version_a: str, version_b: str, page: int = 1):
    """Renderiza el mapa de diferencias visuales entre dos versiones del trabajo."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        diff_bytes = render_version_diff_image(job_data, JOBS_DIR, version_a, version_b, page_num=page)
        return Response(content=diff_bytes, media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/history/{job_id}/download/{version_id}")
def download_version_pdf_endpoint(job_id: str, version_id: str):
    """Descarga el PDF inmutable correspondiente a una versión concreta."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    try:
        path = version_path(job_data, JOBS_DIR, version_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    orig_name = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    stem = Path(orig_name).stem
    return FileResponse(path=str(path), media_type="application/pdf", filename=f"{stem}_{version_id}.pdf")


@app.get("/api/download-approved/{job_id}")
def download_approved_pdf_endpoint(job_id: str):
    """Descarga la entrega oficial aprobada y protegida."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    history = job_data.get("version_history", {})
    approved_id = history.get("approved_version_id")
    if not approved_id:
        auth_sha = job_data.get("job_meta", {}).get("authorized_sha256")
        if auth_sha:
            for v in history.get("versions", []):
                if v.get("sha256") == auth_sha:
                    approved_id = v.get("id")
                    break
    if not approved_id:
        raise HTTPException(status_code=404, detail="No existe una entrega aprobada para este trabajo.")
    try:
        path = version_path(job_data, JOBS_DIR, approved_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    orig_name = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    stem = Path(orig_name).stem
    return FileResponse(path=str(path), media_type="application/pdf", filename=f"IntelliPrint_{stem}_APROBADO.pdf")


# =============================================================================
# IMPOSICIÓN DE PLIEGOS DE TALLER (STEP & REPEAT / BOOKLET SADDLE-STITCH)
# =============================================================================

@app.post("/api/imposition/calculate/{job_id}")
def calculate_imposition_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """Calcula el plan geométrico de imposición y aprovechamiento de pliego."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF de origen no encontrado.")

    options = imposition_options(body)
    sheet_size = options["sheet_size"]
    orientation = options["orientation"]
    mode = options["mode"]
    gap_mm = options["gap_mm"]
    gap_x_mm = options["gap_x_mm"]
    gap_y_mm = options["gap_y_mm"]
    bleed_mm = options["bleed_mm"]
    sheet_margin_mm = options["sheet_margin_mm"]

    try:
        plan = calculate_imposition_plan(
            pdf_path=target_pdf,
            sheet_size=sheet_size,
            orientation=orientation,
            mode=mode,
            gap_mm=gap_mm,
            bleed_mm=bleed_mm,
            sheet_margin_mm=sheet_margin_mm,
            gap_x_mm=gap_x_mm,
            gap_y_mm=gap_y_mm,
        )
        return plan
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculando imposición: {e}")


@app.post("/api/imposition/generate/{job_id}")
def generate_imposition_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """Genera el pliego de imposición montado en formato PDF de alta resolución."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF de origen no encontrado.")

    options = imposition_options(body)
    sheet_size = options["sheet_size"]
    orientation = options["orientation"]
    mode = options["mode"]
    gap_mm = options["gap_mm"]
    gap_x_mm = options["gap_x_mm"]
    gap_y_mm = options["gap_y_mm"]
    bleed_mm = options["bleed_mm"]
    sheet_margin_mm = options["sheet_margin_mm"]
    add_marks = bool(body.get("add_marks", True))
    add_reg = bool(body.get("add_reg_crosses", True))
    add_color = bool(body.get("add_color_bar", True))
    add_slug = bool(body.get("add_slug", True))

    output_pdf = job_output_path(f"{safe_id}_pliego_imposicion_{sheet_size.lower()}.pdf")

    try:
        result = generate_imposed_pdf(
            pdf_path=target_pdf,
            output_path=output_pdf,
            sheet_size=sheet_size,
            orientation=orientation,
            mode=mode,
            gap_mm=gap_mm,
            bleed_mm=bleed_mm,
            sheet_margin_mm=sheet_margin_mm,
            add_marks=add_marks,
            add_reg_crosses=add_reg,
            add_color_bar=add_color,
            add_slug=add_slug,
            job_id=safe_id,
            base_url=str(request.base_url),
            gap_x_mm=gap_x_mm,
            gap_y_mm=gap_y_mm,
        )

        job_meta["imposed_pdf_path"] = str(output_pdf)
        job_meta["imposition_source_sha256"] = job_meta.get("current_sha256") or job_meta.get("sha256")
        job_meta["last_imposition_plan"] = result
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

        result["download_url"] = f"/api/imposition/download/{job_id}"
        result["preview_url"] = f"/api/imposition/preview/{job_id}?sheet_size={sheet_size}&orientation={orientation}&mode={mode}&gap_mm={gap_mm}&gap_x_mm={gap_x_mm}&gap_y_mm={gap_y_mm}&t={int(time.time())}"
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando pliego de imposición: {e}")


@app.get("/api/imposition/download/{job_id}")
def download_imposition_endpoint(job_id: str):
    """Descarga el pliego de imposición PDF generado."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    imposed_path = job_data.get("job_meta", {}).get("imposed_pdf_path")
    if (not imposed_path or not Path(imposed_path).exists()
            or not job_data["job_meta"].get("imposition_source_sha256")
            or job_data["job_meta"].get("imposition_source_sha256") != (job_data["job_meta"].get("current_sha256") or job_data["job_meta"].get("sha256"))):
        raise HTTPException(status_code=404, detail="Pliego de imposición no encontrado. Genéralo primero.")

    orig_filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    stem = Path(orig_filename).stem
    sheet_size = job_data.get("job_meta", {}).get("last_imposition_plan", {}).get("sheet_size", "SRA3")
    download_filename = f"Pliego_Imposicion_{sheet_size}_{stem}.pdf"

    return FileResponse(
        path=imposed_path,
        media_type="application/pdf",
        filename=download_filename
    )


@app.get("/api/imposition/preview/{job_id}")
def preview_imposition_endpoint(
    job_id: str,
    sheet_size: str = "SRA3",
    orientation: str = "auto",
    mode: str = "step_and_repeat",
    gap_mm: float = 4.0,
    gap_x_mm: Optional[float] = None,
    gap_y_mm: Optional[float] = None,
    bleed_mm: float = 2.0,
    sheet_margin_mm: float = 10.0,
    dpi: int = Query(80, ge=36, le=MAX_PREVIEW_DPI)
):
    """Renderiza una imagen JPEG de previsualización del pliego impuesto."""
    sheet_size = checked_sheet_size(sheet_size)
    imposition_options(dict(sheet_size=sheet_size, orientation=orientation, mode=mode,
                            gap_mm=gap_mm, gap_x_mm=gap_x_mm if gap_x_mm is not None else gap_mm,
                            gap_y_mm=gap_y_mm if gap_y_mm is not None else gap_mm,
                            bleed_mm=bleed_mm, sheet_margin_mm=sheet_margin_mm))
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    try:
        img_bytes = render_imposition_preview_image(
            pdf_path=target_pdf,
            sheet_size=sheet_size,
            orientation=orientation,
            mode=mode,
            gap_mm=gap_mm,
            bleed_mm=bleed_mm,
            sheet_margin_mm=sheet_margin_mm,
            dpi=dpi,
            gap_x_mm=gap_x_mm,
            gap_y_mm=gap_y_mm,
        )
        return Response(content=img_bytes, media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renderizando previsualización de imposición: {e}")


# =============================================================================
# ENDPOINTS: DATOS DE TALLER CIP3 / PPF (AJUSTE DE TINTEROS POR ZONAS)
# =============================================================================

@app.post("/api/cip3/calculate/{job_id}")
def calculate_cip3_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """
    Calcula la cobertura de tinta CMYK por franjas longitudinales (zonas de tintero)
    y precalcula los archivos de salida CIP3 (.ppf) y Ficha de Tinteros (PDF).
    """
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    job_dir = JOBS_DIR / safe_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        num_zones = int(body.get("num_zones", 32))
        run_length = int(body.get("run_length", 1000))
        if num_zones not in (16, 24, 32) or not 1 <= run_length <= 10_000_000:
            raise ValueError("Selecciona 16, 24 o 32 zonas y una tirada entre 1 y 10.000.000.")
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    paper_type = str(body.get("paper_type", "coated"))
    source = str(body.get("source", "auto"))

    # Determinar el PDF a analizar: Si se solicita el pliego de imposición y existe, se usa ese
    last_plan = job_meta.get("last_imposition_plan") or {}
    imposed_path = (job_meta.get("imposed_pdf_path") or last_plan.get("output_pdf_path")
                    or last_plan.get("imposed_pdf_path"))
    if not job_meta.get("imposition_source_sha256") or job_meta.get("imposition_source_sha256") != (job_meta.get("current_sha256") or job_meta.get("sha256")):
        imposed_path = None
    if source == "imposed" and not imposed_path:
        raise HTTPException(status_code=409, detail="Regenera la imposición para el PDF actual.")
    if source == "imposed" and imposed_path and Path(imposed_path).exists():
        target_pdf = imposed_path
        sheet_label = "Pliego_Imposicion"
    else:
        target_pdf = (
            imposed_path if (source == "auto" and imposed_path and Path(imposed_path).exists())
            else get_latest_cumulative_pdf(job_meta)
        )
        sheet_label = "Pliego_Imposicion" if (imposed_path and target_pdf == imposed_path) else "Pagina_Individual"

    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF objetivo no encontrado.")

    try:
        cip3_result = calculate_ink_zone_coverage(
            pdf_path=target_pdf,
            num_zones=num_zones,
            run_length=run_length,
            paper_type=paper_type
        )
        
        # Guardar archivo .ppf
        ppf_filename = f"CIP3_{safe_id}_{num_zones}Z.ppf"
        ppf_path = job_dir / ppf_filename
        generate_cip3_ppf(
            cip3_data=cip3_result,
            output_ppf_path=str(ppf_path),
            job_id=safe_id,
            job_title=f"IntelliPrint_Job_{safe_id[:8]}",
            pdf_path=target_pdf,
        )
        
        # Guardar Ficha PDF para el maquinista
        sheet_pdf_filename = f"Ficha_Tinteros_CIP3_{safe_id}.pdf"
        sheet_pdf_path = job_dir / sheet_pdf_filename
        generate_cip3_pdf_sheet(
            cip3_data=cip3_result,
            output_pdf_path=str(sheet_pdf_path),
            job_id=safe_id,
            job_title=f"IntelliPrint_Job_{safe_id[:8]}"
        )
        
        cip3_result["source_used"] = sheet_label
        cip3_result["download_ppf_url"] = f"/api/cip3/download/ppf/{safe_id}?num_zones={num_zones}&run_length={run_length}&paper_type={paper_type}"
        cip3_result["download_pdf_url"] = f"/api/cip3/download/pdf/{safe_id}?num_zones={num_zones}&run_length={run_length}&paper_type={paper_type}"

        # Guardar en metadata de trabajo para consulta posterior
        job_meta["last_cip3_calculation"] = {
            "num_zones": num_zones,
            "run_length": run_length,
            "paper_type": paper_type,
            "ppf_path": str(ppf_path),
            "sheet_pdf_path": str(sheet_pdf_path),
            "source_pdf_path": str(target_pdf),
            "updated_at": datetime.now().isoformat()
        }
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

        return cip3_result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculando cobertura CIP3: {e}")


@app.get("/api/cip3/download/ppf/{job_id}")
def download_cip3_ppf_endpoint(
    job_id: str,
    num_zones: int = 32,
    run_length: int = 1000,
    paper_type: str = "coated"
):
    """Descarga el archivo estándar CIP3 / PPF v3.0 generado para el trabajo."""
    safe_id = safe_job_id(job_id)
    job_dir = JOBS_DIR / safe_id
    ppf_filename = f"CIP3_{safe_id}_{num_zones}Z.ppf"
    ppf_path = job_dir / ppf_filename

    # Regenerar con el origen y los parametros actuales, sin reutilizar datos antiguos.
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    job_meta = job_data.get("job_meta", {})
    imposed = job_meta.get("imposed_pdf_path")
    if not job_meta.get("imposition_source_sha256") or job_meta.get("imposition_source_sha256") != (job_meta.get("current_sha256") or job_meta.get("sha256")):
        imposed = None
    target_pdf = imposed or get_latest_cumulative_pdf(job_meta)
    if num_zones not in (16, 24, 32) or not 1 <= run_length <= 10_000_000:
        raise HTTPException(status_code=422, detail="Zonas o tirada no válidas.")

    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="PDF no disponible.")
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        cip3_res = calculate_ink_zone_coverage(target_pdf, num_zones=num_zones, run_length=run_length, paper_type=paper_type)
        generate_cip3_ppf(cip3_res, str(ppf_path), safe_id, pdf_path=target_pdf)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return FileResponse(
        path=str(ppf_path),
        media_type="application/octet-stream",
        filename=f"CIP3_{safe_id[:8].upper()}_{num_zones}Zonas.ppf"
    )


@app.get("/api/cip3/download/pdf/{job_id}")
def download_cip3_pdf_endpoint(
    job_id: str,
    num_zones: int = 32,
    run_length: int = 1000,
    paper_type: str = "coated"
):
    """Descarga la Ficha Técnica de Ajuste de Tinteros CIP3 en PDF A4."""
    safe_id = safe_job_id(job_id)
    job_dir = JOBS_DIR / safe_id
    sheet_pdf_filename = f"Ficha_Tinteros_CIP3_{safe_id}.pdf"
    sheet_pdf_path = job_dir / sheet_pdf_filename

    # Regenerar con el origen y los parametros actuales, sin reutilizar datos antiguos.
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    job_meta = job_data.get("job_meta", {})
    imposed = job_meta.get("imposed_pdf_path")
    if not job_meta.get("imposition_source_sha256") or job_meta.get("imposition_source_sha256") != (job_meta.get("current_sha256") or job_meta.get("sha256")):
        imposed = None
    target_pdf = imposed or get_latest_cumulative_pdf(job_meta)
    if num_zones not in (16, 24, 32) or not 1 <= run_length <= 10_000_000:
        raise HTTPException(status_code=422, detail="Zonas o tirada no válidas.")

    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="PDF no disponible.")
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        cip3_res = calculate_ink_zone_coverage(target_pdf, num_zones=num_zones, run_length=run_length, paper_type=paper_type)
        generate_cip3_pdf_sheet(cip3_res, str(sheet_pdf_path), safe_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return FileResponse(
        path=str(sheet_pdf_path),
        media_type="application/pdf",
        filename=f"Ficha_Tinteros_CIP3_{safe_id[:8].upper()}.pdf"
    )


# =============================================================================
# ENDPOINTS: INSPECTOR Y CORRECTOR DE CÓDIGOS DE BARRAS Y QR
# =============================================================================

@app.get("/api/barcodes/inspect/{job_id}")
def inspect_barcodes_endpoint(job_id: str):
    """Inspecciona códigos de barras (EAN-13, EAN-8, UPC) y QR en busca de Rich Black o falta de Quiet Zone."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    try:
        report = inspect_barcodes_in_pdf(target_pdf)
        digest = update_pdf_identity(job_data, target_pdf)
        job_meta["barcode_inspection"] = {"sha256": digest, "report": report}
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inspeccionando códigos de barras: {e}")


@app.post("/api/barcodes/fix/{job_id}")
def fix_barcodes_endpoint(job_id: str, request: Request, body: dict = Body(default={})):
    """Corrige códigos de barras y QR forzándolos a 100% K puro e inyectando reserva blanca opaca."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    barcode_ids = body.get("barcode_ids")  # Lista opcional de IDs a corregir
    force_pure_k = bool(body.get("force_pure_k", True))
    add_quiet_zone = bool(body.get("add_quiet_zone", True))
    quiet_zone_margin_mm = float(body.get("quiet_zone_margin_mm", 2.0))

    output_pdf = JOBS_DIR / f"{safe_id}_barcode_fixed.pdf"

    try:
        result = fix_barcodes_in_pdf(
            pdf_path=target_pdf,
            output_path=output_pdf,
            barcode_ids_to_fix=barcode_ids,
            force_pure_k=force_pure_k,
            add_quiet_zone=add_quiet_zone,
            quiet_zone_margin_mm=quiet_zone_margin_mm,
        )

        job_meta["barcode_fixed_pdf_path"] = str(output_pdf)
        register_cumulative_fix(job_data, output_pdf, "barcode_fixed")
        refresh_job_analysis(job_data, output_pdf)
        generate_preflight_certificate_pdf(job_data, JOBS_DIR / f"{safe_id}_ficha_tecnica.pdf")
        result["report"] = job_data
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error corrigiendo códigos de barras: {e}")


@app.get("/api/barcodes/preview/{job_id}")
def preview_barcode_endpoint(
    job_id: str,
    page_index: int = 0,
    x0: float = 0.0,
    y0: float = 0.0,
    x1: float = 100.0,
    y1: float = 100.0,
    dpi: int = Query(150, ge=36, le=MAX_PREVIEW_DPI)
):
    """Renderiza un recorte JPEG de previsualización de un código detectado."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    try:
        img_bytes = render_barcode_preview_image(
            pdf_path=target_pdf,
            page_index=page_index,
            rect_pt=[x0, y0, x1, y1],
            dpi=dpi
        )
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando previsualización de código: {e}")


# =============================================================================
# ENDPOINTS: PROCESAMIENTO POR LOTE (MULTI-PDF) Y CARPETA CALIENTE (HOT-FOLDER)
# =============================================================================

@app.post("/api/batch/upload")
def batch_upload_endpoint(
    files: List[UploadFile] = File(...),
    profile_id: str = Form("OFFSET_300"),
    icc_option: str = Form("preserve"),
    selected_icc: Optional[str] = Form(None)
):
    """Valida el lote completo y procesa un PDF cada vez con memoria acotada."""
    if not files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos.")

    # Validate the complete batch before reading or writing any file.
    try:
        for f in files:
            validate_pdf_filename(f.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail="El lote admite como máximo 10 archivos.")
    total_size = 0
    for upload in files:
        upload.file.seek(0, 2)
        size = upload.file.tell()
        upload.file.seek(0)
        if size > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="El PDF supera el límite de 25 MiB.")
        total_size += size
    if total_size > MAX_BATCH_BYTES:
        raise HTTPException(status_code=413, detail="El lote supera el límite de 50 MiB.")

    results = []
    for upload in files:
        content = read_bounded_upload(upload)
        results.extend(process_batch_upload(
            files=[(upload.filename, content)], profile_id=profile_id,
            icc_option=icc_option, selected_icc=selected_icc,
        ))
        del content
    return {"status": "success", "total_uploaded": len(results), "jobs": results}


@app.post("/api/batch/fix-all")
def batch_fix_all_endpoint(body: dict = Body(default={})):
    """Aplica la auto-corrección acumulativa completa a una lista de trabajos."""
    job_ids = body.get("job_ids", [])
    if not isinstance(job_ids, list) or len(job_ids) > MAX_BATCH_FILES:
        raise HTTPException(status_code=422, detail="El lote admite como máximo 10 trabajos.")
    job_ids = [safe_job_id(jid) for jid in job_ids]
    if not job_ids:
        raise HTTPException(status_code=400, detail="Lista de job_ids vacía.")

    results = batch_fix_jobs(job_ids)
    return {"status": "success", "results": results}


@app.post("/api/batch/download-zip")
def batch_download_zip_endpoint(body: dict = Body(default={})):
    """Empaqueta y descarga un archivo ZIP con los PDFs corregidos e informes del lote."""
    job_ids = body.get("job_ids", [])
    if not isinstance(job_ids, list) or len(job_ids) > MAX_BATCH_FILES:
        raise HTTPException(status_code=422, detail="El lote admite como máximo 10 trabajos.")
    job_ids = [safe_job_id(jid) for jid in job_ids]
    if not job_ids:
        raise HTTPException(status_code=400, detail="No se seleccionaron trabajos para el ZIP.")

    zip_bytes = create_batch_zip(job_ids)
    now_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"Lote_Corregido_IntelliPrint_{now_str}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/hotfolder/status")
def hotfolder_status_endpoint():
    """Consulta el estado del demonio de carpeta caliente y los contadores de colas."""
    return hotfolder_service.get_status()


@app.post("/api/hotfolder/start")
def hotfolder_start_endpoint():
    """Inicia el demonio de vigilancia de hotfolder/in/."""
    hotfolder_service.start()
    return {"status": "success", "message": "Servicio de Carpeta Caliente iniciado.", "running": True}


@app.post("/api/hotfolder/stop")
def hotfolder_stop_endpoint():
    """Detiene el demonio de vigilancia de hotfolder/in/."""
    hotfolder_service.stop()
    return {"status": "success", "message": "Servicio de Carpeta Caliente detenido.", "running": False}


@app.post("/api/hotfolder/process-now")
def hotfolder_process_now_endpoint():
    """Fuerza el procesamiento inmediato de todos los PDFs presentes en hotfolder/in/."""
    in_files = sorted(list(IN_DIR.glob("*.pdf")), key=lambda p: p.stat().st_mtime)
    processed = []
    for f in in_files:
        res = hotfolder_service.process_file_sync(f)
        if res:
            processed.append(res)
    return {"status": "success", "processed_count": len(processed), "items": processed}


@app.get("/api/hotfolder/download-all/{category}")
def hotfolder_download_all_endpoint(category: str):
    """Descarga como ZIP todos los archivos de aprobados o rechazados."""
    if category not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="Categoría de hotfolder no válida.")
    target_dir = APPROVED_DIR if category == "approved" else REJECTED_DIR
    files = sorted(f for f in target_dir.glob("*")
                   if f.is_file() and not f.is_symlink() and not f.name.startswith('.'))
    if not files:
        raise HTTPException(status_code=404, detail="No hay archivos en esta carpeta.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    zip_buffer.seek(0)
    now_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"HotFolder_{category.capitalize()}_{now_str}.zip"
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# =============================================================================
# ENDPOINTS: INSPECTOR DE ZONA DE SEGURIDAD Y LOMO (GUTTER & SAFETY MARGIN)
# =============================================================================

@app.get("/api/safety-margin/inspect/{job_id}")
def inspect_safety_margin_endpoint(
    job_id: str,
    safety_margin_mm: float = 3.0,
    gutter_margin_mm: float = 8.0,
    binding_mode: str = "auto"
):
    """Inspecciona la proximidad de textos y elementos a los bordes de corte y lomo."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    try:
        report = inspect_safety_margins(
            pdf_path=target_pdf,
            safety_margin_mm=safety_margin_mm,
            gutter_margin_mm=gutter_margin_mm,
            binding_mode=binding_mode,
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inspeccionando márgenes de seguridad: {e}")


@app.get("/api/safety-margin/preview/{job_id}")
def preview_safety_margin_endpoint(
    job_id: str,
    page_index: int = 0,
    safety_margin_mm: float = 3.0,
    gutter_margin_mm: float = 8.0,
    binding_mode: str = "auto",
    dpi: int = Query(120, ge=36, le=MAX_PREVIEW_DPI)
):
    """Renderiza una previsualización de la página con guías de corte, seguridad, lomo y resaltado de textos."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})
    target_pdf = get_latest_cumulative_pdf(job_meta)
    if not target_pdf or not Path(target_pdf).exists():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado.")

    try:
        img_bytes = render_safety_margin_preview(
            pdf_path=target_pdf,
            page_index=page_index,
            safety_margin_mm=safety_margin_mm,
            gutter_margin_mm=gutter_margin_mm,
            binding_mode=binding_mode,
            dpi=dpi
        )
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando previsualización de márgenes: {e}")


# =============================================================================
# ENDPOINTS: CÓDIGO QR DE TRAZABILIDAD Y FICHA DEL MAQUINISTA
# =============================================================================

@app.get("/verify/{job_id}", response_class=HTMLResponse)
def verify_press_operator_endpoint(job_id: str):
    """Ficha Técnica de Producción y Trazabilidad en vivo para el Maquinista."""
    safe_id = safe_job_id(job_id)
    job_json_path = get_job_json_path(safe_id)
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo de impresión no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    current_pdf = get_latest_cumulative_pdf(job_data.get("job_meta", {}))
    if current_pdf:
        update_pdf_identity(job_data, current_pdf)
        with open(job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)
    sheet_data = get_press_operator_data(job_data)
    html_content = render_press_operator_html(sheet_data)
    return HTMLResponse(content=html_content)


@app.get("/api/qr/{job_id}")
def get_job_qr_endpoint(job_id: str, request: Request):
    """Genera la imagen PNG del código QR de trazabilidad para este trabajo."""
    safe_id = safe_job_id(job_id)
    qr_bytes = generate_traceability_qr_bytes(safe_id, base_url=str(request.base_url))
    return Response(content=qr_bytes, media_type="image/png")


# =============================================================================
# ENDPOINTS: MODO DIDÁCTICO / SIMULADOR PARA ALUMNOS FP
# =============================================================================

@app.get("/api/didactic/scenarios")
def get_didactic_scenarios_endpoint():
    """Retorna la lista de retos de taller FP disponibles para práctica."""
    return {"scenarios": SCENARIOS_CATALOG}


@app.post("/api/didactic/load-scenario/{scenario_id}")
def load_didactic_scenario_endpoint(scenario_id: str):
    """
    Carga el PDF real del reto didáctico seleccionado,
    lo procesa con el motor de preflight y devuelve el reporte completo para análisis en clase.
    """
    scenario = next((s for s in SCENARIOS_CATALOG if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Reto didáctico no encontrado.")

    job_id = f"fp_{scenario_id}"
    job_folder = UPLOAD_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)

    filename = f"{scenario_id}.pdf"
    file_path = job_folder / filename

    src_pdf = DIDACTIC_SCENARIOS_DIR / filename
    if src_pdf.exists():
        shutil.copyfile(src_pdf, file_path)
    else:
        try:
            generate_scenario_pdf(scenario_id, file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error generando PDF de reto didáctico: {e}")

    file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
    with open(file_path, "rb") as f:
        pdf_sha256 = hashlib.sha256(f.read()).hexdigest()

    try:
        report = engine.run_preflight(
            pdf_path=str(file_path),
            profile_id="OFFSET_300",
            icc_choice="preserve"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante el preflight del reto didáctico: {e}")

    report["job_meta"] = {
        "job_id": job_id,
        "filename": filename,
        "file_size_mb": file_size_mb,
        "sha256": pdf_sha256,
        "profile_id": "OFFSET_300",
        "icc_option": "preserve",
        "selected_icc": None,
        "pdf_path": str(file_path),
        "is_didactic_scenario": True,
        "scenario_id": scenario_id,
        "scenario_title": scenario["title"]
    }
    update_pdf_identity(report, file_path, original_sha256=pdf_sha256)

    job_json_path = get_job_json_path(job_id)
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return {
        "job_id": job_id,
        "scenario": scenario,
        "report": report
    }


@app.get("/api/didactic/scenario/{scenario_id}/download")
def download_didactic_scenario_pdf_endpoint(scenario_id: str):
    """
    Descarga el archivo PDF real y original del reto para que alumnos y profesores
    puedan abrirlo en InDesign, Illustrator o Acrobat e inspeccionar los fallos de arte final.
    """
    safe_id = Path(scenario_id).name
    pdf_path = DIDACTIC_SCENARIOS_DIR / f"{safe_id}.pdf"
    if not pdf_path.exists():
        generate_scenario_pdf(safe_id, pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF de reto didáctico no encontrado.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{safe_id}.pdf"
    )


@app.get("/api/didactic/simulate/register")
def simulate_register_endpoint(shift_px: int = 4):
    """Genera la imagen PNG interactiva de descalce de registro en 4 tintas."""
    buf = simulate_register_misalignment(shift_px)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/didactic/simulate/setoff")
def simulate_setoff_endpoint(tac: int = 360):
    """Genera la imagen PNG interactiva de repintado/maculado en pila."""
    buf = simulate_setoff_stain(tac)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/didactic/simulate/guillotine")
def simulate_guillotine_endpoint(has_bleed: bool = False, cut_drift_mm: float = 1.5):
    """Genera la imagen PNG interactiva de oscilación de cuchilla y filete blanco."""
    buf = simulate_guillotine_shift(has_bleed, cut_drift_mm)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/didactic/simulate/ctp")
def simulate_ctp_endpoint(stroke_pt: float = 0.08):
    """Genera la imagen PNG interactiva de pérdida de emulsión CTP en líneas finas."""
    buf = simulate_ctp_hairline(stroke_pt)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/didactic/quiz/questions")
def get_quiz_questions_endpoint():
    """Retorna las preguntas del cuestionario de autoevaluación FP."""
    clean_questions = []
    for q in QUESTIONS_FP:
        clean_questions.append({
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
            "iso_ref": q["iso_ref"]
        })
    return {"questions": clean_questions}


@app.post("/api/didactic/quiz/evaluate")
def evaluate_quiz_endpoint(request: Request, payload: dict):
    """Evalúa las respuestas del alumno, guarda intento en Panel FP si hay sesión y devuelve nota."""
    answers = payload.get("answers", {})
    results = evaluate_student_quiz(answers)
    auth_user = get_authenticated_user(request)
    if auth_user:
        try:
            score_pct = round(float(results.get("score", 0.0)) * 10.0, 1)
            fp_record_quiz_attempt(
                student_id=auth_user["id"],
                topic=payload.get("topic") or "Cuestionario Técnico FP",
                score_pct=score_pct,
                correct_count=int(results.get("correct_answers", 0)),
                total_count=int(results.get("total_questions", 0)),
                assignment_id=int(payload["assignment_id"]) if payload.get("assignment_id") else None,
                details={"level": results.get("level"), "score_10": results.get("score")},
            )
            results["recorded_in_fp_classroom"] = True
        except Exception as exc:
            print(f"[quiz] Aviso registro FP: {exc}")
    return results


@app.post("/api/didactic/worksheet/generate")
def generate_worksheet_endpoint(payload: dict):
    """Genera la Ficha Oficial de Evaluación del Alumno en PDF A4."""
    student_name = payload.get("student_name", "Estudiante FP")
    school_name = payload.get("school_name", "CPIFP Salesianos Urnieta / CIFP Mendizabala LHII")
    scenario_id = payload.get("scenario_id", "reto_tarjeta_richblack")
    quiz_results = payload.get("quiz_results")

    scenario_info = next((s for s in SCENARIOS_CATALOG if s["id"] == scenario_id), SCENARIOS_CATALOG[0])

    ws_id = f"worksheet_{uuid.uuid4().hex[:8]}"
    worksheet_dir = WORKSHEETS_DIR
    worksheet_dir.mkdir(parents=True, exist_ok=True)
    out_path = worksheet_dir / f"{ws_id}.pdf"

    try:
        generate_student_worksheet_pdf(
            student_name=student_name,
            school_name=school_name,
            scenario_info=scenario_info,
            quiz_results=quiz_results,
            output_pdf_path=out_path,
            assets_dir=ASSETS_DIR
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando hoja de práctica PDF: {e}")

    return {
        "success": True,
        "worksheet_id": ws_id,
        "download_url": f"/api/didactic/worksheet/download/{ws_id}.pdf"
    }


@app.get("/api/didactic/worksheet/download/{filename}")
def download_worksheet_endpoint(filename: str):
    """Descarga el PDF de la Ficha de Evaluación del Alumno."""
    safe_name = Path(filename).name
    target_path = WORKSHEETS_DIR / safe_name
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Ficha didáctica no encontrada.")
    return FileResponse(
        target_path,
        media_type="application/pdf",
        filename=f"IntelliPrint_Ficha_Evaluacion_{safe_name}"
    )


# =============================================================================
# ENDPOINTS: MANUAL DE USUARIO (PDF & DOCX)
# =============================================================================

@app.get("/api/manual/download/pdf")
def download_manual_pdf_endpoint():
    """Descarga el Manual Oficial de Usuario en formato PDF A4."""
    pdf_path = BASE_DIR / "Manual_de_Usuario_IntelliPrint.pdf"
    if not pdf_path.exists():
        from generate_manual_pdf import build_manual_pdf
        build_manual_pdf()

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"Manual_de_Usuario_IntelliPrint_{MANUAL_EDITION}.pdf"
    )


@app.get("/api/manual/download/docx")
def download_manual_docx_endpoint():
    """Descarga el Manual Oficial de Usuario en formato Microsoft Word (.docx)."""
    docx_path = BASE_DIR / "Manual_de_Usuario_IntelliPrint.docx"
    if not docx_path.exists():
        from generate_manual_docx import build_manual_docx
        build_manual_docx()

    return FileResponse(
        docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"Manual_de_Usuario_IntelliPrint_{MANUAL_EDITION}.docx"
    )


@app.get("/manual", response_class=HTMLResponse)
def read_manual_endpoint(embed: bool = False):
    return HTMLResponse(render_manual_page(embedded=embed))


@app.get("/api/manual/download/md")
def download_manual_markdown_endpoint():
    return FileResponse(
        MANUAL_SOURCE, media_type="text/markdown; charset=utf-8",
        filename=f"Manual_de_Usuario_IntelliPrint_{MANUAL_EDITION}.md",
    )


@app.get("/api/manual/info")
def get_manual_info_endpoint():
    """Devuelve metadatos del Manual de Usuario y enlaces de descarga."""
    pdf_path = BASE_DIR / "Manual_de_Usuario_IntelliPrint.pdf"
    docx_path = BASE_DIR / "Manual_de_Usuario_IntelliPrint.docx"
    return {
        "title": MANUAL_TITLE,
        "version": MANUAL_EDITION,
        "updated": MANUAL_UPDATED,
        "centers": ["CPIFP Salesianos Urnieta LHIPI", "CIFP Mendizabala LHII"],
        "government": "Departamento de Educación · Eusko Jaurlaritza / Gobierno Vasco",
        "has_pdf": pdf_path.exists(),
        "pdf_size_kb": round(pdf_path.stat().st_size / 1024, 1) if pdf_path.exists() else 0,
        "has_docx": docx_path.exists(),
        "docx_size_kb": round(docx_path.stat().st_size / 1024, 1) if docx_path.exists() else 0,
        "pdf_download_url": "/api/manual/download/pdf",
        "docx_download_url": "/api/manual/download/docx",
        "markdown_download_url": "/api/manual/download/md",
        "web_url": "/manual",
    }


@app.get("/api/fogra/download")
def download_fogra_sheet_endpoint():
    """Descarga la Lámina Técnica Oficial de la Tira de Control FOGRA / ISO 12647-2 en PDF A4."""
    fogra_pdf = BASE_DIR / "Muestra_Tira_FOGRA_ISO12647.pdf"
    if not fogra_pdf.exists():
        from generate_fogra_sample import create_fogra_spec_sheet
        create_fogra_spec_sheet()
    if not fogra_pdf.exists():
        raise HTTPException(status_code=404, detail="Lámina técnica FOGRA no encontrada.")
    return FileResponse(
        fogra_pdf,
        media_type="application/pdf",
        filename="Muestra_Tira_FOGRA_ISO12647.pdf"
    )


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Iniciando IntelliPrint Preflight Web en http://localhost:8000")
    print("="*50 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

