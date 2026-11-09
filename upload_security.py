"""Validación común de nombres recibidos en subidas PDF."""


def validate_pdf_filename(filename: str | None) -> str:
    """Rechaza rutas tanto de Windows como de POSIX, en cualquier servidor."""
    if not filename or any(c in filename for c in '/\\:') or any(ord(c) < 32 for c in filename):
        raise ValueError("El nombre del PDF no puede contener rutas ni caracteres de control.")
    if not filename.lower().endswith('.pdf') or not filename[:-4].strip():
        raise ValueError("El archivo subido debe ser un documento PDF.")
    return filename


def discard_failed_upload(folder, upload_root):
    """Delete only a generated job subdirectory, never the upload root itself."""
    import shutil
    from pathlib import Path
    target, root = Path(folder).resolve(), Path(upload_root).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("La carpeta del trabajo queda fuera del directorio de subidas.")
    if target.exists():
        shutil.rmtree(target)
