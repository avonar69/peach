"""完成的 debrid 文件复用单条摄取、资料处理与持久后继。"""
import json
from pathlib import Path, PureWindowsPath

from filelock import FileLock, Timeout

from . import settings_file
from .followups import FollowupType, register
from .library_processing import COLLECT_STAGE, process_library, state_path
from .scan import ingest_path, medium_of, walk_root_for

TASK_KEY = 'debrid-import'
LABEL = 'Debrid import'


def import_target(config, path):
    actual = Path(path).resolve()
    candidates = []
    for location, roots in config.locations.items():
        for root in roots:
            mounted = walk_root_for(location, root, declared_roots=config.locations, mounts=config.mounts).resolve()
            if actual.is_relative_to(mounted):
                candidates.append((len(mounted.parts), location, str(PureWindowsPath(root, *actual.relative_to(mounted).parts))))
    if not candidates:
        raise ValueError('Choose a download folder inside a configured media library to enable automatic import.')
    _, location, ledger_path = max(candidates)
    return location, ledger_path


def _busy(config):
    try:
        with FileLock(str(state_path(config)) + '.lock', timeout=0):
            return False
    except Timeout:
        return True


def enqueue(contract, task):
    if not task.get('auto_import') or task.get('status') != 'complete' or task.get('import_cancelled'):
        return None
    config = settings_file.active()
    if _busy(config):
        return None
    parent = contract.task_runs.start(TASK_KEY, trigger='scheduled', mutex_key='debrid-complete:' + task['id'],
                                      conflict='skip', label=LABEL)
    if parent is None:
        return None
    key = TASK_KEY + ':' + task['id']
    result = contract.task_runs.enqueue_followups(parent.id, [(key, TASK_KEY, LABEL)])
    current = contract.task_runs.blocking(key)
    run_id = result['queued'][0] if result['queued'] else current.id if current else None
    contract.task_runs.finish(parent.id, 'succeeded', summary={'followups': len(result['queued'])})
    if run_id is not None:
        contract.followups.wake()
    return run_id


def _collect_video(contract, service, task, identity, handle, config):
    video = Path(task.get('path') or '')
    if not video.is_file():
        raise ValueError('The completed download file is unavailable.')
    if medium_of(video.name) != 'video':
        service.import_progress(identity, import_state='skipped', import_error='The download is not a supported video.')
        return None
    location, ledger_path = import_target(config, video)
    ingested = ingest_path(contract.db_path, location, ledger_path, declared_roots=config.locations, mounts=config.mounts)
    if not ingested.found or ingested.sidecar or ingested.asset_id is None:
        raise ValueError('The completed download could not be registered.')
    checkpoint = config.directory('state') / 'debrid-processing' / (identity + '.json')
    try:
        previous = json.loads(checkpoint.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = None
    result = previous if previous and previous.get('status') == 'complete' else process_library(
        config, contract.db_path, contract.candidate_root, contract.cover_root,
        asset_ids=[ingested.asset_id], stage=COLLECT_STAGE, database=contract.database,
        state_file=checkpoint, resume_state=previous, active=lambda: service.import_active(identity),
        report=lambda state: handle.progress(current=state.get('checked', 0), total=state.get('total', 0), label=state.get('stage', LABEL)))
    if result.get('status') != 'complete':
        raise ValueError('The file is registered, but metadata processing needs attention. Retry the import.')
    return ingested.asset_id


def run(contract, key, handle):
    prefix, _, identity = key.partition(':')
    if prefix != TASK_KEY or len(identity) != 32 or any(char not in '0123456789abcdef' for char in identity):
        raise ValueError('Choose a completed debrid download.')
    service = contract.debrid
    task = service.job(identity)
    if task.get('import_state') == 'complete' or task.get('import_cancelled'):
        return {'already_complete': task.get('import_state') == 'complete'}
    if task.get('status') != 'complete' or not task.get('auto_import'):
        raise ValueError('Choose a completed download with automatic import enabled.')
    config = settings_file.active()
    if Path(contract.db_path).resolve() != (config.directory('database') / 'ledger.db').resolve():
        raise ValueError('The media library configuration does not match this database.')
    if _busy(config):
        service.stopped.wait(5)
        return {'continue': True}
    service.import_progress(identity, import_state='running', import_error='')
    try:
        asset_id = _collect_video(contract, service, task, identity, handle, config)
        if asset_id is None:
            return {'skipped': True}
        service.import_progress(identity, import_state='complete', import_error='', imported_asset_id=asset_id)
        return {'asset_id': asset_id}
    except Timeout:
        service.import_progress(identity, import_state='queued')
        service.stopped.wait(5)
        return {'continue': True}
    except InterruptedError:
        if not service.job(identity).get('import_cancelled'):
            service.import_progress(identity, import_state='pending', import_error='', import_next_attempt=0)
        raise
    except Exception:
        if not service.job(identity).get('import_cancelled'):
            service.import_progress(identity, import_state='failed', import_error='The download completed, but automatic import failed. Retry the import.')
        raise
    finally:
        contract.cache_bust()


TYPE = register(FollowupType(task_key=TASK_KEY, label=LABEL, writes_ledger=True, run=run))
