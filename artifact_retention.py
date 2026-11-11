"""Retention for generated artifacts, with containment and link checks before deletion."""

import shutil
import stat
from os.path import normcase
from pathlib import Path

from security_limits import validate_job_id


def _is_link(info):
    # Includes Windows junctions and other reparse points on Python 3.11 too.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def _checked_root(root):
    root = Path(root).absolute()
    if _is_link(root.lstat()):
        raise ValueError(f'Carpeta gestionada enlazada: {root.name}')
    return root.resolve()


def _tree_info(path, root):
    """Inspect the whole tree without following links; never accept the root itself."""
    info = path.lstat()
    if _is_link(info):
        raise ValueError(f'Enlace o punto de análisis omitido: {path.name}')
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f'Ruta fuera de la carpeta gestionada: {path.name}')
    if stat.S_ISREG(info.st_mode):
        return info.st_size, 1, info.st_mtime
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f'Tipo de archivo no gestionado: {path.name}')
    children = list(path.iterdir())
    # Directory mtimes change when artifacts are removed. Use file activity for
    # nonempty trees, so deleting one artifact does not renew the job's retention.
    if not children:
        return 0, 0, info.st_mtime
    inspected = [_tree_info(child, root) for child in children]
    return (sum(item[0] for item in inspected), sum(item[1] for item in inspected),
            max(item[2] for item in inspected))


def _entries(roots, errors):
    entries = []
    for root in dict.fromkeys(map(Path, roots)):
        try:
            checked = _checked_root(root)
            entries.extend((child, checked) for child in checked.iterdir()
                           if not child.name.startswith('.') or child.name.startswith('.intelliprint_'))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return entries


def artifact_storage_bytes(root):
    total = 0
    for path, checked in _entries([root], []):
        try:
            total += _tree_info(path, checked)[0]
        except (OSError, ValueError):
            continue
    return total


def cleanup_expired_artifacts(jobs_dir, upload_dir, worksheets_dir, output_dirs, cutoff):
    """Expire a job only after its newest artifact; clean old orphans independently.

    Job IDs come from manifest filenames, never from paths in untrusted JSON.
    The manifest is removed last, so a failed deletion can be retried later.
    Input and processing hotfolders are deliberately outside the managed roots.
    """
    result = {'deleted_jobs': 0, 'deleted_files': 0, 'freed_bytes': 0, 'errors': []}
    entries = _entries([jobs_dir, upload_dir, worksheets_dir, *output_dirs], result['errors'])
    jobs_root = Path(jobs_dir).resolve()
    upload_root = Path(upload_dir).resolve()
    worksheet_root = Path(worksheets_dir).resolve()
    manifests = {}
    for path, root in entries:
        if root == jobs_root and path.suffix == '.json':
            try:
                validate_job_id(path.stem)
            except ValueError:
                continue
            manifests[path.stem] = path
    job_ids = sorted(manifests, key=len, reverse=True)
    groups = {job_id: [] for job_id in job_ids}
    orphans = []
    for path, root in entries:
        owner = None
        name = normcase(path.name)
        if root != worksheet_root:
            for job_id in job_ids:
                job_name = normcase(job_id)
                if root == upload_root:
                    matches = name == job_name
                else:
                    matches = (name in (job_name, job_name + '.json')
                               or name.startswith(job_name + '_'))
                if matches:
                    owner = job_id
                    break
        if owner is None:
            orphans.append((path, root))
        else:
            groups[owner].append((path, root))

    def inspect(path, root):
        try:
            return _tree_info(path, root)
        except FileNotFoundError:
            return 0, 0, float('-inf')
        except (OSError, ValueError) as exc:
            result['errors'].append(f'{path.name}: {exc}')
            return None

    def remove(path, root):
        try:
            # Recheck immediately before recursive removal. Nothing outside the
            # verified managed root, including a nested junction, is traversed.
            info = inspect(path, root)
            if info is None or info[2] >= cutoff:
                return False
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            result['freed_bytes'] += info[0]
            result['deleted_files'] += info[1]
            return True
        except OSError as exc:
            result['errors'].append(f'{path.name}: {exc}')
            return False

    for job_id, members in groups.items():
        info = [inspect(path, root) for path, root in members]
        if any(item is None or item[2] >= cutoff for item in info):
            continue
        manifest = manifests[job_id]
        complete = True
        for path, root in members:
            if path != manifest:
                complete = remove(path, root) and complete
        if complete and remove(manifest, jobs_root):
            result['deleted_jobs'] += 1

    for path, root in orphans:
        remove(path, root)
    return result
