"""
hotfolder_engine.py – Procesamiento por Lote y Carpeta Caliente de Producción (Batch Prepress & Hot-Folder Engine).

Módulos incluidos:
  1. HotFolderService:
     - Demonio en segundo plano que vigila hotfolder/in/.
     - Detección de estabilidad de escritura (evita procesar archivos incompletos durante copia/FTP).
     - Preflight automático y cadena acumulativa de auto-corrección (100% K, sangrado, líneas finas, TAC, etc.).
     - Generación automática de Certificado Técnico y de Informe Pedagógico para el Cliente.
     - Enrutamiento inteligente a hotfolder/out_aprobados/ o hotfolder/out_rechazados/.
     - Historial y telemetría de eventos en tiempo real.
  2. BatchQueueManager:
     - Subida masiva de múltiples PDFs (Multi-PDF Drop).
     - Procesamiento paralelo de preflight con ThreadPoolExecutor.
     - Auto-corrección masiva de todo el lote en 1 clic.
     - Empaquetado y descarga consolidada en ZIP organizado (PDFs corregidos + certificados + informes).
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from upload_security import validate_pdf_filename

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
JOBS_DIR = BASE_DIR / "jobs"
HOTFOLDER_DIR = BASE_DIR / "hotfolder"

IN_DIR = HOTFOLDER_DIR / "in"
PROCESSING_DIR = HOTFOLDER_DIR / "processing"
APPROVED_DIR = HOTFOLDER_DIR / "out_aprobados"
REJECTED_DIR = HOTFOLDER_DIR / "out_rechazados"
LOGS_FILE = HOTFOLDER_DIR / "hotfolder_events.json"

for d in (IN_DIR, PROCESSING_DIR, APPROVED_DIR, REJECTED_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Cadena de Auto-Corrección Completa (Reutilizable)
# ---------------------------------------------------------------------------

def apply_full_batch_fix(
    source_pdf: str | Path,
    output_pdf: str | Path,
    profile_id: str = "OFFSET_300",
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta la cadena acumulativa de correcciones estándar de prepress:
      1. White Overprint Killer + Rich Black Killer + Auto-Trapping 100% K
      2. Sobreimpresión de capas técnicas (barnices/troqueles)
      3. Engrosamiento de líneas finas (Hairlines -> 0.3 pt)
      4. Conversión de imágenes RGB a CMYK (ISO Coated v2)
      5. Limitación de Cobertura Total de Tinta (TAC <= 300%)
      6. Inyección de OutputIntent ICC
      7. Corrección de códigos de barras/QR a 100% K puro y reserva blanca
      8. Generación de sangre espejo si no tiene sangrado (Mirror Bleed)
    """
    source_pdf = Path(source_pdf)
    output_pdf = Path(output_pdf)
    safe_id = job_id or str(uuid.uuid4())[:8]

    # Importaciones dinámicas de los módulos del proyecto
    from overprint_fixer import (
        fix_white_overprint,
        fix_rich_black_small_text,
        apply_overprint_to_technical_inks,
        apply_overprint_to_dark_text,
    )
    from hairline_fixer import fix_hairlines
    from color_converter import convert_rgb_images_to_cmyk
    from tac_limiter import limit_pdf_tac
    from icc_manager import apply_icc_to_pdf, ICC_DIR
    from barcode_engine import fix_barcodes_in_pdf
    from mirror_bleed_generator import generate_mirror_bleed
    import pymupdf

    current_in = source_pdf
    steps_applied: List[Dict[str, Any]] = []
    temp_files: List[Path] = []

    try:
        # 1. Trapping & Overprint
        t1_out = JOBS_DIR / f"{safe_id}_hf_t1.pdf"
        temp_files.append(t1_out)
        w_res = fix_white_overprint(str(current_in), str(t1_out))
        cur = t1_out if (w_res.get("success") and w_res.get("objects_fixed", 0) > 0) else current_in

        t2_out = JOBS_DIR / f"{safe_id}_hf_t2.pdf"
        temp_files.append(t2_out)
        rb_res = fix_rich_black_small_text(str(cur), str(t2_out))
        cur2 = t2_out if (rb_res.get("success") and rb_res.get("texts_fixed", 0) > 0) else cur

        t3_out = JOBS_DIR / f"{safe_id}_hf_t3.pdf"
        temp_files.append(t3_out)
        v_res = apply_overprint_to_technical_inks(str(cur2), str(t3_out))
        cur3 = t3_out if (v_res.get("success") and v_res.get("ops_fixed", 0) > 0) else cur2

        t4_out = JOBS_DIR / f"{safe_id}_hf_t4.pdf"
        temp_files.append(t4_out)
        trap_res = apply_overprint_to_dark_text(str(cur3), str(t4_out), dark_k_threshold=0.99)
        if trap_res.get("success") and t4_out.exists():
            current_in = t4_out
            steps_applied.append({"action": "trapping", "details": trap_res})

        # 2. Líneas Finas (Hairlines)
        hl_out = JOBS_DIR / f"{safe_id}_hf_hl.pdf"
        temp_files.append(hl_out)
        hl_res = fix_hairlines(str(current_in), str(hl_out), hairline_threshold=0.25, target_width=0.3)
        if hl_res.get("success") and hl_res.get("lines_fixed", 0) > 0 and hl_out.exists():
            current_in = hl_out
            steps_applied.append({"action": "hairlines", "details": hl_res})

        # 3. Imágenes RGB a CMYK
        cmyk_out = JOBS_DIR / f"{safe_id}_hf_cmyk.pdf"
        temp_files.append(cmyk_out)
        dst_icc = ICC_DIR / "ISOcoated_v2_eci.icc"
        if not dst_icc.exists():
            dst_icc = ICC_DIR / "ISOcoated_v2_300_bas.icc"
        cmyk_res = convert_rgb_images_to_cmyk(
            pdf_path=str(current_in),
            dst_icc_path=str(dst_icc),
            output_path=str(cmyk_out)
        )
        if cmyk_res.get("success") and cmyk_res.get("images_converted", 0) > 0 and cmyk_out.exists():
            current_in = cmyk_out
            steps_applied.append({"action": "cmyk_images", "details": cmyk_res})

        # 4. Limitación de TAC al 300%
        tac_out = JOBS_DIR / f"{safe_id}_hf_tac.pdf"
        temp_files.append(tac_out)
        tac_res = limit_pdf_tac(str(current_in), str(tac_out), max_tac_percent=300.0)
        if tac_res.get("success") and tac_res.get("images_converted", 0) > 0 and tac_out.exists():
            current_in = tac_out
            steps_applied.append({"action": "tac", "details": tac_res})

        # 5. OutputIntent ICC
        icc_out = JOBS_DIR / f"{safe_id}_hf_icc.pdf"
        temp_files.append(icc_out)
        shutil.copyfile(str(current_in), str(icc_out))
        target_icc = "ISOcoated_v2_eci.icc" if (ICC_DIR / "ISOcoated_v2_eci.icc").exists() else "ISOcoated_v2_300_bas.icc"
        applied_icc = apply_icc_to_pdf(icc_out, target_icc)
        if applied_icc and icc_out.exists():
            current_in = icc_out
            steps_applied.append({"action": "icc", "details": applied_icc})

        # 6. Códigos de Barras y QR a 100% K
        bc_out = JOBS_DIR / f"{safe_id}_hf_bc.pdf"
        temp_files.append(bc_out)
        bc_res = fix_barcodes_in_pdf(str(current_in), str(bc_out), force_pure_k=True, add_quiet_zone=True)
        if bc_res.get("status") == "success" and bc_res.get("codes_fixed", 0) > 0 and bc_out.exists():
            current_in = bc_out
            steps_applied.append({"action": "barcodes", "details": bc_res})

        # 7. Mirror Bleed si el documento no tiene sangrado
        doc = pymupdf.open(str(current_in))
        p0 = doc[0]
        has_bleed = False
        try:
            tb = p0.trimbox
            bb = p0.bleedbox
            if tb and bb and (bb.width - tb.width > 3 or bb.height - tb.height > 3):
                has_bleed = True
        except Exception:
            pass
        doc.close()

        if not has_bleed:
            mb_out = JOBS_DIR / f"{safe_id}_hf_mb.pdf"
            temp_files.append(mb_out)
            mb_res = generate_mirror_bleed(str(current_in), str(mb_out), bleed_mm=3.0)
            if mb_res.get("status") == "success" and mb_out.exists():
                current_in = mb_out
                steps_applied.append({"action": "mirror_bleed", "details": mb_res})

        # Copiar al archivo final
        shutil.copyfile(str(current_in), str(output_pdf))

        return {
            "status": "success",
            "output_pdf_path": str(output_pdf),
            "steps_count": len(steps_applied),
            "steps": steps_applied,
        }
    finally:
        for tf in temp_files:
            try:
                if tf.exists():
                    tf.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SERVICIO DE CARPETA CALIENTE (HOT-FOLDER WATCHER)
# ---------------------------------------------------------------------------

class HotFolderService:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.profile_id = "OFFSET_300"
        self.auto_fix = True
        self.generate_reports = True
        self.poll_interval = 3.0  # segundos
        self.events_log: List[Dict[str, Any]] = self._load_persisted_events()

    def _load_persisted_events(self) -> List[Dict[str, Any]]:
        if LOGS_FILE.exists():
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)[-100:]  # Últimos 100 eventos
            except Exception:
                pass
        return []

    def _save_event(self, event: Dict[str, Any]):
        with self._lock:
            self.events_log.insert(0, event)
            if len(self.events_log) > 100:
                self.events_log = self.events_log[:100]
            try:
                with open(LOGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.events_log, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            in_files = [f.name for f in IN_DIR.glob("*.pdf")]
            approved_files = [f.name for f in APPROVED_DIR.glob("*.pdf")]
            rejected_files = [f.name for f in REJECTED_DIR.glob("*.pdf")]

            return {
                "running": self._running,
                "profile_id": self.profile_id,
                "auto_fix": self.auto_fix,
                "generate_reports": self.generate_reports,
                "poll_interval_sec": self.poll_interval,
                "paths": {
                    "in": str(IN_DIR),
                    "processing": str(PROCESSING_DIR),
                    "out_approved": str(APPROVED_DIR),
                    "out_rejected": str(REJECTED_DIR),
                },
                "queue_counts": {
                    "in": len(in_files),
                    "approved": len(approved_files),
                    "rejected": len(rejected_files),
                },
                "in_files": in_files[:10],
                "recent_events": self.events_log[:20],
            }

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()
            logger.info("[HotFolder] Servicio iniciado.")

    def stop(self):
        with self._lock:
            self._running = False
            logger.info("[HotFolder] Servicio detenido.")

    def _is_file_ready(self, file_path: Path) -> bool:
        """Comprueba que el archivo no esté aún siendo escrito por el cliente (FTP o copia)."""
        try:
            s1 = file_path.stat().st_size
            time.sleep(0.5)
            s2 = file_path.stat().st_size
            return s1 == s2 and s1 > 0
        except Exception:
            return False

    def process_file_sync(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Procesa un archivo PDF individual a través del ciclo completo de prepress."""
        if not file_path.exists() or not file_path.name.lower().endswith(".pdf"):
            return None

        from preflight_engine import IntelliPrintEngine
        from report_generator import generate_preflight_certificate_pdf
        from client_report_generator import generate_client_educational_report_pdf

        engine = IntelliPrintEngine()
        filename = file_path.name
        stem = file_path.stem
        job_id = str(uuid.uuid4())[:8]

        # 1. Mover a processing
        proc_path = PROCESSING_DIR / f"{job_id}_{filename}"
        try:
            shutil.move(str(file_path), str(proc_path))
        except Exception as e:
            logger.error(f"[HotFolder] Error al mover a processing {filename}: {e}")
            return None

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event: Dict[str, Any] = {
            "job_id": job_id,
            "filename": filename,
            "timestamp": timestamp_str,
            "status": "PROCESSING",
            "message": "Analizando...",
        }

        try:
            # 2. Preflight inicial
            report = engine.run_preflight(
                pdf_path=str(proc_path),
                profile_id=self.profile_id,
                icc_choice="preserve"
            )

            job_meta = {
                "job_id": job_id,
                "filename": filename,
                "pdf_path": str(proc_path),
                "profile_id": self.profile_id,
            }
            report["job_meta"] = job_meta

            # Contar incidencias
            findings = report.get("findings", [])
            errors = [f for f in findings if f.get("severity") in ("ERROR", "CRITICAL")]
            warnings = [f for f in findings if f.get("severity") == "WARNING"]

            final_pdf_path = proc_path

            # 3. Auto-corrección si está habilitada
            if self.auto_fix and (len(errors) > 0 or len(warnings) > 0):
                fixed_out = PROCESSING_DIR / f"{job_id}_corregido_{filename}"
                fix_res = apply_full_batch_fix(proc_path, fixed_out, profile_id=self.profile_id, job_id=job_id)
                if fix_res.get("status") == "success" and fixed_out.exists():
                    final_pdf_path = fixed_out
                    # Re-preflight sobre el archivo corregido
                    report_fixed = engine.run_preflight(str(final_pdf_path), profile_id=self.profile_id)
                    report_fixed["job_meta"] = job_meta
                    report_fixed["job_meta"]["last_fixed_pdf_path"] = str(final_pdf_path)
                    report = report_fixed
                    findings = report.get("findings", [])
                    errors = [f for f in findings if f.get("severity") in ("ERROR", "CRITICAL")]
                    warnings = [f for f in findings if f.get("severity") == "WARNING"]

            # Guardar JSON del trabajo
            job_json = JOBS_DIR / f"{job_id}.json"
            with open(job_json, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            # 4. Decisión Aprobado vs Rechazado
            is_approved = (len(errors) == 0)

            target_out_dir = APPROVED_DIR if is_approved else REJECTED_DIR
            dest_pdf_name = f"{stem}_CORREGIDO.pdf" if (self.auto_fix and is_approved) else filename
            dest_pdf = target_out_dir / dest_pdf_name

            shutil.copyfile(str(final_pdf_path), str(dest_pdf))

            # 5. Generar Informes
            if self.generate_reports:
                cert_pdf = target_out_dir / f"{stem}_Certificado_Preflight.pdf"
                try:
                    generate_preflight_certificate_pdf(report, cert_pdf)
                except Exception as ce:
                    logger.warning(f"Error generando certificado en hot-folder: {ce}")

                edu_pdf = target_out_dir / f"{stem}_Informe_Cliente.pdf"
                try:
                    generate_client_educational_report_pdf(report, edu_pdf)
                except Exception as ee:
                    logger.warning(f"Error generando informe cliente en hot-folder: {ee}")

            # Limpiar de processing
            try:
                proc_path.unlink(missing_ok=True)
                if final_pdf_path != proc_path:
                    final_pdf_path.unlink(missing_ok=True)
            except Exception:
                pass

            event["status"] = "APPROVED" if is_approved else "REJECTED"
            event["errors_count"] = len(errors)
            event["warnings_count"] = len(warnings)
            event["message"] = (
                f"{'✓ Aprobado y corregido' if is_approved else '✗ Rechazado por errores técnicos'} "
                f"({len(errors)} err, {len(warnings)} adv)"
            )
            event["destination"] = str(target_out_dir.name)
            event["output_pdf"] = dest_pdf_name

            self._save_event(event)
            return event

        except Exception as e:
            logger.error(f"[HotFolder] Excepción procesando {filename}: {e}", exc_info=True)
            event["status"] = "ERROR"
            event["message"] = f"Error crítico: {e}"
            self._save_event(event)
            # Mover a rejected para no atascar
            try:
                dest_err = REJECTED_DIR / f"ERROR_{filename}"
                shutil.move(str(proc_path), str(dest_err))
            except Exception:
                pass
            return event

    def _worker_loop(self):
        """Bucle en segundo plano que vigila IN_DIR periódicamente."""
        while self._running:
            try:
                pdf_candidates = sorted(list(IN_DIR.glob("*.pdf")), key=lambda p: p.stat().st_mtime)
                for pdf_file in pdf_candidates:
                    if not self._running:
                        break
                    if self._is_file_ready(pdf_file):
                        self.process_file_sync(pdf_file)
            except Exception as e:
                logger.error(f"[HotFolder] Error en bucle: {e}")

            time.sleep(self.poll_interval)


# Instancia única del servicio
hotfolder_service = HotFolderService()


# ---------------------------------------------------------------------------
# GESTOR DE COLA DE TRABAJO Y PROCESAMIENTO MASIVO (BATCH QUEUE MANAGER)
# ---------------------------------------------------------------------------

def process_batch_upload(
    files: List[Tuple[str, bytes]],
    profile_id: str = "OFFSET_300",
    icc_option: str = "preserve",
    selected_icc: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Recibe una lista de archivos (nombre, bytes), los analiza en paralelo con el motor
    de Preflight y devuelve la lista de resultados para poblar la tabla de la cola.
    """
    from preflight_engine import IntelliPrintEngine

    files = [(validate_pdf_filename(name), content) for name, content in files]
    results: List[Dict[str, Any]] = []

    def _process_one(item: Tuple[str, bytes]) -> Dict[str, Any]:
        fname, fbytes = item
        job_id = str(uuid.uuid4())[:8]
        job_folder = UPLOAD_DIR / job_id
        job_folder.mkdir(parents=True, exist_ok=True)
        file_path = job_folder / "source.pdf"

        with open(file_path, "wb") as f:
            f.write(fbytes)

        file_size_mb = round(len(fbytes) / (1024 * 1024), 2)
        engine = IntelliPrintEngine()

        try:
            report = engine.run_preflight(
                pdf_path=str(file_path),
                profile_id=profile_id,
                icc_choice=icc_option,
                selected_icc=selected_icc
            )
            report["job_meta"] = {
                "job_id": job_id,
                "filename": fname,
                "file_size_mb": file_size_mb,
                "profile_id": profile_id,
                "icc_option": icc_option,
                "selected_icc": selected_icc,
                "pdf_path": str(file_path),
            }

            job_json = JOBS_DIR / f"{job_id}.json"
            with open(job_json, "w", encoding="utf-8") as jf:
                json.dump(report, jf, ensure_ascii=False, indent=2)

            findings = report.get("findings", [])
            errors = [f for f in findings if f.get("severity") in ("ERROR", "CRITICAL")]
            warnings = [f for f in findings if f.get("severity") == "WARNING"]
            status = "APPROVED" if len(errors) == 0 else "REJECTED"

            return {
                "job_id": job_id,
                "filename": fname,
                "file_size_mb": file_size_mb,
                "status": status,
                "total_findings": len(findings),
                "errors_count": len(errors),
                "warnings_count": len(warnings),
                "pages_count": report.get("job_summary", {}).get("total_pages", 1),
                "summary": report.get("triple_result", {}).get("technical", {}).get("description", "Analizado"),
                "pdf_path": str(file_path),
            }
        except Exception as e:
            return {
                "job_id": job_id,
                "filename": fname,
                "file_size_mb": file_size_mb,
                "status": "ERROR",
                "total_findings": 0,
                "errors_count": 1,
                "warnings_count": 0,
                "pages_count": 0,
                "summary": f"Fallo al procesar: {e}",
                "pdf_path": str(file_path),
            }

    # Ejecutar concurrentemente con 4 hilos de CPU
    with ThreadPoolExecutor(max_workers=4) as executor:
        for item_res in executor.map(_process_one, files):
            results.append(item_res)

    return results


def batch_fix_jobs(job_ids: List[str]) -> List[Dict[str, Any]]:
    """Aplica la auto-corrección acumulativa completa sobre una lista de trabajos."""
    results = []
    for jid in job_ids:
        safe_id = Path(jid).name
        job_json = JOBS_DIR / f"{safe_id}.json"
        if not job_json.exists():
            continue

        with open(job_json, "r", encoding="utf-8") as f:
            job_data = json.load(f)

        job_meta = job_data.get("job_meta", {})
        target_pdf = job_meta.get("last_fixed_pdf_path") or job_meta.get("pdf_path")
        if not target_pdf or not Path(target_pdf).exists():
            continue

        out_pdf = JOBS_DIR / f"{safe_id}_batch_fixed.pdf"
        fix_res = apply_full_batch_fix(target_pdf, out_pdf, job_id=safe_id)

        if fix_res.get("status") == "success":
            job_meta["batch_fixed_pdf_path"] = str(out_pdf)
            job_meta["last_fixed_pdf_path"] = str(out_pdf)
            with open(job_json, "w", encoding="utf-8") as f:
                json.dump(job_data, f, ensure_ascii=False, indent=2)

            results.append({
                "job_id": safe_id,
                "filename": job_meta.get("filename"),
                "status": "success",
                "steps_applied": fix_res.get("steps_count", 0),
            })
        else:
            results.append({
                "job_id": safe_id,
                "filename": job_meta.get("filename"),
                "status": "error",
            })
    return results


def create_batch_zip(job_ids: List[str]) -> bytes:
    """Empaqueta los PDFs corregidos, certificados e informes de los trabajos en un archivo ZIP."""
    from report_generator import generate_preflight_certificate_pdf
    from client_report_generator import generate_client_educational_report_pdf

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = []

        for jid in job_ids:
            safe_id = Path(jid).name
            job_json = JOBS_DIR / f"{safe_id}.json"
            if not job_json.exists():
                continue

            with open(job_json, "r", encoding="utf-8") as f:
                job_data = json.load(f)

            job_meta = job_data.get("job_meta", {})
            orig_name = job_meta.get("filename", f"documento_{safe_id}.pdf")
            stem = Path(orig_name).stem

            # PDF final corregido o original
            best_pdf = (
                job_meta.get("last_fixed_pdf_path")
                or job_meta.get("batch_fixed_pdf_path")
                or job_meta.get("pdf_path")
            )

            if best_pdf and Path(best_pdf).exists():
                zf.write(best_pdf, arcname=f"PDFs_Listos_Impresion/{stem}_CORREGIDO.pdf")

            # Certificado técnico PDF
            cert_temp = JOBS_DIR / f"{safe_id}_temp_cert.pdf"
            try:
                generate_preflight_certificate_pdf(job_data, cert_temp)
                if cert_temp.exists():
                    zf.write(cert_temp, arcname=f"Certificados_Tecnicos/{stem}_Certificado.pdf")
                    cert_temp.unlink(missing_ok=True)
            except Exception:
                pass

            # Informe pedagógico cliente PDF
            edu_temp = JOBS_DIR / f"{safe_id}_temp_edu.pdf"
            try:
                generate_client_educational_report_pdf(job_data, edu_temp)
                if edu_temp.exists():
                    zf.write(edu_temp, arcname=f"Informes_Pedagogicos_Cliente/{stem}_Informe_Cliente.pdf")
                    edu_temp.unlink(missing_ok=True)
            except Exception:
                pass

            manifest.append({
                "job_id": safe_id,
                "archivo": orig_name,
                "resultado": job_data.get("triple_result", {}).get("technical", {}).get("status", "ANALIZADO"),
            })

        # Manifest JSON de trazabilidad
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("Manifiesto_Lote_IntelliPrint.json", manifest_bytes)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()
