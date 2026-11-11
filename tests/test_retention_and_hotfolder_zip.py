"""ZIP downloads and safe retention regressions for audit findings 17 and 18."""

import io
import json
import os
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import app
import artifact_retention as retention
import test_regressions as base


class ArtifactRetentionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.jobs, self.uploads, self.worksheets, self.approved, self.rejected = (
            self.root / name for name in ('jobs', 'uploads', 'worksheets', 'approved', 'rejected'))
        for directory in self.managed:
            directory.mkdir()
            (directory / '.gitkeep').write_bytes(b'')
        self.cutoff = time.time() - 24 * 3600
        self.old = self.cutoff - 60
        self.recent = self.cutoff + 60

    @property
    def managed(self):
        return self.jobs, self.uploads, self.worksheets, self.approved, self.rejected

    def file(self, path, data=b'example', recent=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        age = self.recent if recent else self.old
        os.utime(path, (age, age))
        return path

    def manifest(self, job_id, recent=False, metadata=None):
        return self.file(self.jobs / (job_id + '.json'),
            json.dumps({'job_meta': metadata or {'job_id': job_id}}).encode(), recent)

    def cleanup(self):
        return retention.cleanup_expired_artifacts(self.jobs, self.uploads,
            self.worksheets, (self.approved, self.rejected), self.cutoff)

    def test_old_job_removes_nested_cip3_uploads_and_all_hotfolder_outputs(self):
        self.manifest('expired_job')
        self.file(self.jobs / 'expired_job' / 'nested' / 'CIP3.ppf')
        self.file(self.jobs / 'expired_job_fixed.pdf')
        self.file(self.uploads / 'expired_job' / 'source.pdf')
        self.file(self.approved / 'expired_job_result.pdf')
        self.file(self.rejected / 'expired_job_certificate.pdf')
        expected = sum(retention.artifact_storage_bytes(root) for root in self.managed)
        result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertEqual(result['deleted_files'], 6)
        self.assertEqual(result['freed_bytes'], expected)
        self.assertEqual(result['errors'], [])
        for root in self.managed:
            self.assertEqual([p.name for p in root.iterdir()], ['.gitkeep'])

    def test_recent_jobs_and_recent_artifacts_preserve_the_whole_job(self):
        self.manifest('recent', recent=True)
        recent_source = self.file(self.uploads / 'recent' / 'source.pdf')
        old_manifest = self.manifest('renewed')
        new_ppf = self.file(self.jobs / 'renewed' / 'CIP3.ppf', recent=True)
        old_output = self.file(self.approved / 'renewed_old.pdf')
        result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 0)
        self.assertTrue(all(p.exists() for p in (recent_source, old_manifest, new_ppf, old_output)))

    def test_standalone_worksheets_and_orphan_outputs_expire_by_their_own_age(self):
        expired = [self.file(self.worksheets / 'worksheet_old.pdf'),
                   self.file(self.approved / 'orphan_old.pdf'),
                   self.file(self.rejected / 'orphan_old.pdf'),
                   self.file(self.uploads / 'orphan' / 'source.pdf'),
                   self.file(self.jobs / 'orphan_cip3' / 'data.ppf')]
        recent = [self.file(self.worksheets / 'worksheet_new.pdf', recent=True),
                  self.file(self.approved / 'orphan_new.pdf', recent=True)]
        for name in ('in', 'processing'):
            recent.append(self.file(self.root / 'hotfolder' / name / 'pending.pdf'))
        result = self.cleanup()
        self.assertEqual(result['deleted_files'], 5)
        self.assertTrue(all(not p.exists() for p in expired))
        self.assertTrue(all(p.exists() for p in recent))

    def test_prefix_collisions_do_not_delete_another_live_job(self):
        self.manifest('abc')
        self.manifest('abc_extra', recent=True)
        live = [self.file(self.jobs / 'abc_extra_fixed.pdf'),
                self.file(self.approved / 'abc_extra_result.pdf'),
                self.file(self.uploads / 'abc_extra' / 'source.pdf')]
        self.manifest('abcdef', recent=True)
        live.append(self.file(self.jobs / 'abcdef_fixed.pdf'))
        result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertTrue(all(p.exists() for p in live))

    @unittest.skipUnless(os.name == 'nt', 'Windows job paths are case-insensitive.')
    def test_windows_case_variants_still_belong_to_the_recent_job(self):
        self.manifest('recent_job', recent=True)
        output = self.file(self.approved / 'RECENT_JOB_result.pdf')
        source = self.file(self.uploads / 'RECENT_JOB' / 'source.pdf')
        cip3 = self.file(self.jobs / 'RECENT_JOB' / 'CIP3.ppf')
        result = self.cleanup()
        self.assertEqual(result['deleted_files'], 0)
        self.assertTrue(all(p.exists() for p in (output, source, cip3)))

    def test_manifest_contents_cannot_redirect_cleanup_outside_managed_roots(self):
        outside = self.file(self.root / 'outside' / 'keep.pdf')
        self.manifest('safe', metadata={'job_id': '../outside', 'pdf_path': str(outside)})
        self.file(self.jobs / 'safe' / 'CIP3.ppf')
        self.file(self.uploads / 'safe' / 'source.pdf')
        result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertEqual(outside.read_bytes(), b'example')

    def test_corrupt_manifest_uses_its_complete_filename_without_truncating_id(self):
        self.file(self.jobs / 'fp_long_job_id.json', b'not json')
        self.file(self.uploads / 'fp_long_job_id' / 'source.pdf')
        self.file(self.jobs / 'fp_long_job_id' / 'CIP3.ppf')
        result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertFalse((self.uploads / 'fp_long_job_id').exists())

    def test_a_failed_deletion_keeps_the_manifest_and_does_not_interrupt_other_jobs(self):
        kept_manifest = self.manifest('locked')
        locked = self.file(self.jobs / 'locked' / 'CIP3.ppf')
        self.manifest('other')
        self.file(self.uploads / 'other' / 'source.pdf')
        original = retention.shutil.rmtree
        locked_folder = locked.parent.resolve()

        def refuse(path, *args, **kwargs):
            if Path(path) == locked_folder:
                raise PermissionError('file in use')
            return original(path, *args, **kwargs)

        with patch.object(retention.shutil, 'rmtree', refuse):
            result = self.cleanup()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertTrue(kept_manifest.exists())
        self.assertTrue(locked.exists())
        self.assertTrue(result['errors'])
        self.assertFalse((self.jobs / 'other.json').exists())
        self.assertEqual(self.cleanup()['deleted_jobs'], 1)

    def test_windows_reparse_points_are_rejected_before_recursive_removal(self):
        manifest = self.manifest('unsafe')
        folder = self.file(self.jobs / 'unsafe' / 'keep.ppf').parent
        linked_folder = folder.resolve()
        original = Path.lstat

        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == linked_folder:
                class LinkedInfo:
                    st_mode = info.st_mode
                    st_file_attributes = 0x400
                return LinkedInfo()
            return info

        with patch.object(Path, 'lstat', reparse), patch.object(retention.shutil, 'rmtree') as remove:
            result = self.cleanup()
        remove.assert_not_called()
        self.assertTrue(manifest.exists())
        self.assertTrue(folder.exists())
        self.assertTrue(result['errors'])

    def test_actual_directory_link_is_never_followed(self):
        outside = self.file(self.root / 'outside' / 'keep.pdf')
        link = self.jobs / 'linked'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside.parent)],
                           check=True, capture_output=True)
            self.addCleanup(os.rmdir, link)
        else:
            link.symlink_to(outside.parent, target_is_directory=True)
            self.addCleanup(link.unlink)
        result = self.cleanup()
        self.assertTrue(result['errors'])
        self.assertTrue(link.exists())
        self.assertEqual(outside.read_bytes(), b'example')


class HotfolderAndCleanupEndpointTests(unittest.TestCase):
    def setUp(self):
        base.RegressionTests.setUp(self)
        self.worksheets, self.approved, self.rejected = (
            self.root / name for name in ('worksheets', 'approved', 'rejected'))
        for name, path in (('WORKSHEETS_DIR', self.worksheets), ('APPROVED_DIR', self.approved),
                           ('REJECTED_DIR', self.rejected)):
            path.mkdir()
            patcher = patch.object(app, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_jobs_are_retained_for_a_full_day_before_cleanup(self):
        now = float(int(time.time()))
        job_files = {}
        for job_id, age_seconds in (
            ('six_hours', 6 * 3600),
            ('within_day', 24 * 3600 - 1),
            ('at_boundary', 24 * 3600),
            ('expired_day', 24 * 3600 + 1),
        ):
            paths = [self.jobs / f'{job_id}.json',
                     self.uploads / job_id / 'source.pdf',
                     self.jobs / f'{job_id}_fixed.pdf']
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'{}' if path.suffix == '.json' else b'%PDF example')
                modified = now - age_seconds
                os.utime(path, (modified, modified))
            job_files[job_id] = paths

        with patch.object(app.time, 'time', return_value=now):
            status = self.client.get('/api/storage-status').json()
            self.assertEqual(status['ttl_hours'], 24)
            self.assertIn('24 horas', status['note'])
            response = self.client.post('/api/cleanup-now')

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertEqual(result['deleted_files'], 3)
        self.assertEqual(result['remaining_jobs'], 3)
        self.assertEqual(result['errors'], [])
        for job_id, paths in job_files.items():
            with self.subTest(job_id=job_id):
                self.assertTrue(all(path.exists() == (job_id != 'expired_day') for path in paths))

    def test_hotfolder_zip_contains_each_regular_output_file_with_correct_bytes(self):
        for category, directory in (('approved', self.approved), ('rejected', self.rejected)):
            with self.subTest(category=category):
                files = {'job_source.pdf': b'%PDF example', 'job_certificate.pdf': b'%PDF certificate',
                         'job_report.json': b'{"status":"FAIL"}', 'notes': b'operator note'}
                for name, data in files.items():
                    (directory / name).write_bytes(data)
                (directory / '.gitkeep').touch()
                (directory / 'folder.pdf').mkdir()
                response = self.client.get('/api/hotfolder/download-all/' + category)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers['content-type'], 'application/zip')
                self.assertIn('.zip', response.headers['content-disposition'])
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(set(archive.namelist()), set(files))
                    self.assertEqual({name: archive.read(name) for name in archive.namelist()}, files)

    def test_empty_or_invalid_category_does_not_download_an_unrelated_folder(self):
        (self.approved / '.gitkeep').touch()
        self.assertEqual(self.client.get('/api/hotfolder/download-all/approved').status_code, 404)
        (self.rejected / 'keep.pdf').write_bytes(b'not approved')
        self.assertEqual(self.client.get('/api/hotfolder/download-all/invalid').status_code, 422)

    def test_cleanup_endpoint_counts_all_managed_storage_and_handles_cip3_directories(self):
        old = time.time() - (app.JOB_TTL_HOURS + 1) * 3600
        files = [(self.jobs / 'expired.json', b'{"job_meta":{"job_id":"expired"}}'),
                 (self.jobs / 'expired' / 'CIP3.ppf', b'PPF'),
                 (self.uploads / 'expired' / 'source.pdf', b'PDF'),
                 (self.worksheets / 'worksheet_old.pdf', b'W' * 1024**2),
                 (self.approved / 'expired_result.pdf', b'A' * 1024**2),
                 (self.rejected / 'expired_report.pdf', b'R' * 1024**2)]
        for path, data in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.utime(path, (old, old))
        status = self.client.get('/api/storage-status').json()
        self.assertEqual(status['worksheets_mb'], 1)
        self.assertEqual(status['hotfolder_mb'], 2)
        response = self.client.post('/api/cleanup-now')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['deleted_jobs'], 1)
        self.assertEqual(result['deleted_files'], 6)
        self.assertEqual(result['freed_mb'], 3)
        self.assertEqual(result['errors'], [])
        self.assertEqual(self.client.get('/api/storage-status').json()['total_mb'], 0)


if __name__ == '__main__':
    unittest.main()
