"""StashDB 候选复核、局部写入与扫描后继；媒体文件保持原名。"""
from __future__ import annotations

import hashlib
import io
import json
import time
import uuid

from PIL import Image

from . import avatar_provider, cover_artwork, stashdb_client, stashdb_matching
from .entities import upsert_asset_entity
from .field_owners import owner_of, write_owned_fields
from .fsutil import atomic_write_text
from .western_artwork import artwork_key
from .stashdb_files import policy_stamp as _policy_stamp, recover_images, stash_photo as _stash_photo, read_record, search_stamp, skip_search

SOURCE = 'auto:stashdb'
REVIEW_SOURCE = 'review:stashdb'


def identity(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError) as exc:
        raise ValueError('Choose a valid StashDB identity.') from exc


def asset_evidence(connection, asset_id, *, revision=True, ignore_terms=''):
    row = connection.execute("SELECT id,name,medium,code,catalog_title,original_title,studio,release_date,duration,mutation_revision,field_owners "
                             "FROM asset WHERE id=? AND COALESCE(disposal,'') NOT IN ('trash','vanished')", (asset_id,)).fetchone()
    if not row or row['medium'] != 'video':
        raise ValueError('Choose a video from your library.')
    actors = [item[0] for item in connection.execute(
        "SELECT DISTINCT e.canonical_name FROM entity e JOIN asset_entity ae ON ae.entity_id=e.id "
        "WHERE ae.asset_id=? AND e.kind='performer' ORDER BY e.id", (asset_id,))]
    values = dict(row)
    signature = values if revision else {key: value for key, value in values.items() if key != 'mutation_revision'}
    token = hashlib.sha256(json.dumps([signature, actors], sort_keys=True).encode()).hexdigest()
    return values, stashdb_matching.hints(values, actors, ignore_terms=ignore_terms), token


def library(database, query='', kind='scene'):
    if kind not in ('scene', 'actor'):
        raise ValueError('Choose scenes or actors.')
    value = '%' + str(query or '')[:120].replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    with database.read_connection() as connection:
        if kind == 'actor':
            rows = connection.execute("SELECT id,canonical_name AS label FROM entity WHERE kind='performer' "
                                      "AND canonical_name LIKE ? ESCAPE '!' ORDER BY canonical_name LIMIT 20", (value,))
        else:
            rows = connection.execute("SELECT id,COALESCE(NULLIF(catalog_title,''),name) AS label FROM asset WHERE medium='video' "
                "AND COALESCE(disposal,'') NOT IN ('trash','vanished') AND (name LIKE ? ESCAPE '!' OR catalog_title LIKE ? ESCAPE '!') "
                "ORDER BY id DESC LIMIT 20", (value, value))
        return [dict(row) for row in rows]


def preview(config, database, body, *, client=None):
    owned = client is None
    client = client or stashdb_client.Client(config)
    try:
        if body.get('performer_id'):
            with database.read_connection() as connection:
                row = connection.execute("SELECT canonical_name FROM entity WHERE id=? AND kind='performer'", (body['performer_id'],)).fetchone()
                if not row:
                    raise ValueError('Choose an actor from your library.')
                aliases = [item[0] for item in connection.execute('SELECT alias FROM entity_alias WHERE entity_id=?', (body['performer_id'],))]
                bound = connection.execute("SELECT external_id FROM entity_external_ref WHERE entity_id=? AND provider='stashdb' "
                    "AND external_kind='performer'", (body['performer_id'],)).fetchone()
            if bound and _stash_photo(config.directory('generated') / 'avatars' / f"performer-{body['performer_id']}.img", bound[0]):
                return {'candidates': [{'id': bound[0], 'title': row[0], 'score': 1, 'reasons': ['Already up to date.'],
                    'url': f'https://stashdb.org/performers/{bound[0]}'}], 'review_required': True}
            known = {stashdb_matching.key(name) for name in [row[0], *aliases]}
            candidates = client.performers(row[0])
            result = []
            for item in candidates:
                if item.get('deleted'):
                    continue
                exact = bool(known & {stashdb_matching.key(name) for name in [item['name'], *(item.get('aliases') or [])]})
                result.append({'id': item['id'], 'title': item['name'], 'disambiguation': item.get('disambiguation') or '',
                    'score': 1 if exact else 0, 'reasons': ['Name or alias matches'] if exact else ['Review identity'],
                    'url': f"https://stashdb.org/performers/{item['id']}"})
            return {'candidates': sorted(result, key=lambda item: -item['score']), 'review_required': True}
        policy = stashdb_client.settings(config)
        with database.read_connection() as connection:
            _row, evidence, token = asset_evidence(connection, body.get('asset_id'), ignore_terms=policy['ignore_terms'])
            known_actors = _known_actors(connection, body.get('asset_id'))
        result = stashdb_matching.search_scenes(client, evidence, known_actors=known_actors,
            minimum_confidence=policy['minimum_confidence'])
        result['token'] = token
        return result
    finally:
        if owned:
            client.close()


def _known_actors(connection, asset_id):
    names = {}
    for row in connection.execute("SELECT x.external_id,e.canonical_name FROM entity_external_ref x "
        "JOIN entity e ON e.id=x.entity_id JOIN asset_entity ae ON ae.entity_id=e.id "
        "WHERE x.provider='stashdb' AND x.external_kind='performer' AND ae.asset_id=? UNION "
        "SELECT x.external_id,al.alias FROM entity_external_ref x JOIN entity_alias al ON al.entity_id=x.entity_id "
        "JOIN asset_entity ae ON ae.entity_id=x.entity_id WHERE x.provider='stashdb' AND x.external_kind='performer' AND ae.asset_id=?",
        (asset_id, asset_id)):
        names.setdefault(stashdb_matching.key(row[1]), set()).add(row[0])
    return {name: next(iter(ids)) for name, ids in names.items() if len(ids) == 1}


def review_queue(config, database, *, state_root=None, limit=200):
    root = (state_root if state_root is not None else config.directory('state')) / 'stashdb-review'
    paths = sorted(root.glob('*.json'), key=lambda path: int(path.stem) if path.stem.isdigit() else 0, reverse=True)
    result = []
    with database.read_connection() as connection:
        for path in paths[:limit]:
            if not path.stem.isdigit():
                continue
            row = connection.execute("SELECT name,catalog_title FROM asset WHERE id=? AND COALESCE(disposal,'') NOT IN ('trash','vanished')", (int(path.stem),)).fetchone()
            if not row:
                continue
            try:
                cached = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(cached, dict) and cached.get('candidates'):
                result.append({'id': int(path.stem), 'label': row[1] or row[0], 'preview': cached})
    return result


def _image(client, images, *, portrait=False):
    ordered = sorted(images or [], key=lambda item: (
        portrait and item.get('width', 0) > item.get('height', 0), -item.get('width', 0) * item.get('height', 0)))
    failed = False
    for item in ordered[:3]:
        try:
            body = client.image(item['url'])
        except (InterruptedError, stashdb_client.RateLimited):
            raise
        except (OSError, ValueError):
            failed = True
            continue
        inspected = avatar_provider.inspect_avatar(body)
        if inspected is None or (portrait and not avatar_provider.acceptable_avatar(inspected, 500, 300)):
            continue
        with Image.open(io.BytesIO(body)) as image:
            if getattr(image, 'n_frames', 1) != 1 or image.width * image.height > 24_000_000:
                continue
            if not portrait and (image.width < 320 or image.height < 180):
                continue
            output = io.BytesIO()
            image.convert('RGB').save(output, format='JPEG', quality=92)
            return output.getvalue(), image.size, item['url']
    if failed:
        raise ValueError('StashDB images could not be downloaded. Existing pictures were preserved. Try the scan again.')
    return None


def _performer_entity(connection, performer, asset_id, source=SOURCE):
    if performer.get('deleted') or 'ambiguous' in str(performer.get('disambiguation') or '').casefold():
        return None
    remote_id = identity(performer['id'])
    name = performer['name']
    disambiguation = performer.get('disambiguation') or ''
    if disambiguation:
        name += f' ({disambiguation})'
    conflict = connection.execute("SELECT 1 FROM entity e JOIN entity_external_ref x ON e.id=x.entity_id "
        "WHERE e.kind='performer' AND e.canonical_name=? AND x.provider='stashdb' AND x.external_id<>?", (name, remote_id)).fetchone()
    if conflict:
        name += f' (StashDB {remote_id[:8]})'
    return upsert_asset_entity(connection, kind='performer', name=name, asset_id=asset_id, role='performer',
        source=source, external_provider='stashdb', external_id=remote_id,
        metadata={'stashdb_id': remote_id, 'disambiguation': disambiguation}, update_entity_metadata=False)


def _existing_actor(connection, performer, asset_id):
    names = {stashdb_matching.key(name) for name in [performer['name'], *(performer.get('aliases') or [])]}
    candidates = {row[0] for row in connection.execute(
        "SELECT e.id,e.canonical_name FROM entity e JOIN asset_entity ae ON e.id=ae.entity_id "
        "WHERE ae.asset_id=? AND e.kind='performer' UNION SELECT e.id,al.alias FROM entity e "
        "JOIN entity_alias al ON al.entity_id=e.id JOIN asset_entity ae ON ae.entity_id=e.id "
        "WHERE ae.asset_id=? AND e.kind='performer'", (asset_id, asset_id)) if stashdb_matching.key(row[1]) in names}
    if len(candidates) != 1:
        return None
    entity_id = next(iter(candidates))
    bound = connection.execute("SELECT entity_id,external_id FROM entity_external_ref WHERE provider='stashdb' "
        "AND external_kind='performer' AND (entity_id=? OR external_id=?)", (entity_id, performer['id'])).fetchall()
    if any(row[0] != entity_id or row[1] != performer['id'] for row in bound):
        return None
    connection.execute("INSERT OR IGNORE INTO entity_external_ref(entity_id,provider,external_kind,external_id,metadata_json) "
        "VALUES(?,'stashdb','performer',?,'{}')", (entity_id, performer['id']))
    return entity_id


def _photo(config, client, performer, entity_id, *, manual=False):
    root = config.directory('generated') / 'avatars'
    target = root / f'performer-{entity_id}.img'
    if target.exists() and (not manual or _stash_photo(target, performer['id'])):
        return 0
    prepared = _image(client, performer.get('images'), portrait=True)
    if not prepared:
        return 0
    body, _size, url = prepared
    avatar_provider.install_entity_avatar(root, 'performer', entity_id, body, 'image/jpeg',
        {'provider': 'stashdb', 'source': SOURCE, 'source_kind': 'external_media_library',
         'upstream_url': url, 'profile_url': f"https://stashdb.org/performers/{performer['id']}",
         'external_id': performer['id'], 'identity_verified': True, 'user_selected': manual}, probe_face=False)
    return 1


def _scene_cast(scene):
    performers = [item['performer'] for item in scene.get('performers') or [] if item.get('performer')]
    safe = [item for item in performers if not item.get('deleted') and 'ambiguous' not in str(item.get('disambiguation') or '').casefold()]
    return performers, safe


def _write_cast(connection, asset_id, scene, enabled, source, manual):
    performers, safe = _scene_cast(scene)
    if not enabled or not safe or len(safe) != len(performers):
        return False
    for performer in safe:
        _existing_actor(connection, performer, asset_id)
    replace = [SOURCE, 'scan:filename-actors', REVIEW_SOURCE] if manual else [SOURCE, 'scan:filename-actors']
    marks = ','.join('?' for _ in replace)
    connection.execute(f"DELETE FROM asset_entity WHERE asset_id=? AND role='performer' AND source IN ({marks})", [asset_id, *replace])
    connection.execute(f"DELETE FROM asset_tag WHERE asset_id=? AND source IN ({marks})", [asset_id, *replace])
    for performer in safe:
        entity_id = _performer_entity(connection, performer, asset_id, source)
        if entity_id is not None:
            name = connection.execute('SELECT canonical_name FROM entity WHERE id=?', (entity_id,)).fetchone()[0]
            connection.execute('INSERT OR IGNORE INTO asset_tag(asset_id,tag,confidence,source) VALUES(?,?,1,?)',
                (asset_id, '演员:' + name, source))
    return True


def _write_studio(connection, asset_id, studio, source):
    current = connection.execute('SELECT studio FROM asset WHERE id=?', (asset_id,)).fetchone()[0]
    connection.execute("DELETE FROM asset_entity WHERE asset_id=? AND role='studio' AND source IN (?,?)", (asset_id, SOURCE, source))
    if studio.get('id') and studio.get('name') and stashdb_matching.key(current) == stashdb_matching.key(studio['name']):
        upsert_asset_entity(connection, kind='studio', name=studio['name'], asset_id=asset_id, role='studio',
            source=source, external_provider='stashdb', external_id=identity(studio['id']), update_entity_metadata=False)


def _write_scene(connection, asset_id, scene, row, policy, source, manual):
    fields = {key: value for key, value in {'catalog_title': scene.get('title'),
        'release_date': scene.get('release_date'), 'studio': (scene.get('studio') or {}).get('name')}.items() if value}
    if manual:
        fields = {key: value for key, value in fields.items()
            if not owner_of(row['field_owners'], key).startswith(('user:', 'review:')) or owner_of(row['field_owners'], key) == REVIEW_SOURCE}
    if fields:
        write_owned_fields(connection, [asset_id], fields, source)
    cast_updated = _write_cast(connection, asset_id, scene, policy['correct_cast'], source, manual)
    _write_studio(connection, asset_id, scene.get('studio') or {}, source)
    return cast_updated


def _photo_links(connection, asset_id, performers):
    links = []
    for performer in performers:
        bound = connection.execute("SELECT entity_id FROM entity_external_ref WHERE provider='stashdb' "
            "AND external_kind='performer' AND external_id=?", (performer['id'],)).fetchall()
        entity_id = bound[0][0] if len(bound) == 1 else _existing_actor(connection, performer, asset_id)
        if entity_id is not None:
            from .actor_details import sync
            sync(connection, entity_id, performer)
            links.append((performer, entity_id))
    return links


def apply_scene(config, database, asset_id, scene_id, token, *, client=None, manual=True):
    owned = client is None
    client = client or stashdb_client.Client(config)
    try:
        policy = stashdb_client.settings(config)
        source = REVIEW_SOURCE if manual else SOURCE
        scene = client.scene(identity(scene_id))
        if not scene or scene.get('deleted'):
            raise ValueError('This StashDB scene is no longer available.')
        if scene.get('id') != scene_id:
            raise ValueError('The StashDB scene identity does not match the selection.')
        with database.read_connection() as connection:
            row, evidence, current = asset_evidence(connection, asset_id, ignore_terms=policy['ignore_terms'])
        if not token or token != current:
            raise ValueError('The local scene changed. Preview the match again.')
        ranked = stashdb_matching.rank_scene(scene, evidence)
        if not manual and (not ranked or not ranked['strong'] or ranked['score'] < policy['minimum_confidence'] / 100):
            raise ValueError('This scene needs review before applying metadata.')
        recover_images(config)
        target = config.directory('generated') / 'covers' / (artwork_key(asset_id, row['code']) + '.jpg')
        picture = _image(client, scene.get('images')) if policy['scene_images'] and (manual or not target.exists()) else None
        with database.write_transaction() as connection:
            if asset_evidence(connection, asset_id)[2] != token:
                raise ValueError('The local scene changed. Preview the match again.')
            cast_updated = _write_scene(connection, asset_id, scene, row, policy, source, manual)
            performers, safe = _scene_cast(scene)
            actor_links = _photo_links(connection, asset_id, safe)
            if picture:
                body, size, url = picture
                cover_artwork.install_cover(target, row['code'] or '', body, size, evidence={
                    'provider': 'stashdb', 'source': source, 'source_url': url, 'scene_id': scene_id,
                    'scene_url': ranked['url'], 'performers': [item['name'] for item in performers], 'cast_size': len(performers), 'match': ranked})
        photos = sum(_photo(config, client, performer, entity_id, manual=manual) for performer, entity_id in actor_links) if policy['actor_images'] else 0
        with database.read_connection() as connection:
            completed_token = asset_evidence(connection, asset_id, revision=False)[2]
        record = {'scene_id': scene_id, 'filename': row['name'], 'match': ranked, 'reviewed': manual,
                  'token': completed_token, 'policy': _policy_stamp(policy),
                  'files': [str(path.relative_to(config.directory('generated'))) for path in
                    [target, *(config.directory('generated') / 'avatars' / f'performer-{entity_id}.img' for _, entity_id in actor_links)]
                    if path.is_file()]}
        atomic_write_text(config.directory('state') / 'stashdb-matches' / f'{asset_id}.json', json.dumps(record, ensure_ascii=False))
        (config.directory('state') / 'stashdb-review' / f'{asset_id}.json').unlink(missing_ok=True)
        return {'ok': True, 'scene_id': scene_id, 'actor_photos': photos, 'scene_picture': bool(picture), 'cast_updated': cast_updated}
    finally:
        if owned:
            client.close()


def apply_performer(config, database, performer_id, remote_id, *, client=None):
    remote_id = identity(remote_id)
    recover_images(config)
    target = config.directory('generated') / 'avatars' / f'performer-{performer_id}.img'
    if _stash_photo(target, remote_id):
        with database.read_connection() as connection:
            bound = connection.execute("SELECT 1 FROM entity_external_ref WHERE entity_id=? AND provider='stashdb' "
                "AND external_kind='performer' AND external_id=?", (performer_id, remote_id)).fetchone()
        if bound:
            return {'ok': True, 'actor_photos': 0, 'skipped': 1}
    owned = client is None
    client = client or stashdb_client.Client(config)
    try:
        performer = client.performer(identity(remote_id))
        if not performer or performer.get('deleted') or 'ambiguous' in str(performer.get('disambiguation') or '').casefold():
            raise ValueError('Choose a disambiguated StashDB performer.')
        if performer.get('id') != remote_id:
            raise ValueError('The StashDB performer identity does not match the selection.')
        with database.write_transaction() as connection:
            row = connection.execute("SELECT id FROM entity WHERE id=? AND kind='performer'", (performer_id,)).fetchone()
            if not row:
                raise ValueError('Choose an actor from your library.')
            existing = connection.execute("SELECT entity_id,external_id FROM entity_external_ref WHERE provider='stashdb' AND external_kind='performer' "
                "AND (entity_id=? OR external_id=?)", (performer_id, remote_id)).fetchall()
            if any(item[0] != performer_id or item[1] != remote_id for item in existing):
                raise ValueError('This performer has a different StashDB identity. Review the identity links first.')
            connection.execute("INSERT OR IGNORE INTO entity_external_ref(entity_id,provider,external_kind,external_id,metadata_json) "
                "VALUES(?,'stashdb','performer',?,'{}')", (performer_id, remote_id))
        photos = _photo(config, client, performer, performer_id, manual=True) if stashdb_client.settings(config)['actor_images'] else 0
        with database.write_transaction() as connection:
            from .actor_details import sync
            sync(connection, performer_id, performer)
        return {'ok': True, 'actor_photos': photos}
    finally:
        if owned:
            client.close()


def scan_assets(config, database, rows, *, progress, issue, active=lambda: True):
    policy = stashdb_client.settings(config)
    if not policy['enabled'] or not policy['api_key_set']:
        return {'applied': 0, 'review': 0}
    recover_images(config)
    applied = review = skipped = 0
    client = stashdb_client.Client(config)
    try:
        if not policy['scene_images']:
            from .stashdb_entities import scan
            return scan(config, database, rows, client=client, progress=progress, issue=issue, active=active)
        for position, row in enumerate(rows):
            if not active():
                break
            token = None
            try:
                with database.read_connection() as connection:
                    token = asset_evidence(connection, row['id'], revision=False)[2]
                    current = asset_evidence(connection, row['id'])[2]
                path = config.directory('state') / 'stashdb-review' / f"{row['id']}.json"
                cached = read_record(path)
                reason, reusable = skip_search(config, row['id'], token, policy, cached, first_seen=row.get('first_seen'))
                if reason:
                    skipped += 1
                    if reusable:
                        cached['token'] = current
                        atomic_write_text(path, json.dumps(cached, ensure_ascii=False))
                        review += bool(cached.get('candidates'))
                    progress(stage=reason, checked=position + 1, total=len(rows), current_asset_id=row['id'])
                    continue
                progress(stage='StashDB matching', checked=position, total=len(rows), current_asset_id=row['id'])
                result = preview(config, database, {'asset_id': row['id']}, client=client)
                (config.directory('state') / 'stashdb-failures' / f"{row['id']}.json").unlink(missing_ok=True)
                result.update(search_policy=search_stamp(policy), searched_at=time.time())
                if not (policy['auto_apply'] and result['automatic_match']):
                    result['evidence_token'] = token
                atomic_write_text(path, json.dumps(result, ensure_ascii=False))
                if policy['auto_apply'] and result['automatic_match']:
                    apply_scene(config, database, row['id'], result['automatic_match'], result['token'], client=client, manual=False)
                    applied += 1
                elif result['candidates']:
                    review += 1
            except InterruptedError:
                raise
            except stashdb_client.RateLimited as exc:
                issue(row, str(exc), paused=True, retryable=True)
                break
            except (ValueError, OSError) as exc:
                if token:
                    atomic_write_text(config.directory('state') / 'stashdb-failures' / f"{row['id']}.json", json.dumps({
                        'token': token, 'search_policy': search_stamp(policy), 'policy': _policy_stamp(policy)}))
                issue(row, str(exc), retryable=True)
    finally:
        client.close()
    return {'applied': applied, 'review': review, 'skipped': skipped}


def dismiss(config, database, asset_id, token):
    with database.read_connection() as connection:
        if not token or asset_evidence(connection, asset_id)[2] != token:
            raise ValueError('The local scene changed. Preview the match again.')
        signature = asset_evidence(connection, asset_id, revision=False)[2]
    atomic_write_text(config.directory('state') / 'stashdb-matches' / f'{asset_id}.json', json.dumps({
        'decision': 'dismissed', 'token': signature, 'policy': _policy_stamp(stashdb_client.settings(config)), 'files': []}))
    (config.directory('state') / 'stashdb-review' / f'{asset_id}.json').unlink(missing_ok=True)
    return {'ok': True}
