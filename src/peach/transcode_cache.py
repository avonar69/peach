"""转码缓存偏好与可再生媒体缓存的共享容量预算。"""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .fsutil import atomic_write_text


def load(state_root):
    try:
        value = json.loads((Path(state_root) / 'transcode-cache.json').read_text(encoding='utf-8'))
        return validate(value)
    except (OSError, ValueError, TypeError):
        return {'folder': '', 'max_gb': 10}


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid transcode cache settings')
    folder = str(value.get('folder') or '').strip()
    limit = value.get('max_gb', 10)
    if folder and not Path(folder).is_absolute():
        raise ValueError('Transcode folder must be an absolute server path')
    if type(limit) is not int or not 1 <= limit <= 1024:
        raise ValueError('Transcode storage limit must be between 1 and 1024 GiB')
    return {'folder': folder, 'max_gb': limit}


def save(state_root, value):
    value = validate(value)
    atomic_write_text(Path(state_root) / 'transcode-cache.json', json.dumps(value))
    return value


def roots(value, full_root, segment_root):
    if value['folder']:
        root = Path(value['folder']) / 'peach-transcode-cache'
        return root / 'files', root / 'segments'
    return Path(full_root), Path(segment_root)


class CacheBudget:
    """只淘汰自身缓存，保护在途写入；原媒体和其他目录不在扫描范围。"""
    def __init__(self, full_root, segment_root, limit):
        self.roots = (Path(full_root), Path(segment_root))
        self.limit = limit
        self.lock = threading.RLock()
        self.protected = set()
        self.last_check = 0.0

    def _files(self):
        files = []
        for root, pattern in zip(self.roots, ('*.mp4', '*.ts')):
            for path in root.rglob(pattern):
                if path.is_symlink() or (pattern == '*.mp4' and not re.match(r'^\d+-', path.name)):
                    continue
                try:
                    stat = path.stat()
                    if path.is_file():
                        files.append((stat.st_mtime, stat.st_size, path))
                except OSError:
                    continue
        return files

    def usage(self):
        with self.lock:
            return sum(size for _, size, _ in self._files())

    @contextmanager
    def writing(self, path):
        with self.lock:
            self.protected.add(path)
        try:
            yield
        finally:
            with self.lock:
                self.protected.discard(path)

    def enforce(self, *, keep=(), force=False):
        with self.lock:
            now = time.monotonic()
            if not force and now - self.last_check < 1:
                return True
            self.last_check = now
            files = self._files()
            total = sum(size for _, size, _ in files)
            for _, size, path in sorted(files):
                if total <= self.limit:
                    break
                if path in self.protected or path in keep:
                    continue
                try:
                    path.unlink()
                    total -= size
                except OSError:
                    continue
            return total <= self.limit
