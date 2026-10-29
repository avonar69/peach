"""演员批量合并的持久差异与有条件撤销，不替换整份账本。"""
import base64
import json
from contextlib import contextmanager

from .fsutil import atomic_write_bytes, atomic_write_text


TABLES = ('entity', 'entity_alias', 'entity_external_ref', 'asset_entity', 'entity_link',
          'entity_search_term', 'entity_membership', 'label_maker', 'performer_profile',
          'follow_source', 'feed_source', 'feed_discovery_entity', 'entity_redirect',
          'entity_classification', 'entity_identity_link', 'asset_tag', 'profile', 'asset')
SUFFIXES = ('', '.ct', '.face.json', '.provenance.json')


def capture(connection):
    result = {}
    for table in TABLES:
        info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        if not info:
            continue
        columns = [row[1] for row in info]
        keys = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
        if not keys:
            keys = ['rowid']
            columns.insert(0, 'rowid')
        if table == 'asset':
            columns = ['id', 'mutation_revision']
        projection = ','.join(f'"{column}"' for column in columns)
        rows = [dict(row) for row in connection.execute(f'SELECT {projection} FROM "{table}"')]
        result[table] = {'keys': keys, 'rows': {tuple(row[key] for key in keys): row for row in rows}}
    return result


def delta(before, after):
    changes = []
    for table, original in before.items():
        old, new = original['rows'], after[table]['rows']
        for key in old.keys() | new.keys():
            left, right = old.get(key), new.get(key)
            if left == right:
                continue
            if left is not None and right is not None:
                columns = set(original['keys']) | {column for column in left if left[column] != right[column]}
                left, right = ({column: row[column] for column in columns} for row in (left, right))
            changes.append({'table': table, 'keys': original['keys'], 'before': left, 'after': right})
    return changes


def _where(change, row):
    return ' AND '.join(f'"{key}" IS ?' for key in change['keys']), [row[key] for key in change['keys']]


def validate(connection, changes):
    """验证当前数据仍包含这批合并的终态。"""
    for change in changes:
        table, before, after = change['table'], change['before'], change['after']
        if table not in TABLES:
            raise ValueError('演员撤销记录无效')
        where, values = _where(change, after or before)
        projection = 'rowid AS rowid,*' if change['keys'] == ['rowid'] else '*'
        current = connection.execute(f'SELECT {projection} FROM "{table}" WHERE {where}', values).fetchone()
        if (after is None and current is not None) or (after is not None and (current is None or any(current[key] != value for key, value in after.items()))):
            raise ValueError('合并后的演员资料已修改，无法安全撤销')


def restore(connection, changes):
    """先逐项验证终态；只还原合并改动的列，保留播放历史等无关写入。"""
    validate(connection, changes)
    connection.execute('PRAGMA defer_foreign_keys=ON')
    # 先释放唯一键，再按实体、关系的次序复原。
    for change in reversed(changes):
        if change['before'] is None:
            where, values = _where(change, change['after'])
            connection.execute(f'DELETE FROM "{change["table"]}" WHERE {where}', values)
    ordered = sorted(changes, key=lambda change: (change['table'] != 'entity', change['after'] is None))
    for change in ordered:
        table, before, after = change['table'], change['before'], change['after']
        if before is None:
            continue
        columns = list(before)
        if after is None:
            names = ','.join(f'"{column}"' for column in columns)
            connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in columns)})', [before[column] for column in columns])
        else:
            where, values = _where(change, after)
            assignments = ','.join(f'"{column}"=?' for column in columns if column not in change['keys'])
            connection.execute(f'UPDATE "{table}" SET {assignments} WHERE {where}', [before[column] for column in columns if column not in change['keys']] + values)


def save(path, record):
    atomic_write_text(path, json.dumps(record, ensure_ascii=False, default=lambda value: {'$bytes': base64.b64encode(value).decode()}))


def load(path):
    return json.loads(path.read_text(encoding='utf-8'), object_hook=lambda value: base64.b64decode(value['$bytes']) if set(value) == {'$bytes'} else value)


def pictures(root, identifiers):
    return {f'performer-{identifier}.img{suffix}': base64.b64encode(path.read_bytes()).decode() if path.is_file() else None
            for identifier in identifiers for suffix in SUFFIXES for path in [root / f'performer-{identifier}.img{suffix}']}


def _write_pictures(root, files):
    for name, payload in files.items():
        if payload is None:
            (root / name).unlink(missing_ok=True)
        else:
            atomic_write_bytes(root / name, base64.b64decode(payload))


@contextmanager
def restore_pictures(root, before, after):
    if any((base64.b64encode((root / name).read_bytes()).decode() if (root / name).is_file() else None) != payload for name, payload in after.items()):
        raise ValueError('合并后的演员资料已修改，无法安全撤销')
    try:
        _write_pictures(root, before)
        yield
    except BaseException:
        _write_pictures(root, after)
        raise
