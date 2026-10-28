"""按忽略词选定已有影片，独立执行文件名或 StashDB 匹配。"""
from . import filename_actors, filename_matching, filename_text, stashdb_client
from .processing_control import checkpoint

LABELS = {'stashdb_actors': 'Resync Actors', 'stashdb_studios': 'Resync Studios',
          'stashdb_ignored': 'Rematch ignored filenames with StashDB',
          'filename_ignored': 'Rematch actors and studios from filenames'}
REMATCH_STAGES = ('stashdb_ignored', 'filename_ignored')


def selection(config, database, stage, selected=None):
    policy = stashdb_client.settings(config) if stage == 'stashdb_ignored' else filename_matching.read(config.directory('state'))
    if stage == 'stashdb_ignored' and not policy['api_key_set']:
        raise ValueError('Save a StashDB API key before rematching.')
    if stage == 'filename_ignored' and not (policy['actors'] or policy['studios']):
        raise ValueError('Enable actor or studio filename matching before rematching.')
    return filename_text.matching_assets(database, policy.get('ignore_terms', ''), selected)


def run(config, database, stage, *, selected, progress, issue, active, previous):
    if stage in ('stashdb_actors', 'stashdb_studios'):
        from .stashdb_entities import resync
        count = resync(config, database, 'performer' if stage == 'stashdb_actors' else 'studio',
            progress=progress, issue=issue, active=active, completed=previous.get('resynced_entities', []))
        return {'stashdb_applied': count}
    rows = selection(config, database, stage, selected)
    progress(stage=LABELS[stage], total=len(rows), checked=0)
    completed = previous.get('rematched_asset_ids', [])
    if stage == 'stashdb_ignored':
        from .stashdb import scan_assets
        baseline = {key: previous.get('stashdb_' + key, 0) for key in ('applied', 'review')}
        def publish(**values):
            for key, count in baseline.items():
                field = 'stashdb_' + key
                if field in values:
                    values[field] += count
            progress(**values)
        result = scan_assets(config, database, rows, progress=publish, issue=issue,
            active=active, force=True, completed=completed)
        return {'stashdb_' + key: value + baseline.get(key, 0) for key, value in result.items()}
    return _filename(config, database, rows, progress, active, completed, previous.get('filename_matched', 0))


def _filename(config, database, rows, progress, active, completed, count):
    policy = filename_matching.read(config.directory('state'))
    done = set(completed)
    with database.read_connection() as connection:
        index = filename_actors.actor_index(connection) if policy['actors'] else None
    for start in range(0, len(rows), 64):
        if not active():
            raise InterruptedError('处理任务已停止')
        checkpoint()
        batch = rows[start:start + 64]
        ids = [row['id'] for row in batch if row['id'] not in done]
        with database.write_transaction() as connection:
            count += filename_actors.apply(connection, ids, **policy, index=index)
        done.update(ids)
        progress(stage=LABELS['filename_ignored'], checked=start + len(batch), total=len(rows),
            rematched_asset_ids=sorted(done), filename_matched=count, current_asset_name=batch[-1]['name'])
    return {'filename_matched': count}
