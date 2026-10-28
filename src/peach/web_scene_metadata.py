"""单条作品的手工资料、图片及定向来源重匹配。"""
import base64
import binascii
import io
from datetime import date

from PIL import Image

from . import entities, settings_file, stashdb_client, stashdb_entities
from .cover_artwork import install_cover
from .field_owners import USER_MANUAL, check_revision, write_owned_fields
from .web_catalog import q_item

FIELDS = ('catalog_title', 'original_title', 'code', 'release_date', 'studio', 'series')


def _id(value):
    if type(value) is not int or value < 1:
        raise ValueError('请选择有效项目')
    return value


def q_scene_metadata(contract, args):
    asset_id = _id(int(args.get('id') or 0))
    with contract.read_connection() as connection:
        row = connection.execute('SELECT id,medium,mutation_revision,' + ','.join(FIELDS) + ' FROM asset WHERE id=? AND disposal IS NULL', (asset_id,)).fetchone()
        if not row or row['medium'] != 'video':
            raise ValueError('请选择馆藏中的视频')
        result = dict(row)
        result['performers'] = [row[0] for row in connection.execute("SELECT DISTINCT e.canonical_name FROM asset_entity ae JOIN entity e ON e.id=ae.entity_id WHERE ae.asset_id=? AND e.kind='performer' ORDER BY e.canonical_name", (asset_id,))]
        if not result['performers']:
            result['performers'] = [row[0][3:] for row in connection.execute("SELECT DISTINCT tag FROM asset_tag WHERE asset_id=? AND tag LIKE '演员:%'", (asset_id,))]
    return result


def _values(body):
    values = body.get('values')
    if not isinstance(values, dict) or set(values) - set(FIELDS):
        raise ValueError('作品资料字段无效')
    if any(not isinstance(value, str) or len(value) > 1000 for value in values.values()):
        raise ValueError('资料字段最多 1000 个字符')
    values = {key: value.strip() for key, value in values.items()}
    if values.get('release_date'):
        date.fromisoformat(values['release_date'])
    names = body.get('performers')
    if names is not None and (not isinstance(names, list) or len(names) > 100 or any(not isinstance(name, str) or not name.strip() or len(name) > 200 for name in names)):
        raise ValueError('演员名单无效')
    return values, names


def _picture(raw):
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > 8_000_000:
        raise ValueError('图片最多 6 MB')
    try:
        payload = base64.b64decode(raw, validate=True)
        with Image.open(io.BytesIO(payload)) as image:
            if image.width * image.height > 24_000_000 or min(image.size) < 32 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('请选择单张图片，尺寸最多 2400 万像素')
            output = io.BytesIO()
            image.convert('RGB').save(output, 'JPEG', quality=92)
            return output.getvalue(), image.size
    except (OSError, binascii.Error, Image.DecompressionBombError) as error:
        raise ValueError('图片无法读取') from error


def _relations(connection, asset_id, values, names):
    for kind in ('studio', 'series'):
        if kind in values:
            connection.execute('DELETE FROM asset_entity WHERE asset_id=? AND role=?', (asset_id, kind))
            if values[kind]:
                entities.upsert_asset_entity(connection, kind=kind, name=values[kind], asset_id=asset_id, role=kind, source=USER_MANUAL, update_entity_metadata=False)
    if names is None:
        return
    connection.execute("DELETE FROM asset_entity WHERE asset_id=? AND role='performer'", (asset_id,))
    connection.execute("DELETE FROM asset_tag WHERE asset_id=? AND tag LIKE '演员:%'", (asset_id,))
    for name in dict.fromkeys(name.strip() for name in names):
        entity_id = entities.upsert_asset_entity(connection, kind='performer', name=name, asset_id=asset_id, role='performer', source=USER_MANUAL, update_entity_metadata=False)
        if entity_id is None:
            raise ValueError('演员名称无效')
        canonical = connection.execute('SELECT canonical_name FROM entity WHERE id=?', (entity_id,)).fetchone()[0]
        connection.execute('INSERT OR IGNORE INTO asset_tag(asset_id,tag,confidence,source) VALUES(?,?,1,?)', (asset_id, '演员:' + canonical, USER_MANUAL))
    connection.execute("UPDATE asset SET field_owners=json_set(coalesce(field_owners,'{}'),'$.performers',?),mutation_revision=mutation_revision+1 WHERE id=?", (USER_MANUAL, asset_id))


def w_scene_metadata(contract, body):
    asset_id = _id(body.get('id'))
    revision = body.get('expected_revision')
    if type(revision) is not int or revision < 0:
        raise ValueError('请刷新作品后重试')
    values, names = _values(body)
    cover, thumbnail = _picture(body.get('cover')), _picture(body.get('thumbnail'))
    with contract.write_transaction() as connection:
        row = connection.execute("SELECT medium FROM asset WHERE id=? AND disposal IS NULL", (asset_id,)).fetchone()
        if not row or row[0] != 'video':
            raise ValueError('请选择馆藏中的视频')
        check_revision(connection, [asset_id], revision)
        if values:
            write_owned_fields(connection, [asset_id], values, USER_MANUAL, expected_revision=revision)
        _relations(connection, asset_id, values, names)
        if cover:
            key = f'MANUAL-ASSET-{asset_id}'
            install_cover(contract.cover_root / (key + '.jpg'), key, cover[0], cover[1], evidence={'source': USER_MANUAL, 'user_selected': True})
        if thumbnail:
            key = f'MANUAL-THUMB-{asset_id}'
            install_cover(contract.cover_root / (key + '.jpg'), key, thumbnail[0], thumbnail[1], evidence={'source': USER_MANUAL, 'user_selected': True})
        if cover or thumbnail:
            connection.execute('UPDATE asset SET mutation_revision=mutation_revision+1 WHERE id=?', (asset_id,))
    contract.cache_bust()
    return {'ok': True, 'item': q_item(contract, asset_id)}


def w_rematch_metadata(contract, body):
    kind, identifier = body.get('kind'), _id(body.get('id'))
    if kind == 'scene':
        from .web_library_processing import w_library_processing
        return w_library_processing(contract, {'stage': 'rematch', 'asset_ids': [identifier]})
    if kind not in ('performer', 'studio'):
        raise ValueError('请选择作品、演员或厂牌')
    config = settings_file.active()
    policy = stashdb_client.settings(config)
    if not policy['api_key_set']:
        raise ValueError('请先在来源与订阅中配置 StashDB')
    with contract.read_connection() as connection:
        row = connection.execute('SELECT canonical_name FROM entity WHERE id=? AND kind=?', (identifier, kind)).fetchone()
        if not row:
            raise ValueError('项目不存在')
        entity = dict(id=identifier, kind=kind, name=row[0], aliases=[row[0] for row in connection.execute('SELECT alias FROM entity_alias WHERE entity_id=?', (identifier,))], remote=[row[0] for row in connection.execute("SELECT external_id FROM entity_external_ref WHERE entity_id=? AND provider='stashdb' AND external_kind=?", (identifier, kind))])
    client = stashdb_client.Client(config)
    try:
        found = stashdb_entities._match(client, entity)
        if not found:
            raise ValueError('未找到唯一匹配，请检查名称和别名')
        stashdb_entities._apply(config, contract.database, client, entity, found, policy)
    finally:
        client.close()
    contract.cache_bust()
    return {'ok': True}
