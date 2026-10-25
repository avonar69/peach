"""演员资料的来源快照、手工覆盖和公开读写契约。"""
import json
from datetime import date

from .entities import normalize_entity_name
from .performer_header import age_on
from .performer_profiles import read_profile

FIELDS = ('birth_date', 'career_start_year', 'career_end_year', 'height', 'measurements',
          'breast_type', 'nationality', 'ethnicity', 'eye_color', 'hair_color')


def metadata(connection, entity_id):
    row = connection.execute("SELECT metadata_json FROM entity WHERE id=? AND kind='performer'", (entity_id,)).fetchone()
    if not row:
        raise ValueError('Choose an actor from your library.')
    return json.loads(row[0] or '{}')


def public(connection, entity_id, today=None):
    stored = metadata(connection, entity_id)
    source = stored.get('stashdb_profile') or {}
    edits = stored.get('actor_profile_edits') or {}
    legacy = read_profile(connection, entity_id) or {}
    fallback = {'birth_date': legacy.get('birth_date') or '', 'height': legacy.get('height_cm') or '',
        'career_start_year': legacy.get('debut_year') or '', 'career_end_year': legacy.get('active_until') or ''}
    if any(legacy.get(key) for key in ('bust_cm', 'waist_cm', 'hip_cm')):
        fallback['measurements'] = ' / '.join(str(legacy.get(key) or '—') for key in ('bust_cm', 'waist_cm', 'hip_cm'))
    values = {**fallback, **{key: value for key, value in source.items() if value != ''}, **edits}
    result = {key: values.get(key, '') for key in FIELDS}
    birth = result['birth_date']
    age = age_on(birth, today or date.today()) if birth else None
    if age is not None and age >= 0:
        result['age'] = age
    result['edited_fields'] = list(edits)
    return result


def sync(connection, entity_id, performer):
    stored = metadata(connection, entity_id)
    measurements = {'band_size': performer.get('band_size'), 'cup_size': performer.get('cup_size'),
        'waist': performer.get('waist_size'), 'hip': performer.get('hip_size')}
    band = str(measurements.get('band_size') or '') + str(measurements.get('cup_size') or '')
    size = ' / '.join(str(value or '—') for value in (band, measurements.get('waist'), measurements.get('hip')))
    stored['stashdb_profile'] = {
        **{key: performer.get(key) or '' for key in FIELDS if key not in ('measurements', 'nationality')},
        'measurements': size if any(measurements.values()) else '', 'nationality': performer.get('country') or '',
    }
    connection.execute('UPDATE entity SET metadata_json=? WHERE id=?', (json.dumps(stored), entity_id))
    connection.execute("DELETE FROM entity_alias WHERE entity_id=? AND source='stashdb:alias'", (entity_id,))
    for alias in performer.get('aliases') or []:
        alias = ' '.join(str(alias).split())
        if alias and len(alias) <= 200:
            connection.execute('INSERT OR IGNORE INTO entity_alias(entity_id,alias,normalized_alias,source,confidence) '
                "VALUES(?,?,?,'stashdb:alias',1)", (entity_id, alias, normalize_entity_name(alias)))


def write(contract, body):
    entity_id = body.get('entity_id')
    if type(entity_id) is not int or entity_id < 1:
        raise ValueError('Choose an actor from your library.')
    values = body.get('values')
    if not isinstance(values, dict) or set(values) - set(FIELDS):
        raise ValueError('Enter valid actor details.')
    cleaned = {}
    for key, value in values.items():
        if value is None:
            cleaned[key] = None
            continue
        if not isinstance(value, str) or len(value) > 200:
            raise ValueError('Enter valid actor details.')
        value = value.strip()
        if value and key == 'birth_date':
            try:
                if date.fromisoformat(value) > date.today():
                    raise ValueError()
            except ValueError:
                raise ValueError('Enter a valid birthdate in YYYY-MM-DD format.') from None
        if value and key in ('height', 'career_start_year', 'career_end_year'):
            maximum = 300 if key == 'height' else date.today().year + 1
            if not value.isdigit() or not 1 <= int(value) <= maximum:
                raise ValueError('Enter a valid height or career year.')
        cleaned[key] = value
    with contract.database.write_transaction() as connection:
        stored = metadata(connection, entity_id)
        edits = stored.setdefault('actor_profile_edits', {})
        for key, value in cleaned.items():
            if value is None:
                edits.pop(key, None)
            else:
                edits[key] = value
        merged = {**(stored.get('stashdb_profile') or {}), **edits}
        if merged.get('career_start_year') and merged.get('career_end_year') and int(merged['career_start_year']) > int(merged['career_end_year']):
            raise ValueError('Career end must be on or after career start.')
        connection.execute('UPDATE entity SET metadata_json=? WHERE id=?', (json.dumps(stored), entity_id))
        result = {'ok': True, 'actor_details': public(connection, entity_id)}
    contract.cache_bust()
    return result
