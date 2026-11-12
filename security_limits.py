"""Limits for untrusted requests, PDF geometry and server-side rendering."""

import ctypes
import gc
import math
import asyncio
import re
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

try:
    _LIBC = ctypes.CDLL("libc.so.6")
except Exception:
    _LIBC = None


def release_pdf_memory() -> None:
    """Evict MuPDF's internal C store cache, collect cyclic garbage, and trim glibc heap arenas."""
    try:
        import pymupdf
        pymupdf.TOOLS.store_shrink(100)
    except Exception:
        pass
    gc.collect()
    if _LIBC is not None:
        try:
            _LIBC.malloc_trim(0)
        except Exception:
            pass


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_BATCH_FILES = 10
MAX_PDF_PAGES = 300
MAX_IMAGE_PIXELS = 20_000_000
UPLOAD_TIMEOUT_SEC = 30
MAX_RENDER_PIXELS = 4_000_000
MAX_RENDER_EDGE = 4096
MAX_PREVIEW_DPI = 200
MAX_IMPOSITION_POSES = 2500

# Shared by HTTP work and background subprocess submissions. The request context
# is propagated by Starlette to its worker thread, so a batch request can submit
# to the PDF process without trying to acquire its own slot a second time.
PDF_PROCESSING_SLOT = threading.BoundedSemaphore(1)
_owns_pdf_slot = ContextVar('owns_pdf_slot', default=False)


@contextmanager
def pdf_processing_slot():
    acquired = not _owns_pdf_slot.get()
    if acquired:
        PDF_PROCESSING_SLOT.acquire()
    try:
        yield
    finally:
        if acquired:
            release_pdf_memory()
            PDF_PROCESSING_SLOT.release()


class ResourceLimitError(ValueError):
    pass


def validate_job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError("Identificador de trabajo no válido.")
    return value


def contained_job_path(root, filename):
    """Also reject existing symlinks that would redirect an otherwise safe name."""
    root = Path(root).resolve()
    target = (root / filename).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("La ruta del trabajo queda fuera del directorio permitido.")
    return target


def validate_pdf_resources(pdf_path):
    """Inspect dimensions before any image decoding or page rasterization."""
    import pikepdf
    from pdf_utils import iter_resources
    try:
        with pikepdf.open(pdf_path) as doc:
            if not len(doc.pages):
                raise ValueError("El PDF debe contener páginas.")
            if len(doc.pages) > MAX_PDF_PAGES:
                raise ResourceLimitError(f"El PDF supera el límite de {MAX_PDF_PAGES} páginas.")
            for page in doc.pages:
                box = page.cropbox
                unit = float(page.obj.get('/UserUnit', 1))
                dimensions = ((float(box[2]) - float(box[0])) * unit,
                              (float(box[3]) - float(box[1])) * unit)
                if not all(math.isfinite(v) and 0 < v <= 14400 for v in dimensions):
                    raise ResourceLimitError("Las dimensiones de página exceden el límite de 200 pulgadas.")
            seen = set()
            for page in doc.pages:
                pending = [page]
                forms_seen = set()
                while pending:
                    content = pending.pop()
                    for instruction in pikepdf.parse_content_stream(content):
                        if isinstance(instruction, pikepdf.ContentStreamInlineImage):
                            width, height = instruction.iimage.size
                            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                                raise ResourceLimitError('Una imagen inline supera el límite de 20 megapíxeles.')
                    resources = content.resources if isinstance(content, pikepdf.Page) else content.get('/Resources', {})
                    for obj in resources.get('/XObject', {}).values():
                        if str(obj.get('/Subtype')) == '/Form' and obj.objgen not in forms_seen:
                            forms_seen.add(obj.objgen)
                            pending.append(obj)
            for _, resources in iter_resources(doc):
                for image in resources.get('/XObject', {}).values():
                    if str(image.get('/Subtype')) != '/Image' or image.objgen in seen:
                        continue
                    seen.add(image.objgen)
                    for candidate in (image, image.get('/SMask'), image.get('/Mask')):
                        if isinstance(candidate, pikepdf.Stream):
                            pixels = int(candidate.get('/Width', 0)) * int(candidate.get('/Height', 0))
                            if pixels <= 0 or pixels > MAX_IMAGE_PIXELS:
                                raise ResourceLimitError("Una imagen del PDF supera el límite de 20 megapíxeles.")
    except ResourceLimitError:
        raise
    except Exception as exc:
        raise ValueError("No se pudo abrir un PDF válido y sin cifrado.") from exc


def bounded_render_dpi(rect, dpi):
    """Keep both pixel count and edge length bounded, even on very large pages."""
    width, height = float(rect.width), float(rect.height)
    dpi = float(dpi)
    if not all(math.isfinite(v) and v > 0 for v in (width, height, dpi)):
        raise ValueError("Dimensiones o resolución de previsualización no válidas.")
    scale = min(dpi / 72, 300 / 72,
                math.sqrt(MAX_RENDER_PIXELS / (width * height)),
                MAX_RENDER_EDGE / max(width, height))
    result = max(1, math.floor(scale * 72))
    if math.ceil(width * result / 72) * math.ceil(height * result / 72) > MAX_RENDER_PIXELS:
        result -= 1
    if result < 1 or max(width, height) * result / 72 > MAX_RENDER_EDGE:
        raise ResourceLimitError("La página es demasiado grande para previsualizarla.")
    return result


class RequestLimitsMiddleware:
    """Bound bodies before multipart parsing; keep expensive requests off a flood queue.

    One PDF request runs at a time, with at most four waiting requests. Status,
    profile reads remain available while a PDF is being processed.
    Bodies spool to disk above 1 MiB, including requests without Content-Length.
    """

    def __init__(self, app):
        self.app = app
        self.active = PDF_PROCESSING_SLOT
        self.admitted = threading.BoundedSemaphore(5)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        api = path.startswith("/api/") or path.startswith("/verify/")
        # Report reads and student submissions can rehydrate a didactic PDF, so they also need a slot.
        cheap = (
            path.startswith((
                "/api/profiles",
                "/api/manual/",
                "/api/auth/",
                "/api/admin/",
                "/api/didactic/quiz/",
                "/api/client-approval/info/",
                "/api/client-approval/submit/",
            ))
            or (
                path.startswith("/api/fp/")
                and not path.endswith(("/student/submit", "/report-pdf"))
            )
            or path in (
                "/api/icc-catalog",
                "/api/storage-status",
                "/api/hotfolder/status",
                "/api/hotfolder/start",
                "/api/hotfolder/stop",
                "/api/didactic/scenarios",
                "/api/production-orders/catalogs",
                "/api/production-orders/calculate",
                "/api/validation/standards",
                "/api/jobs",
            )
        )
        expensive = api and not cheap
        admitted = acquired = False
        slot_token = None
        body = None

        async def reject(status, detail):
            response = JSONResponse({"detail": detail}, status_code=status,
                                    headers={"Retry-After": "2"} if status == 429 else None)
            await response(scope, receive, send)

        async def acquire_processing():
            nonlocal acquired, slot_token
            if expensive:
                acquired = await run_in_threadpool(self.active.acquire, timeout=10)
                if not acquired:
                    return False
                slot_token = _owns_pdf_slot.set(True)
            return True

        try:
            if expensive:
                admitted = self.admitted.acquire(blocking=False)
                if not admitted:
                    return await reject(429, "El servidor está ocupado. Reintenta en unos segundos.")

            if scope.get("method") in ("POST", "PUT", "PATCH", "DELETE"):
                limit = (MAX_BATCH_BYTES + 1024 * 1024 if path == "/api/batch/upload" else
                         MAX_FILE_BYTES + 1024 * 1024 if path in ("/api/check", "/api/inspect-pdf") else
                         1024 * 1024)
                headers = dict(scope.get("headers", []))
                try:
                    length = int(headers.get(b"content-length", b"0"))
                except ValueError:
                    return await reject(400, "Content-Length no válido.")
                if length < 0:
                    return await reject(400, "Content-Length no válido.")
                if length > limit:
                    return await reject(413, "La petición supera el tamaño permitido.")
                body = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
                total = 0
                deadline = asyncio.get_running_loop().time() + UPLOAD_TIMEOUT_SEC
                while True:
                    try:
                        message = await asyncio.wait_for(receive(), max(0, deadline - asyncio.get_running_loop().time()))
                    except TimeoutError:
                        return await reject(408, 'Se agotó el tiempo permitido para recibir la petición.')
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    total += len(chunk)
                    if total > limit:
                        return await reject(413, "La petición supera el tamaño permitido.")
                    await run_in_threadpool(body.write, chunk)
                    if not message.get("more_body", False):
                        break
                body.seek(0)
                delivered = False

                async def bounded_receive():
                    nonlocal delivered
                    if delivered:
                        return await receive()
                    chunk = await run_in_threadpool(body.read, 64 * 1024)
                    more = body.tell() < total
                    delivered = not more
                    return {"type": "http.request", "body": chunk, "more_body": more}

                if not await acquire_processing():
                    return await reject(429, 'El servidor está ocupado. Reintenta en unos segundos.')
                await self.app(scope, bounded_receive, send)
            else:
                if not await acquire_processing():
                    return await reject(429, 'El servidor está ocupado. Reintenta en unos segundos.')
                await self.app(scope, receive, send)
        finally:
            if body is not None:
                body.close()
            if acquired:
                release_pdf_memory()
                _owns_pdf_slot.reset(slot_token)
                self.active.release()
            if admitted:
                self.admitted.release()
