"""人工复核中的演员合并列表、预览与备份写入。"""
import json
import uuid
from contextlib import contextmanager, ExitStack
from pathlib import Path

from . import actor_merge
from .avatar_provider import install_entity_avatar
from .fsutil import atomic_write_bytes, atomic_write_text
from .migrations import sqlite_backup
from .entities import canonicalize_entity_name, normalize_entity_name


def snapshot(contract):
    def read():
        with contract.read_connection() as connection:
            actors = actor_merge.actors(connection)
        return {'actors': actors, 'groups': actor_merge.suggestions(actors)}
    return contract.cached_until_changed('actor-merge-suggestions', read)


def _public(contract, actor):
    path = contract.avatar_root / f"performer-{actor['id']}.img"
    return {'id': actor['id'], 'name': actor['canonical_name'], 'scenes': actor['count'], 'aliases': actor['aliases'], 'has_image': path.is_file()}


def q_actor_merge(contract, args):
    from . import web_actor_merge_batch
    if args.get('mode') == 'automatic':
        return web_actor_merge_batch.preview(contract)
    if args.get('mode') == 'history':
        return web_actor_merge_batch.history(contract)
    data = snapshot(contract)
    query = str(args.get('query') or '').strip().casefold()
    selected = int(args.get('actor_id') or 0)
    if selected:
        group = next((row for row in data['groups'] if row['id'] == selected), None)
        if not group:
            raise ValueError('演员合并建议已变化，请刷新后重试')
        anchor = data['actors'][selected]
        with contract.read_connection() as connection:
            target = {**_public(contract, anchor), 'token': actor_merge.token(connection, selected)}
            matches = [{**_public(contract, data['actors'][match['id']]), 'reason': match['reason'],
                'conflicts': actor_merge.conflicts([anchor, data['actors'][match['id']]]),
                'token': actor_merge.token(connection, match['id'])} for match in group['matches']]
        return {'actor': target, 'matches': matches}
    groups = [group for group in data['groups'] if not query or any(query in name.casefold() for identifier in [group['id'], *(match['id'] for match in group['matches'])] for name in [data['actors'][identifier]['canonical_name'], *data['actors'][identifier]['aliases']])]
    if str(args.get('hide_conflicts') or '') == '1':
        groups = [group for group in groups if any(not actor_merge.conflicts([data['actors'][group['id']], data['actors'][match['id']]]) for match in group['matches'])]
    groups.sort(key=lambda group: (-len(group['matches']), data['actors'][group['id']]['canonical_name']))
    offset = max(0, int(args.get('offset') or 0))
    return {'total': len(groups), 'offset': offset, 'groups': [{**_public(contract, data['actors'][group['id']]), 'matches': len(group['matches'])} for group in groups[offset:offset + 20]]}


def _selection(body):
    target, selected, expected = body.get('actor_id'), body.get('merge_ids'), body.get('expected')
    if body.get('confirmed') is not True or type(target) is not int or target < 1:
        raise ValueError('请确认要保留的演员')
    if not isinstance(selected, list) or not 1 <= len(selected) <= 2000 or any(type(value) is not int or value < 1 or value == target for value in selected) or len(set(selected)) != len(selected):
        raise ValueError('请选择 1–2000 个要合并的演员')
    identifiers = [target, *selected]
    if not isinstance(expected, dict) or set(expected) != {str(value) for value in identifiers}:
        raise ValueError('请刷新演员合并建议后重试')
    return target, identifiers, expected


def _image_files(root, identifier):
    path = root / f'performer-{identifier}.img'
    return {suffix: Path(str(path) + suffix).read_bytes() for suffix in ('', '.ct', '.face.json', '.provenance.json') if Path(str(path) + suffix).is_file()}


@contextmanager
def _pictures(contract, chosen, preferred, kept_id, backup):
    order = dict.fromkeys([preferred['id'], kept_id, *(actor['id'] for actor in chosen)])
    preferred_id = next((value for value in order if (contract.avatar_root / f'performer-{value}.img').is_file()), None)
    if preferred_id is None or preferred_id == kept_id:
        yield
        return
    original, files = _image_files(contract.avatar_root, kept_id), _image_files(contract.avatar_root, preferred_id)
    for identifier, pictures in ((kept_id, original), (preferred_id, files)):
        for suffix, payload in pictures.items():
            atomic_write_bytes(backup.with_suffix('.images') / f'performer-{identifier}.img{suffix}', payload)
    try:
        install_entity_avatar(contract.avatar_root, 'performer', kept_id, files[''], files.get('.ct', b'image/jpeg').decode(),
            json.loads(files.get('.provenance.json', b'{}')), json.loads(files.get('.face.json', b'null')), probe_face=False)
        yield
    except BaseException:
        for suffix in ('', '.ct', '.face.json', '.provenance.json'):
            path = contract.avatar_root / f'performer-{kept_id}.img{suffix}'
            if suffix in original:
                atomic_write_bytes(path, original[suffix])
            else:
                path.unlink(missing_ok=True)
        raise


def w_actor_merge(contract, body):
    from . import web_actor_merge_batch
    if body.get('action') in ('automatic', 'undo'):
        return web_actor_merge_batch.write(contract, body)
    target, identifiers, expected = _selection(body)
    backup = Path(contract.database.db_path).with_name(f'ledger.pre-actor-merge-{uuid.uuid4().hex}.db')
    with ExitStack() as stack, contract.write_transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        actors = actor_merge.actors(connection)
        if any(value not in actors or actor_merge.token(connection, value) != expected[str(value)] for value in identifiers):
            raise ValueError('演员资料已变化，请刷新后重试')
        group = next((row for row in actor_merge.suggestions(actors) if row['id'] == target), None)
        if not group or not set(identifiers[1:]).issubset({row['id'] for row in group['matches']}):
            raise ValueError('请选择当前建议中的演员')
        chosen = [actors[value] for value in identifiers]
        preferred = _preferred(connection, actors[target], chosen, body.get('name'))
        if actor_merge.conflicts(chosen):
            raise ValueError('来源身份冲突，请分别核对演员')
        sqlite_backup(contract.database.db_path, backup)
        receipt = {'actor_id': target, 'actors': chosen, 'preferred_name': preferred['canonical_name'], 'status': 'prepared', 'backup': backup.name}
        atomic_write_text(backup.with_suffix('.merge.json'), json.dumps(receipt, ensure_ascii=False))
        before = {tuple(row) for row in connection.execute('PRAGMA foreign_key_check')}
        result = actor_merge.merge(connection, chosen, preferred)
        if any(tuple(row) not in before for row in connection.execute('PRAGMA foreign_key_check')):
            raise ValueError('演员合并校验失败，资料保持原样')
        stack.enter_context(_pictures(contract, chosen, actors[target], result['id'], backup))
    receipt.update(status='merged', result=result)
    atomic_write_text(backup.with_suffix('.merge.json'), json.dumps(receipt, ensure_ascii=False))
    contract.cache_bust()
    return {'ok': True, **result, 'backup': backup.name}


def _preferred(connection, actor, chosen, name):
    value = name if name is not None else actor['canonical_name']
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('请输入有效的演员规范名')
    canonical = canonicalize_entity_name('performer', value)
    if not canonical:
        raise ValueError('请输入有效的演员规范名')
    existing = connection.execute("SELECT id FROM entity WHERE kind='performer' AND normalized_name=?", (normalize_entity_name(canonical),)).fetchone()
    if existing and existing[0] not in {row['id'] for row in chosen}:
        raise ValueError('该名字属于其他演员，请将其加入合并范围')
    return {**actor, 'canonical_name': canonical}
