"""文件名归属匹配的本机开关，扫描与推送共用。"""
import json
from pathlib import Path

from .fsutil import atomic_write_text

FILENAME = 'filename-matching.json'


def read(root: Path) -> dict:
    try:
        saved = json.loads((Path(root) / FILENAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    return {key: isinstance(saved, dict) and saved.get(key) is True for key in ('actors', 'studios')}


def save(root: Path, body: dict) -> dict:
    if set(body) != {'actors', 'studios'} or any(type(value) is not bool for value in body.values()):
        raise ValueError('请选择演员与厂牌文件名匹配状态')
    atomic_write_text(Path(root) / FILENAME, json.dumps(body) + '\n')
    return read(root)


def apply(connection, asset_ids, db_path):
    from . import filename_actors
    from .update_tasks import state_for
    policy = read(state_for(Path(db_path)).parent)
    if not any(policy.values()):
        return 0
    return filename_actors.apply(connection, asset_ids, **policy)
