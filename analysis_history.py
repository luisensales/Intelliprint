"""Keep the first preflight separate from the analysis of the corrected PDF."""

from copy import deepcopy
from pathlib import Path

from document_identity import sha256_file


def capture_original_analysis(job_data, analysis=None):
    """Capture once; later changes to current findings cannot change this snapshot."""
    if "original_analysis" in job_data:
        return False
    source = job_data if analysis is None else analysis
    technical = source.get("triple_result", {}).get("technical")
    if source.get("error") or not isinstance(technical, dict):
        return False
    job_data["original_analysis"] = {
        "job_summary": deepcopy(source.get("job_summary", {})),
        "findings": deepcopy(source.get("findings", [])),
        "triple_result": {"technical": deepcopy(technical)},
    }
    job_data.pop("original_analysis_unavailable", None)
    return True


def _has_corrections(meta):
    return bool(meta.get("applied_fixes_history") or meta.get("batch_steps_applied")
                or meta.get("last_fixed_pdf_path") or meta.get("batch_fixed_pdf_path")
                or any(key.startswith("has_") and value for key, value in meta.items()))


def _original_source(meta, source_roots, corrected):
    candidate = meta.get("original_pdf_path") or meta.get("pdf_path")
    if not candidate:
        return None
    path = Path(candidate).resolve()
    if not path.is_file():
        return None
    roots = [Path(root).resolve() for root in source_roots]
    if roots and not any(path.is_relative_to(root) for root in roots):
        return None
    if corrected:
        # Older hotfolder jobs can point pdf_path at the corrected output.
        for key, value in meta.items():
            if key.endswith("_pdf_path") and key != "original_pdf_path" and value:
                if path == Path(value).resolve():
                    return None
        original_hash = meta.get("original_sha256")
        if original_hash and sha256_file(path) != original_hash:
            return None
    return path


def ensure_original_analysis(job_data, run_preflight, source_roots=()):
    """Recover legacy history only from the original source, never a fixed PDF.

    History recovery is best effort: a missing source must not block correction.
    Return whether persisted history metadata changed.
    """
    if "original_analysis" in job_data:
        return False
    meta = job_data.get("job_meta", {})
    if not isinstance(meta, dict):
        meta = {}
    corrected = _has_corrections(meta)
    reason = "No se conserva el PDF original para recuperar el análisis inicial."
    try:
        source = _original_source(meta, source_roots, corrected)
        if source is not None:
            initial = run_preflight(str(source),
                                    profile_id=meta.get("profile_id", "OFFSET_300"),
                                    icc_choice="preserve")
            if capture_original_analysis(job_data, initial):
                return True
            reason = "No se pudo verificar el PDF original para recuperar el análisis inicial."
        elif not corrected and capture_original_analysis(job_data):
            return True
    except Exception:
        reason = "No se pudo verificar el PDF original para recuperar el análisis inicial."
    if job_data.get("original_analysis_unavailable") == reason:
        return False
    job_data["original_analysis_unavailable"] = reason
    return True
