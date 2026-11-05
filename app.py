import os
import shutil
import hashlib
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from preflight_engine import IntelliPrintEngine
from icc_manager import get_available_icc_profiles
from spellcheck_engine import save_word_to_glossary
from report_generator import generate_preflight_certificate_pdf

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
JOBS_DIR = BASE_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

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

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Iniciando IntelliPrint Preflight Web en http://localhost:8000")
    print("="*50 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

