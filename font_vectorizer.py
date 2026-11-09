"""Outline text through a PDF interpreter while retaining print semantics."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pikepdf
import pymupdf

from pdf_utils import atomic_output, copy_pdf, used_spot_names


def find_ghostscript():
    configured = os.environ.get("GHOSTSCRIPT_BIN")
    if configured:
        return configured
    for name in ("gs", "gswin64c", "gswin32c"):
        found = shutil.which(name)
        if found:
            return found
    portable = Path(__file__).parent / ".venv/tools/ghostscript/bin/gswin64c.exe"
    if portable.is_file():
        return str(portable)
    for folder in (Path("C:/Program Files/gs"), Path("C:/Program Files (x86)/gs")):
        matches = sorted(folder.glob("*/bin/gswin64c.exe"), reverse=True)
        if matches:
            return str(matches[0])
    raise RuntimeError("El trazado seguro de fuentes requiere Ghostscript.")


def outline_fonts_in_pdf(pdf_path, output_path, target_pages=None):
    from preflight_engine import extract_pdf_spot_colors
    with pymupdf.open(pdf_path) as doc:
        total_pages = len(doc)
        requested = set(range(1, total_pages + 1) if target_pages is None else target_pages)
        if any(p < 1 or p > total_pages for p in requested):
            raise ValueError("Pagina fuera del documento.")
        selected = [i for i in range(total_pages) if i + 1 in requested and doc[i].get_fonts()]
    if not selected:
        copy_pdf(pdf_path, output_path)
        return {"success": True, "status": "success", "total_pages": total_pages, "pages_vectorized": 0}
    executable = find_ghostscript()
    with tempfile.TemporaryDirectory(prefix="intelliprint_fonts_") as folder:
        subset = Path(folder) / "source.pdf"
        converted = Path(folder) / "outlined.pdf"
        with pikepdf.open(pdf_path) as original, pikepdf.new() as part:
            for index in selected:
                part.pages.append(original.pages[index])
                # GS flattens rotation. Remove it in the temporary input and
                # restore the original page dictionary after outlining.
                part.pages[-1].Rotate = 0
            part.save(subset)
        result = subprocess.run([
            executable, "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET",
            "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7", "-dNoOutputFonts",
            "-dAutoRotatePages=/None", "-dPreserveSeparation=true",
            "-dPreserveDeviceN=true", "-dPreserveOverprintSettings=true",
            "-sColorConversionStrategy=LeaveColorUnchanged",
            f"-sOutputFile={converted}", str(subset),
        ], capture_output=True, timeout=180)
        if result.returncode or not converted.is_file():
            raise RuntimeError("No se pudo trazar el PDF conservando sus propiedades de impresion.")
        with atomic_output(output_path) as temporary:
            with pikepdf.open(pdf_path) as original, pikepdf.open(converted) as outlined:
                spots_before = {s["name"] for s in extract_pdf_spot_colors(original)}
                used_before = used_spot_names(original)
                for position, index in enumerate(selected):
                    page = original.pages[index]
                    boxes = {key: [float(v) for v in page[key]] for key in
                             ("/MediaBox", "/CropBox", "/TrimBox", "/BleedBox", "/ArtBox") if key in page}
                    original_spaces = page.obj.get("/Resources", {}).get("/ColorSpace", {})
                    rotation = int(page.get("/Rotate", 0))
                    media = boxes.get("/MediaBox", [0, 0, 595.28, 841.89])
                    replacement = outlined.pages[position]
                    generated_media = [float(v) for v in replacement.MediaBox]
                    dx, dy = media[0] - generated_media[0], media[1] - generated_media[1]
                    if dx or dy:
                        replacement.contents_add(outlined.make_stream(f"q 1 0 0 1 {dx} {dy} cm\n".encode()), prepend=True)
                        replacement.contents_add(outlined.make_stream(b"\nQ"))
                    original.pages[index] = replacement
                    # Keep unused catalog resources too. They may document
                    # technical inks; only actual operators determine plate use.
                    resources = original.pages[index].Resources
                    if original_spaces and "/ColorSpace" not in resources:
                        resources.ColorSpace = pikepdf.Dictionary()
                    for key, value in original_spaces.items():
                        if key not in resources.ColorSpace:
                            resources.ColorSpace[key] = value
                    for key, values in boxes.items():
                        original.pages[index][key] = pikepdf.Array(values)
                    original.pages[index].Rotate = rotation
                spots_after = {s["name"] for s in extract_pdf_spot_colors(original)}
                if spots_before != spots_after or used_before != used_spot_names(original):
                    raise ValueError("El trazado no conserva las separaciones de tinta originales.")
                original.save(temporary)
            with pymupdf.open(temporary) as verified:
                if any(verified[i].get_fonts() for i in selected):
                    raise ValueError("El PDF resultante aun contiene fuentes en las paginas seleccionadas.")
    return {"success": True, "status": "success", "total_pages": total_pages,
            "pages_vectorized": len(selected)}
