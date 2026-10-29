"""临时账本验证名字建议、确认范围、备份与实体关联迁移。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from peach import actor_merge, web_actor_merge
from peach.entities import upsert_asset_entity
from peach.migrations import upgrade
from peach.repository import LedgerDatabase
from peach.web_state import WebContract


class ActorMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.database = LedgerDatabase(self.root / 'database' / 'ledger.db')
        self.database.db_path.parent.mkdir()
        upgrade(self.database.db_path, Path(__file__).resolve().parents[1] / 'migrations')
        self.contract = WebContract(self.database.db_path, database=self.database, avatar_root=self.root / 'avatars',
            candidate_root=self.root / 'candidates', cover_root=self.root / 'covers', follow_state_root=self.root / 'state')
        with self.database.write_transaction() as connection:
            for identifier in range(1, 5):
                connection.execute("INSERT INTO asset(id,location,path,name,medium,play_seconds) VALUES(?,'local',?,?,'video',42)", (identifier, f'R:\\example-{identifier}.mp4', f'example-{identifier}.mp4'))
            self.clean = upsert_asset_entity(connection, kind='performer', name='Jane Doe', asset_id=1, role='performer', source='user:manual')
            self.extra = upsert_asset_entity(connection, kind='performer', name='Jane Doe Beach Scene', asset_id=2, role='performer', source='scan:filename-actors')
            upsert_asset_entity(connection, kind='performer', name='Jane Doe Beach Scene', asset_id=3, role='performer', source='scan:filename-actors')
            self.other = upsert_asset_entity(connection, kind='performer', name='Jane Doe Morning Scene', asset_id=4, role='performer', source='scan:filename-actors')
            connection.execute("INSERT INTO entity_alias(entity_id,alias,normalized_alias,source,confidence) VALUES(?,'Clara Fargo','clara fargo','user:alias',1)", (self.clean,))
            connection.execute("UPDATE entity SET metadata_json=? WHERE id=?", (json.dumps({'actor_profile_edits': {'height': '172'}}), self.clean))
            settings = {'libraryShortcuts': {'favorites': [{'entity_id': self.clean, 'kind': 'performer', 'name': 'Jane Doe'}]}}
            connection.execute('UPDATE profile SET settings_json=?', (json.dumps(settings),))
            for asset_id, name in ((1, 'Jane Doe'), (2, 'Jane Doe Beach Scene'), (3, 'Jane Doe Beach Scene'), (4, 'Jane Doe Morning Scene')):
                connection.execute("INSERT INTO asset_tag(asset_id,tag,source,confidence) VALUES(?,?,'scan:filename-actors',1)", (asset_id, '演员:' + name))

    def preview(self):
        return web_actor_merge.q_actor_merge(self.contract, {'actor_id': str(self.clean)})

    def request(self, ids=None):
        detail = self.preview()
        ids = ids or [self.extra]
        return {'actor_id': self.clean, 'merge_ids': ids, 'confirmed': True,
            'expected': {str(actor['id']): actor['token'] for actor in [detail['actor'], *detail['matches']] if actor['id'] == self.clean or actor['id'] in ids}}

    def test_suggestions_cover_scene_suffixes_and_aliases_without_writing(self):
        listing = web_actor_merge.q_actor_merge(self.contract, {})
        self.assertEqual(listing['total'], 1)
        self.assertEqual(listing['groups'][0]['name'], 'Jane Doe')
        self.assertEqual({row['id'] for row in self.preview()['matches']}, {self.extra, self.other})
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'query': 'Clara Fargo'})['total'], 1)
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM entity WHERE kind='performer'").fetchone()[0], 3)

    def test_only_selected_actor_is_merged_with_backup_aliases_and_history(self):
        result = web_actor_merge.w_actor_merge(self.contract, self.request())
        self.assertEqual(result['id'], self.extra)
        self.assertEqual(result['name'], 'Jane Doe')
        self.assertTrue((self.database.db_path.parent / result['backup']).is_file())
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute('SELECT count(DISTINCT asset_id) FROM asset_entity WHERE entity_id=?', (self.extra,)).fetchone()[0], 3)
            self.assertIsNotNone(connection.execute('SELECT 1 FROM entity WHERE id=?', (self.other,)).fetchone())
            aliases = {row[0] for row in connection.execute('SELECT alias FROM entity_alias WHERE entity_id=?', (self.extra,))}
            self.assertTrue({'Jane Doe Beach Scene', 'Clara Fargo'}.issubset(aliases))
            metadata = json.loads(connection.execute('SELECT metadata_json FROM entity WHERE id=?', (self.extra,)).fetchone()[0])
            self.assertEqual(metadata['actor_profile_edits']['height'], '172')
            settings = json.loads(connection.execute('SELECT settings_json FROM profile LIMIT 1').fetchone()[0])
            self.assertEqual(settings['libraryShortcuts']['favorites'][0]['entity_id'], self.extra)
            self.assertEqual(settings['libraryShortcuts']['favorites'][0]['name'], 'Jane Doe')
            self.assertEqual([row[0] for row in connection.execute('SELECT play_seconds FROM asset')], [42] * 4)
            self.assertEqual([row[0] for row in connection.execute('SELECT tag FROM asset_tag WHERE asset_id IN (1,2,3) ORDER BY asset_id')], ['演员:Jane Doe'] * 3)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_stale_and_unconfirmed_requests_do_not_merge(self):
        request = self.request()
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE entity SET metadata_json='{}' WHERE id=?", (self.clean,))
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, request)
        request['confirmed'] = False
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, request)
        self.assertEqual(list(self.database.db_path.parent.glob('ledger.pre-actor-merge-*.db')), [])

    def test_conflicting_source_identities_are_flagged_and_blocked(self):
        with self.database.write_transaction() as connection:
            for identifier, remote in ((self.clean, 'remote-one'), (self.extra, 'remote-two')):
                connection.execute("INSERT INTO entity_external_ref(entity_id,provider,external_kind,external_id) VALUES(?,'stashdb','performer',?)", (identifier, remote))
        match = next(row for row in self.preview()['matches'] if row['id'] == self.extra)
        self.assertEqual(match['conflicts'], ['stashdb:performer'])
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, self.request())

    def test_chosen_name_and_picture_follow_retained_entity(self):
        self.contract.avatar_root.mkdir()
        picture = self.contract.avatar_root / f'performer-{self.clean}.img'
        picture.write_bytes(b'preferred-picture')
        Path(str(picture) + '.ct').write_text('image/jpeg', encoding='utf-8')
        request = self.request([self.extra, self.other])
        request['name'] = 'Jane Doe Corrected'
        result = web_actor_merge.w_actor_merge(self.contract, request)
        self.assertEqual(result['name'], 'Jane Doe Corrected')
        self.assertEqual((self.contract.avatar_root / f"performer-{result['id']}.img").read_bytes(), b'preferred-picture')
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {})['total'], 0)

    def test_transaction_failure_restores_database_and_picture(self):
        request = self.request()
        with patch('peach.web_actor_merge._pictures', side_effect=OSError('picture unavailable')):
            with self.assertRaises(OSError):
                web_actor_merge.w_actor_merge(self.contract, request)
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM entity WHERE kind='performer'").fetchone()[0], 3)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_picture_installation_is_restored_if_the_merge_does_not_commit(self):
        self.contract.avatar_root.mkdir()
        original = self.contract.avatar_root / f'performer-{self.extra}.img'
        preferred = self.contract.avatar_root / f'performer-{self.clean}.img'
        original.write_bytes(b'original-picture')
        preferred.write_bytes(b'preferred-picture')
        with self.database.read_connection() as connection:
            actors = actor_merge.actors(connection)
        with self.assertRaises(RuntimeError):
            with web_actor_merge._pictures(self.contract, [actors[self.clean], actors[self.extra]], actors[self.clean], self.extra, self.root / 'backup.db'):
                self.assertEqual(original.read_bytes(), b'preferred-picture')
                raise RuntimeError('commit failed')
        self.assertEqual(original.read_bytes(), b'original-picture')
        self.assertFalse(Path(str(original) + '.provenance.json').exists())

    def test_name_similarity_is_bounded_and_not_a_merge_decision(self):
        rows = {1: {'id': 1, 'canonical_name': 'Jane Doe Sunset Beach', 'count': 1, 'aliases': []},
                2: {'id': 2, 'canonical_name': 'Jane Doe Morning Dream', 'count': 1, 'aliases': []},
                3: {'id': 3, 'canonical_name': 'John Smith', 'count': 1, 'aliases': []}}
        groups = actor_merge.suggestions(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['matches'][0]['id'], 2)

    def test_data_management_counts_include_actor_merge_groups(self):
        from peach.web_router import _get_review
        result = _get_review(self.contract, {'counts': '1'})
        self.assertEqual(result['counts']['actor_merge'], 1)
        self.assertNotIn('sections', result)

    def automatic(self):
        plan = web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})
        return web_actor_merge.w_actor_merge(self.contract, {'action': 'automatic', 'expected': plan['token'], 'confirmed': True})

    def test_automatic_merge_and_persistent_undo_preserve_unrelated_playback(self):
        from peach import actor_merge_undo
        with self.database.read_connection() as connection:
            before = actor_merge_undo.capture(connection)
        result = self.automatic()
        history = web_actor_merge.q_actor_merge(self.contract, {'mode': 'history'})
        self.assertEqual(history['batches'][0]['id'], result['id'])
        self.assertEqual(result['actors'], 2)
        self.assertTrue((self.database.db_path.parent / 'actor-merge-history' / f"{result['id']}.db").is_file())
        with self.database.write_transaction() as connection:
            connection.execute('UPDATE asset SET play_seconds=123 WHERE id=1')
        web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': result['id'], 'confirmed': True})
        with self.database.read_connection() as connection:
            self.assertEqual(actor_merge_undo.capture(connection), before)
            self.assertEqual(connection.execute('SELECT play_seconds FROM asset WHERE id=1').fetchone()[0], 123)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'mode': 'history'})['batches'], [])

    def test_automatic_excludes_conflicts_and_filter_hides_conflict_only_groups(self):
        with self.database.write_transaction() as connection:
            for identifier, remote in ((self.clean, 'one'), (self.extra, 'two'), (self.other, 'three')):
                connection.execute("INSERT INTO entity_external_ref(entity_id,provider,external_kind,external_id) VALUES(?,'stashdb','performer',?)", (identifier, remote))
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})['actors'], 0)
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {})['total'], 1)
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'hide_conflicts': '1'})['total'], 0)

    def test_undo_refuses_later_changes_and_invalid_identifiers(self):
        result = self.automatic()
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE entity SET metadata_json='{}' WHERE id=?", (self.extra,))
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': result['id'], 'confirmed': True})
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': '../ledger', 'confirmed': True})

    def test_automatic_rejects_stale_plan_and_rolls_back_failed_batch(self):
        plan = web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})
        with self.database.write_transaction() as connection:
            connection.execute("UPDATE entity SET metadata_json='{}' WHERE id=?", (self.clean,))
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, {'action': 'automatic', 'expected': plan['token'], 'confirmed': True})
        with patch('peach.web_actor_merge._pictures', side_effect=OSError('picture unavailable')):
            with self.assertRaises(OSError):
                self.automatic()
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM entity WHERE kind='performer'").fetchone()[0], 3)

    def test_automatic_does_not_merge_mutually_conflicting_candidates(self):
        with self.database.write_transaction() as connection:
            for identifier, remote in ((self.extra, 'two'), (self.other, 'three')):
                connection.execute("INSERT INTO entity_external_ref(entity_id,provider,external_kind,external_id) VALUES(?,'stashdb','performer',?)", (identifier, remote))
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})['actors'], 0)

    def test_automatic_undo_restores_portrait_and_rejects_changed_picture(self):
        self.contract.avatar_root.mkdir()
        for identifier, payload in ((self.clean, b'clean'), (self.extra, b'original')):
            (self.contract.avatar_root / f'performer-{identifier}.img').write_bytes(payload)
        result = self.automatic()
        picture = self.contract.avatar_root / f'performer-{self.extra}.img'
        self.assertEqual(picture.read_bytes(), b'clean')
        picture.write_bytes(b'new-edit')
        with self.assertRaises(ValueError):
            web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': result['id'], 'confirmed': True})
        picture.write_bytes(b'clean')
        web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': result['id'], 'confirmed': True})
        self.assertEqual(picture.read_bytes(), b'original')

    def test_automatic_skips_fuzzy_spelling_and_recovers_committed_journal(self):
        from peach import actor_merge_undo
        with self.database.write_transaction() as connection:
            upsert_asset_entity(connection, kind='performer', name='John Smith', asset_id=1, role='performer', source='user:manual')
            upsert_asset_entity(connection, kind='performer', name='John Smithe', asset_id=2, role='performer', source='scan:filename-actors')
        plan = web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})
        self.assertEqual(plan['actors'], 2)
        result = self.automatic()
        path = self.database.db_path.parent / 'actor-merge-history' / f"{result['id']}.json"
        record = actor_merge_undo.load(path)
        record['status'] = 'prepared'
        actor_merge_undo.save(path, record)
        self.assertEqual(len(web_actor_merge.q_actor_merge(self.contract, {'mode': 'history'})['batches']), 1)
        web_actor_merge.w_actor_merge(self.contract, {'action': 'undo', 'batch_id': result['id'], 'confirmed': True})
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM entity WHERE kind='performer'").fetchone()[0], 5)

    def test_ignored_pair_is_hidden_from_automatic_plan_and_can_be_restored(self):
        request = self.request()
        web_actor_merge.w_actor_merge(self.contract, {**request, 'action': 'ignore'})
        self.assertNotIn(self.extra, {row['id'] for row in self.preview()['matches']})
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})['actors'], 1)
        detail = web_actor_merge.q_actor_merge(self.contract, {'actor_id': str(self.clean), 'include_ignored': '1'})
        self.assertTrue(next(row for row in detail['matches'] if row['id'] == self.extra)['ignored'])
        web_actor_merge.w_actor_merge(self.contract, {**request, 'action': 'unignore'})
        self.assertEqual(web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic'})['actors'], 2)

    def test_selected_groups_merge_independently_and_leave_unselected_group(self):
        with self.database.write_transaction() as connection:
            john = upsert_asset_entity(connection, kind='performer', name='John Smith', asset_id=1, role='performer', source='user:manual')
            upsert_asset_entity(connection, kind='performer', name='John Smith Scene', asset_id=2, role='performer', source='scan:filename-actors')
            upsert_asset_entity(connection, kind='performer', name='Alice Brown', asset_id=3, role='performer', source='user:manual')
            upsert_asset_entity(connection, kind='performer', name='Alice Brown Scene', asset_id=4, role='performer', source='scan:filename-actors')
        selected = [self.clean, john]
        plan = web_actor_merge.q_actor_merge(self.contract, {'mode': 'automatic', 'actor_ids': ','.join(map(str, selected))})
        result = web_actor_merge.w_actor_merge(self.contract, {'action': 'automatic', 'group_ids': selected, 'expected': plan['token'], 'confirmed': True})
        self.assertEqual(result['groups'], 2)
        with self.database.read_connection() as connection:
            names = {row[0] for row in connection.execute("SELECT canonical_name FROM entity WHERE kind='performer'")}
            self.assertEqual(names, {'Jane Doe', 'John Smith', 'Alice Brown', 'Alice Brown Scene'})
