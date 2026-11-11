"""Job conservation, persistence, expiration, recovery, search, filtering and production package bundling.

Ensures reliable 24-hour retention across restarts, transparent expiration tracking,
fast multi-field job searching and filtering, instant job recovery, and full production package export.
"""

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from client_report_generator import generate_client_educational_report_pdf
from report_generator import generate_preflight_certificate_pdf
from security_limits import contained_job_path, validate_job_id
from version_history import public_history, version_path


JOB_TTL_HOURS = 24


class JobManagerError(ValueError):
    pass


def format_remaining_time(seconds: int) -> str:
    """Formatea los segundos restantes en un texto legible en español."""
    if seconds <= 0:
        return "Vencido"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours >= 24:
        days = hours // 24
        rem_h = hours % 24
        return f"{days} d {rem_h} h" if rem_h > 0 else f"{days} d"
    if hours > 0:
        return f"{hours} h {minutes} min" if minutes > 0 else f"{hours} h"
    return f"{minutes} min" if minutes > 0 else "< 1 min"


def calculate_job_expiration(
    job_data: Dict[str, Any],
    manifest_path: Optional[Path] = None,
    ttl_hours: int = JOB_TTL_HOURS,
) -> Dict[str, Any]:
    """Calcula la caducidad y tiempo restante de un trabajo basándose en su última actividad."""
    meta = job_data.get("job_meta") or {}
    now = time.time()

    # Determinar la marca temporal más reciente (mtime o timestamps registrados)
    timestamps = []
    if manifest_path and manifest_path.exists():
        try:
            timestamps.append(manifest_path.stat().st_mtime)
        except OSError:
            pass

    for key in ("timestamp", "created_at", "updated_at", "registered_at"):
        val = meta.get(key)
        if isinstance(val, (int, float)):
            timestamps.append(float(val))
        elif isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                timestamps.append(dt.timestamp())
            except (ValueError, TypeError):
                pass

    last_active = max(timestamps) if timestamps else now
    ttl_seconds = ttl_hours * 3600
    expires_at_timestamp = last_active + ttl_seconds
    remaining_seconds = max(0, int(expires_at_timestamp - now))

    expires_dt = datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc)
    created_val = meta.get("timestamp") or meta.get("created_at") or last_active
    if isinstance(created_val, (int, float)):
        created_dt = datetime.fromtimestamp(created_val, tz=timezone.utc).isoformat()
    else:
        created_dt = str(created_val)

    is_expiring_soon = 0 < remaining_seconds <= (2 * 3600)  # Menos de 2 horas
    is_expired = remaining_seconds == 0

    return {
        "ttl_hours": ttl_hours,
        "created_at": created_dt,
        "last_activity_timestamp": last_active,
        "expires_at_timestamp": expires_at_timestamp,
        "expires_at_iso": expires_dt.isoformat(),
        "remaining_seconds": remaining_seconds,
        "remaining_human": format_remaining_time(remaining_seconds),
        "is_expiring_soon": is_expiring_soon,
        "is_expired": is_expired,
        "persistent_storage": True,
    }


def list_managed_jobs(
    jobs_dir: Path,
    query: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    ttl_hours: int = JOB_TTL_HOURS,
) -> Dict[str, Any]:
    """Lista los trabajos almacenados con búsqueda y filtros multifunción."""
    jobs_root = Path(jobs_dir).resolve()
    if not jobs_root.exists() or not jobs_root.is_dir():
        return {"total": 0, "jobs": []}

    q = (query or "").strip().lower()
    sf = (status_filter or "all").strip().lower()

    manifest_files = []
    try:
        manifest_files = [p for p in jobs_root.iterdir() if p.suffix == ".json" and p.is_file()]
    except OSError:
        pass

    results = []
    for manifest in manifest_files:
        try:
            job_id = validate_job_id(manifest.stem)
        except ValueError:
            continue

        try:
            with open(manifest, "r", encoding="utf-8") as f:
                job_data = json.load(f)
        except Exception:
            continue

        meta = job_data.get("job_meta") or {}
        tr = job_data.get("triple_result") or {}
        rel = tr.get("release") or {}
        tech = tr.get("technical") or {}
        prod = tr.get("production") or {}

        filename = meta.get("filename") or "documento.pdf"
        profile_name = (job_data.get("perfil_seleccionado") or {}).get("nombre") or meta.get("profile_name") or "Estándar"
        profile_id = (job_data.get("perfil_seleccionado") or {}).get("id") or meta.get("profile_id") or ""
        release_status = rel.get("status") or "PENDING"
        operator = rel.get("operator_name") or ""
        is_approved = release_status == "AUTHORIZED"

        tech_summary = tech.get("summary") or {}
        errors_count = tech_summary.get("errors", 0)
        warnings_count = tech_summary.get("warnings", 0)

        page_count = (job_data.get("paginas") or {}).get("total_paginas") or meta.get("page_count") or 1
        file_size_bytes = meta.get("file_size_bytes") or 0

        exp = calculate_job_expiration(job_data, manifest_path=manifest, ttl_hours=ttl_hours)

        # Omitir trabajos totalmente vencidos de la lista activa
        if exp["is_expired"]:
            continue

        # Filtro de texto (q): busca en job_id, filename, profile_name, operator
        if q:
            searchable = f"{job_id} {filename} {profile_name} {profile_id} {operator}".lower()
            if q not in searchable:
                continue

        # Filtro de estado
        if sf in ("approved", "authorized"):
            if not is_approved:
                continue
        elif sf in ("rejected", "rechazado"):
            if release_status != "REJECTED":
                continue
        elif sf in ("pending", "pendiente"):
            if release_status != "PENDING":
                continue
        elif sf in ("errors", "con_errores"):
            if errors_count == 0:
                continue

        history = job_data.get("version_history") or {}
        versions_count = len(history.get("versions", []))
        has_imposed_pdf = bool(meta.get("imposed_pdf_path"))
        has_ppf = bool(contained_job_path(jobs_root, f"{job_id}").exists() and list(contained_job_path(jobs_root, f"{job_id}").glob("*.ppf"))) if (jobs_root / job_id).exists() else False

        item = {
            "job_id": job_id,
            "filename": filename,
            "profile_name": profile_name,
            "profile_id": profile_id,
            "release_status": release_status,
            "is_approved": is_approved,
            "operator": operator,
            "errors_count": errors_count,
            "warnings_count": warnings_count,
            "page_count": page_count,
            "file_size_bytes": file_size_bytes,
            "has_imposed_pdf": has_imposed_pdf,
            "has_ppf": has_ppf,
            "versions_count": versions_count,
            "expiration": exp,
            "last_activity_timestamp": exp["last_activity_timestamp"],
        }
        results.append(item)

    # Ordenar por actividad más reciente (descendente)
    results.sort(key=lambda x: x["last_activity_timestamp"], reverse=True)
    total_matches = len(results)
    sliced = results[:max(1, limit)]

    return {
        "total": total_matches,
        "limit": limit,
        "query": q,
        "status_filter": sf,
        "jobs": sliced,
    }


def get_job_data_for_recovery(
    job_id: str,
    jobs_dir: Path,
    ttl_hours: int = JOB_TTL_HOURS,
) -> Dict[str, Any]:
    """Carga y rehidrata completamente un trabajo para su recuperación en la interfaz."""
    safe_id = validate_job_id(job_id)
    jobs_root = Path(jobs_dir).resolve()
    manifest_path = contained_job_path(jobs_root, f"{safe_id}.json")

    if not manifest_path.exists():
        raise JobManagerError(f"El trabajo '{safe_id}' no existe o ha superado el tiempo de retención.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    # Inyectar metadatos de caducidad calculados dinámicamente
    job_data["expiration_info"] = calculate_job_expiration(job_data, manifest_path=manifest_path, ttl_hours=ttl_hours)

    # Asegurar que el resumen de historial está actualizado
    try:
        job_data["version_history_summary"] = public_history(job_data, jobs_root)
    except Exception:
        pass

    return job_data


def build_production_package(
    job_id: str,
    jobs_dir: Path,
    upload_dir: Optional[Path] = None,
    engine: Optional[Any] = None,
) -> Tuple[bytes, str]:
    """
    Empaqueta el entregable completo de producción en un archivo .zip profesional.
    Incluye:
      01_Arte_Final_Impresion/: PDF final / aprobado
      02_Documentacion_Tecnica/: Ficha técnica preflight, Guía de cliente e Informe JSON
      03_Taller_e_Imposicion/: Pliego de imposición y tinteros CIP3 (si existen)
      04_Historial_de_Versiones/: Registro cronológico de versiones
      MANIFIESTO_PRODUCCION.txt: Resumen formal con firmas, hashes y parámetros de taller
    """
    safe_id = validate_job_id(job_id)
    jobs_root = Path(jobs_dir).resolve()
    manifest_path = contained_job_path(jobs_root, f"{safe_id}.json")

    if not manifest_path.exists():
        raise JobManagerError(f"No se encontró el trabajo '{safe_id}' para empaquetar.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    meta = job_data.get("job_meta") or {}
    filename = meta.get("filename") or "documento.pdf"
    stem = Path(filename).stem
    exp = calculate_job_expiration(job_data, manifest_path=manifest_path)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. ARTE FINAL (PDF de Producción)
        # Buscar el PDF más reciente corregido o aprobado
        final_pdf_path = None
        for candidate_key in ("last_fixed_pdf_path", "cmyk_pdf_path", "file_path"):
            cand = meta.get(candidate_key)
            if cand and Path(cand).exists():
                final_pdf_path = Path(cand)
                break

        history = job_data.get("version_history") or {}
        approved_id = history.get("approved_version_id")
        if approved_id:
            try:
                approved_path = version_path(job_data, jobs_root, approved_id)
                if approved_path.exists():
                    zf.writestr(
                        f"01_Arte_Final_Impresion/IntelliPrint_{stem}_APROBADO.pdf",
                        approved_path.read_bytes(),
                    )
            except Exception:
                pass

        if final_pdf_path and final_pdf_path.exists():
            zf.writestr(
                f"01_Arte_Final_Impresion/IntelliPrint_{stem}_FINAL.pdf",
                final_pdf_path.read_bytes(),
            )

        # 2. DOCUMENTACIÓN TÉCNICA
        # Ficha técnica
        cert_path = jobs_root / f"{safe_id}_ficha_tecnica.pdf"
        if not cert_path.exists():
            try:
                generate_preflight_certificate_pdf(job_data, cert_path)
            except Exception:
                pass
        if cert_path.exists():
            zf.writestr("02_Documentacion_Tecnica/Ficha_Tecnica_Preflight.pdf", cert_path.read_bytes())

        # Guía para el cliente
        guide_path = jobs_root / f"{safe_id}_guia_cliente.pdf"
        if not guide_path.exists():
            try:
                generate_client_educational_report_pdf(
                    job_data, guide_path, pdf_path=str(final_pdf_path) if final_pdf_path else None
                )
            except Exception:
                pass
        if guide_path.exists():
            zf.writestr("02_Documentacion_Tecnica/Guia_Cliente_Correcciones.pdf", guide_path.read_bytes())

        # Hoja de Ruta / Job Ticket si existe
        ticket_path = jobs_root / f"{safe_id}_job_ticket.pdf"
        if ticket_path.exists():
            zf.writestr("02_Documentacion_Tecnica/Hoja_de_Ruta_JobTicket.pdf", ticket_path.read_bytes())

        # Informe de auditoría JSON
        zf.writestr(
            "02_Documentacion_Tecnica/Informe_Auditoria.json",
            json.dumps(job_data, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        # 3. TALLER E IMPOSICIÓN
        imposed_path = meta.get("imposed_pdf_path")
        if imposed_path and Path(imposed_path).exists():
            zf.writestr("03_Taller_e_Imposicion/Pliego_Imposicion.pdf", Path(imposed_path).read_bytes())

        # CIP3 PPF
        job_dir = jobs_root / safe_id
        if job_dir.exists():
            for ppf_file in job_dir.glob("*.ppf"):
                zf.writestr(f"03_Taller_e_Imposicion/{ppf_file.name}", ppf_file.read_bytes())

        # 4. HISTORIAL DE VERSIONES
        try:
            pub_hist = public_history(job_data, jobs_root)
            zf.writestr(
                "04_Historial_de_Versiones/Historial_Versiones.json",
                json.dumps(pub_hist, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        except Exception:
            pass

        # 5. MANIFIESTO DE PRODUCCIÓN (TXT)
        tr = job_data.get("triple_result") or {}
        tech_status = (tr.get("technical") or {}).get("status", "REVISAR")
        prod_status = (tr.get("production") or {}).get("status", "NO_CONFORME")
        rel_info = tr.get("release") or {}
        rel_status = rel_info.get("status", "PENDING")
        operator = rel_info.get("operator_name") or "No asignado"
        notes = rel_info.get("notes") or "Sin notas adicionales"
        profile_name = (job_data.get("perfil_seleccionado") or {}).get("nombre") or "Estándar"

        pdf_sha = meta.get("current_sha256") or meta.get("original_sha256") or "N/D"

        manifest_text = f"""================================================================================
PAQUETE COMPLETO DE PRODUCCIÓN · INTELLIPRINT
================================================================================

DATOS GENERALES DEL TRABAJO:
  - Identificador de Trabajo (Job ID) : {safe_id}
  - Archivo Original                 : {filename}
  - Fecha de Registro                : {exp.get('created_at', 'N/D')}
  - Fecha de Generación de Paquete   : {datetime.now(timezone.utc).isoformat()}
  - Perfil Técnico de Preflight       : {profile_name}

RESULTADO TRIPLE DE CALIDAD:
  1. Estado Técnico de Preflight     : {tech_status}
  2. Aptitud para Producción         : {prod_status}
  3. Autorización de Salida (Release): {rel_status}
     * Operador Responsable          : {operator}
     * Observaciones de Taller       : {notes}

INTEGRIDAD Y SEGURIDAD:
  - Huella Digital SHA-256 (PDF)     : {pdf_sha}
  - Política de Conservación         : Retención garantizada de 24 horas.
  - Caducidad Programada             : {exp.get('expires_at_iso', 'N/D')} ({exp.get('remaining_human', 'Vencido')} restantes)

ESTRUCTURA DE ESTE PAQUETE ZIP:
  ├── 01_Arte_Final_Impresion/       -> PDF de producción con correcciones aplicadas
  ├── 02_Documentacion_Tecnica/      -> Ficha técnica oficial, Guía de cliente e Informe JSON
  ├── 03_Taller_e_Imposicion/        -> Pliego de imposición y tinteros CIP3 (si generados)
  ├── 04_Historial_de_Versiones/     -> Registro cronológico inmutable de intervenciones
  └── MANIFIESTO_PRODUCCION.txt      -> Este documento de entrega

================================================================================
CPIFP Salesianos Urnieta · CIFP Mendizabala · IntelliPrint Prepress Suite
================================================================================
"""
        zf.writestr("MANIFIESTO_PRODUCCION.txt", manifest_text.encode("utf-8"))

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()
    zip_name = f"Paquete_Produccion_IntelliPrint_{stem}_{safe_id[:8]}.zip"
    return zip_bytes, zip_name
