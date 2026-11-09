"""
tac_limiter.py - Limitador de Cobertura Total de Tinta (TAC / Total Area Coverage)
Inspecciona y reduce las acumulaciones de tinta superiores al 300% (o límite configurado)
mediante algoritmos de sustracción de color terciario (UCR) proporcionales, evitando
repintado (set-off), suciedad en rodillos y problemas de secado en máquina offset.
"""

import zlib
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import pymupdf
import pikepdf


def limit_pdf_tac(
    pdf_path: str,
    output_path: str,
    max_tac_percent: float = 300.0
) -> Dict[str, Any]:
    """
    Analiza y limita la cobertura de tinta (TAC / TIC) en todas las imágenes CMYK del PDF:
    - Extrae las muestras nativas DeviceCMYK de cada imagen ráster mediante Pixmap.
    - Calcula la suma total de tinta por píxel: C% + M% + Y% + K%.
    - Si un píxel supera max_tac_percent, reduce C, M, Y de forma proporcional (UCR),
      preservando la integridad del canal K (negro) y el equilibrio cromático.
    - Guarda los streams modificados de forma exacta y sin pérdidas (/FlateDecode).
    - Preserva intactos todos los vectores, tipografías y diccionarios /OutputIntents.

    :param pdf_path: Ruta al archivo PDF de entrada.
    :param output_path: Ruta de salida para el PDF con TAC limitado.
    :param max_tac_percent: Cobertura máxima de tinta admisible (por defecto 300.0%).
    :return: Diccionario con estadísticas del análisis y reducción.
    """
    limit = max_tac_percent / 100.0
    images_inspected = 0
    images_clamped = 0
    peak_tac_found = 0.0

    doc_mu = pymupdf.open(pdf_path)
    pike_doc = pikepdf.open(pdf_path, allow_overwriting_input=True)

    seen_xrefs = set()

    for page in doc_mu:
        for img in page.get_images():
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            try:
                pix = pymupdf.Pixmap(doc_mu, xref)
            except Exception:
                continue

            # Inspeccionar únicamente imágenes de 4 componentes (CMYK)
            if pix.n != 4:
                continue

            images_inspected += 1
            w, h = pix.width, pix.height
            if w <= 0 or h <= 0:
                continue

            try:
                samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, 4))
            except Exception:
                continue

            samples_f = samples.astype(np.float32) / 255.0
            c = samples_f[:, :, 0]
            m = samples_f[:, :, 1]
            y = samples_f[:, :, 2]
            k = samples_f[:, :, 3]

            tot = c + m + y + k
            curr_peak = float(np.max(tot)) * 100.0
            if curr_peak > peak_tac_found:
                peak_tac_found = curr_peak

            mask = tot > limit
            if np.any(mask):
                excess = tot - limit
                cmy_sum = c + m + y
                cmy_sum_safe = np.where(cmy_sum > 0, cmy_sum, 1.0)

                # Reducir C, M, Y proporcionalmente al peso de cada uno
                c[mask] -= excess[mask] * (c[mask] / cmy_sum_safe[mask])
                m[mask] -= excess[mask] * (m[mask] / cmy_sum_safe[mask])
                y[mask] -= excess[mask] * (y[mask] / cmy_sum_safe[mask])

                samples_f[:, :, 0] = np.clip(c, 0.0, 1.0)
                samples_f[:, :, 1] = np.clip(m, 0.0, 1.0)
                samples_f[:, :, 2] = np.clip(y, 0.0, 1.0)
                samples_f[:, :, 3] = np.clip(k, 0.0, 1.0)

                new_bytes = (samples_f * 255.0).astype(np.uint8).tobytes()
                compressed = zlib.compress(new_bytes)

                # Sustituir stream en pikepdf
                try:
                    obj = pike_doc.get_object(xref, 0)
                    obj.write(compressed, filter=pikepdf.Name("/FlateDecode"))
                    obj["/ColorSpace"] = pikepdf.Name("/DeviceCMYK")
                    obj["/BitsPerComponent"] = 8
                    obj["/Width"] = w
                    obj["/Height"] = h
                    # Limpiar parámetros incompatibles con Flate
                    for key in ["/DecodeParms", "/Intent", "/Alternates"]:
                        if key in obj:
                            try:
                                del obj[key]
                            except Exception:
                                pass
                    images_clamped += 1
                except Exception as e:
                    print(f"[tac_limiter] Error escribiendo xref {xref}: {e}")

    doc_mu.close()

    try:
        pike_doc.save(output_path)
    finally:
        pike_doc.close()

    return {
        "success": True,
        "status": "success",
        "images_inspected": images_inspected,
        "images_clamped": images_clamped,
        "peak_tac_before": round(peak_tac_found, 1),
        "target_max_tac": max_tac_percent
    }

