"""Validación común de nombres recibidos en subidas PDF."""


def validate_pdf_filename(filename: str | None) -> str:
    """Rechaza rutas tanto de Windows como de POSIX, en cualquier servidor."""
    if not filename or any(c in filename for c in '/\\:') or any(ord(c) < 32 for c in filename):
        raise ValueError("El nombre del PDF no puede contener rutas ni caracteres de control.")
    if not filename.lower().endswith('.pdf') or not filename[:-4].strip():
        raise ValueError("El archivo subido debe ser un documento PDF.")
    return filename
