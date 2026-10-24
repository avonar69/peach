"""按文件名的明确演员字段与唯一规范名关联演员，保留独立来源。"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import PureWindowsPath

import ahocorasick

from .entities import canonicalize_entity_name, studio_identity_ids, upsert_asset_entity
from .field_owners import owner_of, write_owned_fields

SOURCE = 'scan:filename-actors'
STUDIO_SOURCE = 'scan:filename-studio'
_FIELD = re.compile(r'\[(?:actors?|performers?)\s*=\s*([^\[\]]{1,1000})\]', re.I)
_DATED_RELEASE = re.compile(r'^.+?[._ ](\d{4}|\d{2})[._ ](\d{2})[._ ](\d{2})[._ ](.+)$')
_QUALITY = re.compile(r'[._ ](?:\d{3,4}p|\d{1,2}k|web(?:[._ -]?dl)?|bluray|hdtv|hevc|avc|[xh][._ ]?26[45]|aac|xxx|repack)(?:[._ -]|$)', re.I)


def release_actors(stem):
    """Studio.YY.MM.DD.First.Last.And.First.Last 的演员字段。"""
    match = _DATED_RELEASE.fullmatch(stem)
    if not match:
        return []
    year, month, day, cast = match.groups()
    try:
        date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    except ValueError:
        return []
    cast = _QUALITY.split(cast, maxsplit=1)[0]
    found = []
    for raw in re.split(r'[._ ]+and[._ ]+|[&,;]', cast, flags=re.I):
        words = re.sub(r'[._]+', ' ', raw).strip().split()
        if not 2 <= len(words) <= 5 or not all(
                all(character.isalpha() or character in "'-’" for character in word) for word in words):
            return []
        name = canonicalize_entity_name('performer', ' '.join(words))
        if name:
            found.append(name)
    return found


def _key(value):
    return re.sub(r'[\W_]+', ' ', unicodedata.normalize('NFKC', value).casefold()).strip()


def actor_index(connection):
    """索引仅保留唯一身份，重叠名字优先完整长名。"""
    names = defaultdict(set)
    canonical = {}
    for entity_id, name in connection.execute("SELECT id,canonical_name FROM entity WHERE kind='performer'"):
        canonical[entity_id] = name
        names[_key(name)].add(entity_id)
    for entity_id, alias in connection.execute(
            "SELECT a.entity_id,a.alias FROM entity_alias a JOIN entity e ON e.id=a.entity_id "
            "WHERE e.kind='performer'"):
        names[_key(alias)].add(entity_id)
    index = ahocorasick.Automaton()
    for name, ids in names.items():
        if len(name) >= 2 and len(ids) == 1:
            index.add_word(name, (len(name), canonical[next(iter(ids))]))
    if len(index):
        index.make_automaton()
    return index


def names_from_filename(filename, index):
    stem = PureWindowsPath(filename).stem
    explicit = release_actors(stem)
    for field in _FIELD.findall(stem):
        for raw in re.split(r'[;,、&]', field):
            name = canonicalize_entity_name('performer', raw.strip())
            if name and len(name) <= 120:
                explicit.append(name)
    text = ' ' + _key(_FIELD.sub(' ', stem)) + ' '
    found = list(explicit)
    matches = []
    if len(index):
        for end, (length, canonical) in index.iter(text):
            start = end + 1 - length
            if (start == 0 or not text[start - 1].isalnum()) and (
                    end + 1 == len(text) or not text[end + 1].isalnum()):
                matches.append((start, end + 1, canonical))
    occupied = []
    for start, end, canonical in sorted(matches, key=lambda row: (row[0] - row[1], row[0])):
        if not any(start < other_end and end > other_start for other_start, other_end in occupied):
            occupied.append((start, end))
            found.append(canonical)
    return list(dict.fromkeys(found))


def studio_from_filename(connection, filename):
    """日期前的厂牌字段按唯一规范名或别名复用，未登记时保留原品牌写法。"""
    stem = PureWindowsPath(filename).stem
    match = _DATED_RELEASE.fullmatch(stem)
    if not match:
        return None
    year, month, day, _cast = match.groups()
    try:
        date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    except ValueError:
        return None
    prefix = stem[:match.start(1)].rstrip('._ ')
    name = canonicalize_entity_name('studio', re.sub(r'[._]+', ' ', prefix).strip())
    if not name or len(name) > 120 or not all(c.isalnum() or c in " &'’-" for c in name):
        return None
    ids = studio_identity_ids(connection, name)
    if len(ids) > 1:
        return None
    if ids:
        return connection.execute('SELECT canonical_name FROM entity WHERE id=?', (next(iter(ids)),)).fetchone()[0]
    return name


def _studio(connection, asset_id, filename):
    row = connection.execute('SELECT studio,field_owners FROM asset WHERE id=?', (asset_id,)).fetchone()
    owned = owner_of(row[1], 'studio') == STUDIO_SOURCE
    name = studio_from_filename(connection, filename)
    conflict = connection.execute(
        "SELECT 1 FROM asset_entity ae JOIN entity e ON e.id=ae.entity_id "
        "WHERE ae.asset_id=? AND e.kind='studio' AND ae.source<>? AND e.canonical_name<>?",
        (asset_id, STUDIO_SOURCE, name or '')).fetchone()
    connection.execute('DELETE FROM asset_entity WHERE asset_id=? AND source=?', (asset_id, STUDIO_SOURCE))
    if owned:
        write_owned_fields(connection, [asset_id], {'studio': ''}, STUDIO_SOURCE)
    if not name or conflict or owner_of(row[1], 'studio').startswith(('user:', 'review:')) or (row[0] and not owned and row[0] != name):
        return 0
    entity_id = upsert_asset_entity(connection, kind='studio', name=name, asset_id=asset_id, role='studio',
        source=STUDIO_SOURCE, metadata={'filename': filename}, update_entity_metadata=False)
    if entity_id is None:
        return 0
    write_owned_fields(connection, [asset_id], {'studio': name}, STUDIO_SOURCE, require_empty=True)
    return 1


def apply(connection, asset_ids, *, actors=True, studios=False):
    """扫描与推送共用；只重建本来源的关系及兼容标签。"""
    if not connection.execute("SELECT 1 FROM sqlite_schema WHERE name='asset_entity'").fetchone():
        return 0
    index = actor_index(connection) if actors else None
    count = 0
    for asset_id in asset_ids:
        row = connection.execute('SELECT name,medium FROM asset WHERE id=?', (asset_id,)).fetchone()
        if row is None or row[1] != 'video':
            continue
        if studios:
            count += _studio(connection, asset_id, row[0])
        if not actors:
            continue
        connection.execute('DELETE FROM asset_entity WHERE asset_id=? AND source=?', (asset_id, SOURCE))
        connection.execute('DELETE FROM asset_tag WHERE asset_id=? AND source=?', (asset_id, SOURCE))
        for name in names_from_filename(row[0], index):
            entity_id = upsert_asset_entity(connection, kind='performer', name=name, asset_id=asset_id,
                role='performer', source=SOURCE, metadata={'filename': row[0]}, update_entity_metadata=False)
            if entity_id is not None:
                canonical = connection.execute('SELECT canonical_name FROM entity WHERE id=?', (entity_id,)).fetchone()[0]
                connection.execute('INSERT OR IGNORE INTO asset_tag(asset_id,tag,confidence,source) VALUES(?,?,1,?)',
                                   (asset_id, '演员:' + canonical, SOURCE))
                count += 1
    return count
