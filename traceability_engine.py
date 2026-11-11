"""
traceability_engine.py – Motor de Código QR de Trazabilidad y Ficha de Producción para el Maquinista.

Permite:
  1. Generar e incrustar códigos QR vectoriales/ráster de alta resolución (100% K puro)
     en el área de información técnica (Slug / margen exterior) de los pliegos de imposición
     y marcas de corte.
  2. Al escanear el QR en máquina desde un teléfono o tablet, abre la Ficha Técnica de Producción
     en vivo (/verify/{job_id}) con los parámetros exactos de tirada:
     - Perfil ICC de color y OutputIntent (FOGRA39 / ISO Coated v2).
     - Cobertura Máxima de Tinta (TAC) y alerta de repintado.
     - Cuerpos de tinta activos (CMYK + Tintas Planas / Barniz UVI).
     - Estado de sangrado (3 mm), líneas finas (>= 0.3 pt) y códigos de barras (100% K).
     - Acceso instantáneo al Certificado Técnico Oficial PDF y al Informe Pedagógico.
"""

from __future__ import annotations

import io
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional

import pymupdf
import qrcode
from PIL import Image

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0


def generate_traceability_qr_bytes(
    job_id: str,
    base_url: str = "",
    size_pixels: int = 240,
) -> bytes:
    """
    Genera el archivo de imagen PNG del código QR de trazabilidad codificando la URL
    de verificación del trabajo.
    """
    safe_id = Path(job_id).name
    # Si base_url no incluye protocolo, formatear URL relativa o absoluta
    if base_url:
        verify_url = f"{base_url.rstrip('/')}/verify/{safe_id}"
    else:
        # Fallback estándar web
        verify_url = f"/verify/{safe_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=1,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def embed_traceability_qr(
    page: pymupdf.Page,
    rect_pt: pymupdf.Rect,
    job_id: str,
    base_url: str = "",
):
    """
    Inyecta el código QR de trazabilidad en la página del pliego o marcas de imprenta
    en las coordenadas especificadas (rect_pt).
    """
    qr_bytes = generate_traceability_qr_bytes(job_id=job_id, base_url=base_url)
    page.insert_image(rect_pt, stream=qr_bytes)


def get_press_operator_data(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae y formatea todos los parámetros técnicos que el maquinista de offset o digital
    necesita consultar a pie de máquina en su consola o smartphone.
    """
    job_meta = job_data.get("job_meta", {})
    job_summary = job_data.get("job_summary", {})
    triple = job_data.get("triple_result", {})
    findings = job_data.get("findings", [])

    # 1. Estado técnico general
    tech = triple.get("technical", {})
    status = tech.get("status", "ANALIZADO")
    is_ready = status in ("PASS", "PASS_WITH_WARNINGS") and triple.get("release", {}).get("status") == "AUTHORIZED"
    current_hash = job_meta.get("current_sha256") or job_meta.get("sha256")
    authorized_hash = ((job_meta.get("authorized_sha256") or triple.get("release", {}).get("sha256"))
                       if triple.get("release", {}).get("status") == "AUTHORIZED" else None)
    is_ready = is_ready and bool(current_hash) and authorized_hash == current_hash

    # 2. Perfil ICC y OutputIntent
    icc_info = job_summary.get("icc_detected", {})
    icc_profile_name = (
        icc_info.get("friendly_description")
        or icc_info.get("identifier")
        or icc_info.get("profile_name")
        or icc_info.get("output_condition")
        or job_meta.get("selected_icc")
        or "No declarado"
    )
    icc_issue = any(f.get("rule_id") == "DOCUMENT_OUTPUT_ICC" for f in findings)
    family = job_summary.get("required_color_family")
    icc_status = ("FAIL" if icc_issue else
                  "PASS" if icc_info.get("icc_valid") is True and
                  (not family or icc_info.get("detected_family") == family) else "NOT_VERIFIED")

    # 3. Tintas y separaciones
    # Contar si hay tintas planas o barnices
    spot_findings = [
        f for f in findings
        if f.get("rule_id") == "SPOT_COLOR_FOUND"
        or "pantone" in f.get("title", "").lower()
        or "tinta plana" in f.get("title", "").lower()
    ]
    has_spots = len(spot_findings) > 0
    spots_list = []
    if has_spots:
        for sf in spot_findings:
            title = sf.get("title", "")
            if "·" in title:
                spots_list.append(title.split("·")[-1].strip())
            else:
                spots_list.append(title)

    # 4. Cobertura máxima de tinta (TAC)
    measurement = job_summary.get("tac_measurement", {})
    tac_val = measurement.get("peak_percent") if measurement.get("measured") else None
    tac_limit = job_summary.get("max_tac_limit", 300)
    tac_issue = any(f.get("rule_id") == "MAX_INK_COVERAGE" for f in findings)
    tac_status = ("WARNING" if tac_issue else "NOT_APPLICABLE" if measurement.get("not_applicable") else
                  "NOT_MEASURED" if tac_val is None else "WARNING" if tac_val > tac_limit + 0.5 else "OK")

    # 5. Sangrado y Cajas de Página
    bleed_mm = job_summary.get("bleed_detected_mm")
    bleed_status = job_summary.get("bleed_status", "NOT_VERIFIED")
    if any(f.get("rule_id") == "BLEED_GEOMETRY_3MM" for f in findings):
        bleed_status = "FAIL"
    has_bleed = bleed_status == "PASS"

    # 6. Códigos de barras 100% K
    barcode_finding = next((f for f in findings if "código de barras" in f.get("title", "").lower() or "barcode" in f.get("title", "").lower()), None)
    inspection = job_meta.get("barcode_inspection", {})
    barcode_status = "NOT_VERIFIED"
    if current_hash and inspection.get("sha256") == current_hash:
        checked = inspection.get("report", {})
        if checked.get("status") == "ERROR" or checked.get("errors_count", 0):
            barcode_status = "FAIL"
        elif checked.get("status") == "WARNING" or checked.get("warnings_count", 0):
            barcode_status = "WARNING"
        elif checked.get("status") == "OK" and checked.get("total_barcodes_found", 0) > 0:
            barcode_status = "PASS"
        elif checked.get("status") == "OK":
            barcode_status = "NOT_DETECTED"
    if barcode_finding:
        barcode_status = "FAIL"
    barcodes_pure_k = True if barcode_status == "PASS" else None if barcode_status in ("NOT_VERIFIED", "NOT_DETECTED") else False

    # 7. Líneas finas (hairlines)
    hairline_finding = next((f for f in findings if f.get("rule_id") == "HAIRLINE_DETECTED"), None)
    hairline_status = job_summary.get("rules_evaluated", {}).get("HAIRLINE_DETECTED", "NOT_VERIFIED")
    if hairline_finding:
        hairline_status = "FAIL"
    elif any(f.get("rule_id") == "GRAPHICS_NOT_VERIFIED" for f in findings):
        hairline_status = "NOT_VERIFIED"
    hairlines_ok = True if hairline_status == "PASS" else False if hairline_status == "FAIL" else None

    # 8. Datos del pliego impuesto si existe
    last_imp = job_meta.get("last_imposition_plan", {})
    imposition_info = None
    if last_imp:
        sheet_dim = last_imp.get("sheet_dimensions_mm", [320, 450])
        grid = last_imp.get("grid", {})
        imposition_info = {
            "mode": last_imp.get("mode", "step_and_repeat"),
            "sheet_size": last_imp.get("sheet_size", "SRA3"),
            "sheet_dimensions_mm": f"{sheet_dim[0]:.0f} × {sheet_dim[1]:.0f} mm",
            "poses_count": grid.get("total_poses", 1),
            "grid": f"{grid.get('cols', 1)} cols × {grid.get('rows', 1)} filas",
            "efficiency": f"{last_imp.get('efficiency_percent', 0)}%",
        }

    return {
        "job_id": job_meta.get("job_id", "DESCONOCIDO"),
        "filename": job_meta.get("filename", "documento.pdf"),
        "sha256": current_hash or "No registrado",
        "original_sha256": job_meta.get("original_sha256") or job_meta.get("sha256") or "No registrado",
        "authorized_sha256": authorized_hash or "No registrado",
        "file_size_mb": job_meta.get("file_size_mb", 0.0),
        "status": status,
        "is_ready_for_press": is_ready,
        "description": tech.get("description", "Pliego verificado por IntelliPrint"),
        "icc_profile": icc_profile_name,
        "icc_status": icc_status,
        "inks_description": f"CMYK (4 Cuerpos){' + Tintas Planas: ' + ', '.join(spots_list) if spots_list else ''}",
        "has_spots": has_spots,
        "spots_list": spots_list,
        "max_tac_percent": tac_val,
        "tac_status": tac_status,
        "tac_limit": tac_limit,
        "bleed_mm": bleed_mm,
        "bleed_status": bleed_status,
        "has_bleed": has_bleed,
        "barcodes_pure_k": barcodes_pure_k,
        "barcode_status": barcode_status,
        "hairlines_ok": hairlines_ok,
        "hairline_status": hairline_status,
        "min_hairline_threshold": job_summary.get("min_hairline_threshold"),
        "imposition": imposition_info,
        "institutions": [
            "Salesianos Urnieta",
            "CIFP Mendizabala LHII",
            "Eusko Jaurlaritza · Departamento de Educación",
        ],
        "certificate_url": f"/api/download-certificate/{job_meta.get('job_id')}",
        "client_report_url": f"/api/download-client-report/{job_meta.get('job_id')}",
        "download_imposed_url": f"/api/imposition/download/{job_meta.get('job_id')}" if imposition_info else None,
    }


def render_press_operator_html(d: Dict[str, Any]) -> str:
    """Genera la plantilla HTML responsive para la Ficha de Producción en Vivo del Maquinista."""
    def safe(value):
        if isinstance(value, str):
            return escape(value, quote=True)
        if isinstance(value, list):
            return [safe(item) for item in value]
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        return value
    d = safe(d)
    tac_display = "No medido" if d.get("max_tac_percent") is None else f"{d['max_tac_percent']:.1f}% (estimado)"
    def badge(state, success, failure, unknown="No verificado"):
        if state in ("PASS", "OK"):
            return success, "bg-emerald-100 text-emerald-800", "text-emerald-700"
        if state in ("FAIL", "WARNING"):
            return failure, "bg-rose-100 text-rose-800", "text-rose-700"
        if state in ("NOT_APPLICABLE", "NOT_REQUIRED"):
            return "No requerido", "bg-slate-100 text-slate-700", "text-slate-600"
        if state == "NOT_DETECTED":
            return "No detectados", "bg-slate-100 text-slate-700", "text-slate-600"
        return unknown, "bg-amber-100 text-amber-800", "text-amber-700"

    icc_text, icc_badge, _ = badge(d.get("icc_status"), "ICC OK", "ICC no conforme")
    tac_text, tac_badge, _ = badge(d.get("tac_status"), "TAC OK (estimado)", "TAC excedido", "No medido")
    bleed_text, _, bleed_color = badge(d.get("bleed_status"), "Conforme", "No conforme")
    if d.get("bleed_mm") is not None and d.get("bleed_status") in ("PASS", "FAIL"):
        bleed_text += f" · {d['bleed_mm']:.1f} mm"
    hairline_text, _, hairline_color = badge(d.get("hairline_status"), "Conforme", "No conforme")
    if d.get("min_hairline_threshold") is not None:
        hairline_text += f" · mín. {d['min_hairline_threshold']} pt"
    barcode_text, _, barcode_color = badge(d.get("barcode_status"), "Conforme", "Revisar códigos")
    is_ready = d.get("is_ready_for_press", False)
    status_bg = "bg-emerald-600" if is_ready else "bg-rose-600"
    status_title = "LISTO PARA IMPRESIÓN · TIRADA AUTORIZADA" if is_ready else "REQUIERE AJUSTES PREVIOS · NO IMPRIMIR"
    status_icon = "fa-circle-check" if is_ready else "fa-triangle-exclamation"
    status_badge_bg = "bg-emerald-100 text-emerald-800 border-emerald-300" if is_ready else "bg-rose-100 text-rose-800 border-rose-300"

    imp = d.get("imposition")
    imp_html = ""
    if imp:
        imp_html = f"""
        <div class="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-2">
          <div class="flex items-center gap-2 text-xs font-bold text-slate-800">
            <i class="fa-solid fa-table-cells text-purple-600"></i>
            <span>Pliego de Imposición Montado:</span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-slate-50 p-2 rounded-lg">
              <span class="text-[10px] text-slate-400 block uppercase">Pliego:</span>
              <strong class="text-slate-800">{imp['sheet_size']} ({imp['sheet_dimensions_mm']})</strong>
            </div>
            <div class="bg-slate-50 p-2 rounded-lg">
              <span class="text-[10px] text-slate-400 block uppercase">Poses:</span>
              <strong class="text-slate-800">{imp['poses_count']} poses ({imp['grid']})</strong>
            </div>
          </div>
          <div class="text-[11px] text-slate-500">
            Aprovechamiento de hoja: <strong class="text-purple-700">{imp['efficiency']}</strong>
          </div>
        </div>
        """

    spots_html = ""
    if d.get("has_spots"):
        spots_html = f"""
        <div class="p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900">
          <strong class="block font-bold">Tintas Planas / Directas Detectadas:</strong>
          <span>{', '.join(d.get('spots_list', []))}</span>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IntelliPrint · Ficha de Producción para el Maquinista · {d.get('job_id')}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  </style>
</head>
<body class="bg-slate-100 text-slate-800 min-h-screen pb-12">

  <!-- Top Brand Banner -->
  <header class="bg-slate-900 text-white px-4 py-3 border-b border-slate-800">
    <div class="max-w-md mx-auto flex items-center justify-between">
      <a href="/" class="flex items-center gap-2.5 hover:opacity-90 transition group" title="Ir a IntelliPrint">
        <img src="/asset/Logo-intelliprint-imago.svg" alt="IntelliPrint" class="h-8 w-auto rounded-lg shrink-0 group-hover:scale-105 transition-transform duration-150">
        <div>
          <h1 class="text-sm flex items-baseline tracking-normal">
            <span class="text-white font-light tracking-wide" style="font-weight: 300;">Intelli</span><span class="text-cyan-400 font-bold ml-0.5" style="font-weight: 700;">Print</span>
          </h1>
          <p class="text-[10px] text-slate-400">Ficha Técnica de Producción y Trazabilidad</p>
        </div>
      </a>
      <span class="text-[10px] bg-slate-800 px-2 py-0.5 rounded font-mono font-bold text-amber-300">
        #{d.get('job_id')}
      </span>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-md mx-auto p-4 space-y-3.5">

    <!-- Big Status Hero Banner -->
    <div class="rounded-2xl p-4 text-white shadow-md {status_bg} flex items-center gap-3.5">
      <i class="fa-solid {status_icon} text-3xl shrink-0"></i>
      <div>
        <span class="text-[10px] font-bold uppercase tracking-wider text-white/80 block">Estado de Producción</span>
        <h2 class="text-sm font-black leading-tight">{status_title}</h2>
        <p class="text-[11px] text-white/90 mt-0.5">{d.get('description')}</p>
      </div>
    </div>

    <!-- Job Info Card -->
    <div class="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-2">
      <div class="flex items-center justify-between text-xs pb-2 border-b border-slate-100">
        <span class="text-slate-400 uppercase text-[10px] font-bold">Archivo de Producción</span>
        <span class="font-mono text-[11px] text-slate-500">{d.get('file_size_mb')} MB</span>
      </div>
      <div class="font-bold text-slate-800 text-sm truncate" title="{d.get('filename')}">
        <i class="fa-solid fa-file-pdf text-rose-500 mr-1.5"></i>{d.get('filename')}
      </div>
      <div class="text-[10px] font-mono text-slate-500 break-all space-y-1">
        <p>SHA-256 original: {d.get('original_sha256')}</p>
        <p>SHA-256 PDF actual: {d.get('sha256')}</p>
        <p>SHA-256 autorizado: {d.get('authorized_sha256')}</p>
      </div>
    </div>

    <!-- Machine Specifications Card -->
    <div class="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-3">
      <div class="flex items-center gap-1.5 text-xs font-bold text-slate-800">
        <i class="fa-solid fa-gears text-indigo-600"></i>
        <span>Parámetros de Tirada en Máquina:</span>
      </div>

      <div class="space-y-2 text-xs">
        <!-- 1. Perfil ICC -->
        <div class="flex items-start justify-between gap-2 p-2 bg-slate-50 rounded-lg">
          <div>
            <span class="text-[10px] text-slate-400 block uppercase">Perfil de Color Destino:</span>
            <strong class="text-slate-800 font-mono text-[11px]">{d.get('icc_profile')}</strong>
          </div>
          <span class="text-[10px] px-2 py-0.5 {icc_badge} font-bold rounded">{icc_text}</span>
        </div>

        <!-- 2. Cuerpos / Tintas -->
        <div class="flex items-start justify-between gap-2 p-2 bg-slate-50 rounded-lg">
          <div>
            <span class="text-[10px] text-slate-400 block uppercase">Cuerpos / Tintas:</span>
            <strong class="text-slate-800">{d.get('inks_description')}</strong>
          </div>
          <span class="text-[10px] px-2 py-0.5 bg-sky-100 text-sky-800 font-bold rounded">4C</span>
        </div>

        {spots_html}

        <!-- 3. TAC Cobertura -->
        <div class="flex items-start justify-between gap-2 p-2 bg-slate-50 rounded-lg">
          <div>
            <span class="text-[10px] text-slate-400 block uppercase">Cobertura Máx. Tinta (TAC):</span>
            <strong class="text-slate-800">{tac_display}</strong>
            <span class="text-[10px] text-slate-400 block">(Límite del perfil: {d.get('tac_limit')}%)</span>
          </div>
          <span class="text-[10px] px-2 py-0.5 {tac_badge} font-bold rounded">{tac_text}</span>
        </div>

        <!-- 4. Geometría y Cortes -->
        <div class="grid grid-cols-3 gap-1.5 pt-1">
          <div class="p-2 bg-slate-50 rounded-lg text-center">
            <span class="text-[9px] text-slate-400 block uppercase">Sangrado</span>
            <strong class="{bleed_color} text-[11px]">{bleed_text}</strong>
          </div>
          <div class="p-2 bg-slate-50 rounded-lg text-center">
            <span class="text-[9px] text-slate-400 block uppercase">Líneas Finas</span>
            <strong class="{hairline_color} text-[11px]">{hairline_text}</strong>
          </div>
          <div class="p-2 bg-slate-50 rounded-lg text-center">
            <span class="text-[9px] text-slate-400 block uppercase">Códigos 100% K</span>
            <strong class="{barcode_color} text-[11px]">{barcode_text}</strong>
          </div>
        </div>
      </div>
    </div>

    <!-- Imposition Card (si aplica) -->
    {imp_html}

    <!-- Press Operator Quick Downloads -->
    <div class="space-y-2 pt-1">
      <span class="text-xs font-bold text-slate-700 block px-1">Documentos de Trazabilidad Oficial:</span>

      <a href="{d.get('certificate_url')}" class="w-full flex items-center justify-between p-3.5 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl shadow-xs transition text-xs font-bold text-slate-800">
        <div class="flex items-center gap-2.5">
          <i class="fa-solid fa-certificate text-emerald-600 text-base"></i>
          <span>Descargar Certificado Oficial Preflight PDF</span>
        </div>
        <i class="fa-solid fa-arrow-down text-slate-400"></i>
      </a>

      <a href="{d.get('client_report_url')}" class="w-full flex items-center justify-between p-3.5 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl shadow-xs transition text-xs font-bold text-slate-800">
        <div class="flex items-center gap-2.5">
          <i class="fa-solid fa-file-invoice text-indigo-600 text-base"></i>
          <span>Descargar Informe Pedagógico para el Cliente</span>
        </div>
        <i class="fa-solid fa-arrow-down text-slate-400"></i>
      </a>

      {f'''<a href="{d.get('download_imposed_url')}" class="w-full flex items-center justify-between p-3.5 bg-purple-50 hover:bg-purple-100 border border-purple-200 rounded-xl shadow-xs transition text-xs font-bold text-purple-900">
        <div class="flex items-center gap-2.5">
          <i class="fa-solid fa-table-cells text-purple-700 text-base"></i>
          <span>Descargar Pliego de Imposición de Máquina</span>
        </div>
        <i class="fa-solid fa-arrow-down text-purple-500"></i>
      </a>''' if d.get('download_imposed_url') else ''}
    </div>

    <!-- Institutional Footer -->
    <div class="text-center pt-4 text-[10px] text-slate-400 space-y-1">
      <p class="font-semibold text-slate-600"><a href="/" class="hover:underline">IntelliPrint</a> · Proyecto de Innovación en FP Gráfica</p>
      <p class="space-x-1">
        <a href="https://salesianosurnieta.com/" target="_blank" rel="noopener noreferrer" class="hover:underline text-slate-500 font-medium">Salesianos Urnieta</a> · 
        <a href="https://www.mendizabala.eus/" target="_blank" rel="noopener noreferrer" class="hover:underline text-slate-500 font-medium">CIFP Mendizabala LHII</a> · 
        <a href="https://www.euskadi.eus/gobierno-vasco/departamento-educacion/" target="_blank" rel="noopener noreferrer" class="hover:underline text-slate-500 font-medium">Eusko Jaurlaritza</a>
      </p>
    </div>

  </main>
</body>
</html>"""

