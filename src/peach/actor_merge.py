"""演员名字相似候选、冻结证据及人工合并；不自动确认身份。"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from collections import defaultdict
from difflib import SequenceMatcher

from .entities import merge_entity, normalize_entity_name, rewrite_flat_projection, _transfer_favorites


def words(name):
    text = unicodedata.normalize('NFKD', name).casefold()
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return tuple(re.findall(r'[^\W_]+', text)[:32])


def actors(connection):
    rows = {row['id']: {**dict(row), 'aliases': [], 'refs': [], 'count': 0} for row in connection.execute("SELECT * FROM entity WHERE kind='performer'")}
    for row in connection.execute("SELECT entity_id,count(DISTINCT asset_id) FROM asset_entity ae JOIN asset a ON a.id=ae.asset_id WHERE a.disposal IS NULL GROUP BY entity_id"):
        if row[0] in rows:
            rows[row[0]]['count'] = row[1]
    for row in connection.execute('SELECT entity_id,alias FROM entity_alias ORDER BY alias'):
        if row[0] in rows:
            rows[row[0]]['aliases'].append(row[1])
    for row in connection.execute('SELECT entity_id,provider,external_kind,external_id FROM entity_external_ref ORDER BY provider,external_kind,external_id'):
        if row[0] in rows:
            rows[row[0]]['refs'].append(list(row[1:]))
    return rows


def _order(actor):
    return len(words(actor['canonical_name'])), -actor['count'], actor['id']


def _pairs(rows):
    names, buckets, prefixes, pairs = defaultdict(set), defaultdict(list), defaultdict(list), {}
    for actor in rows.values():
        for name in [actor['canonical_name'], *actor['aliases'][:30]]:
            tokens = words(name)
            if tokens:
                names[tokens].add(actor['id'])
        tokens = words(actor['canonical_name'])
        if len(tokens) >= 2:
            buckets[tokens[0]].append(actor['id'])
            prefixes[tokens[:2]].append(actor['id'])
    def add(left, right, reason):
        if left != right:
            anchor, other = sorted((left, right), key=lambda value: _order(rows[value]))
            pairs.setdefault((anchor, other), reason)
    for tokens, identifiers in names.items():
        ordered = sorted(identifiers, key=lambda value: _order(rows[value]))
        for other in ordered[1:]:
            add(ordered[0], other, 'Matching actor alias')
        for length in range(2, len(tokens)):
            for left in names.get(tokens[:length], ()):
                for right in identifiers:
                    add(left, right, 'Name contains another actor name')
    for identifiers in prefixes.values():
        ordered = sorted(identifiers, key=lambda value: _order(rows[value]))
        for other in ordered[1:]:
            add(ordered[0], other, 'Names share the same first and last name')
    for left, right in _fuzzy_pairs(rows, buckets):
        add(left, right, 'Similar actor name')
    return pairs


def _fuzzy_pairs(rows, buckets):
    pairs = []
    for identifiers in buckets.values():
        ordered = sorted(identifiers, key=lambda value: words(rows[value]['canonical_name']))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:index + 25]:
                first, second = words(rows[left]['canonical_name']), words(rows[right]['canonical_name'])
                if len(first) == len(second) and SequenceMatcher(None, ' '.join(first), ' '.join(second), autojunk=False).ratio() >= .9:
                    pairs.append((left, right))
    return pairs


def suggestions(rows):
    groups = defaultdict(list)
    for (anchor, other), reason in _pairs(rows).items():
        groups[anchor].append({'id': other, 'reason': reason})
    children = {item['id'] for matches in groups.values() for item in matches}
    return [{'id': key, 'matches': matches} for key, matches in groups.items() if key not in children]


def conflicts(actors_to_merge):
    sources = defaultdict(set)
    for actor in actors_to_merge:
        for provider, kind, identity in actor['refs']:
            sources[provider, kind].add(identity)
    return [f'{provider}:{kind}' for (provider, kind), identities in sources.items() if len(identities) > 1]


def automatic_groups(rows):
    """批量授权仅覆盖明确的别名和完整姓名称包含，排除模糊拼写与整组来源歧义。"""
    result, used = [], set()
    for group in sorted(suggestions(rows), key=lambda row: _order(rows[row['id']])):
        anchor = rows[group['id']]
        candidates = [rows[match['id']] for match in group['matches']
                      if match['reason'] != 'Similar actor name' and not conflicts([anchor, rows[match['id']]])]
        safe = [row for row in candidates if not any(conflicts([row, other]) for other in candidates if other['id'] != row['id'])]
        identifiers = [anchor['id'], *(row['id'] for row in safe if row['id'] not in used)]
        if anchor['id'] not in used and len(identifiers) > 1:
            result.append(identifiers)
            used.update(identifiers)
    return result


def token(connection, identifier):
    queries = [('entity', 'id'), ('entity_alias', 'entity_id'), ('entity_external_ref', 'entity_id'), ('asset_entity', 'entity_id'), ('performer_profile', 'entity_id')]
    values = [sorted((list(row) for row in connection.execute(f'SELECT * FROM {table} WHERE {column}=?', (identifier,))), key=repr) for table, column in queries]
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def merge(connection, chosen, preferred):
    """保留作品最多的实体标识，采用用户选定的规范名并补齐资料。"""
    kept = max(chosen, key=lambda row: (row['count'], -row['id']))
    target_id, old_name = kept['id'], kept['canonical_name']
    _rewrite_names(connection, chosen, preferred['canonical_name'])
    metadata = json.loads(kept['metadata_json'] or '{}')
    preferred_metadata = json.loads(preferred['metadata_json'] or '{}')
    for key in ('actor_profile_edits', 'stashdb_profile'):
        metadata[key] = {**metadata.get(key, {}), **preferred_metadata.get(key, {})}
    moved = []
    for actor in chosen:
        incoming = json.loads(actor['metadata_json'] or '{}')
        for key, value in incoming.items():
            if key in ('actor_profile_edits', 'stashdb_profile'):
                metadata[key] = {**value, **metadata.get(key, {})}
            elif key not in metadata:
                metadata[key] = value
        if actor['id'] != target_id:
            result = merge_entity(connection, target_id=target_id, source_id=actor['id'], source_name=actor['canonical_name'], alias_source='user:actor-merge')
            if result['dropped_refs']:
                raise ValueError('来源身份冲突，请刷新后重新选择')
            moved.append(actor['id'])
    name = preferred['canonical_name']
    connection.execute('INSERT OR IGNORE INTO entity_alias(entity_id,alias,normalized_alias,source,confidence) VALUES(?,?,?,?,1)', (target_id, old_name, normalize_entity_name(old_name), 'user:actor-merge'))
    connection.execute('UPDATE entity SET canonical_name=?,normalized_name=?,metadata_json=? WHERE id=?', (name, normalize_entity_name(name), json.dumps(metadata, ensure_ascii=False), target_id))
    _transfer_favorites(connection, target_id, target_id, datetime.now(timezone.utc).isoformat())
    connection.execute('UPDATE asset SET mutation_revision=mutation_revision+1 WHERE id IN (SELECT asset_id FROM asset_entity WHERE entity_id=?)', (target_id,))
    return {'id': target_id, 'name': name, 'merged_ids': moved}


def _rewrite_names(connection, chosen, name):
    for actor in chosen:
        if actor['canonical_name'] != name:
            rewrite_flat_projection(connection, 'performer', actor['id'], actor['canonical_name'], name)
