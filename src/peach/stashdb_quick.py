"""按待复核的已保存分数应用候选，不重查作品或演员。"""
import math

from . import stashdb_client
from .processing_control import checkpoint


def threshold(value):
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError('Choose a quick matching threshold from 0 to 100.')
    return value


def candidate(preview, minimum):
    if preview.get('truncated'):
        return None
    rows = {row['id']: row for row in preview.get('candidates', [])
            if isinstance(row, dict) and row.get('id') and type(row.get('score')) in (int, float)
            and math.isfinite(row['score']) and 0 <= row['score'] <= 1}
    ranked = sorted(rows.values(), key=lambda row: (-row['score'], row['id']))
    if not ranked or ranked[0]['score'] < minimum / 100:
        return None
    top = ranked[0]
    if top.get('conflict') or {'Studio differs', 'Release date differs'} & set(top.get('reasons') or []):
        return None
    if len(ranked) > 1 and top['score'] == ranked[1]['score']:
        return None
    return top


def run(config, database, rows, *, minimum, progress, issue, active, previous):
    from .stashdb import asset_evidence, apply_scene
    from .stashdb_files import read_record
    minimum = threshold(minimum)
    done = set(previous.get('rematched_asset_ids', []))
    applied = previous.get('stashdb_applied', 0)
    skipped = previous.get('stashdb_skipped', 0)
    client = stashdb_client.Client(config)
    try:
        for position, row in enumerate(rows):
            if not active():
                raise InterruptedError('处理任务已停止')
            checkpoint()
            if row['id'] in done:
                continue
            preview = read_record(config.directory('state') / 'stashdb-review' / f"{row['id']}.json")
            match = candidate(preview, minimum)
            try:
                with database.read_connection() as connection:
                    current = asset_evidence(connection, row['id'])[2]
                if not match or not preview.get('token') or preview['token'] != current:
                    skipped += 1
                else:
                    progress(checked=position, total=len(rows), current_asset_id=row['id'], current_asset_name=row['name'])
                    apply_scene(config, database, row['id'], match['id'], current, client=client,
                                manual=False, cached_match=match, minimum_confidence=minimum)
                    applied += 1
                done.add(row['id'])
            except InterruptedError:
                raise
            except stashdb_client.RateLimited as exc:
                issue(row, str(exc), paused=True, retryable=True)
                break
            except (ValueError, OSError) as exc:
                issue(row, str(exc), retryable=True)
            progress(checked=position + 1, total=len(rows), current_asset_name=row['name'],
                     rematched_asset_ids=sorted(done), stashdb_applied=applied, stashdb_skipped=skipped)
    finally:
        client.close()
    return {'stashdb_applied': applied, 'stashdb_skipped': skipped}
