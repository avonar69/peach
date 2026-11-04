"""批量手工厂牌与演员沿用作品编辑的规范关系及字段归属。"""
from .field_owners import USER_MANUAL, write_owned_fields
from .web_scene_metadata import _relations


def apply(connection, ids, operation, body, region):
    if operation == 'region':
        write_owned_fields(connection, ids, {'region': region}, USER_MANUAL)
        return
    value = body.get('name')
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('Enter a valid name.')
    value = value.strip()
    for asset_id in ids:
        row = connection.execute('SELECT medium,disposal FROM asset WHERE id=?', (asset_id,)).fetchone()
        if row['medium'] != 'video' or row['disposal']:
            raise ValueError('请选择馆藏中的视频')
        if operation == 'studio':
            write_owned_fields(connection, [asset_id], {'studio': value}, USER_MANUAL)
            _relations(connection, asset_id, {'studio': value}, None)
        else:
            names = [row[0] for row in connection.execute("SELECT DISTINCT e.canonical_name FROM entity e JOIN asset_entity ae ON ae.entity_id=e.id WHERE ae.asset_id=? AND e.kind='performer'", (asset_id,))]
            _relations(connection, asset_id, {}, [*names, value])
