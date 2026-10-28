"""媒体目录的独立发现范围、嵌套身份与关闭自动重扫的回归。"""
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock, patch
from contextlib import closing

from peach import media_configuration, media_scan_schedule, settings_file, web_media_scan_schedule
from peach.library_processing import _scan_sources
from tests.support.ledger import fresh_ledger


class MediaScanScheduleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = settings_file.PeachConfig(self.root, self.root / 'config.toml', present=True,
            locations={'local': (r'R:\videos', r'R:\videos\new')}, media_scan_updates={r'R:\videos': False})

    def test_nested_mounts_share_identity_and_roundtrip_scan_preferences(self):
        raw = [{'location': 'local', 'path': '/videos', 'scan_updates': False},
               {'location': 'local', 'path': '/videos/new', 'scan_hours': 2}]
        prepared = media_configuration.prepare_sources(raw, windows=False)
        parent, child = [PureWindowsPath(row['root']) for row in prepared]
        self.assertEqual(child, parent / 'new')
        locations, mounts, errors = media_configuration.validate(prepared, windows=False)
        self.assertEqual(errors, [])
        config = replace(self.config, locations=locations, mounts=mounts,
                         **media_configuration.scan_preferences(prepared, windows=False))
        settings_file.write(config)
        loaded = settings_file.load_config(environ={'PEACH_DATA_ROOT': str(self.root)})
        self.assertFalse(loaded.media_scan_updates[str(parent)])
        self.assertEqual(loaded.media_scan_hours[str(parent)], 0)
        self.assertEqual(loaded.media_scan_hours[str(child)], 2)
        self.assertEqual(raw[1].get('root'), None)

    def test_zero_hours_never_schedules_and_due_roots_use_find_new(self):
        job = Mock(return_value={'job_id': 'scoped'})
        contract = Mock()
        with patch('peach.settings_file.active', return_value=self.config), \
                patch('peach.web_media_scan_schedule._current', return_value={}), \
                patch('peach.web_media_scan_schedule.w_library_processing', job):
            web_media_scan_schedule.check_due(contract, now=100)
            web_media_scan_schedule.check_due(contract, now=1000000)
            job.assert_not_called()
        config = replace(self.config, media_scan_hours={r'R:\videos\new': 2})
        with patch('peach.settings_file.active', return_value=config), \
                patch('peach.web_media_scan_schedule._current', return_value={}), \
                patch('peach.web_media_scan_schedule.w_library_processing', job):
            web_media_scan_schedule.check_due(contract, now=100)
            web_media_scan_schedule.check_due(contract, now=7299)
            job.assert_not_called()
            web_media_scan_schedule.check_due(contract, now=7300)
            self.assertEqual(job.call_args.args[1], {'stage': 'find_new', 'scan_roots': [r'R:\videos\new']})
            media_scan_schedule.record_scanned(config, r'R:\videos\new', now=7300)
            job.reset_mock()
            web_media_scan_schedule.check_due(contract, now=8000)
            job.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', '使用临时 Windows 媒体路径')
    def test_parent_discovery_prunes_separately_configured_children(self):
        media = self.root / 'videos'
        child, archived = media / 'new', media / 'archive'
        child.mkdir(parents=True)
        archived.mkdir()
        (media / 'old.mp4').write_bytes(b'old')
        (child / 'new.mp4').write_bytes(b'new')
        (archived / 'hidden.mp4').write_bytes(b'archive')
        config = replace(self.config, locations={'local': tuple(map(str, (media, child, archived)))},
                         media_scan_updates={str(archived): False})
        database = fresh_ledger(self.root)
        locations = media_scan_schedule.processing_locations(config, 'configured', 'find_new', False, None)
        with patch('peach.scan.os.scandir', wraps=os.scandir) as walk:
            result = _scan_sources(config, database, locations=locations, asset_ids=None, stage='find_new',
                guard=Mock(), update=lambda **kw: None, issue=lambda *args: None)
        self.assertEqual(result.scanned, 2)
        self.assertFalse(any(Path(call.args[0]).is_relative_to(archived) for call in walk.call_args_list))
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM asset').fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM asset WHERE path LIKE '%new.mp4'").fetchone()[0], 1)

    def test_nested_sources_and_duplicate_paths_are_rejected(self):
        self.assertTrue(media_configuration.validate([
            {'location': 'local', 'path': '/videos'}, {'location': '115', 'path': '/videos/new'}], windows=False)[2])
        self.assertTrue(media_configuration.validate([
            {'location': 'local', 'path': '/videos'}, {'location': 'local', 'path': '/videos'}], windows=False)[2])
