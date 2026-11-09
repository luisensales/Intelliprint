"""
tac_limiter.py - Limitador de Cobertura Total de Tinta (TAC / Total Area Coverage)
Inspecciona y reduce las acumulaciones de tinta superiores al 300% (o límite configurado)
mediante algoritmos de sustracción de color terciario (UCR) proporcionales, evitando
repintado (set-off), suciedad en rodillos y problemas de secado en máquina offset.
"""

import gc
import shutil
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
    - Calcula la suma total de tinta por píxel: C% + M% + Y% + K% usando enteros uint16 (mínimo consumo de RAM).
    - Si un píxel supera max_tac_percent, reduce C, M, Y de forma proporcional (UCR),
      preservando la integridad del canal K (negro) y el equilibrio cromático.
    - Optimizado para instancias de memoria reducida (512 MB): libera memoria de forma agresiva.
    """
    limit_val = int(round(max_tac_percent * 255.0 / 100.0))
    images_inspected = 0
    images_clamped = 0
    peak_tac_found = 0.0

    doc_mu = pymupdf.open(pdf_path)
    pike_doc = None
    seen_xrefs = set()

    try:
        for page in doc_mu:
            for img in page.get_images():
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                pix = None
                try:
                    pix = pymupdf.Pixmap(doc_mu, xref)
                    if pix.n != 4:
                        continue

                    images_inspected += 1
                    w, h = pix.width, pix.height
                    if w <= 0 or h <= 0:
                        continue

                    samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, 4))
                    tot = (
                        samples[:, :, 0].astype(np.uint16)
                        + samples[:, :, 1]
                        + samples[:, :, 2]
                        + samples[:, :, 3]
                    )

                    curr_peak = float(np.max(tot)) * 100.0 / 255.0
                    if curr_peak > peak_tac_found:
                        peak_tac_found = curr_peak

                    mask = tot > limit_val
                    if np.any(mask):
                        # Abrir pikepdf solo cuando realmente se requiere modificar un stream
                        if pike_doc is None:
                            pike_doc = pikepdf.open(pdf_path, allow_overwriting_input=True)

                        c = samples[:, :, 0][mask].astype(np.float32)
                        m = samples[:, :, 1][mask].astype(np.float32)
                        y = samples[:, :, 2][mask].astype(np.float32)
                        k = samples[:, :, 3][mask].astype(np.float32)

                        excess = (c + m + y + k) - limit_val
                        cmy_sum = c + m + y
                        cmy_sum_safe = np.where(cmy_sum > 0, cmy_sum, 1.0)

                        c -= excess * (c / cmy_sum_safe)
                        m -= excess * (m / cmy_sum_safe)
                        y -= excess * (y / cmy_sum_safe)

                        new_samples = samples.copy()
                        new_samples[:, :, 0][mask] = np.clip(np.round(c), 0, 255).astype(np.uint8)
                        new_samples[:, :, 1][mask] = np.clip(np.round(m), 0, 255).astype(np.uint8)
                        new_samples[:, :, 2][mask] = np.clip(np.round(y), 0, 255).astype(np.uint8)

                        compressed = zlib.compress(new_samples.tobytes())

                        del c, m, y, k, excess, cmy_sum, cmy_sum_safe, new_samples

                        try:
                            obj = pike_doc.get_object(xref, 0)
                            obj.write(compressed, filter=pikepdf.Name("/FlateDecode"))
                            obj["/ColorSpace"] = pikepdf.Name("/DeviceCMYK")
                            obj["/BitsPerComponent"] = 8
                            obj["/Width"] = w
                            obj["/Height"] = h
                            for key in ["/DecodeParms", "/Intent", "/Alternates"]:
                                if key in obj:
                                    try:
                                        del obj[key]
                                    except Exception:
                                        pass
                            images_clamped += 1
                        except Exception as e:
                            print(f"[tac_limiter] Error escribiendo xref {xref}: {e}")
                        finally:
                            del compressed

                    del mask, tot, samples
                except Exception as e:
                    print(f"[tac_limiter] Error inspeccionando imagen xref {xref}: {e}")
                finally:
                    if pix is not None:
                        del pix
                    gc.collect()

    finally:
        doc_mu.close()

    if pike_doc is not None and images_clamped > 0:
        try:
            pike_doc.save(output_path)
        finally:
            pike_doc.close()
    else:
        # Si no hubo imágenes que sobrepasaran el TAC, copia directa instantánea sin consumir RAM
        shutil.copy2(pdf_path, output_path)

    gc.collect()

    return {
        "success": True,
        "status": "success",
        "images_inspected": images_inspected,
        "images_clamped": images_clamped,
        "peak_tac_before": round(peak_tac_found, 1),
        "target_max_tac": max_tac_percent
    }

