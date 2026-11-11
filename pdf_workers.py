"""Background PDF work runs on the main thread of a separate spawn process.

Only paths, options and JSON-compatible reports cross the process boundary;
MuPDF documents, pages and pixmaps always stay in the process that opened them.
One worker bounds memory and prevents batch/hotfolder tasks from overlapping.
"""

import atexit
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from security_limits import pdf_processing_slot

_pool = None
_pool_lock = threading.Lock()


def shutdown_pdf_workers():
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)


atexit.register(shutdown_pdf_workers)


def run_pdf_task(function, *args):
    with pdf_processing_slot():
        return _run_pdf_task(function, *args)


def _run_pdf_task(function, *args):
    """Submit a trusted module-level callable; recover the pool after native failure."""
    global _pool
    try:
        with _pool_lock:
            if _pool is None:
                _pool = ProcessPoolExecutor(max_workers=1,
                                           mp_context=multiprocessing.get_context('spawn'))
            pool = _pool
            future = pool.submit(function, *args)
        return future.result()
    except BrokenProcessPool as exc:
        with _pool_lock:
            if _pool is pool:
                _pool = None
        pool.shutdown(wait=False, cancel_futures=True)
        raise RuntimeError('El proceso PDF se ha interrumpido. El trabajo no se ha completado.') from exc


def profile_paths():
    import profile_manager
    return {name: str(getattr(profile_manager, name))
            for name in ('CUSTOM_PROFILES_FILE', 'STANDARD_PROFILES_FILE')}


def _set_profile_paths(paths):
    import profile_manager
    for name, value in paths.items():
        setattr(profile_manager, name, Path(value))


def preflight_in_worker(pdf_path, profile_id, icc_option, selected_icc, profiles):
    _set_profile_paths(profiles)
    from preflight_engine import IntelliPrintEngine
    return IntelliPrintEngine().run_preflight(pdf_path, profile_id=profile_id,
                                             icc_choice=icc_option, selected_icc=selected_icc)


def hotfolder_in_worker(file_path, paths, options, profiles, job_id):
    _set_profile_paths(profiles)
    import hotfolder_engine
    for name, value in paths.items():
        setattr(hotfolder_engine, name, Path(value))
    service = hotfolder_engine.HotFolderService()
    for name, value in options.items():
        setattr(service, name, value)
    return service._process_file_in_worker(Path(file_path), job_id)
