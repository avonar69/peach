"""只按本机已有演员与厂牌去重采集，不查询作品。"""
import hashlib
import json
import time

from . import stashdb_client, stashdb_matching
from .fsutil import atomic_write_text
from .processing_control import checkpoint
from .stashdb_files import read_record, stash_photo


def _entities(database, selected):
    with database.read_connection() as connection:
        entities = {}
        for row in connection.execute("SELECT e.id,e.kind,e.canonical_name,ae.asset_id FROM entity e "
                "JOIN asset_entity ae ON ae.entity_id=e.id WHERE e.kind IN ('performer','studio') ORDER BY e.id"):
            if row[3] in selected:
                entities.setdefault(row[0], dict(id=row[0], kind=row[1], name=row[2], asset_id=row[3]))
        for entity in entities.values():
            entity['aliases'] = [row[0] for row in connection.execute(
                'SELECT alias FROM entity_alias WHERE entity_id=?', (entity['id'],))]
            entity['remote'] = [row[0] for row in connection.execute(
                "SELECT external_id FROM entity_external_ref WHERE entity_id=? AND provider='stashdb'",
                (entity['id'],))]
    return entities


def _cached(config, entity, policy):
    path = config.directory('state') / 'stashdb-entities' / f"{entity['id']}.json"
    token = hashlib.sha256(json.dumps([entity['kind'], entity['name'], entity['aliases'],
        policy['actor_images']], sort_keys=True).encode()).hexdigest()
    cached = read_record(path)
    target = config.directory('generated') / 'avatars' / f"performer-{entity['id']}.img"
    photos = entity['kind'] == 'performer' and policy['actor_images']
    installed = not photos or (len(entity['remote']) == 1 and stash_photo(target, entity['remote'][0]))
    fresh = time.time() - cached.get('searched_at', 0) < 86400
    reusable = cached.get('token') == token and (
        cached.get('ok') and (installed or target.exists() or not cached.get('had_image'))
        or policy['skip_failed']
        or fresh and not cached.get('ok') and not cached.get('failed'))
    return path, token, (entity['remote'] and installed) or reusable


def _match(client, entity):
    client.incomplete = False
    if entity['kind'] == 'performer' and len(entity['remote']) == 1:
        candidates = [client.performer(entity['remote'][0])]
    else:
        candidates = (client.performers if entity['kind'] == 'performer' else client.studios)(entity['name'])
        known = {stashdb_matching.key(name) for name in [entity['name'], *entity['aliases']]}
        candidates = [item for item in candidates if known & {
            stashdb_matching.key(name) for name in [item['name'], *(item.get('aliases') or [])]}]
    candidates = [item for item in candidates if item and not item.get('deleted')
        and 'ambiguous' not in str(item.get('disambiguation') or '').casefold() and item.get('id')]
    return candidates[0] if len(candidates) == 1 and not client.incomplete else None


def _apply(config, database, client, entity, found, policy):
    from .stashdb import SOURCE, _photo, identity
    remote = identity(found['id'])
    with database.write_transaction() as connection:
        conflicts = connection.execute("SELECT entity_id,external_id FROM entity_external_ref "
            "WHERE provider='stashdb' AND external_kind=? AND (entity_id=? OR external_id=?)",
            (entity['kind'], entity['id'], remote)).fetchall()
        if any(row[0] != entity['id'] or row[1] != remote for row in conflicts):
            raise ValueError('Review the conflicting StashDB identity before matching this actor or studio.')
        connection.execute("INSERT OR IGNORE INTO entity_external_ref"
            "(entity_id,provider,external_kind,external_id,metadata_json) VALUES(?,'stashdb',?,?,?)",
            (entity['id'], entity['kind'], remote, json.dumps({'source': SOURCE})))
    photos = entity['kind'] == 'performer' and policy['actor_images']
    if photos:
        _photo(config, client, found, entity['id'])
    return bool(photos and found.get('images'))


def scan(config, database, rows, *, client, progress, issue, active):
    policy = stashdb_client.settings(config)
    selected = {row['id']: row for row in rows if not policy['only_new_media']
        or row['id'] > policy['new_media_after_id']
        or (row.get('first_seen') or '') > policy['new_media_enabled_at']}
    entities = _entities(database, selected)
    applied = skipped = 0
    for position, entity in enumerate(entities.values()):
        if not active():
            raise InterruptedError('处理任务已停止')
        checkpoint()
        path, token, reusable = _cached(config, entity, policy)
        progress(stage='StashDB actor and studio matching', checked=position, total=len(entities),
                 current_asset_id=entity['asset_id'])
        if reusable:
            skipped += 1
            continue
        try:
            found = _match(client, entity)
            ok, had_image = bool(found), False
            if ok:
                had_image = _apply(config, database, client, entity, found, policy)
                applied += 1
            atomic_write_text(path, json.dumps(dict(token=token, ok=ok, had_image=had_image, searched_at=time.time())))
        except InterruptedError:
            raise
        except stashdb_client.RateLimited as exc:
            issue(selected[entity['asset_id']], str(exc), paused=True, retryable=True)
            break
        except (ValueError, OSError) as exc:
            atomic_write_text(path, json.dumps(dict(token=token, failed=True, searched_at=time.time())))
            issue(selected[entity['asset_id']], str(exc), retryable=True)
    return {'applied': applied, 'review': 0, 'skipped': skipped}
