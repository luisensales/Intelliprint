"""Identity of the uploaded, current and authorized PDF versions."""

import hashlib
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def clear_pdf_authorization(job_data):
    job_data.setdefault('triple_result', {})['release'] = {
        'status': 'PENDING_AUTHORIZATION',
        'label': 'Pendiente de autorizar el PDF actual',
    }
    job_data.setdefault('job_meta', {}).pop('authorized_sha256', None)


def update_pdf_identity(job_data, pdf_path, original_sha256=None):
    """Keep sha256 compatible with clients: it always identifies the current PDF."""
    meta = job_data.setdefault('job_meta', {})
    previous = meta.get('current_sha256') or meta.get('sha256')
    current = sha256_file(pdf_path)
    meta.setdefault('original_sha256', original_sha256 or previous or current)
    meta.update(sha256=current, current_sha256=current,
                file_size_mb=round(Path(pdf_path).stat().st_size / 1024**2, 2))
    if previous and previous != current:
        clear_pdf_authorization(job_data)
        meta.pop('barcode_inspection', None)
        for key in ('imposed_pdf_path', 'imposition_source_sha256', 'last_imposition_plan', 'last_cip3_calculation'):
            meta.pop(key, None)
    return current
