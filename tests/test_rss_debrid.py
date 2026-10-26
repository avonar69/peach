"""使用临时账本、RSS 字节与假服务响应验证订阅下载。"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from peach import debrid_client, debrid_service, debrid_transfer, feeds, public_download_http, rss_feeds, web_rss
from peach.migrations import upgrade
from peach.repository import LedgerDatabase
from peach.routes_auth import require_auth
from peach.routes_rss import router
from peach.settings_file import PeachConfig

ROOT = Path(__file__).resolve().parents[1]
MAGNET = 'magnet:?xt=urn:btih:' + '1' * 40
RSS = f'''<rss version="2.0"><channel><title>Example feed</title><item><guid>scene-1</guid>
<title>Example studio scene without a release code</title><pubDate>Sat, 24 Oct 2026 10:00:00 GMT</pubDate>
<link>https://example.org/scene</link><enclosure url="{MAGNET}" type="application/x-bittorrent"/>
<description><![CDATA[<a href="https://rg.to/file/test">Download</a> https://example.org/media.torrent]]></description>
</item></channel></rss>'''.encode()


class RSSDebridTests(unittest.TestCase):
    def test_saved_posts_survive_feed_rotation_and_changed_ids_merge_links(self):
        with self.database.write_transaction() as connection:
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            rss_feeds.poll(connection, source, RSS)
            original = dict(connection.execute('SELECT * FROM feed_item WHERE source_id=?', (self.source,)).fetchone())
            rss_feeds.poll(connection, source, b'<rss version="2.0"><channel><title>Rotated</title></channel></rss>')
            self.assertEqual(connection.execute('SELECT count(*) FROM feed_item').fetchone()[0], 1)
            changed = RSS.replace(b'scene-1</guid>', b'new-id</guid>').replace(b'/file/test', b'/file/updated')
            result = rss_feeds.poll(connection, source, changed)
        self.assertEqual(result['added'], 0)
        saved = rss_feeds.items(self.database)['items'][0]
        self.assertEqual(saved['id'], original['id'])
        self.assertEqual(saved['first_seen'], original['first_seen'])
        self.assertTrue({'https://rg.to/file/test', 'https://rg.to/file/updated'}.issubset({item['url'] for item in saved['links']}))

    def test_retention_expires_content_and_preserves_dedup_memory_per_source(self):
        from datetime import datetime, timezone
        with self.database.write_transaction() as connection:
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            rss_feeds.poll(connection, source, RSS)
            other = feeds.add_source(connection, url='https://other.example.org/feed', kind='rss')
            other_source = connection.execute('SELECT * FROM feed_source WHERE id=?', (other,)).fetchone()
            rss_feeds.poll(connection, other_source, RSS)
            connection.execute("UPDATE feed_item SET first_seen='2026-01-01T00:00:00Z'")
            connection.execute("UPDATE feed_source SET rss_retention_count=2,rss_retention_unit='months',enabled=0 WHERE id=?", (self.source,))
            self.assertEqual(rss_feeds.expire(connection, now=datetime(2026, 4, 1, tzinfo=timezone.utc)), 1)
            expired = connection.execute('SELECT * FROM feed_item WHERE source_id=?', (self.source,)).fetchone()
            self.assertIsNone(expired['title'])
            self.assertEqual(expired['download_links_json'], '[]')
            self.assertEqual(expired['rss_images_json'], '{}')
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            rss_feeds.poll(connection, source, RSS.replace(b'scene-1</guid>', b'another-id</guid>'))
            self.assertEqual(connection.execute('SELECT count(*) FROM feed_item WHERE source_id=?', (self.source,)).fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(rss_feeds.count_items(self.database), 1)
        self.assertEqual(rss_feeds.items(self.database)['items'][0]['source_id'], other)

    def test_retention_settings_validate_units_and_calendar_boundaries(self):
        from datetime import datetime, timezone
        contract = SimpleNamespace(database=self.database)
        for count, unit in ((30, 'days'), (6, 'months'), (2, 'years'), (None, 'days')):
            web_rss.source_action(contract, {'action': 'retention', 'id': self.source, 'count': count, 'unit': unit})
            with self.database.read_connection() as connection:
                saved = feeds.sources(connection)[0]
            self.assertEqual((saved['rss_retention_count'], saved['rss_retention_unit']), (count, unit))
        for count, unit in ((0, 'days'), (-1, 'months'), (True, 'days'), (1.5, 'years'), (101, 'years'), (1201, 'months'), (1, [])):
            with self.assertRaises(ValueError):
                web_rss.source_action(contract, {'action': 'retention', 'id': self.source, 'count': count, 'unit': unit})
        self.assertEqual(rss_feeds.retention_cutoff(datetime(2024, 3, 31, tzinfo=timezone.utc), 1, 'months').day, 29)
        self.assertEqual(rss_feeds.retention_cutoff(datetime(2024, 2, 29, tzinfo=timezone.utc), 1, 'years').day, 28)

    def test_legacy_duplicate_post_urls_merge_and_source_removal_cleans_identity_rows(self):
        old = rss_feeds.parse(RSS, 'https://example.org/feed')[1][0]
        changed_body = RSS.replace(b'scene-1</guid>', b'new-id</guid>')
        new = rss_feeds.parse(changed_body, 'https://example.org/feed')[1][0]
        with self.database.write_transaction() as connection:
            for row in (old, new):
                feeds.record_entry(connection, self.source, feeds.FeedEntry(row['key'], row['title'], 'https://example.org/scene', row['published_at']), code=None)
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            rss_feeds.poll(connection, source, changed_body)
            self.assertEqual(connection.execute('SELECT count(*) FROM feed_item WHERE rss_merged_into IS NOT NULL').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM feed_item WHERE rss_merged_into IS NULL AND rss_expired_at IS NULL').fetchone()[0], 1)
            feeds.remove_source(connection, self.source)
            self.assertEqual(connection.execute('SELECT count(*) FROM rss_item_identity').fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_rss_schedules_default_to_six_hours_and_can_be_changed_or_disabled(self):
        from datetime import datetime, timezone
        from peach import web_feeds
        contract = SimpleNamespace(database=self.database)
        with self.database.read_connection() as connection:
            saved = feeds.sources(connection)[0]
        self.assertEqual(saved['interval_minutes'], 360)
        self.assertTrue(saved['enabled'])
        for enabled in (False, True):
            web_rss.source_action(contract, {'action': 'schedule', 'id': self.source,
                'enabled': enabled, 'interval_minutes': 120})
            with self.database.read_connection() as connection:
                saved = feeds.sources(connection)[0]
                self.assertEqual(saved['interval_minutes'], 120)
                self.assertEqual(saved['enabled'], enabled)
                due = feeds.due_sources(connection, now='2999-01-01T00:00:00Z')
            self.assertEqual(bool(due), enabled)
            self.assertAlmostEqual((datetime.fromisoformat(saved['next_fetch_at'].replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds(), 7200, delta=5)
        for value in (True, 14, 10081, '360'):
            with self.assertRaises(ValueError):
                web_rss.source_action(contract, {'action': 'schedule', 'id': self.source,
                    'enabled': True, 'interval_minutes': value})
        with self.database.write_transaction() as connection:
            connection.execute('UPDATE feed_source SET next_fetch_at=NULL')
            actor = feeds.add_source(connection, url='https://javdb.com/actors/example')
        self.assertEqual([row['id'] for row in web_feeds._check_sources(contract, {'automatic': True, 'rss_only': True}, {})], [self.source])
        self.assertEqual([row['id'] for row in web_feeds._check_sources(contract, {'automatic': True}, {})], [actor])
        self.assertEqual(rss_feeds.count_items(self.database), 0)
        with patch('peach.web_feeds.w_feed_check', return_value={'ok': True}) as run:
            web_rss.check_due(contract)
            self.assertEqual(run.call_args.args[1], {'sources': [self.source], 'automatic': True, 'rss_only': True})
            with self.database.write_transaction() as connection:
                feeds.set_enabled(connection, self.source, False)
            run.reset_mock()
            self.assertEqual(web_rss.check_due(contract)['checked'], 0)
            run.assert_not_called()

    def test_post_images_use_content_thumbnails_and_full_preview_links_without_prose(self):
        body = b'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Sample RSS</title>
          <item><guid>picture-post</guid><title>Studio - Example Actor</title><description>Unwanted prose</description>
          <content:encoded><![CDATA[<p><a href="https://images.example.org/full-main"><img src="https://images.example.org/main.webp" width="622" height="350"></a></p>
          <p>Hidden description and <script>bad()</script></p><strong>Preview:</strong><br>
          <a href="https://images.example.org/full-preview"><img src="https://images.example.org/preview.webp" width="103" height="200"></a>
          <a href="https://images.example.org/full-preview-2"><img src="https://images.example.org/preview-2.webp"></a>
          <a href="https://rg.to/file/example">Download</a>]]></content:encoded></item></channel></rss>'''
        _, rows = rss_feeds.parse(body, 'https://example.org/feed')
        self.assertEqual(rows[0]['images'], {
            'main': {'src': 'https://images.example.org/main.webp', 'href': 'https://images.example.org/full-main'},
            'previews': [{'src': 'https://images.example.org/preview.webp', 'href': 'https://images.example.org/full-preview'},
                         {'src': 'https://images.example.org/preview-2.webp', 'href': 'https://images.example.org/full-preview-2'}]})
        self.assertEqual(rows[0]['links'], [{'url': 'https://rg.to/file/example', 'kind': 'link'}])
        self.assertNotIn('Unwanted prose', json.dumps(rows))
        self.assertNotIn('bad()', json.dumps(rows))
        with self.database.write_transaction() as connection:
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            rss_feeds.poll(connection, source, body)
        self.assertEqual(rss_feeds.items(self.database)['items'][0]['images'], rows[0]['images'])

    def test_unsafe_images_tracking_pixels_and_empty_sources_are_excluded(self):
        html = rss_feeds._Anchors()
        html.feed('<img><img src="javascript:bad()"><img src="http://127.0.0.1/a">'
                  '<img src="https://images.example.org/pixel" width="1" height="1">'
                  '<img src="/cover.webp"><strong>Preview:</strong><a href="/full"><img src="/thumb.webp"></a>'
                  '<a href="/full2"><img src="/thumb.webp"></a>')
        images = rss_feeds._images({}, html, 'https://example.org/feed')
        self.assertEqual(images['main']['src'], 'https://example.org/cover.webp')
        self.assertEqual(images['previews'][0]['href'], 'https://example.org/full')
        self.assertEqual(images['previews'][1]['href'], 'https://example.org/full2')

    def test_source_link_filter_is_persisted_and_reversible(self):
        contract = SimpleNamespace(database=self.database, debrid=self.service())
        for value in (True, False):
            web_rss.source_action(contract, {'action': 'filter', 'id': self.source, 'hide_unsupported': value})
            with self.database.read_connection() as connection:
                row = connection.execute('SELECT hide_unsupported FROM feed_source WHERE id=?', (self.source,)).fetchone()
            self.assertEqual(bool(row[0]), value)
            with patch('peach.settings_file.active', return_value=self.config):
                self.assertEqual(web_rss.snapshot(contract)['sources'][0]['hide_unsupported'], value)
        with self.assertRaises(ValueError):
            web_rss.source_action(contract, {'action': 'filter', 'id': self.source, 'hide_unsupported': 'false'})

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = PeachConfig(self.root, self.root / 'config.toml')
        self.database = LedgerDatabase(self.root / 'database/ledger.db')
        self.database.db_path.parent.mkdir()
        upgrade(self.database.db_path, ROOT / 'migrations')
        with self.database.write_transaction() as connection:
            self.source = feeds.add_source(connection, url='https://example.org/feed.xml', name='Example', kind='rss')
        self.requests = []

    def provider(self, key='alldebrid', handler=None):
        debrid_client.save(self.config, key, {'api_key': 'test-private-key'})
        def transport(request):
            self.requests.append(request)
            return handler(request) if handler else httpx.Response(200, json={})
        client = debrid_client.Client(self.config, key, client=httpx.Client(transport=httpx.MockTransport(transport)))
        self.addCleanup(client.close)
        return client

    def service(self):
        service = debrid_service.Service(self.config)
        service.start = Mock()
        self.addCleanup(service.stop)
        return service

    def seed(self):
        with self.database.write_transaction() as connection:
            source = connection.execute('SELECT * FROM feed_source WHERE id=?', (self.source,)).fetchone()
            return rss_feeds.poll(connection, source, RSS)

    def test_rss_extracts_hosters_magnets_and_torrents_without_release_codes(self):
        title, rows = rss_feeds.parse(RSS, 'https://example.org/feed.xml')
        self.assertEqual(title, 'Example feed')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['published_at'], '2026-10-24T10:00:00+00:00')
        self.assertIn({'url': 'https://rg.to/file/test', 'kind': 'link'}, rows[0]['links'])
        self.assertIn({'url': MAGNET, 'kind': 'magnet'}, rows[0]['links'])
        self.assertIn({'url': 'https://example.org/media.torrent', 'kind': 'torrent'}, rows[0]['links'])

    def test_atom_relative_enclosure_and_unsafe_links(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>New videos</title><entry>
        <id>entry-1</id><title>Video</title><link rel="enclosure" href="/video.mp4" type="video/mp4"/>
        <link href="javascript:alert(1)"/><link href="http://127.0.0.1/admin"/></entry></feed>'''
        rows = rss_feeds.parse(body, 'https://example.org/feed')[1]
        self.assertEqual(rows[0]['links'], [{'url': 'https://example.org/video.mp4', 'kind': 'link'}])
        self.assertIsNone(rows[0]['published_at'])

    def test_non_feeds_dtds_and_utf16_entities_are_rejected(self):
        for value in (b'<html>Not a feed</html>', b'<!DOCTYPE rss><rss/>', '<!DOCTYPE rss><rss/>'.encode('utf-16')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rss_feeds.parse(value, 'https://example.org/feed')

    def test_poll_is_idempotent_and_keeps_items_out_of_the_library(self):
        self.assertEqual(self.seed()['added'], 1)
        self.assertEqual(self.seed()['added'], 0)
        data = rss_feeds.items(self.database)
        self.assertEqual(data['total'], 1)
        self.assertEqual(len(data['items'][0]['links']), 4)
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM asset').fetchone()[0], 0)

    def test_feed_remove_clears_its_download_entries(self):
        self.seed()
        web_rss.source_action(SimpleNamespace(database=self.database), {'action': 'remove', 'id': self.source})
        self.assertEqual(rss_feeds.items(self.database)['total'], 0)

    def test_private_redirect_is_rejected_before_a_second_request(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
                patch('peach.public_download_http.resolves_publicly', return_value=True):
            with self.assertRaises(ValueError), public_download_http.stream(client, 'https://example.org/feed'):
                pass
        self.assertEqual(len(requests), 1)

    def test_settings_redact_keys_and_validate_the_container_folder(self):
        self.provider()
        state = debrid_client.save(self.config, 'alldebrid', {'download_folder': str(self.root)})
        self.assertNotIn('test-private-key', json.dumps(state))
        self.assertTrue(state['providers'][0]['configured'])
        self.assertEqual(state['providers'][0]['download_folder'], str(self.root))
        with self.assertRaises(ValueError):
            debrid_client.save(self.config, 'alldebrid', {'download_folder': '../outside'})
        debrid_client.save(self.config, 'alldebrid', {'remove_key': True})
        self.assertFalse(debrid_client.settings(self.config)['providers'][0]['configured'])

    def test_hosters_unlock_with_bearer_header_and_no_key_in_urls(self):
        for provider in ('alldebrid', 'realdebrid'):
            payload = {'link': 'https://cdn.example.org/video', 'filename': 'video.mp4', 'filesize': 5}
            response = {'status': 'success', 'data': payload} if provider == 'alldebrid' else {**payload, 'download': payload['link']}
            client = self.provider(provider, lambda request, response=response: httpx.Response(200, json=response))
            with patch('peach.debrid_client.time.sleep'):
                result = client.unlock('https://rg.to/file/test')
            self.assertEqual(result['filename'], 'video.mp4')
            request = self.requests[-1]
            self.assertEqual(request.headers['Authorization'], 'Bearer test-private-key')
            self.assertNotIn('test-private-key', str(request.url))
            self.assertIn(b'link=https%3A%2F%2Frg.to', request.content)

    def test_alldebrid_delayed_link_is_polled_without_unlocking_again(self):
        def handler(request):
            value = {'delayed': 123, 'filename': 'scene.mp4', 'filesize': 5} if request.url.path.endswith('/unlock') else {
                'status': 2, 'link': 'https://cdn.example.org/scene'}
            return httpx.Response(200, json={'status': 'success', 'data': value})
        client = self.provider(handler=handler)
        previous = {}
        with patch('peach.debrid_client.time.sleep'):
            self.assertIsNone(client.unlock('https://rg.to/file/test', persist=previous.update))
            ready = client.unlock('https://rg.to/file/test', previous=previous)
        self.assertEqual(ready['filename'], 'scene.mp4')
        self.assertEqual([request.url.path for request in self.requests], ['/v4/link/unlock', '/v4/link/delayed'])

    def test_real_debrid_torrent_selection_and_ready_links(self):
        statuses = iter(['waiting_files_selection', 'downloaded'])
        def handler(request):
            if '/info/' in request.url.path:
                return httpx.Response(200, json={'status': next(statuses), 'links': ['https://real-debrid.com/d/test']})
            return httpx.Response(204)
        client = self.provider('realdebrid', handler)
        with patch('peach.debrid_client.time.sleep'):
            self.assertIsNone(client.torrent_links('123'))
            self.assertEqual(client.torrent_links('123'), ['https://real-debrid.com/d/test'])
        self.assertIn(b'files=all', self.requests[1].content)

    def test_alldebrid_nested_torrent_file_links(self):
        def handler(request):
            value = {'magnets': [{'id': 123, 'statusCode': 4}]} if '/status' in request.url.path else {
                'magnets': [{'id': 123, 'files': [{'n': 'folder', 'e': [{'n': 'video', 'l': 'https://alldebrid.com/f/test'}]}]}]}
            return httpx.Response(200, json={'status': 'success', 'data': value})
        client = self.provider(handler=handler)
        with patch('peach.debrid_client.time.sleep'):
            self.assertEqual(client.torrent_links('123'), ['https://alldebrid.com/f/test'])

    def test_service_reuses_remote_identity_after_restart_and_hides_key_stamp(self):
        self.provider()
        service = self.service()
        task = service.submit(1, {'kind': 'magnet', 'url': MAGNET}, 'alldebrid')
        client = Mock()
        client.create_torrent.return_value = 'remote-123'
        client.torrent_links.return_value = None
        with patch('peach.debrid_client.Client', return_value=client):
            service._run(dict(task))
            restored = debrid_service.Service(self.config)
            self.addCleanup(restored.stop)
            restored._run(dict(restored.jobs[task['id']]))
        self.assertEqual(client.create_torrent.call_count, 1)
        self.assertNotIn('key_stamp', json.dumps(restored.snapshot()))
        self.assertNotIn('test-private-key', json.dumps(restored.snapshot()))

    def test_duplicate_resolve_and_folder_downloads_share_a_task(self):
        self.provider()
        debrid_client.save(self.config, 'alldebrid', {'download_folder': str(self.root)})
        service = self.service()
        link = {'kind': 'link', 'url': 'https://rg.to/file/test'}
        task = service.submit(1, link, 'alldebrid')
        self.assertEqual(service.submit(1, link, 'alldebrid')['id'], task['id'])
        service._update(task['id'], status='ready', files=[{'url': 'https://cdn.example.org/file', 'filename': 'file.mp4', 'size': 5}])
        first = service.download(task['id'], 0)
        self.assertEqual(service.download(task['id'], 0)['id'], first['id'])
        service.cancel(first['id'])
        self.assertEqual(service.jobs[first['id']]['status'], 'cancelled')

    def test_six_persisted_download_requests_fill_and_refill_three_slots(self):
        self._assert_download_slots(6, 3)

    def test_twenty_persisted_download_requests_fill_and_refill_ten_slots(self):
        self._assert_download_slots(20, 10)

    def _assert_download_slots(self, total, limit):
        self.provider()
        debrid_client.save(self.config, 'alldebrid', {'download_folder': str(self.root), 'max_concurrent_downloads': limit})
        service = self.service()
        for index in range(total):
            task = service.submit(index, {'kind': 'link', 'url': f'https://rg.to/file/{index}'},
                                  'alldebrid', auto_download=True)
            service._update(task['id'], status='ready', files=[{
                'url': f'https://cdn.example.org/{index}', 'filename': f'{index}.mp4', 'size': 1}])
        restored = debrid_service.Service(self.config)
        release, first_wave, finished = threading.Event(), threading.Event(), threading.Event()
        counts = {'running': 0, 'peak': 0, 'complete': 0}
        lock = threading.Lock()

        def transfer(task, *, update, active):
            with lock:
                counts['running'] += 1
                counts['peak'] = max(counts['peak'], counts['running'])
                if counts['running'] == limit:
                    first_wave.set()
            release.wait(5)
            update(status='complete', path=str(self.root / task['filename']))
            with lock:
                counts['running'] -= 1
                counts['complete'] += 1
                if counts['complete'] == total:
                    finished.set()

        try:
            with patch('peach.debrid_transfer.transfer', side_effect=transfer):
                restored.start()
                self.assertTrue(first_wave.wait(5))
                self.assertEqual(counts['peak'], limit)
                release.set()
                self.assertTrue(finished.wait(5))
                self.assertEqual(counts['peak'], limit)
                self.assertEqual(len([job for job in restored.snapshot() if job['kind'] == 'download']), total)
                restored.stop()
        finally:
            release.set()
            restored.stop()

    def test_download_concurrency_defaults_and_validation(self):
        self.assertEqual(debrid_client.settings(self.config)['providers'][0]['max_concurrent_downloads'], 3)
        result = debrid_client.save(self.config, 'alldebrid', {'max_concurrent_downloads': 1})
        self.assertEqual(result['providers'][0]['max_concurrent_downloads'], 1)
        debrid_client.save(self.config, 'alldebrid', {'max_concurrent_downloads': 10})
        self.assertEqual(debrid_client.settings(self.config)['providers'][0]['max_concurrent_downloads'], 10)
        for value in (0, 11, True, 1.5, '3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                debrid_client.save(self.config, 'alldebrid', {'max_concurrent_downloads': value})

    def test_finished_download_receipt_survives_clearing_without_clearing_imports(self):
        self.provider()
        debrid_client.save(self.config, 'alldebrid', {'download_folder': str(self.root)})
        service = self.service()
        parent = service.submit(1, {'kind': 'link', 'url': 'https://rg.to/file/finished'}, 'alldebrid')
        service._update(parent['id'], status='ready', files=[{'url': 'https://cdn.example.org/file', 'filename': 'file.mp4'}])
        child = service.download(parent['id'], 0)
        service._update(child['id'], status='complete', import_state='queued')
        self.assertEqual(service.clear_finished()['cleared'], 0)
        service._update(child['id'], import_state='complete')
        self.assertEqual(service.clear_finished()['cleared'], 1)
        restored = debrid_service.Service(self.config)
        self.addCleanup(restored.stop)
        rows = {row['id']: row for row in restored.snapshot()}
        self.assertTrue(rows[child['id']]['dismissed'])
        self.assertEqual(rows[parent['id']]['files'][0]['download_id'], child['id'])
        self.assertEqual(rows[child['id']]['parent_id'], parent['id'])
        self.assertEqual(restored.clear_finished()['cleared'], 0)

    def test_saved_rss_posts_are_paginated_with_twenty_as_default(self):
        with self.database.write_transaction() as connection:
            connection.executemany('INSERT INTO feed_item(source_id,item_key,title,first_seen) VALUES(?,?,?,?)',
                [(self.source, str(index), f'Post {index}', '2026-10-01T00:00:00Z') for index in range(45)])
        first = rss_feeds.items(self.database)
        second = rss_feeds.items(self.database, offset=20)
        self.assertEqual(len(first['items']), 20)
        self.assertEqual(first['total'], 45)
        self.assertFalse({row['id'] for row in first['items']} & {row['id'] for row in second['items']})
        self.assertEqual(len(rss_feeds.items(self.database, limit=10)['items']), 10)

    def test_transfer_resumes_with_range_and_publishes_only_a_complete_file(self):
        identity = '1' * 32
        partial = self.root / f'.peach-{identity}.part'
        partial.write_bytes(b'first')
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(206, headers={'content-range': 'bytes 5-9/10', 'etag': 'version1'}, content=b'last!')
        task = {'id': identity, 'folder': str(self.root), 'filename': '../../video.mp4', 'url': 'https://cdn.example.org/file', 'etag': 'version1', 'size': 10}
        changes = []
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, patch('peach.public_download_http.resolves_publicly', return_value=True):
            debrid_transfer.transfer(task, update=lambda **values: changes.append(values), active=lambda: True, client=client)
        self.assertEqual(requests[0].headers['Range'], 'bytes=5-')
        self.assertEqual(requests[0].headers['If-Range'], 'version1')
        path = Path(changes[-1]['path'])
        self.assertEqual(path.parent, self.root)
        self.assertEqual(path.read_bytes(), b'firstlast!')
        self.assertFalse(partial.exists())

    def test_short_download_is_not_published_and_existing_files_are_not_overwritten(self):
        task = {'id': '2' * 32, 'folder': str(self.root), 'filename': 'video.mp4', 'url': 'https://cdn.example.org/file', 'size': 100}
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'short'))) as client, \
                patch('peach.public_download_http.resolves_publicly', return_value=True):
            with self.assertRaises(ValueError):
                debrid_transfer.transfer(task, update=lambda **_: None, active=lambda: True, client=client)
        target = self.root / debrid_transfer.filename(task['filename'], task['id'])
        self.assertFalse(target.exists())
        target.write_bytes(b'existing')
        with self.assertRaises(ValueError):
            debrid_transfer.transfer(task, update=lambda **_: None, active=lambda: True)
        self.assertEqual(target.read_bytes(), b'existing')

    def test_rss_api_lists_items_and_rejects_read_only_mutations(self):
        self.seed()
        service = self.service()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_auth] = lambda: {}
        app.state.web_contract = SimpleNamespace(database=self.database, debrid=service)
        app.state.sync = SimpleNamespace(read_only=False)
        with patch('peach.settings_file.active', return_value=self.config), TestClient(app) as client:
            self.assertEqual(client.get('/api/rss').json()['total'], 1)
            with self.database.write_transaction() as connection:
                feeds.set_enabled(connection, self.source, False)
            with patch('peach.web_feeds.w_feed_check', return_value={'ok': True}) as run:
                self.assertEqual(client.post('/api/rss/check').status_code, 200)
                self.assertEqual(run.call_args.args[1]['sources'], [self.source])
            app.state.sync.read_only = True
            self.assertEqual(client.post('/api/rss/source', json={'action': 'remove', 'id': self.source}).status_code, 403)

    def test_rate_limit_cooldown_blocks_another_provider_request(self):
        client = self.provider(handler=lambda request: httpx.Response(429, headers={'retry-after': '120'}))
        with patch('peach.debrid_client.time.sleep'):
            with self.assertRaises(ValueError):
                client.call('GET', '/v4/user')
            with self.assertRaises(ValueError):
                client.call('GET', '/v4/user')
        self.assertEqual(len(self.requests), 1)
        state = json.loads((self.config.directory('state') / 'debrid-alldebrid-cooldown.json').read_text())
        self.assertGreater(state['until'], time.time() + 110)

    def test_cancelled_transfer_keeps_partial_file_without_publishing(self):
        task = {'id': '3' * 32, 'folder': str(self.root), 'filename': 'video.mp4', 'url': 'https://cdn.example.org/file'}
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'complete'))) as client, \
                patch('peach.public_download_http.resolves_publicly', return_value=True):
            with self.assertRaises(InterruptedError):
                debrid_transfer.transfer(task, update=lambda **_: None, active=lambda: False, client=client)
        self.assertFalse((self.root / debrid_transfer.filename(task['filename'], task['id'])).exists())
        self.assertTrue((self.root / ('.peach-' + task['id'] + '.part')).exists())
