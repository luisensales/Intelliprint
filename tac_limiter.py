"""Native CMYK image limiting and explicit, bounded TAC measurement."""

import gc
import math
import shutil
import zlib

import numpy as np
import pikepdf
import pymupdf

from pdf_utils import atomic_output, copy_pdf


def _peak(samples):
    flat = samples.reshape(-1, 4)
    peak = 0
    for offset in range(0, len(flat), 250_000):
        total = flat[offset:offset + 250_000].sum(axis=1, dtype=np.uint16)
        peak = max(peak, int(total.max()))
    return peak * 100 / 255


def measure_pdf_tac(pdf_path):
    """Estimate composite TAC at up to 72 dpi, also checking native CMYK images.

    This is an explicit measurement, not a press/RIP certification. Render size
    is bounded to one million pixels per page. Images are released individually.
    """
    peak = 0.0
    seen = set()
    with pymupdf.open(pdf_path) as doc:
        doc.xref_set_key(doc.pdf_catalog(), "OutputIntents", "null")
        for page in doc:
            for image in page.get_images(full=True):
                if image[0] in seen:
                    continue
                seen.add(image[0])
                pix = pymupdf.Pixmap(doc, image[0])
                if pix.colorspace and pix.colorspace.n == 4 and not pix.alpha:
                    peak = max(peak, _peak(np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.width, 4)))
                del pix
            scale = min(1.0, math.sqrt(1_000_000 / max(1, page.rect.width * page.rect.height)))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csCMYK, alpha=False)
            peak = max(peak, _peak(np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.width, 4)))
            del pix
    return {"measured": True, "peak_percent": round(peak, 2),
            "method": "native_cmyk_images_and_composite_up_to_72dpi", "estimated": True}


def limit_pdf_tac(pdf_path, output_path, max_tac_percent=300.0):
    if not math.isfinite(max_tac_percent) or not 100 <= max_tac_percent <= 400:
        raise ValueError("El limite TAC debe estar entre 100 y 400 %.")
    limit = int(math.floor(max_tac_percent * 255 / 100))
    inspected = clamped = 0
    peak = 0.0
    errors = []
    with atomic_output(output_path) as temporary:
        with pymupdf.open(pdf_path) as doc, pikepdf.open(pdf_path) as pdf:
            seen = set()
            for page in doc:
                for image in page.get_images(full=True):
                    xref = image[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        pix = pymupdf.Pixmap(doc, xref)
                        if not pix.colorspace or pix.colorspace.n != 4 or pix.alpha:
                            continue
                        inspected += 1
                        samples = np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.width, 4)
                        image_peak = _peak(samples)
                        peak = max(peak, image_peak)
                        if image_peak * 255 / 100 <= limit:
                            continue
                        flat = samples.reshape(-1, 4)
                        compressor = zlib.compressobj()
                        compressed = bytearray()
                        # Transform bounded chunks instead of allocating several
                        # full-resolution float arrays in the 512 MB deployment.
                        for offset in range(0, len(flat), 250_000):
                            block = flat[offset:offset + 250_000].copy()
                            mask = block.sum(axis=1, dtype=np.uint16) > limit
                            cmy = block[mask, :3].astype(np.float32)
                            available = limit - block[mask, 3].astype(np.float32)
                            ratio = available / np.maximum(cmy.sum(axis=1), 1)
                            block[mask, :3] = np.floor(cmy * ratio[:, None]).clip(0, 255).astype(np.uint8)
                            compressed.extend(compressor.compress(block.tobytes()))
                        compressed.extend(compressor.flush())
                        obj = pdf.get_object(xref, 0)
                        obj.write(bytes(compressed), filter=pikepdf.Name.FlateDecode)
                        obj.ColorSpace = pikepdf.Name.DeviceCMYK
                        obj.BitsPerComponent = 8
                        # Pixmap already applied Decode; do not invert normalized samples again.
                        for key in ("/Decode", "/DecodeParms", "/Intent", "/Alternates"):
                            if key in obj:
                                del obj[key]
                        clamped += 1
                    except Exception as exc:
                        errors.append(f"Imagen {xref}: {exc}")
                    finally:
                        pix = None
                        gc.collect()
            if errors:
                raise ValueError("; ".join(errors))
            if clamped:
                pdf.save(temporary)
            else:
                shutil.copyfile(pdf_path, temporary)
    return {"success": True, "status": "success", "images_inspected": inspected,
            "images_clamped": clamped, "peak_tac_before": round(peak, 2),
            "target_max_tac": max_tac_percent, "errors": []}
