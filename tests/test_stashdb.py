"""隔离验证 StashDB 查询、复核、来源归属及图片选项，不连接真实服务。"""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from peach import stashdb, stashdb_client, stashdb_matching
from peach.entities import upsert_asset_entity
from peach.http import HttpResponse
from peach.migrations import upgrade
from peach.repository import LedgerDatabase
from peach.western_artwork import artwork_cast_size
from peach.settings_file import PeachConfig

SCENE = '11111111-1111-4111-8111-111111111111'
ACTOR = '22222222-2222-4222-8222-222222222222'
STUDIO = '33333333-3333-4333-8333-333333333333'


def scene(identity=SCENE, **values):
    return {'id': identity, 'title': 'A summer scene', 'release_date': '2026-10-22', 'duration': 1200,
        'deleted': False, 'studio': {'id': STUDIO, 'name': 'Evil Angel', 'parent': None},
        'images': [{'url': 'https://stashdb.org/images/scene.jpg', 'width': 800, 'height': 450}],
        'performers': [{'as': 'Jane Alias', 'performer': {'id': ACTOR, 'name': 'Jane Doe', 'aliases': ['Jane Alias'],
            'disambiguation': None, 'deleted': False, 'images': [{'url': 'https://stashdb.org/images/actor.jpg', 'width': 500, 'height': 800}]}}], **values}


class StashDBTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = PeachConfig(data_root=self.root, path=self.root / 'config.toml')
        self.database = LedgerDatabase(self.root / 'database' / 'ledger.db')
        self.database.db_path.parent.mkdir()
        upgrade(self.database.db_path, Path(__file__).resolve().parents[1] / 'migrations')
        with self.database.write_transaction() as connection:
            connection.execute("INSERT INTO asset(id,location,path,name,medium,duration) VALUES(1,'local','R:\\scene.mp4',?, 'video',1200)",
                ('EvilAngel.26.10.22.Jane.Doe.mp4',))
        stashdb_client.save_settings(self.config, {'api_key': 'test-secret-token'})
        self.calls = []
        self.scenes = [scene()]

    def transport(self, request, _timeout, _limit):
        self.calls.append(request)
        if request.method == 'GET':
            return HttpResponse(200, {}, b'image', request.url)
        payload = json.loads(request.body or '{}')
        query = payload.get('query', '')
        if 'queryPerformers' in query:
            data = {'queryPerformers': {'count': 1, 'performers': [scene()['performers'][0]['performer']]}}
        elif 'queryStudios' in query:
            data = {'queryStudios': {'studios': [scene()['studio']]}}
        elif 'queryScenes' in query:
            data = {'queryScenes': {'count': len(self.scenes), 'scenes': self.scenes}}
        elif 'findScene' in query:
            data = {'findScene': self.scenes[0]}
        elif 'findPerformer' in query:
            data = {'findPerformer': self.scenes[0]['performers'][0]['performer']}
        else:
            data = {'me': {'id': 'test-account', 'name': 'Test account'}}
        return HttpResponse(200, {}, json.dumps({'data': data}).encode(), stashdb_client.ENDPOINT)

    def client(self):
        client = stashdb_client.Client(self.config, transport=self.transport, interval=0)
        self.addCleanup(client.close)
        return client

    def test_actor_and_studio_mode_never_queries_scenes_and_reuses_shared_identities(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'scene_images': False,
            'actor_images': False, 'correct_cast': True})
        with self.database.write_transaction() as connection:
            for kind, name in [('performer', 'Jane Doe'), ('studio', 'Evil Angel')]:
                upsert_asset_entity(connection, kind=kind, name=name, asset_id=1, role=kind,
                    source='scan:filename-actors')
        issues = []
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}] * 20,
                progress=lambda **_: None, issue=lambda *args, **kwargs: issues.append(args))
        self.assertEqual(result['applied'], 2)
        self.assertEqual(issues, [])
        queries = [json.loads(call.body)['query'] for call in self.calls]
        self.assertEqual(len(queries), 2)
        self.assertFalse(any('Scene' in query for query in queries))
        self.calls.clear()
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}],
                progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(result['skipped'], 2)
        self.assertEqual(self.calls, [])

    def test_actor_only_mode_installs_actor_photo_without_scene_queries(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'scene_images': False})
        with self.database.write_transaction() as connection:
            upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1,
                role='performer', source='scan:filename-actors')
        image = io.BytesIO()
        Image.new('RGB', (500, 800), 'gray').save(image, format='JPEG')
        client = self.client()
        client.image = mock.Mock(return_value=image.getvalue())
        with mock.patch('peach.stashdb_client.Client', return_value=client):
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}],
                progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(result['applied'], 1)
        self.assertEqual(client.image.call_count, 1)
        self.assertEqual(len(list((self.root / 'generated/avatars').glob('performer-*.img'))), 1)
        self.assertFalse(any('Scene' in json.loads(call.body)['query'] for call in self.calls))
        self.calls.clear()
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}],
                progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(self.calls, [])

    def test_stopping_after_stashdb_response_prevents_further_requests(self):
        from peach.processing_control import control_for
        control = control_for(self.config)
        client = self.client()
        original = client.transport
        def stop_after_response(*args):
            response = original(*args)
            control.request('stop', 'cancel-test')
            return response
        client.transport = stop_after_response
        with control.bind('cancel-test', publish=lambda **_: None, active=lambda: True,
                          db_path=self.database.db_path, mode='high'):
            with self.assertRaises(InterruptedError):
                stashdb.preview(self.config, self.database, {'asset_id': 1}, client=client)
        self.assertEqual(len(self.calls), 1)

    def test_actor_only_failures_retry_unless_failed_search_skipping_is_enabled(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'scene_images': False})
        with self.database.write_transaction() as connection:
            upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1,
                role='performer', source='scan:filename-actors')
        client = self.client()
        client.performers = mock.Mock(side_effect=ValueError('temporary failure'))
        def scan():
            with mock.patch('peach.stashdb_client.Client', return_value=client):
                return stashdb.scan_assets(self.config, self.database, [{'id': 1}],
                    progress=lambda **_: None, issue=lambda *_, **__: None)
        scan()
        scan()
        self.assertEqual(client.performers.call_count, 2)
        stashdb_client.save_settings(self.config, {'skip_failed': True})
        self.assertEqual(scan()['skipped'], 1)
        self.assertEqual(client.performers.call_count, 2)
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE entity SET canonical_name='Jane Alias' WHERE kind='performer'")
        self.assertEqual(scan()['skipped'], 0)
        self.assertEqual(client.performers.call_count, 3)

    def test_structured_queries_match_date_studio_and_cast_without_scene_title(self):
        result = stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        self.assertEqual(result['automatic_match'], SCENE)
        self.assertEqual(result['hints']['title'], '')
        self.assertEqual(result['hints']['actors'], ['Jane Doe'])
        queries = [json.loads(call.body)['variables'].get('input', {}) for call in self.calls]
        self.assertTrue(any(query.get('date', {}).get('value') == '2026-10-22' and 'studios' in query for query in queries))
        self.assertTrue(any('performers' in query for query in queries))
        self.assertTrue(all(call.headers['ApiKey'] == 'test-secret-token' for call in self.calls))
        self.assertTrue(all(call.url == stashdb_client.ENDPOINT for call in self.calls))

    def test_ties_conflicting_dates_and_deleted_records_need_review(self):
        self.scenes = [scene(), scene('44444444-4444-4444-8444-444444444444')]
        result = stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        self.assertIsNone(result['automatic_match'])
        self.scenes = [scene(release_date='2026-10-21'), scene('55555555-5555-4555-8555-555555555555', deleted=True)]
        result = stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        self.assertIsNone(result['automatic_match'])
        self.assertEqual(len(result['candidates']), 1)
        self.assertIn('Release date differs', result['candidates'][0]['reasons'])

    def test_settings_do_not_return_keys_and_cooldown_stops_further_requests(self):
        public = stashdb_client.settings(self.config)
        self.assertNotIn('api_key', public)
        self.assertNotIn('test-secret-token', json.dumps(public))
        requests = []
        def rate_limited(request, _timeout, _limit):
            requests.append(request)
            return HttpResponse(429, {'retry-after': '90'}, b'')
        client = stashdb_client.Client(self.config, transport=rate_limited, interval=0)
        for _ in range(2):
            with self.assertRaises(stashdb_client.RateLimited):
                client.check()
        self.assertEqual(len(requests), 1)
        with self.assertRaises(ValueError):
            client.query('mutation { sceneDestroy }')
        with self.assertRaises(ValueError):
            stashdb_client.save_settings(self.config, {'enabled': 'yes'})
        stashdb_client.save_settings(self.config, {'api_key': '', 'enabled': False})
        self.assertFalse(stashdb_client.settings(self.config)['api_key_set'])

    def test_cast_correction_preserves_manual_links_and_protected_metadata(self):
        stashdb_client.save_settings(self.config, {'correct_cast': True, 'actor_images': False, 'scene_images': False})
        with self.database.write_transaction() as connection:
            for name, source in [('Manual Actor', 'user:test'), ('Filename Guess', 'scan:filename-actors')]:
                upsert_asset_entity(connection, kind='performer', name=name, asset_id=1, role='performer', source=source)
            connection.execute("UPDATE asset SET catalog_title='Manual title',field_owners=? WHERE id=1", ('{"catalog_title":"user:manual"}',))
            token = stashdb.asset_evidence(connection, 1)[2]
        result = stashdb.apply_scene(self.config, self.database, 1, SCENE, token, client=self.client())
        self.assertTrue(result['cast_updated'])
        with self.database.read_connection() as connection:
            cast = {row[0] for row in connection.execute("SELECT e.canonical_name FROM entity e JOIN asset_entity ae ON e.id=ae.entity_id WHERE ae.asset_id=1 AND e.kind='performer'")}
            self.assertEqual(cast, {'Manual Actor', 'Jane Doe'})
            self.assertEqual(connection.execute('SELECT catalog_title FROM asset WHERE id=1').fetchone()[0], 'Manual title')
            self.assertEqual(connection.execute("SELECT external_id FROM entity_external_ref WHERE provider='stashdb' AND external_kind='performer'").fetchone()[0], ACTOR)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM asset_entity WHERE role='studio'").fetchone()[0], 1)

    def test_stale_preview_is_rejected_and_ambiguous_cast_is_not_replaced(self):
        with self.database.read_connection() as connection:
            token = stashdb.asset_evidence(connection, 1)[2]
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE asset SET name='changed.mp4' WHERE id=1")
        with self.assertRaisesRegex(ValueError, 'changed'):
            stashdb.apply_scene(self.config, self.database, 1, SCENE, token, client=self.client())
        stashdb_client.save_settings(self.config, {'correct_cast': True, 'actor_images': False, 'scene_images': False})
        self.scenes[0]['performers'][0]['performer']['disambiguation'] = 'Ambiguous performer'
        with self.database.read_connection() as connection:
            token = stashdb.asset_evidence(connection, 1)[2]
        result = stashdb.apply_scene(self.config, self.database, 1, SCENE, token, client=self.client())
        self.assertFalse(result['cast_updated'])

    def test_image_options_are_independent_and_use_matching_existing_actors(self):
        with self.database.write_transaction() as connection:
            actor = upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1, role='performer', source='user:test')
            token = stashdb.asset_evidence(connection, 1)[2]
        client = self.client()
        def image(url):
            output = io.BytesIO()
            Image.new('RGB', (500, 800) if 'actor' in url else (800, 450), 'gray').save(output, format='JPEG')
            return output.getvalue()
        client.image = mock.Mock(side_effect=image)
        with mock.patch('peach.cover_artwork._default_detector', return_value=SimpleNamespace(detect=lambda *_: [])):
            result = stashdb.apply_scene(self.config, self.database, 1, SCENE, token, client=client)
        self.assertTrue(result['scene_picture'])
        self.assertEqual(result['actor_photos'], 1)
        self.assertFalse(result['cast_updated'])
        self.assertTrue((self.root / 'generated/avatars' / f'performer-{actor}.img').is_file())
        self.assertTrue((self.root / 'generated/covers' / 'ASSET-ID-1.jpg').is_file())
        self.assertEqual(artwork_cast_size(self.root / 'generated/covers' / 'ASSET-ID-1.jpg', 0), 1)
        self.assertTrue(all(not call.headers.get('ApiKey') for call in self.calls if call.method == 'GET'))

    def test_actor_search_and_review_bind_the_selected_identity(self):
        with self.database.write_transaction() as connection:
            actor = upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1, role='performer', source='user:test')
        result = stashdb.preview(self.config, self.database, {'performer_id': actor}, client=self.client())
        self.assertEqual(result['candidates'][0]['id'], ACTOR)
        stashdb_client.save_settings(self.config, {'actor_images': False})
        self.assertTrue(stashdb.apply_performer(self.config, self.database, actor, ACTOR, client=self.client())['ok'])
        with self.assertRaisesRegex(ValueError, 'identity'):
            stashdb.apply_performer(self.config, self.database, actor, '44444444-4444-4444-8444-444444444444', client=self.client())

    def test_disabled_scan_is_offline_and_enabled_scan_can_queue_review(self):
        row = {'id': 1}
        with mock.patch('peach.stashdb_client.Client') as factory:
            self.assertEqual(stashdb.scan_assets(self.config, self.database, [row], progress=lambda **_: None, issue=lambda *_: None), {'applied': 0, 'review': 0})
            factory.assert_not_called()
        stashdb_client.save_settings(self.config, {'enabled': True})
        client = self.client()
        with mock.patch('peach.stashdb_client.Client', return_value=client):
            result = stashdb.scan_assets(self.config, self.database, [row], progress=lambda **_: None, issue=lambda *_: None)
        self.assertEqual(result, {'applied': 0, 'review': 1, 'skipped': 0})
        self.assertTrue((self.root / 'state' / 'stashdb-review' / '1.json').is_file())
        queued = stashdb.review_queue(self.config, self.database)
        self.assertEqual(queued[0]['id'], 1)
        self.assertEqual(queued[0]['preview']['automatic_match'], SCENE)

    def test_unrelated_title_alone_never_becomes_automatic(self):
        evidence = {'title': 'A summer scene', 'date': '', 'studio': '', 'actors': [], 'duration': 0}
        ranked = stashdb_matching.rank_scene(scene(), evidence)
        self.assertFalse(ranked['strong'])
        self.assertLess(ranked['score'], .85)
        duplicate = copy.deepcopy(scene())
        duplicate['studio']['name'] = 'Other Studio'
        evidence.update(studio='EvilAngel', date='2026-10-22', actors=['Jane Alias'])
        self.assertFalse(stashdb_matching.rank_scene(duplicate, evidence)['strong'])

    def test_image_downloads_never_receive_api_keys_or_follow_redirects(self):
        client = self.client()
        with mock.patch('peach.stashdb_client.resolves_publicly', return_value=True):
            client.image('https://images.example.org/photo.jpg')
        self.assertEqual(self.calls[-1].method, 'GET')
        self.assertNotIn('ApiKey', self.calls[-1].headers)
        with self.assertRaises(ValueError):
            client.image('http://127.0.0.1/private')
        client.transport = lambda *_: HttpResponse(302, {'location': 'http://127.0.0.1/private'}, b'')
        with mock.patch('peach.stashdb_client.resolves_publicly', return_value=True), self.assertRaises(ValueError):
            client.image('https://images.example.org/photo.jpg')

    def test_library_search_escapes_literal_wildcards_and_lists_scenes(self):
        with self.database.write_transaction() as connection:
            actor = upsert_asset_entity(connection, kind='performer', name='A_100%!', asset_id=1, role='performer', source='user:test')
        self.assertEqual(stashdb.library(self.database, '100%', 'actor'), [{'id': actor, 'label': 'A_100%!'}])
        self.assertEqual(len(stashdb.library(self.database)), 1)
        self.assertEqual(stashdb.library(self.database, 'missing', 'actor'), [])

    def test_recovery_preserves_current_images_and_finished_actors_are_offline(self):
        from peach.stashdb_files import recover_images
        with self.database.write_transaction() as connection:
            actor = upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1, role='performer',
                source='user:test', external_provider='stashdb', external_id=ACTOR)
        old = self.root / 'avatars' / f'performer-{actor}.img'
        old.parent.mkdir()
        old.write_bytes(b'original-download')
        Path(str(old) + '.provenance.json').write_text(json.dumps({'provider': 'stashdb', 'external_id': ACTOR}))
        self.assertEqual(recover_images(self.config), 1)
        target = self.root / 'generated/avatars' / old.name
        self.assertEqual(target.read_bytes(), b'original-download')
        target.write_bytes(b'current-picture')
        self.assertEqual(recover_images(self.config), 0)
        self.assertEqual(target.read_bytes(), b'current-picture')
        with mock.patch('peach.stashdb_client.Client') as client:
            result = stashdb.apply_performer(self.config, self.database, actor, ACTOR)
        client.assert_not_called()
        self.assertEqual(result['skipped'], 1)
        preview = stashdb.preview(self.config, self.database, {'performer_id': actor}, client=self.client())
        self.assertEqual(preview['candidates'][0]['reasons'], ['Already up to date.'])
        self.assertEqual(self.calls, [])

    def test_completed_scan_skips_network_until_local_evidence_or_options_change(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'auto_apply': True,
            'actor_images': False, 'scene_images': True, 'correct_cast': True})
        client = self.client()
        with mock.patch('peach.stashdb_client.Client', return_value=client), mock.patch('peach.stashdb._image', return_value=None):
            first = stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(first['applied'], 1)
        count = len(self.calls)
        with self.database.write_transaction() as connection:
            connection.execute('UPDATE asset SET mutation_revision=mutation_revision+1 WHERE id=1')
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            second = stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(second['skipped'], 1)
        self.assertEqual(len(self.calls), count)

    def test_cast_correction_reuses_existing_actor_identity_and_keeps_its_picture(self):
        with self.database.write_transaction() as connection:
            actor = upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1,
                role='performer', source='scan:filename-actors')
            token = stashdb.asset_evidence(connection, 1)[2]
        target = self.root / 'generated/avatars' / f'performer-{actor}.img'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing-profile-picture')
        self.scenes[0]['performers'][0]['performer']['disambiguation'] = 'US'
        stashdb_client.save_settings(self.config, {'correct_cast': True, 'scene_images': False})
        result = stashdb.apply_scene(self.config, self.database, 1, SCENE, token, client=self.client(), manual=False)
        self.assertTrue(result['cast_updated'])
        self.assertEqual(target.read_bytes(), b'existing-profile-picture')
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute('SELECT entity_id FROM asset_entity WHERE asset_id=1').fetchone()[0], actor)

    def test_image_download_failure_keeps_existing_picture_and_tries_other_candidates(self):
        client = self.client()
        output = io.BytesIO()
        Image.new('RGB', (500, 800), 'gray').save(output, format='JPEG')
        client.image = mock.Mock(side_effect=[ValueError('temporary download failure'), output.getvalue()])
        prepared = stashdb._image(client, [{'url': 'https://example.org/first', 'width': 600, 'height': 900},
            {'url': 'https://example.org/second', 'width': 500, 'height': 800}], portrait=True)
        self.assertIsNotNone(prepared)
        client.image = mock.Mock(side_effect=ValueError('temporary download failure'))
        with self.assertRaisesRegex(ValueError, 'preserved'):
            stashdb._image(client, [{'url': 'https://example.org/first'}])

    def test_dismissed_scene_stays_out_of_automatic_review_until_evidence_changes(self):
        stashdb_client.save_settings(self.config, {'enabled': True})
        with self.database.read_connection() as connection:
            token = stashdb.asset_evidence(connection, 1)[2]
        self.assertTrue(stashdb.dismiss(self.config, self.database, 1, token)['ok'])
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(self.calls, [])
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE asset SET catalog_title='A different title' WHERE id=1")
        with self.assertRaisesRegex(ValueError, 'changed'):
            stashdb.dismiss(self.config, self.database, 1, token)

    def test_known_stashdb_actor_identity_is_used_without_name_lookup(self):
        with self.database.write_transaction() as connection:
            upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1, role='performer',
                source='auto:stashdb', external_provider='stashdb', external_id=ACTOR)
        stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        queries = [json.loads(request.body)['query'] for request in self.calls]
        self.assertFalse(any('queryPerformers' in query for query in queries))

    def test_pending_review_and_empty_search_are_cached_without_repeat_requests(self):
        stashdb_client.save_settings(self.config, {'enabled': True})
        def scan():
            with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
                return stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None,
                    issue=lambda *_, **__: self.fail('scan must succeed'))
        self.assertEqual(scan()['review'], 1)
        count = len(self.calls)
        with self.database.write_transaction() as connection:
            connection.execute('UPDATE asset SET mutation_revision=mutation_revision+1 WHERE id=1')
        self.assertEqual(scan(), {'applied': 0, 'review': 1, 'skipped': 1})
        self.assertEqual(len(self.calls), count)
        with self.database.read_connection() as connection:
            self.assertEqual(stashdb.review_queue(self.config, self.database)[0]['preview']['token'],
                stashdb.asset_evidence(connection, 1)[2])
        stashdb_client.save_settings(self.config, {'ignore_terms': '!'})
        self.scenes = []
        self.assertEqual(scan()['review'], 0)
        count = len(self.calls)
        self.assertEqual(scan()['skipped'], 1)
        self.assertEqual(len(self.calls), count)

    def test_filename_ignores_are_literal_and_leave_filename_and_saved_metadata_intact(self):
        stashdb_client.save_settings(self.config, {'ignore_terms': '!\n[extra]'})
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE asset SET name='!EvilAngel.26.10.22.Jane.Doe.[extra].mp4' WHERE id=1")
        result = stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        self.assertEqual(result['hints']['studio'], 'EvilAngel')
        self.assertEqual(result['hints']['actors'], ['Jane Doe'])
        self.assertEqual(result['automatic_match'], SCENE)
        self.assertEqual(result['hints']['filename'], '!EvilAngel.26.10.22.Jane.Doe.[extra].mp4')

    def test_confidence_threshold_changes_auto_selection_and_apply_but_keeps_conflict_guards(self):
        stashdb_client.save_settings(self.config, {'minimum_confidence': 100, 'actor_images': False, 'scene_images': False})
        result = stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())
        self.assertIsNone(result['automatic_match'])
        with self.assertRaisesRegex(ValueError, 'needs review'):
            stashdb.apply_scene(self.config, self.database, 1, SCENE, result['token'], client=self.client(), manual=False)
        stashdb_client.save_settings(self.config, {'minimum_confidence': 85})
        self.assertEqual(stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())['automatic_match'], SCENE)
        stashdb_client.save_settings(self.config, {'minimum_confidence': 50})
        self.scenes = [scene(release_date='2026-10-21')]
        self.assertIsNone(stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())['automatic_match'])
        for body in ({'minimum_confidence': True}, {'minimum_confidence': 49}, {'minimum_confidence': 101}, {'ignore_terms': ['!']}):
            with self.assertRaises(ValueError):
                stashdb_client.save_settings(self.config, body)

    def test_general_manual_review_count_includes_stashdb_queue_and_updates_after_dismissal(self):
        from peach.web_state import WebContract
        from peach.web_router import _get_review
        stashdb_client.save_settings(self.config, {'enabled': True})
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
            stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None, issue=lambda *_, **__: None)
        contract = WebContract(self.database.db_path, database=self.database, candidate_root=self.root/'generated',
            cover_root=self.root/'generated/covers', avatar_root=self.root/'generated/avatars', follow_state_root=self.root/'state')
        self.assertEqual(_get_review(contract, {'counts': '1'})['counts']['stashdb'], 1)
        self.assertEqual(_get_review(contract, {})['counts']['stashdb'], 1)
        with self.database.read_connection() as connection:
            token = stashdb.asset_evidence(connection, 1)[2]
        stashdb.dismiss(self.config, self.database, 1, token)
        self.assertEqual(_get_review(contract, {'counts': '1'})['counts']['stashdb'], 0)

    def test_new_media_scan_only_searches_new_scene_and_failed_applications_stay_retryable(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'auto_apply': True,
            'actor_images': False, 'scene_images': True, 'correct_cast': True})
        def scan(rows):
            with mock.patch('peach.stashdb_client.Client', return_value=self.client()), mock.patch('peach.stashdb._image', return_value=None):
                return stashdb.scan_assets(self.config, self.database, rows, progress=lambda **_: None, issue=lambda *_, **__: None)
        self.assertEqual(scan([{'id': 1}])['applied'], 1)
        with self.database.write_transaction() as connection:
            connection.execute("INSERT INTO asset(id,location,path,name,medium,duration) VALUES(2,'local','R:\\new.mp4',"
                "'EvilAngel.26.10.22.Jane.Doe.mp4','video',1200)")
        with mock.patch('peach.stashdb.preview', wraps=stashdb.preview) as preview:
            result = scan([{'id': 1}, {'id': 2}])
        self.assertEqual(result, {'applied': 1, 'review': 0, 'skipped': 1})
        self.assertEqual([call.args[2]['asset_id'] for call in preview.call_args_list], [2])
        stashdb_client.save_settings(self.config, {'actor_images': True})
        with mock.patch('peach.stashdb.apply_scene', side_effect=ValueError('temporary image failure')) as apply:
            scan([{'id': 2}])
            scan([{'id': 2}])
            self.assertEqual(apply.call_count, 2)

    def test_failed_search_skip_is_optional_and_changed_hints_allow_retry(self):
        stashdb_client.save_settings(self.config, {'enabled': True, 'skip_failed': True})
        def scan():
            with mock.patch('peach.stashdb_client.Client', return_value=self.client()):
                return stashdb.scan_assets(self.config, self.database, [{'id': 1}], progress=lambda **_: None, issue=lambda *_, **__: None)
        with mock.patch('peach.stashdb.preview', side_effect=ValueError('temporary failure')) as preview:
            self.assertEqual(scan()['skipped'], 0)
            self.assertEqual(scan()['skipped'], 1)
            self.assertEqual(preview.call_count, 1)
            stashdb_client.save_settings(self.config, {'ignore_terms': '!'})
            self.assertEqual(scan()['skipped'], 0)
            self.assertEqual(preview.call_count, 2)
            stashdb_client.save_settings(self.config, {'skip_failed': False})
            self.assertEqual(scan()['skipped'], 0)
            self.assertEqual(preview.call_count, 3)

    def test_new_media_only_uses_saved_watermark_and_manual_preview_remains_available(self):
        policy = stashdb_client.save_settings(self.config, {'enabled': True, 'only_new_media': True}, database=self.database)
        self.assertEqual(policy['new_media_after_id'], 1)
        with self.database.write_transaction() as connection:
            connection.execute("INSERT INTO asset(id,location,path,name,medium,duration) VALUES(2,'local','R:\\new.mp4',"
                "'EvilAngel.26.10.22.Jane.Doe.mp4','video',1200)")
        with mock.patch('peach.stashdb_client.Client', return_value=self.client()), mock.patch('peach.stashdb.preview', wraps=stashdb.preview) as preview:
            result = stashdb.scan_assets(self.config, self.database, [{'id': 1}, {'id': 2}], progress=lambda **_: None, issue=lambda *_, **__: None)
            self.assertEqual([call.args[2]['asset_id'] for call in preview.call_args_list], [2])
        self.assertEqual(result['skipped'], 1)
        self.assertTrue(stashdb.preview(self.config, self.database, {'asset_id': 1}, client=self.client())['candidates'])

    def test_unmatched_search_can_be_skipped_beyond_daily_cache_and_reused_ids_can_be_new(self):
        from peach.stashdb_files import search_stamp, skip_search
        stashdb_client.save_settings(self.config, {'skip_failed': True})
        policy = stashdb_client.settings(self.config)
        cached = {'evidence_token': 'evidence', 'search_policy': search_stamp(policy), 'candidates': [], 'searched_at': 0}
        self.assertTrue(skip_search(self.config, 1, 'evidence', policy, cached)[0])
        policy['skip_failed'] = False
        self.assertFalse(skip_search(self.config, 1, 'evidence', policy, cached)[0])
        policy.update(only_new_media=True, new_media_after_id=10, new_media_enabled_at='2026-10-23 10:00:00')
        self.assertFalse(skip_search(self.config, 1, 'other', policy, {}, first_seen='2026-10-24 10:00:00')[0])
