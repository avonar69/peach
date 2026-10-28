"""目录发现范围与持久重扫时钟；沿用统一处理任务和 APScheduler。"""
import json
import time
from pathlib import PureWindowsPath
from filelock import FileLock

from .fsutil import atomic_write_text


def selected_locations(config, locations, requested=None):
    allowed = {root for roots in config.locations.values() for root in roots}
    if requested is not None and (not isinstance(requested, list) or not requested
            or any(not isinstance(root, str) or root not in allowed for root in requested)):
        raise ValueError('Choose configured media folders to scan.')
    return {source: tuple(root for root in roots if config.media_scan_updates.get(root, True)
                          and (requested is None or root in requested)) for source, roots in locations.items()}


def child_roots(config, source, root):
    parent = PureWindowsPath(root)
    return [candidate for candidate in config.locations.get(source, ())
            if PureWindowsPath(candidate) != parent and PureWindowsPath(candidate).is_relative_to(parent)]


def processing_locations(config, location, stage, targeted, requested):
    """目录发现使用开关与定时范围，明确选中的已有影片保留处理能力。"""
    locations = config.locations if location == 'configured' else {location: config.locations[location]}
    if targeted or stage not in ('find_new', 'all', 'scan'):
        return locations
    return selected_locations(config, locations, requested)


def _clock(config):
    path = config.directory('state') / 'media-folder-scans.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def record_scanned(config, root, *, now=None):
    path = config.directory('state') / 'media-folder-scans.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + '.lock', timeout=5):
        clock = _clock(config)
        clock[root] = time.time() if now is None else now
        atomic_write_text(path, json.dumps(clock))


def due_roots(config, *, now=None):
    """只返回已启用且到期的目录，初次启用从当前时刻开始计时。"""
    moment = time.time() if now is None else now
    clock = _clock(config)
    roots = [root for values in selected_locations(config, config.locations).values() for root in values
             if config.media_scan_hours.get(root, 0) > 0]
    fresh = [root for root in roots if root not in clock]
    for root in fresh:
        record_scanned(config, root, now=moment)
    due = [root for root in roots if root in clock and isinstance(clock[root], (int, float))
           and moment >= clock[root] + config.media_scan_hours.get(root, 0) * 3600]
    return due
