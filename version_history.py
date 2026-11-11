"""Immutable, content-addressed PDF versions belonging to a temporary job.

Only manifest references are changed by undo/restore. PDF bytes are copied once
and are never overwritten; callers persist the updated manifest atomically.
"""

from copy import deepcopy
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from PIL import Image, ImageChops
import pymupdf

from document_identity import sha256_file
from pdf_utils import atomic_output
from security_limits import contained_job_path, validate_job_id


MAX_VERSION_BYTES = 200 * 1024 * 1024
MAX_VERSIONS = 100
_SHA = re.compile(r"[a-f0-9]{64}")
_VERSION = re.compile(r"v[0-9]{4}")


class VersionHistoryError(ValueError):
    pass


class VersionQuotaError(VersionHistoryError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _check_path(path, *, directory):
    info = path.lstat()
    linked = stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if linked or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise VersionHistoryError("El historial no admite enlaces ni tipos de archivo especiales.")
    return info


def _storage_dir(job_data, jobs_dir, create=False):
    meta = job_data.get("job_meta") or {}
    job_id = validate_job_id(meta.get("job_id"))
    root = Path(jobs_dir).absolute()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    _check_path(root, directory=True)
    root = root.resolve()
    current = root
    for name in ("versions", job_id):
        candidate = contained_job_path(current, name)
        if create:
            candidate.mkdir(exist_ok=True)
        if candidate.exists() or candidate.is_symlink():
            _check_path(candidate, directory=True)
        if not candidate.is_relative_to(root):
            raise VersionHistoryError("El historial queda fuera de la carpeta de trabajos.")
        current = candidate
    return current


def _history(job_data, allow_missing=False):
    if "version_history" not in job_data and allow_missing:
        return {
            "versions": [],
            "active_id": None,
            "approved_version_id": None,
            "undo_stack": [],
            "redo_stack": [],
            "updated_at": None,
        }
    history = job_data.get("version_history")
    if not isinstance(history, dict) or not isinstance(history.get("versions"), list):
        raise VersionHistoryError("El historial del trabajo no es válido.")
    entries = history["versions"]
    known = set()
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
                or not _VERSION.fullmatch(entry["id"]) or entry["id"] in known
                or not isinstance(entry.get("sha256"), str) or not _SHA.fullmatch(entry["sha256"])
                or entry.get("blob") != entry["sha256"] + ".pdf"
                or not isinstance(entry.get("size_bytes"), int) or entry["size_bytes"] <= 0
                or not isinstance(entry.get("label"), str) or not isinstance(entry.get("created_at"), str)):
            raise VersionHistoryError("El historial contiene una versión no válida.")
        known.add(entry["id"])
    if history.get("active_id") not in known:
        raise VersionHistoryError("No se encuentra la versión activa del trabajo.")
    approved_id = history.get("approved_version_id")
    if approved_id is not None and (not isinstance(approved_id, str) or approved_id not in known):
        raise VersionHistoryError("La versión aprobada no es válida.")
    for key in ("undo_stack", "redo_stack"):
        stack = history.get(key)
        if not isinstance(stack, list) or any(not isinstance(item, str) or item not in known for item in stack):
            raise VersionHistoryError("La navegación del historial no es válida.")
    return history


def _entry(history, version_id):
    if not isinstance(version_id, str) or not _VERSION.fullmatch(version_id):
        raise VersionHistoryError("Identificador de versión no válido.")
    for entry in history["versions"]:
        if entry["id"] == version_id:
            return entry
    raise VersionHistoryError("La versión solicitada no pertenece a este trabajo.")


def _blob_path(folder, entry):
    # Derive the filename from the validated SHA, never from a JSON path.
    path = folder / (entry["sha256"] + ".pdf")
    _check_path(path, directory=False)
    contained = contained_job_path(folder, path.name)
    if path.stat().st_size != entry["size_bytes"] or sha256_file(contained) != entry["sha256"]:
        raise VersionHistoryError("La copia de esta versión ha cambiado o está dañada.")
    return contained


def _storage_bytes(folder):
    total = 0
    for path in folder.iterdir():
        total += _check_path(path, directory=False).st_size
    return total


def version_path(job_data, jobs_dir, version_id=None):
    history = _history(job_data)
    selected = _entry(history, history["active_id"] if version_id is None else version_id)
    return _blob_path(_storage_dir(job_data, jobs_dir), selected)


def capture_version(job_data, pdf_path, jobs_dir, label="PDF recibido", is_approved=False):
    """Capture a new active state, deduplicating its bytes; no-op for same PDF.

    Quota and source validation precede mutation. A failed copy, quota check or
    corrupt blob never changes the active history in ``job_data``.
    """
    previous = _history(job_data, allow_missing=True)
    source = Path(pdf_path).absolute()
    size = _check_path(source, directory=False).st_size
    if not size:
        raise VersionHistoryError("No se puede conservar una versión vacía.")
    digest = sha256_file(source)
    if previous["active_id"] is not None:
        active = _entry(previous, previous["active_id"])
        if digest == active["sha256"]:
            version_path(job_data, jobs_dir)
            if is_approved and not active.get("is_approved"):
                active["is_approved"] = True
                active["label"] = str(label)
                previous["approved_version_id"] = active["id"]
                previous["updated_at"] = _now()
                job_data["version_history"] = previous
                return True
            return False
    if len(previous["versions"]) >= MAX_VERSIONS:
        raise VersionQuotaError(f"El trabajo ha alcanzado el límite de {MAX_VERSIONS} versiones.")
    try:
        folder = _storage_dir(job_data, jobs_dir)
        used = _storage_bytes(folder)
    except FileNotFoundError:
        folder = None
        used = 0
    exists = folder is not None and (folder / (digest + ".pdf")).exists()
    entry = {
        "id": f"v{max((int(item['id'][1:]) for item in previous['versions']), default=0) + 1:04d}",
        "sha256": digest,
        "blob": digest + ".pdf",
        "label": str(label),
        "created_at": _now(),
        "size_bytes": size,
        "is_approved": bool(is_approved),
    }
    if not _VERSION.fullmatch(entry["id"]):
        raise VersionQuotaError("No se pueden añadir más versiones al trabajo.")
    if used + (0 if exists else size) > MAX_VERSION_BYTES:
        raise VersionQuotaError(f"El historial supera el límite de {MAX_VERSION_BYTES // (1024 * 1024)} MB por trabajo.")
    folder = _storage_dir(job_data, jobs_dir, create=True)
    destination = folder / entry["blob"]
    if exists:
        _blob_path(folder, entry)
    else:
        # Atomic publication: link with fallback to safe copy for cross-device support.
        scratch = folder / (".capture_" + uuid.uuid4().hex + ".pdf")
        try:
            with atomic_output(scratch) as temporary:
                shutil.copyfile(source, temporary)
                if temporary.stat().st_size != size or sha256_file(temporary) != digest:
                    raise VersionHistoryError("El PDF cambió mientras se guardaba la versión.")
            try:
                os.link(scratch, destination)
            except (FileExistsError, OSError):
                if not destination.exists():
                    shutil.copyfile(scratch, destination)
            _blob_path(folder, entry)
        finally:
            scratch.unlink(missing_ok=True)
    updated = deepcopy(previous)
    if updated["active_id"] is not None:
        updated["undo_stack"].append(updated["active_id"])
    updated["versions"].append(entry)
    updated.update(active_id=entry["id"], redo_stack=[], updated_at=entry["created_at"])
    if is_approved:
        updated["approved_version_id"] = entry["id"]
    job_data["version_history"] = updated
    return True


def select_version(job_data, jobs_dir, version_id=None, operation="restore"):
    """Move the active pointer after verifying the selected immutable blob."""
    history = _history(job_data)
    updated = deepcopy(history)
    if operation == "restore":
        selected = _entry(history, version_id)
        if selected["id"] == history["active_id"]:
            version_path(job_data, jobs_dir, selected["id"])
            return deepcopy(selected)
        updated["undo_stack"].append(history["active_id"])
        updated["redo_stack"] = []
    elif operation in ("undo", "redo"):
        key, opposite = (("undo_stack", "redo_stack") if operation == "undo" else ("redo_stack", "undo_stack"))
        if not updated[key]:
            raise VersionHistoryError("No hay una versión disponible para esta operación.")
        selected = _entry(history, updated[key].pop())
        updated[opposite].append(history["active_id"])
    else:
        raise VersionHistoryError("Operación de historial no válida.")
    version_path(job_data, jobs_dir, selected["id"])
    updated.update(active_id=selected["id"], updated_at=_now())
    job_data["version_history"] = updated
    return deepcopy(selected)


def public_history(job_data, jobs_dir):
    history = _history(job_data)
    folder = _storage_dir(job_data, jobs_dir)
    versions = []
    for entry in history["versions"]:
        _blob_path(folder, entry)
        item = {key: entry[key] for key in ("id", "sha256", "label", "created_at", "size_bytes")}
        item["is_active"] = item["id"] == history["active_id"]
        item["is_approved"] = bool(entry.get("is_approved", False))
        versions.append(item)
    return {
        "versions": versions,
        "active_id": history["active_id"],
        "approved_version_id": history.get("approved_version_id"),
        "can_undo": bool(history["undo_stack"]),
        "can_redo": bool(history["redo_stack"]),
        "storage_bytes": _storage_bytes(folder),
        "max_storage_bytes": MAX_VERSION_BYTES,
        "max_versions": MAX_VERSIONS,
        "updated_at": history.get("updated_at"),
    }


def compare_versions(job_data, jobs_dir, version_id_a, version_id_b, page_num=1):
    """Compara metadatos, páginas y dimensiones de dos versiones del historial."""
    history = _history(job_data)
    folder = _storage_dir(job_data, jobs_dir)
    entry_a = _entry(history, version_id_a)
    entry_b = _entry(history, version_id_b)
    path_a = _blob_path(folder, entry_a)
    path_b = _blob_path(folder, entry_b)

    with pymupdf.open(path_a) as doc_a, pymupdf.open(path_b) as doc_b:
        count_a = len(doc_a)
        count_b = len(doc_b)
        safe_page = max(1, min(page_num, max(count_a, count_b)))

        p_a = doc_a[safe_page - 1] if safe_page <= count_a else None
        p_b = doc_b[safe_page - 1] if safe_page <= count_b else None

        dim_a = [round(p_a.rect.width * 25.4 / 72.0, 1), round(p_a.rect.height * 25.4 / 72.0, 1)] if p_a else None
        dim_b = [round(p_b.rect.width * 25.4 / 72.0, 1), round(p_b.rect.height * 25.4 / 72.0, 1)] if p_b else None

    identical_bytes = (entry_a["sha256"] == entry_b["sha256"])

    return {
        "version_a": {
            "id": entry_a["id"],
            "label": entry_a["label"],
            "created_at": entry_a["created_at"],
            "size_bytes": entry_a["size_bytes"],
            "sha256": entry_a["sha256"],
            "page_count": count_a,
            "dimensions_mm": dim_a,
            "is_approved": entry_a.get("is_approved", False),
        },
        "version_b": {
            "id": entry_b["id"],
            "label": entry_b["label"],
            "created_at": entry_b["created_at"],
            "size_bytes": entry_b["size_bytes"],
            "sha256": entry_b["sha256"],
            "page_count": count_b,
            "dimensions_mm": dim_b,
            "is_approved": entry_b.get("is_approved", False),
        },
        "page": safe_page,
        "max_pages": max(count_a, count_b),
        "identical": identical_bytes,
        "size_diff_bytes": entry_b["size_bytes"] - entry_a["size_bytes"],
    }


def render_version_page_image(job_data, jobs_dir, version_id, page_num=1, dpi=120):
    """Renderiza una página de una versión específica a JPEG."""
    history = _history(job_data)
    folder = _storage_dir(job_data, jobs_dir)
    entry = _entry(history, version_id)
    path = _blob_path(folder, entry)

    with pymupdf.open(path) as doc:
        if len(doc) == 0:
            raise VersionHistoryError("El documento no contiene páginas.")
        safe_p = max(0, min(page_num - 1, len(doc) - 1))
        pix = doc[safe_p].get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("jpeg")


def render_version_diff_image(job_data, jobs_dir, version_id_a, version_id_b, page_num=1, dpi=120):
    """Genera una imagen JPEG con el mapa de diferencias visuales entre dos versiones."""
    history = _history(job_data)
    folder = _storage_dir(job_data, jobs_dir)
    entry_a = _entry(history, version_id_a)
    entry_b = _entry(history, version_id_b)
    path_a = _blob_path(folder, entry_a)
    path_b = _blob_path(folder, entry_b)

    with pymupdf.open(path_a) as doc_a, pymupdf.open(path_b) as doc_b:
        safe_a = max(0, min(page_num - 1, len(doc_a) - 1))
        safe_b = max(0, min(page_num - 1, len(doc_b) - 1))

        pix_a = doc_a[safe_a].get_pixmap(dpi=dpi, alpha=False)
        pix_b = doc_b[safe_b].get_pixmap(dpi=dpi, alpha=False)

    img_a = Image.frombytes("RGB", (pix_a.width, pix_a.height), pix_a.samples)
    img_b = Image.frombytes("RGB", (pix_b.width, pix_b.height), pix_b.samples)

    if img_a.size != img_b.size:
        img_b_resized = img_b.resize(img_a.size, Image.Resampling.BILINEAR)
    else:
        img_b_resized = img_b

    # Diferencia entre imágenes
    diff = ImageChops.difference(img_a, img_b_resized)
    gray_diff = diff.convert("L")

    # Si no hay diferencias perceptibles, devolver versión B directa
    base = img_b_resized.convert("RGBA")
    mask = gray_diff.point(lambda p: 255 if p > 8 else 0)

    # Resaltado rojo-magenta en los píxeles cambiados
    highlight = Image.new("RGBA", base.size, (230, 20, 60, 210))
    res = Image.composite(highlight, base, mask)

    out_io = io.BytesIO()
    res.convert("RGB").save(out_io, format="JPEG", quality=85)
    return out_io.getvalue()
