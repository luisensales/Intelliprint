import os
import shutil
import hashlib
import json
import uuid
import time
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pymupdf

from preflight_engine import IntelliPrintEngine
from icc_manager import get_available_icc_profiles, detect_pdf_output_intent
from spellcheck_engine import save_word_to_glossary
from report_generator import generate_preflight_certificate_pdf
from color_converter import convert_rgb_images_to_cmyk, extract_embedded_icc_to_tempfile
from separations_viewer import render_page_separation
from overprint_fixer import apply_overprint_to_dark_text

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
JOBS_DIR = BASE_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"

UPLOAD_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

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

engine = IntelliPrintEngine()

# ---------------------------------------------------------------------------
# Limpieza automática de jobs antiguos
# ---------------------------------------------------------------------------
JOB_TTL_HOURS = 4          # Eliminar jobs con más de N horas de antigüedad
CLEANUP_INTERVAL_SEC = 3600  # Ejecutar limpieza cada hora

def _cleanup_old_jobs():
    """Elimina uploads y jobs con más de JOB_TTL_HOURS horas de antigüedad."""
    cutoff = time.time() - JOB_TTL_HOURS * 3600
    deleted_jobs = 0
    freed_bytes = 0

    # Recorrer todos los JSON de jobs
    for json_file in JOBS_DIR.glob("*.json"):
        try:
            if json_file.stat().st_mtime < cutoff:
                # Leer para obtener la carpeta de uploads asociada
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        job_data = json.load(f)
                    job_id = job_data.get("job_meta", {}).get("job_id", json_file.stem.split("_")[0])
                except Exception:
                    job_id = json_file.stem.split("_")[0]

                # Eliminar carpeta de uploads (PDF original)
                upload_folder = UPLOAD_DIR / job_id
                if upload_folder.exists():
                    freed_bytes += sum(f.stat().st_size for f in upload_folder.rglob("*") if f.is_file())
                    shutil.rmtree(upload_folder, ignore_errors=True)

                # Eliminar todos los archivos del job en jobs/
                for job_file in JOBS_DIR.glob(f"{job_id}*"):
                    freed_bytes += job_file.stat().st_size if job_file.exists() else 0
                    job_file.unlink(missing_ok=True)

                deleted_jobs += 1
        except Exception as e:
            print(f"[cleanup] Error procesando {json_file.name}: {e}")

    if deleted_jobs:
        print(f"[cleanup] {deleted_jobs} jobs eliminados · {freed_bytes // 1024} KB liberados")

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
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>IntelliPrint Web en preparación...</h1>")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/profiles")
async def get_profiles():
    # Read profiles from IntelliPrint_perfiles_v1.json
    json_path = BASE_DIR / "IntelliPrint_perfiles_v1.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "version": data.get("version", "1.2.0"),
                    "profiles": data.get("profiles", [])
                }
        except Exception:
            pass

    # Fallback default description
    return {
        "version": "1.2.0",
        "profiles": [
            {
                "id": "OFFSET_300",
                "name": "IntelliPrint Offset 300",
                "destination": "Impresión Offset Comercial",
                "dpi": 300,
                "bleed_mm": 3.0,
                "color": "CMYK"
            },
            {
                "id": "DIGITAL_200",
                "name": "IntelliPrint Digital 200",
                "destination": "Impresión Digital",
                "dpi": 200,
                "bleed_mm": 3.0,
                "color": "CMYK"
            },
            {
                "id": "PANTALLA_RGB",
                "name": "IntelliPrint Pantalla RGB",
                "destination": "Publicación Digital y Web",
                "dpi": 96,
                "bleed_mm": 0.0,
                "color": "RGB"
            }
        ]
    }

@app.get("/api/icc-catalog")
async def get_icc_catalog():
    return {
        "profiles": get_available_icc_profiles()
    }

@app.post("/api/inspect-pdf")
async def inspect_pdf(file: UploadFile = File(...)):
    """
    Lightweight instant inspection of uploaded PDF:
    Returns page count, file size, dimensions, and embedded OutputIntent / ICC profile.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="El archivo subido debe ser un documento PDF.")

    temp_id = uuid.uuid4().hex[:8]
    temp_path = UPLOAD_DIR / f"inspect_{temp_id}_{file.filename}"
    try:
        content = await file.read()
        temp_path.write_bytes(content)

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

        file_size_mb = round(len(content) / (1024 * 1024), 2)

        return {
            "filename": file.filename,
            "file_size_mb": file_size_mb,
            "pages": page_count,
            "page_size_mm": f"{w_mm} × {h_mm} mm",
            "total_images": total_images,
            "output_intent": icc_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al inspeccionar PDF: {e}")
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

@app.post("/api/check")
async def check_pdf(
    file: UploadFile = File(...),
    profile_id: str = Form("OFFSET_300"),
    icc_option: str = Form("preserve"),
    selected_icc: Optional[str] = Form(None)
):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="El archivo subido debe ser un documento PDF.")

    job_id = str(uuid.uuid4())[:8]
    job_folder = UPLOAD_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)
    
    file_path = job_folder / file.filename
    sha256_hash = hashlib.sha256()

    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 64):
            buffer.write(chunk)
            sha256_hash.update(chunk)

    file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
    pdf_sha256 = sha256_hash.hexdigest()

    # Execute Preflight Engine
    try:
        report = engine.run_preflight(
            pdf_path=str(file_path),
            profile_id=profile_id,
            icc_choice=icc_option,
            selected_icc=selected_icc
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante el preflight: {e}")

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

    # Persist Job JSON
    job_json_path = JOBS_DIR / f"{job_id}.json"
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report

@app.post("/api/proofreading/action")
async def handle_proofreading_action(
    job_id: str = Form(...),
    suggestion_id: str = Form(...),
    action: str = Form(...), # accept, ignore, add_to_glossary
    word: str = Form(...)
):
    job_json_path = JOBS_DIR / f"{job_id}.json"
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
async def release_production(
    job_id: str = Form(...),
    operator_name: str = Form(...),
    decision: str = Form(...), # approved, approved_with_warnings, rejected
    notes: Optional[str] = Form("")
):
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    job_data["triple_result"]["release"] = {
        "status": "AUTHORIZED" if "approved" in decision else "REJECTED",
        "label": f"Autorizado por {operator_name}" if "approved" in decision else f"Rechazado por {operator_name}",
        "decision": decision,
        "operator": operator_name,
        "notes": notes,
        "signed_at": now_str
    }

    # Generate Official Preflight Certificate PDF
    cert_path = JOBS_DIR / f"{job_id}_ficha_tecnica.pdf"
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
        "production_pdf_url": f"/api/download-pdf/{job_id}",
        "json_report_url": f"/api/report/{job_id}",
        "saved_location": f"jobs/{job_id}.json"
    }

@app.get("/api/download-certificate/{job_id}")
async def download_certificate_pdf(job_id: str):
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    
    cert_path = JOBS_DIR / f"{job_id}_ficha_tecnica.pdf"
    if not cert_path.exists():
        generate_preflight_certificate_pdf(job_data, cert_path)

    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
    clean_name = filename.replace(".pdf", "")
    return FileResponse(
        path=str(cert_path),
        media_type="application/pdf",
        filename=f"Ficha_Tecnica_IntelliPrint_{clean_name}_{job_id}.pdf"
    )

@app.get("/api/report/{job_id}")
async def download_json_report(job_id: str):
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    return FileResponse(
        path=str(job_json_path),
        media_type="application/json",
        filename=f"Informe_IntelliPrint_{job_id}.json"
    )


@app.get("/api/storage-status")
async def storage_status():
    """Estado del almacenamiento: número de jobs y espacio usado."""
    def _dir_size(path: Path) -> int:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0

    uploads_bytes = _dir_size(UPLOAD_DIR)
    jobs_bytes    = _dir_size(JOBS_DIR)
    total_bytes   = uploads_bytes + jobs_bytes

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
        "total_mb":   round(total_bytes   / 1024 / 1024, 2),
        "oldest_job_hours": oldest_age_h,
        "ttl_hours": JOB_TTL_HOURS,
        "note": f"Los jobs se eliminan automáticamente después de {JOB_TTL_HOURS} horas."
    }


@app.post("/api/cleanup-now")
async def cleanup_now():
    """Fuerza la limpieza inmediata de jobs antiguos."""
    before_bytes = sum(
        f.stat().st_size for d in [UPLOAD_DIR, JOBS_DIR]
        for f in d.rglob("*") if f.is_file()
    ) if UPLOAD_DIR.exists() and JOBS_DIR.exists() else 0

    _cleanup_old_jobs()

    after_bytes = sum(
        f.stat().st_size for d in [UPLOAD_DIR, JOBS_DIR]
        for f in d.rglob("*") if f.is_file()
    ) if UPLOAD_DIR.exists() and JOBS_DIR.exists() else 0

    return {
        "status": "ok",
        "freed_mb": round((before_bytes - after_bytes) / 1024 / 1024, 2),
        "remaining_jobs": len(list(JOBS_DIR.glob("*.json")))
    }

@app.get("/api/download-pdf/{job_id}")
async def download_pdf_file(job_id: str):
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)
    pdf_p = job_data.get("job_meta", {}).get("pdf_path")
    filename = job_data.get("job_meta", {}).get("filename", "documento.pdf")
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
    use_embedded_icc: bool = Form(True),
    custom_icc: Optional[str] = Form(None),
):
    """
    Convierte las imágenes RGB del PDF a CMYK usando perfiles ICC.
    - use_embedded_icc=true  → usa el OutputIntent embebido en el PDF
    - use_embedded_icc=false → usa custom_icc (nombre de archivo en icc_profiles/)
    """
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})

    # Usar el PDF más reciente como fuente: overprint_fixed > cmyk_converted > original
    # Así las correcciones son acumulativas independientemente del orden
    overprint_path_prev = job_meta.get("overprint_fixed_pdf_path")
    cmyk_path_prev      = job_meta.get("cmyk_converted_pdf_path")
    pdf_path_orig       = job_meta.get("pdf_path")

    if overprint_path_prev and os.path.exists(overprint_path_prev):
        pdf_path = overprint_path_prev
    elif cmyk_path_prev and os.path.exists(cmyk_path_prev):
        pdf_path = cmyk_path_prev
    else:
        pdf_path = pdf_path_orig

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
            fallback_name = job_data.get("job_meta", {}).get("selected_icc", "ISOcoated_v2_300_bas.icc")
            dst_icc_path = str(ICC_PROFILES_DIR / fallback_name)
    else:
        if not custom_icc:
            raise HTTPException(status_code=400, detail="Se requiere un perfil ICC personalizado.")
        # Validar nombre para evitar path traversal
        safe_name = Path(custom_icc).name
        dst_icc_path = str(ICC_PROFILES_DIR / safe_name)
        if not os.path.exists(dst_icc_path):
            raise HTTPException(status_code=400, detail=f"Perfil ICC no encontrado: {safe_name}")

    output_path = JOBS_DIR / f"{job_id}_cmyk_converted.pdf"

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

    if not conv_result.get("success"):
        errors = conv_result.get("errors", [])
        raise HTTPException(status_code=500, detail=f"La conversión falló: {'; '.join(errors)}")

    # Guardar la ruta del PDF convertido en el job
    # Si se aplicó sobre un overprint_fixed anterior, limpiar overprint_fixed_pdf_path
    # para que el visor y el endpoint de descarga usen el cmyk_converted (más reciente y completo)
    job_data["job_meta"]["cmyk_converted_pdf_path"] = str(output_path)
    if job_data["job_meta"].get("overprint_fixed_pdf_path"):
        # El overprint ya está integrado en el cmyk_converted; dejar de apuntar al anterior
        job_data["job_meta"]["overprint_fixed_pdf_path"] = ""
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    # Regenerar el certificado PDF si ya existe (para que refleje los avisos RGB resueltos)
    cert_path = JOBS_DIR / f"{job_id}_ficha_tecnica.pdf"
    if cert_path.exists():
        try:
            generate_preflight_certificate_pdf(job_data, cert_path)
        except Exception as e:
            print(f"[convert-to-cmyk] Aviso: no se pudo regenerar el certificado: {e}")

    return {
        "status": "success",
        "images_converted": conv_result["images_converted"],
        "images_skipped": conv_result["images_skipped"],
        "errors": conv_result.get("errors", []),
        "download_url": f"/api/download-cmyk/{job_id}",
    }


@app.get("/api/download-cmyk/{job_id}")
async def download_cmyk_pdf(job_id: str):
    """Descarga el PDF con imágenes convertidas a CMYK."""
    job_json_path = JOBS_DIR / f"{job_id}.json"
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
# Auto-Trapping: Corrección automática de sobreimpresión en textos negros
# ---------------------------------------------------------------------------

@app.post("/api/apply-overprint/{job_id}")
async def apply_overprint_fix(job_id: str, mode: str = "all"):
    """
    Aplica sobreimpresión automática a textos negros en calado.
    mode: 'all' (ambos: 100% K y >=80% K) o 'k100' (solo negro puro 100% K).
    """
    # Validar job_id para evitar path traversal
    safe_id = Path(job_id).name
    job_json_path = JOBS_DIR / f"{safe_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_meta = job_data.get("job_meta", {})

    # Usar el PDF más reciente como fuente: cmyk_converted > original
    # (El overprint_fixed ya apunta al resultado final acumulado, no lo usamos como fuente
    #  para evitar re-aplicar overprint sobre overprint; siempre partimos del CMYK o el original)
    source_pdf = job_meta.get("cmyk_converted_pdf_path") or job_meta.get("pdf_path")
    if not source_pdf or not Path(source_pdf).exists():
        raise HTTPException(
            status_code=400,
            detail="PDF de origen no encontrado. Sube el archivo o ejecuta la conversión CMYK primero."
        )

    output_path = JOBS_DIR / f"{safe_id}_overprint_fixed.pdf"

    k_threshold = 0.99 if mode == "k100" else 0.80
    result = apply_overprint_to_dark_text(str(source_pdf), str(output_path), dark_k_threshold=k_threshold)

    if not result.get("success"):
        errors = result.get("errors", [])
        raise HTTPException(
            status_code=500,
            detail=f"La corrección de sobreimpresión falló: {'; '.join(errors)}"
        )

    # Guardar la ruta en el job para el endpoint de descarga
    job_data["job_meta"]["overprint_fixed_pdf_path"] = str(output_path)
    with open(job_json_path, "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "mode": mode,
        "pages_modified": result["pages_modified"],
        "text_ops_fixed": result["text_ops_fixed"],
        "errors": result.get("errors", []),
        "download_url": f"/api/download-overprint/{safe_id}",
    }


@app.get("/api/download-overprint/{job_id}")
async def download_overprint_pdf(job_id: str):
    """Descarga el PDF con sobreimpresión corregida automáticamente."""
    safe_id = Path(job_id).name
    job_json_path = JOBS_DIR / f"{safe_id}.json"
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


@app.get("/api/spot-colors/{job_id}")
async def get_job_spot_colors(job_id: str):
    """Devuelve las tintas planas detectadas en el documento del trabajo."""
    safe_id = Path(job_id).name
    job_json_path = JOBS_DIR / f"{safe_id}.json"
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
async def get_page_separation(
    job_id: str,
    page: int = 1,
    c: bool = True,
    m: bool = True,
    y: bool = True,
    k: bool = True,
    disabled_spots: Optional[str] = None,
    mode: str = "color",
    dpi: int = 110,
    use_converted: bool = True,
    icc: Optional[str] = None
):
    """
    Renderiza la simulación de separaciones de color CMYK para la página seleccionada.
    Permite activar/desactivar individualmente planchas de Cian, Magenta, Amarillo y Negro
    para verificar visualmente sobreimpresiones y calados como en Adobe Acrobat Output Preview.
    Aplica el perfil de simulación ICC escogido en la página inicial o el indicado en el visor.
    """
    job_json_path = JOBS_DIR / f"{job_id}.json"
    if not job_json_path.exists():
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    overprint_path = job_data.get("job_meta", {}).get("overprint_fixed_pdf_path")
    converted_path = job_data.get("job_meta", {}).get("cmyk_converted_pdf_path")
    original_path = job_data.get("job_meta", {}).get("pdf_path")

    target_pdf = None
    if use_converted and overprint_path and os.path.exists(overprint_path):
        target_pdf = overprint_path
    elif use_converted and converted_path and os.path.exists(converted_path):
        target_pdf = converted_path
    elif original_path and os.path.exists(original_path):
        target_pdf = original_path

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
            icc_cmyk_path=icc_cmyk_path
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


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Iniciando IntelliPrint Preflight Web en http://localhost:8000")
    print("="*50 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

