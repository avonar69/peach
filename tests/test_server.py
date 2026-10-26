"""无桌面入口的进程退出与现有数据保护。"""
import subprocess
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from peach import server, settings_file
from starlette.requests import Request


class ServerTests(unittest.TestCase):
    def test_existing_rss_database_is_upgraded_with_backup_before_serving(self):
        from peach.config import MIGRATIONS_DIR
        from peach.migrations import upgrade
        from peach import feeds
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = settings_file.load_config(environ={"PEACH_DATA_ROOT": str(root)})
            settings_file.write(config)
            prior = root / 'prior-migrations'
            prior.mkdir()
            for migration in MIGRATIONS_DIR.glob('*.sql'):
                if migration.name < '0050_':
                    shutil.copyfile(migration, prior / migration.name)
            database = config.directory('database') / 'ledger.db'
            database.parent.mkdir(exist_ok=True)
            upgrade(database, prior)
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.row_factory = sqlite3.Row
                identity = feeds.add_source(connection, url='https://example.com/feed', name='Example', kind='rss')
                connection.execute("INSERT INTO feed_item(source_id,item_key,title,first_seen) VALUES(?,?,?,?)",
                                   (identity, 'saved', 'Saved post', '2026-10-01T00:00:00Z'))
            with patch.dict(os.environ, {'PEACH_DATA_ROOT': str(root)}):
                server.prepare_database()
                server.prepare_database()
            with closing(sqlite3.connect(database)) as connection:
                connection.row_factory = sqlite3.Row
                self.assertEqual(feeds.sources(connection)[0]['name'], 'Example')
                self.assertEqual([tuple(row) for row in connection.execute('SELECT title,rss_merged_into,rss_expired_at FROM feed_item')], [('Saved post', None, None)])
                self.assertEqual(connection.execute("SELECT count(*) FROM schema_migration WHERE version='0050'").fetchone()[0], 1)
            self.assertEqual(len(list(database.parent.glob('ledger.pre-migrate-*.db'))), 1)

    def test_reader_does_not_upgrade_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = settings_file.load_config(environ={'PEACH_DATA_ROOT': str(root)})
            database = config.directory('database') / 'ledger.db'
            database.parent.mkdir(parents=True)
            database.touch()
            with patch.object(server.settings_file, 'load_config', return_value=config), \
                    patch('peach.runtime_prepare.ledger_writer', return_value=(False, 'reader')), \
                    patch.object(server.subprocess, 'run') as run:
                server.prepare_database()
            run.assert_not_called()

    def test_failed_upgrade_prevents_service_start(self):
        with patch.object(server, 'initialize'), \
                patch.object(server, 'prepare_database', side_effect=subprocess.CalledProcessError(1, 'migrate')), \
                patch.object(server, 'supervise') as supervise, patch.object(server.signal, 'signal'):
            with self.assertRaises(subprocess.CalledProcessError):
                server.main([])
            supervise.assert_not_called()

    def test_headless_configuration_accepts_private_peers_and_rejects_forwarding(self):
        from peach.routes_configuration import local_client, managed_configuration
        with patch.dict("os.environ", {"PEACH_HEADLESS_MANAGED": "1"}):
            self.assertTrue(managed_configuration())
            for peer, headers, allowed in (
                ("192.0.2.1", [], True), ("198.51.100.10", [], True),
                ("8.8.8.8", [], False), ("169.254.1.1", [], False),
                ("0.0.0.0", [], False), ("240.0.0.1", [], False),
                ("127.0.0.1", [], True), ("fd00::1", [], True),
                ("192.0.2.1", [(b"x-forwarded-for", b"8.8.8.8")], False),
                ("192.0.2.1", [(b"x-forwarded-host", b"example.com")], False),
            ):
                request = Request({"type": "http", "client": (peer, 1234),
                                   "server": ("0.0.0.0", 8900), "headers": headers,
                                   "app": SimpleNamespace(state=SimpleNamespace(tunnel=None))})
                with self.subTest(peer=peer, headers=headers):
                    self.assertEqual(local_client(request), allowed)

    def test_cli_without_mdns_or_tunnel_needs_no_network_route(self):
        from peach import cli
        with patch.object(cli, "_require_readable_settings"), \
                patch.object(cli, "_serve_token", return_value="test"), \
                patch.object(cli, "_build_sync", return_value=None), \
                patch.object(cli, "create_app"), patch.object(cli, "TUNNEL_ENABLED", False), \
                patch("peach.mdns.lan_ipv4", side_effect=OSError("no route")) as route, \
                patch("uvicorn.run"):
            self.assertEqual(cli.main(["serve", "--host", "0.0.0.0", "--no-mdns"]), 0)
        route.assert_not_called()

    def test_initialization_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = settings_file.load_config(environ={"PEACH_DATA_ROOT": str(root)})
            settings_file.write(config)
            existing = config.path.read_bytes()
            with patch.object(server.settings_file, "load_config", return_value=settings_file.load_config(
                    environ={"PEACH_DATA_ROOT": str(root)})), patch.object(server, "launch") as launch:
                server.initialize()
            launch.assert_not_called()
            self.assertEqual(config.path.read_bytes(), existing)

    def test_initialization_rejects_database_without_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = settings_file.load_config(environ={"PEACH_DATA_ROOT": str(root)})
            config.directory("database").mkdir()
            config.directory("database").joinpath("ledger.db").write_bytes(b"existing")
            with patch.object(server.settings_file, "load_config", return_value=config), \
                    patch.object(server, "launch") as launch:
                with self.assertRaisesRegex(RuntimeError, "已有数据库"):
                    server.initialize()
            launch.assert_not_called()

    def test_stop_waits_for_child_exit(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                   stdin=subprocess.DEVNULL)
        try:
            server.stop_process(process)
            self.assertIsNotNone(process.poll())
        finally:
            server.stop_process(process)

    def test_service_failure_exits_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            config = settings_file.load_config(environ={"PEACH_DATA_ROOT": str(Path(directory).resolve())})
            process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(17)"],
                                       stdin=subprocess.DEVNULL)
            process.wait(timeout=15)
            with patch.object(server.settings_file, "load_config", return_value=config), \
                    patch.object(server, "launch", return_value=process):
                self.assertEqual(server.supervise("127.0.0.1", 8900, threading.Event()), 17)
