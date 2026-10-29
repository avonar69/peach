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


def _plan(connection, group_ids=None, *, ignore=False):
    actors = actor_merge.actors(connection)
    ignored = actor_merge.ignored_pairs(connection)
    groups = [[row['id'], *(match['id'] for match in row['matches'])] for row in actor_merge.suggestions(actors, ignored)] if ignore else actor_merge.automatic_groups(actors, ignored)
    if group_ids is not None:
        groups = [group for group in groups if group[0] in group_ids]
    tokens = {str(identifier): actor_merge.token(connection, identifier) for group in groups for identifier in group}
    token = hashlib.sha256(json.dumps([groups, tokens], sort_keys=True).encode()).hexdigest()
    return actors, groups, token


def preview(contract, actor_ids=None, *, ignore=False):
    group_ids = _group_ids(actor_ids.split(',') if actor_ids else None, strings=True)
    with contract.read_connection() as connection:
        _, groups, token = _plan(connection, group_ids, ignore=ignore)
    return {'groups': len(groups), 'actors': sum(len(group) - 1 for group in groups), 'token': token}


def _group_ids(values, strings=False):
    if values is None:
        return None
    if not isinstance(values, list) or not 1 <= len(values) <= 2000 or any(not str(value).isdecimal() if strings else type(value) is not int for value in values):
        raise ValueError('请选择当前建议中的演员')
    result = list(dict.fromkeys(map(int, values)))
    if any(value <= 0 for value in result):
        raise ValueError('请选择当前建议中的演员')
    return result


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
    if body['action'] == 'ignore_groups':
        return _ignore_groups(contract, body)
    return _automatic(contract, body)


def _ignore_groups(contract, body):
    from .web_actor_merge import _ignore_pair
    identifiers = _group_ids(body.get('group_ids'))
    if identifiers is None:
        raise ValueError('请选择当前建议中的演员')
    with contract.write_transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        _, groups, token = _plan(connection, identifiers, ignore=True)
        if token != body.get('expected') or {group[0] for group in groups} != set(identifiers):
            raise ValueError('演员资料已变化，请刷新后重试')
        for group in groups:
            for value in group[1:]:
                _ignore_pair(connection, group[0], value)
    contract.cache_bust()
    return {'ok': True, 'groups': len(groups), 'ignored': sum(len(group) - 1 for group in groups)}


def _automatic(contract, body):
    from .web_actor_merge import _pictures
    identifier = uuid.uuid4().hex
    root = _root(contract)
    root.mkdir(parents=True, exist_ok=True)
    backup, journal = root / f'{identifier}.db', root / f'{identifier}.json'
    with ExitStack() as stack, contract.write_transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        actors, groups, token = _plan(connection, _group_ids(body.get('group_ids')))
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
