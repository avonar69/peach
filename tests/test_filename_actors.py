"""临时账本验证文件名演员识别、来源隔离及扫描入口。"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from peach import filename_actors, filename_matching, scan
from peach.entities import upsert_asset_entity
from peach.migrations import upgrade


class FilenameActorsTests(unittest.TestCase):
    def test_dated_studio_releases_create_multiple_actors_without_a_seed_catalog(self):
        index = filename_actors.actor_index(self.connection)
        self.assertEqual(filename_actors.names_from_filename(
            'StudioName.26.10.22.Naomi.Lastname.And.Aubree.Blair.mp4', index),
            ['Naomi Lastname', 'Aubree Blair'])
        self.assertEqual(filename_actors.names_from_filename(
            'Studio.Name.2026.10.22.Naomi.Lastname.And.Aubree.Blair.1080p.WEB-DL.x264.mp4', index),
            ['Naomi Lastname', 'Aubree Blair'])
        self.assertEqual(filename_actors.names_from_filename('Studio.26.02.31.Jane.Doe.mp4', index), [])
        self.assertEqual(filename_actors.names_from_filename('ABC-123.1080p.mp4', index), [])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.db = self.root / 'ledger.db'
        upgrade(self.db, Path(__file__).resolve().parents[1] / 'migrations')
        self.connection = sqlite3.connect(self.db)
        self.addCleanup(self.connection.close)
        self.connection.execute("INSERT INTO asset(id,location,path,name,medium) VALUES(1,'local','R:\\seed.mp4','seed.mp4','video')")

    def seed(self, name):
        return upsert_asset_entity(self.connection, kind='performer', name=name, asset_id=1,
                                   role='performer', source='user:test', update_entity_metadata=False)

    def test_multiple_names_aliases_boundaries_and_ambiguous_aliases(self):
        jane, john = self.seed('Jane Doe'), self.seed('John Smith')
        self.seed('Ann')
        for entity_id, alias in [(jane, 'JD'), (john, 'Johnny'), (jane, 'Shared'), (john, 'Shared')]:
            self.connection.execute('INSERT INTO entity_alias(entity_id,alias,normalized_alias,source) VALUES(?,?,?,?)',
                                    (entity_id, alias, alias.lower(), 'user:test'))
        index = filename_actors.actor_index(self.connection)
        self.assertCountEqual(filename_actors.names_from_filename('Jane.Doe & Johnny - Scene.mp4', index), ['John Smith', 'Jane Doe'])
        self.assertEqual(filename_actors.names_from_filename('Anna Shared.mp4', index), [])
        self.assertEqual(filename_actors.names_from_filename('JD_Jane_Doe.mp4', index), ['Jane Doe'])

    def test_explicit_fields_create_actors_and_keep_other_sources(self):
        self.seed('Manual Actor')
        self.connection.execute("UPDATE asset SET name='Scene [actors=Jane Doe; John Smith].mp4' WHERE id=1")
        self.assertEqual(filename_actors.apply(self.connection, [1]), 2)
        self.assertEqual(filename_actors.apply(self.connection, [1]), 2)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE asset_id=1').fetchone()[0], 3)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_tag WHERE source=?', (filename_actors.SOURCE,)).fetchone()[0], 2)
        self.connection.execute("UPDATE asset SET name='Scene.mp4' WHERE id=1")
        filename_actors.apply(self.connection, [1])
        self.assertEqual(self.connection.execute('SELECT source FROM asset_entity WHERE asset_id=1').fetchone()[0], 'user:test')

    def test_scan_and_push_ingestion_attach_filename_actors(self):
        filename_matching.save(self.root / 'state', {'actors': True, 'studios': True})
        self.seed('Jane Doe')
        self.connection.commit()
        media = self.root / 'media'
        media.mkdir()
        (media / 'EvilAngel.26.10.22.Jane.Doe.mp4').write_bytes(b'test')
        declared = {'local': (str(media),)}
        scan.scan_location(self.db, 'local', str(media), declared_roots=declared, report=lambda _: None)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.SOURCE,)).fetchone()[0], 1)
        (media / 'OtherStudio.26.10.22.John.Smith.mp4').write_bytes(b'test')
        scan.ingest_path(self.db, 'local', str(media / 'OtherStudio.26.10.22.John.Smith.mp4'), declared_roots=declared)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.SOURCE,)).fetchone()[0], 2)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.STUDIO_SOURCE,)).fetchone()[0], 2)
        self.assertEqual({row[0] for row in self.connection.execute("SELECT studio FROM asset WHERE id<>1")}, {'EvilAngel', 'OtherStudio'})

    def test_studio_prefix_alias_conflicts_and_owned_projection(self):
        studio = upsert_asset_entity(self.connection, kind='studio', name='Evil Angel', asset_id=1,
            role='studio', source='user:test', update_entity_metadata=False)
        self.connection.execute('INSERT INTO entity_alias(entity_id,alias,normalized_alias,source) VALUES(?,?,?,?)',
            (studio, 'EvilAngel', 'evilangel', 'user:test'))
        self.assertEqual(filename_actors.studio_from_filename(self.connection, 'EvilAngel.26.10.22.Jane.Doe.mp4'), 'Evil Angel')
        self.assertIsNone(filename_actors.studio_from_filename(self.connection, 'EvilAngel.26.02.31.Jane.Doe.mp4'))
        self.assertIsNone(filename_actors.studio_from_filename(self.connection, 'random.scene.mp4'))
        self.connection.execute('DELETE FROM asset_entity WHERE asset_id=1')
        self.connection.execute("UPDATE asset SET name='NewStudio.26.10.22.Jane.Doe.mp4' WHERE id=1")
        self.assertEqual(filename_actors.apply(self.connection, [1], actors=False, studios=True), 1)
        self.assertEqual(self.connection.execute('SELECT studio FROM asset WHERE id=1').fetchone()[0], 'NewStudio')
        self.assertEqual(filename_actors.apply(self.connection, [1], actors=False, studios=True), 1)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.SOURCE,)).fetchone()[0], 0)
        self.connection.execute("UPDATE asset SET name='OtherStudio.26.10.22.Jane.Doe.mp4' WHERE id=1")
        filename_actors.apply(self.connection, [1], actors=False, studios=True)
        self.assertEqual(self.connection.execute('SELECT studio FROM asset WHERE id=1').fetchone()[0], 'OtherStudio')
        self.connection.execute("UPDATE asset SET studio='Manual studio',field_owners=? WHERE id=1", ('{"studio":"user:test"}',))
        filename_actors.apply(self.connection, [1], actors=False, studios=True)
        self.assertEqual(self.connection.execute('SELECT studio FROM asset WHERE id=1').fetchone()[0], 'Manual studio')
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.STUDIO_SOURCE,)).fetchone()[0], 0)
        self.connection.execute("UPDATE asset SET studio='' WHERE id=1")
        filename_actors.apply(self.connection, [1], actors=False, studios=True)
        self.assertEqual(self.connection.execute('SELECT studio FROM asset WHERE id=1').fetchone()[0], '')
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.STUDIO_SOURCE,)).fetchone()[0], 0)

    def test_matching_is_opt_in_and_switches_are_independent(self):
        self.connection.execute("UPDATE asset SET name='EvilAngel.26.10.22.Jane.Doe.mp4' WHERE id=1")
        self.assertEqual(filename_matching.read(self.root / 'state'), {'actors': False, 'studios': False})
        self.assertEqual(filename_matching.apply(self.connection, [1], self.db), 0)
        filename_matching.save(self.root / 'state', {'actors': False, 'studios': True})
        self.assertEqual(filename_matching.apply(self.connection, [1], self.db), 1)
        filename_matching.save(self.root / 'state', {'actors': True, 'studios': False})
        filename_matching.apply(self.connection, [1], self.db)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE source=?', (filename_actors.SOURCE,)).fetchone()[0], 1)
        filename_matching.save(self.root / 'state', {'actors': False, 'studios': False})
        filename_matching.apply(self.connection, [1], self.db)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM asset_entity WHERE asset_id=1').fetchone()[0], 2)
        with self.assertRaises(ValueError):
            filename_matching.save(self.root / 'state', {'actors': 'true', 'studios': False})
