"""时间轴预览的采集任务：选一档密度、后台跑、页面轮询。

档位存在服务端而不是浏览器里：跑的是这台机器上的一条长任务，从另一台设备打开设置
时要看到的是「这台机器正在按 10 秒一帧采集」，不是那台设备自己的上一次选择。
"""
import json
import time
from pathlib import Path

from . import timeline_sheets
from .config import FFMPEG_DIR, STATE_DIR
from .ffmpeg import FFmpegResolver
from .fsutil import atomic_path
from .jobs import DiskGuard
from .media_processing_policy import metadata_only, save as save_processing_policy
from .platform import system_volume
from .processing_control import ProcessingControl, MODES as SPEED_MODES

#: 采集期间系统盘至少留这么多 GiB。数字和抽帧脚本的默认值同一个：真正会把系统盘写满的
#: 是网盘缓存那一类第三方消耗方，与产物落在哪块盘无关。
MIN_FREE_GB = 40.0

MODE_PATH = STATE_DIR / 'timeline-thumbnails.json'


def _mode_file(path: Path | None = None) -> Path:
    return Path(path) if path is not None else MODE_PATH


def read_mode(path: Path | None = None) -> str:
    """当前档位。读不出来就是关着——这条链会写盘也会读片子，不能靠猜来开。"""
    try:
        data = json.loads(_mode_file(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return timeline_sheets.OFF
    mode = str((data or {}).get('mode') or timeline_sheets.OFF)
    return mode if mode in timeline_sheets.MODES else timeline_sheets.OFF


def read_interval(path: Path | None = None) -> int:
    try:
        data = json.loads(_mode_file(path).read_text(encoding='utf-8'))
        value = data.get('interval_seconds', 10)
        return value if type(value) is int and 1 <= value <= 3600 else 10
    except (OSError, ValueError, AttributeError):
        return 10


def write_mode(mode: str, path: Path | None = None, *, interval_seconds=None) -> None:
    interval_seconds = read_interval(path) if interval_seconds is None else interval_seconds
    with atomic_path(_mode_file(path)) as destination:
        destination.write_text(json.dumps({'mode': mode, 'interval_seconds': interval_seconds, 'saved_at': time.time()}),
                               encoding='utf-8')


def q_media_processing(contract, _args):
    return {'metadata_only': metadata_only(contract.follow_state_root)}


def w_media_processing(contract, body):
    value = (body or {}).get('metadata_only')
    save_processing_policy(contract.follow_state_root, value)
    if value:
        write_mode('off', Path(contract.follow_state_root) / 'timeline-thumbnails.json')
        contract.thumbnail_job.stop(resume=False)
    return q_media_processing(contract, {})


def q_timeline(contract, args):
    """一部片子的时间轴索引。没铺到就回空对象，页面据此决定要不要画这一层。

    单独一条而不是随列表下发：一页六十张卡里真正被悬停的是个位数，为此每行多读一份
    `meta.json` 是把六十次文件读摊到每一次翻页上。
    """
    asset_id = int((args or {}).get('id') or 0)
    if asset_id <= 0:
        return {}
    return timeline_sheets.read_meta(contract.timeline_root, asset_id) or {}


def q_thumbnail_jobs(contract, _args):
    state = contract.thumbnail_job.snapshot() or {}
    return {'mode': read_mode(), 'modes': list(timeline_sheets.MODES),
            'speed_mode': _speed_control().mode, 'speed_modes': list(SPEED_MODES),
            'interval_seconds': timeline_sheets.INTERVALS.get(read_mode(), read_interval()),
            'acceleration': read_acceleration(),
            'intervals': dict(timeline_sheets.INTERVALS),
            'status': state.get('status') or 'idle',
            'stage': state.get('stage') or '',
            'message': state.get('message') or '',
            'waiting_for_update': bool(state.get('waiting_for_update')),
            'job_id': state.get('job_id') or '',
            'total': state.get('total') or 0, 'done': state.get('done') or 0,
            'made': state.get('made') or 0, 'skipped': state.get('skipped') or 0,
            'failed': state.get('failed') or 0, 'stopped': state.get('stopped') or '',
            'current_frame': state.get('current_frame') or 0, 'current_frames': state.get('current_frames') or 0}


def _speed_control():
    path = MODE_PATH.with_name('timeline-thumbnail-control.json')
    control = ProcessingControl(path)
    if not path.exists():
        control.mode = 'low'
    return control


def read_acceleration():
    try:
        value = json.loads(MODE_PATH.with_name('thumbnail-acceleration.json').read_text(encoding='utf-8'))
        return value if value in ('cpu', 'cuda', 'vulkan') else 'cpu'
    except (OSError, ValueError):
        return 'cpu'


def _active(contract, job_id):
    state = contract.thumbnail_job.snapshot() or {}
    if state.get('job_id') != job_id or state.get('status') != 'running':
        return False
    if read_mode() == timeline_sheets.OFF or metadata_only(contract.follow_state_root):
        return False
    run_id = state.get('run_id')
    if type(run_id) is int:
        run = contract.task_runs.get(run_id)
        return run is not None and run.active
    return True


def _with_progress(fields: dict) -> dict:
    """任务中心（活动页）按 `checked` / `total` 画进度条，这条链自己的计数叫 `done`。"""
    return {**fields, 'checked': fields['done']} if 'done' in fields else fields


def _delete_thumbnails(contract, body):
    if body.get('confirmed') is not True:
        raise ValueError('Confirm deletion of generated timeline thumbnails.')
    write_mode('off')
    worker = getattr(contract.thumbnail_job, 'thread', None)
    contract.thumbnail_job.stop(resume=False)
    if worker is not None and worker.is_alive():
        raise ValueError('Thumbnail generation is stopping. Try deleting again shortly.')
    removed = timeline_sheets.clear_library(contract.timeline_root)
    return {**q_thumbnail_jobs(contract, {}), 'removed': removed}


def w_thumbnail_jobs(contract, body):
    """选档位。选 `off` 只是停手，已经生成的图留在盘上——几 GB 的产物删不删是另一件
    事，走数据管理页那条清理链，不在切换开关时顺手做掉。"""
    if (body or {}).get('action') == 'delete_all':
        return _delete_thumbnails(contract, body)
    if (body or {}).get('action') == 'set_speed':
        _speed_control().request('set_speed', mode=body.get('speed_mode'))
        return q_thumbnail_jobs(contract, {})
    if (body or {}).get('action') == 'set_acceleration':
        value = body.get('acceleration')
        if value not in ('cpu', 'cuda', 'vulkan'):
            raise ValueError('Invalid thumbnail acceleration backend')
        from .fsutil import atomic_write_text
        atomic_write_text(MODE_PATH.with_name('thumbnail-acceleration.json'), json.dumps(value))
        return q_thumbnail_jobs(contract, {})
    mode = str((body or {}).get('mode') or timeline_sheets.OFF)
    regeneration = (body or {}).get('regeneration', 'upgrade')
    if regeneration not in ('all', 'upgrade'):
        raise ValueError('Choose a valid timeline regeneration scope.')
    if mode not in timeline_sheets.MODES:
        raise ValueError('采集密度无效')
    if mode != timeline_sheets.OFF and metadata_only(contract.follow_state_root):
        raise ValueError('视频预览生成已关闭，请先在媒体库设置中开启')
    interval = (body or {}).get('interval_seconds', read_interval()) if mode == 'custom' else timeline_sheets.INTERVALS.get(mode, 10)
    if type(interval) is not int or not 1 <= interval <= 3600:
        raise ValueError('Interval must be between 1 and 3600 seconds.')
    write_mode(mode, interval_seconds=interval)
    if mode == timeline_sheets.OFF:
        contract.thumbnail_job.stop(resume=False)
        return q_thumbnail_jobs(contract, {})
    choice = FFmpegResolver(FFMPEG_DIR).ffmpeg()
    if choice is None:
        raise ValueError('未找到 ffmpeg，无法采集缩略图')
    current = contract.thumbnail_job.snapshot() or {}
    if current.get('status') == 'running' and current.get('interval') != interval:
        contract.thumbnail_job.stop(resume=False)
    root = contract.timeline_root

    def work(job_id):
        guard = DiskGuard(system_volume(), MIN_FREE_GB)
        with _speed_control().bind(job_id, db_path=contract.db_path,
                                  active=lambda: _active(contract, job_id),
                                  publish=lambda **fields: contract.thumbnail_job.update(job_id, **fields)):
            result = timeline_sheets.generate_library(
                contract.db_path, root, interval, ffmpeg=str(choice.path),
                acceleration=read_acceleration,
                regeneration=regeneration,
                active=lambda: _active(contract, job_id),
                report=lambda **fields: contract.thumbnail_job.update(job_id, **_with_progress(fields)),
                guard=guard, resume_state=contract.thumbnail_job.snapshot(),
                checkpoint=lambda **fields: contract.thumbnail_job.checkpoint(job_id, **fields))
        # 磁盘触线停下来的那一轮不能记成完成：队列后面还剩几千部，而页面上「完成」
        # 和「跑完了」是同一个意思。按停是用户自己做的，不算故障。
        stopped = str(result.get('stopped') or '')
        failed = bool(stopped) and stopped != timeline_sheets.STOPPED_BY_USER
        contract.thumbnail_job.update(
            job_id, **_with_progress(result), completed_at=time.time(),
            status='failed' if failed else 'complete',
            error=stopped if failed else '')

    contract.thumbnail_job.start(work, restart=True, recovery={'mode': mode, 'interval_seconds': interval, 'regeneration': regeneration},
                                 initial={'mode': mode, 'interval': interval,
                                          'stage': '采集缩略图', 'checked': 0,
                                          'total': 0, 'done': 0, 'made': 0,
                                          'skipped': 0, 'failed': 0, 'stopped': ''})
    return q_thumbnail_jobs(contract, {})
