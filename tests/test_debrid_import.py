"""debrid 落地文件只触发定向导入，下载与资料失败各自结算。"""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from peach import debrid_client, debrid_import, debrid_service
from peach.migrations import upgrade
from peach.repository import LedgerDatabase
from peach.settings_file import PeachConfig
from peach.task_runs import TaskRunStore

ROOT = Path(__file__).resolve().parents[1]


class DebridImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.media = self.root / 'media'
        self.media.mkdir()
        roots = (str(self.media),) if os.name == 'nt' else ('R:\\media',)
        self.config = PeachConfig(self.root, self.root / 'config.toml', present=True,
            locations={'local': roots}, mounts={} if os.name == 'nt' else {'local': (str(self.media),)})
        self.database = LedgerDatabase(self.root / 'database/ledger.db')
        self.database.db_path.parent.mkdir()
        upgrade(self.database.db_path, ROOT / 'migrations')
        debrid_client.save(self.config, 'alldebrid', {'api_key': 'test-key', 'download_folder': str(self.media), 'auto_import': True})
        self.service = debrid_service.Service(self.config)
        self.service.start = Mock()
        self.addCleanup(self.service.stop)
        self.identity = '1' * 32
        self.video = self.media / 'Example Actor.mp4'
        self.video.write_bytes(b'completed download')
        self.task = dict(id=self.identity, kind='download', status='complete', provider='alldebrid',
            auto_import=True, path=str(self.video), folder=str(self.media), key_stamp=debrid_client.key_stamp(self.config, 'alldebrid'))
        self.service.jobs[self.identity] = dict(self.task)
        self.service.import_progress(self.identity, import_state='pending')
        self.contract = SimpleNamespace(database=self.database, db_path=self.database.db_path,
            candidate_root=self.root / 'generated', cover_root=self.root / 'covers',
            debrid=self.service, cache_bust=Mock(), task_runs=TaskRunStore(self.database), followups=Mock())

    def test_completed_video_uses_single_asset_collection_and_is_idempotent(self):
        with patch('peach.debrid_import.settings_file.active', return_value=self.config), \
                patch('peach.debrid_import.process_library', return_value={'status': 'complete'}) as process, \
                patch('peach.library_processing.scan_location') as scan:
            result = debrid_import.run(self.contract, 'debrid-import:' + self.identity, Mock())
            self.assertEqual(process.call_args.kwargs['asset_ids'], [result['asset_id']])
            self.assertEqual(process.call_args.kwargs['stage'], 'collect')
            scan.assert_not_called()
            self.assertEqual(self.service.job(self.identity)['import_state'], 'complete')
            self.assertTrue(debrid_import.run(self.contract, 'debrid-import:' + self.identity, Mock())['already_complete'])
            self.assertEqual(process.call_count, 1)
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM asset').fetchone()[0], 1)

    def test_provider_option_requires_a_library_folder_and_is_independent(self):
        outside = self.root / 'outside'
        outside.mkdir()
        with self.assertRaises(ValueError):
            debrid_client.save(self.config, 'realdebrid', {'download_folder': str(outside), 'auto_import': True})
        with self.assertRaises(ValueError):
            debrid_client.save(self.config, 'realdebrid', {'auto_import': 'yes'})
        settings = debrid_client.settings(self.config)['providers']
        self.assertTrue(settings[0]['auto_import'])
        self.assertFalse(settings[1]['auto_import'])
        location, path = debrid_import.import_target(self.config, self.video)
        self.assertEqual(location, 'local')
        self.assertTrue(path.endswith('\\Example Actor.mp4'))
        self.assertNotIn('api_key', str(settings))

    def test_import_failure_preserves_completed_download_and_retry_does_not_download(self):
        with patch('peach.debrid_import.settings_file.active', return_value=self.config), \
                patch('peach.debrid_import.process_library', return_value={'status': 'failed'}), \
                self.assertRaises(ValueError):
            debrid_import.run(self.contract, 'debrid-import:' + self.identity, Mock())
        self.assertEqual(self.service.job(self.identity)['status'], 'complete')
        self.assertEqual(self.service.job(self.identity)['import_state'], 'failed')
        with patch('peach.debrid_transfer.transfer') as download:
            self.service.retry_import(self.identity)
            download.assert_not_called()
        self.assertTrue(self.video.is_file())
        self.assertEqual(self.service.job(self.identity)['import_state'], 'pending')

    def test_import_queue_waits_for_library_processing_and_deduplicates_followups(self):
        with patch('peach.debrid_import.settings_file.active', return_value=self.config), \
                patch('peach.debrid_import._busy', return_value=True):
            self.assertIsNone(debrid_import.enqueue(self.contract, self.task))
        with patch('peach.debrid_import.settings_file.active', return_value=self.config):
            first = debrid_import.enqueue(self.contract, self.task)
            second = debrid_import.enqueue(self.contract, self.task)
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        self.service.import_progress(self.identity, import_state='queued')
        self.service.cancel(self.identity)
        self.assertEqual(self.service.job(self.identity)['status'], 'complete')
        with patch('peach.debrid_import.process_library') as process:
            debrid_import.run(self.contract, 'debrid-import:' + self.identity, Mock())
            process.assert_not_called()

    def test_transfer_completion_dispatches_import_and_restart_retains_pending_work(self):
        after = Mock(return_value=7)
        self.service.after_download = after
        self.service.jobs[self.identity]['status'] = 'queued'
        def transfer(task, *, update, active):
            self.assertTrue(active())
            after.assert_not_called()
            update(status='complete', path=str(self.video))
        with patch('peach.debrid_transfer.transfer', side_effect=transfer):
            self.service._run(dict(self.service.jobs[self.identity]))
        self.assertEqual(after.call_count, 1)
        self.assertEqual(self.service.job(self.identity)['import_state'], 'queued')
        self.service.import_progress(self.identity, import_state='running')
        restored = debrid_service.Service(self.config)
        self.assertEqual(restored.job(self.identity)['status'], 'complete')
        self.assertEqual(restored.job(self.identity)['import_state'], 'pending')
