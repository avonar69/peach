"""文件名归属匹配的本机开关，扫描与推送共用。"""
import json
from pathlib import Path

from .fsutil import atomic_write_text
from .filename_text import terms

FILENAME = 'filename-matching.json'


def read(root: Path) -> dict:
    try:
        saved = json.loads((Path(root) / FILENAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    return {key: isinstance(saved, dict) and saved.get(key) is True for key in ('actors', 'studios')} | {
        'ignore_terms': saved.get('ignore_terms', '') if isinstance(saved, dict) and isinstance(saved.get('ignore_terms', ''), str) else ''}


def save(root: Path, body: dict) -> dict:
    if (not {'actors', 'studios'}.issubset(body) or set(body) - {'actors', 'studios', 'ignore_terms'}
            or any(type(body[key]) is not bool for key in ('actors', 'studios'))):
        raise ValueError('请选择演员与厂牌文件名匹配状态')
    policy = {**read(root), **body}
    policy['ignore_terms'] = '\n'.join(terms(policy['ignore_terms']))
    Path(root).mkdir(parents=True, exist_ok=True)
    atomic_write_text(Path(root) / FILENAME, json.dumps(policy) + '\n')
    return read(root)


def apply(connection, asset_ids, db_path):
    from . import filename_actors
    from .update_tasks import state_for
    policy = read(state_for(Path(db_path)).parent)
    if not (policy['actors'] or policy['studios']):
        return 0
    return filename_actors.apply(connection, asset_ids, **policy)
