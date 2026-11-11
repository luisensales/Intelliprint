"""Validación común de nombres recibidos en subidas PDF."""

import hashlib
from security_limits import MAX_FILE_BYTES, ResourceLimitError


def save_bounded_upload(upload, destination):
    """Stream an UploadFile to disk and remove partial output on rejection."""
    size = 0
    digest = hashlib.sha256()
    try:
        with open(destination, 'wb') as output:
            while chunk := upload.file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ResourceLimitError("El PDF supera el límite de 25 MiB.")
                output.write(chunk)
                digest.update(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


def read_bounded_upload(upload):
    content = upload.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ResourceLimitError("El PDF supera el límite de 25 MiB.")
    return content


def validate_pdf_filename(filename: str | None) -> str:
    """Rechaza rutas tanto de Windows como de POSIX, en cualquier servidor."""
    if not filename or len(filename) > 240 or any(c in filename for c in '/\\:') or any(ord(c) < 32 for c in filename):
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
