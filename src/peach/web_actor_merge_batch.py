"""演员批量合并、持久备份与撤销入口。"""
import hashlib
import json
import re
import shutil
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from . import actor_merge, actor_merge_undo
from .migrations import sqlite_backup


def _root(contract):
    return Path(contract.database.db_path).parent / 'actor-merge-history'


def _plan(connection):
    actors = actor_merge.actors(connection)
    groups = actor_merge.automatic_groups(actors)
    tokens = {str(identifier): actor_merge.token(connection, identifier) for group in groups for identifier in group}
    token = hashlib.sha256(json.dumps([groups, tokens], sort_keys=True).encode()).hexdigest()
    return actors, groups, token


def preview(contract):
    with contract.read_connection() as connection:
        _, groups, token = _plan(connection)
    return {'groups': len(groups), 'actors': sum(len(group) - 1 for group in groups), 'token': token}


def history(contract):
    root = _root(contract)
    batches = []
    if root.is_dir():
        for path in root.glob('*.json'):
            try:
                row = actor_merge_undo.load(path)
                if row['status'] == 'prepared':
                    with contract.read_connection() as connection:
                        actor_merge_undo.validate(connection, row['changes'])
                if row['status'] in ('merged', 'prepared'):
                    batches.append({key: row[key] for key in ('id', 'created_at', 'groups', 'actors')})
            except (OSError, ValueError, KeyError):
                continue
    return {'batches': sorted(batches, key=lambda row: row['created_at'], reverse=True)}


def write(contract, body):
    if body.get('confirmed') is not True:
        raise ValueError('请确认演员批量操作')
    if body['action'] == 'undo':
        return _undo(contract, body)
    return _automatic(contract, body)


def _automatic(contract, body):
    from .web_actor_merge import _pictures
    identifier = uuid.uuid4().hex
    root = _root(contract)
    root.mkdir(parents=True, exist_ok=True)
    backup, journal = root / f'{identifier}.db', root / f'{identifier}.json'
    with ExitStack() as stack, contract.write_transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        actors, groups, token = _plan(connection)
        if token != body.get('expected'):
            raise ValueError('演员资料已变化，请刷新后重试')
        if not groups:
            raise ValueError('没有可自动合并的演员')
        sqlite_backup(contract.database.db_path, backup)
        picture_backup = root / f'{identifier}.portraits'
        picture_backup.mkdir()
        for path in contract.avatar_root.glob('performer-*.img*'):
            if path.is_file():
                shutil.copy2(path, picture_backup / path.name)
        before = actor_merge_undo.capture(connection)
        violations = {tuple(row) for row in connection.execute('PRAGMA foreign_key_check')}
        identifiers = [value for group in groups for value in group]
        images = actor_merge_undo.pictures(contract.avatar_root, identifiers)
        for group in groups:
            chosen = [actors[value] for value in group]
            result = actor_merge.merge(connection, chosen, chosen[0])
            stack.enter_context(_pictures(contract, chosen, chosen[0], result['id'], backup.with_name(f'{identifier}-{group[0]}.db')))
        if any(tuple(row) not in violations for row in connection.execute('PRAGMA foreign_key_check')):
            raise ValueError('演员合并校验失败，资料保持原样')
        record = {'id': identifier, 'status': 'prepared', 'created_at': datetime.now(timezone.utc).isoformat(),
                  'groups': len(groups), 'actors': sum(len(group) - 1 for group in groups),
                  'changes': actor_merge_undo.delta(before, actor_merge_undo.capture(connection)),
                  'tokens': {str(row[0]): actor_merge.token(connection, row[0]) for row in connection.execute("SELECT id FROM entity WHERE kind='performer'") if row[0] in identifiers},
                  'pictures_before': images, 'pictures_after': actor_merge_undo.pictures(contract.avatar_root, identifiers)}
        actor_merge_undo.save(journal, record)
    record['status'] = 'merged'
    actor_merge_undo.save(journal, record)
    contract.cache_bust()
    return {'ok': True, 'id': identifier, 'groups': record['groups'], 'actors': record['actors']}


def _undo(contract, body):
    identifier = str(body.get('batch_id') or '')
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ValueError('演员撤销记录无效')
    journal = _root(contract) / f'{identifier}.json'
    with ExitStack() as stack, contract.write_transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        record = actor_merge_undo.load(journal)
        if record['status'] not in ('merged', 'prepared'):
            raise ValueError('演员撤销记录无效')
        if any(actor_merge.token(connection, int(value)) != token for value, token in record['tokens'].items()):
            raise ValueError('合并后的演员资料已修改，无法安全撤销')
        violations = {tuple(row) for row in connection.execute('PRAGMA foreign_key_check')}
        actor_merge_undo.restore(connection, record['changes'])
        if any(tuple(row) not in violations for row in connection.execute('PRAGMA foreign_key_check')):
            raise ValueError('合并后的演员资料已修改，无法安全撤销')
        sqlite_backup(contract.database.db_path, _root(contract) / f'{identifier}.pre-undo-{uuid.uuid4().hex}.db')
        stack.enter_context(actor_merge_undo.restore_pictures(contract.avatar_root, record['pictures_before'], record['pictures_after']))
    record['status'] = 'undone'
    actor_merge_undo.save(journal, record)
    contract.cache_bust()
    return {'ok': True}
