"""只按已有 StashDB 场景绑定补空，保存停点并遵守共享限流。"""
from . import stashdb, stashdb_client
from .processing_control import checkpoint
from .stashdb_files import read_record


def run(config, database, *, progress, issue, active, completed=()):
    with database.read_connection() as connection:
        rows = [dict(row) for row in connection.execute("SELECT id,name FROM asset WHERE medium='video' AND disposal IS NULL ORDER BY id")]
    matched = [(row, read_record(config.directory('state') / 'stashdb-matches' / f"{row['id']}.json")) for row in rows]
    matched = [(row, record) for row, record in matched if record.get('scene_id') and record.get('decision') != 'dismissed']
    done, count = set(completed), 0
    client = stashdb_client.Client(config)
    try:
        for position, (row, record) in enumerate(matched):
            if not active():
                raise InterruptedError('处理任务已停止')
            checkpoint()
            progress(stage='Resync Scenes', checked=position, total=len(matched), current_asset_name=row['name'])
            if row['id'] not in done:
                try:
                    with database.read_connection() as connection:
                        token = stashdb.asset_evidence(connection, row['id'])[2]
                    stashdb.apply_scene(config, database, row['id'], record['scene_id'], token, client=client, manual=False, fill_only=True)
                    done.add(row['id'])
                    count += 1
                except stashdb_client.RateLimited:
                    raise
                except (ValueError, OSError) as exc:
                    issue(row, str(exc), retryable=True)
            progress(checked=position + 1, total=len(matched), resynced_scenes=sorted(done))
    finally:
        client.close()
    return {'stashdb_applied': count}
