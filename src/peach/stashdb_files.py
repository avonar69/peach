"""StashDB 图片的正式目录、兼容导入及已完成判据。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .fsutil import atomic_write_bytes


def read_record(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def stash_photo(target, remote_id):
    record = read_record(str(target) + '.provenance.json')
    return target.is_file() and record.get('provider') == 'stashdb' and record.get('external_id') == remote_id


def policy_stamp(policy):
    return {key: policy[key] for key in ('actor_images', 'scene_images', 'correct_cast')}


def recover_images(config):
    """只复制本来源的缓存；正式目录已有的图片及原缓存均保留。"""
    restored = 0
    for folder, pattern, provenance in (('avatars', 'performer-*.img', '.provenance.json'),
                                         ('covers', '*.jpg', '.scraping.json')):
        old_root = config.data_root / folder
        root = config.directory('generated') / folder
        for old in old_root.glob(pattern):
            if folder == 'avatars' and not re.fullmatch(r'performer-\d+\.img', old.name):
                continue
            evidence = Path(str(old) + provenance) if folder == 'avatars' else old.with_suffix(provenance)
            if read_record(evidence).get('provider') != 'stashdb' or (root / old.name).exists():
                continue
            atomic_write_bytes(root / old.name, old.read_bytes())
            for sidecar in old_root.glob(old.stem + '.*'):
                if sidecar != old and sidecar.is_file() and not (root / sidecar.name).exists():
                    atomic_write_bytes(root / sidecar.name, sidecar.read_bytes())
            restored += 1
    return restored


def completed(config, asset_id, token, policy):
    record = read_record(config.directory('state') / 'stashdb-matches' / f'{asset_id}.json')
    return (record.get('token') == token and record.get('policy') == policy_stamp(policy)
            and all((config.directory('generated') / name).is_file() for name in record.get('files', [])))


def search_stamp(policy):
    return {key: policy[key] for key in ('ignore_terms', 'minimum_confidence', 'auto_apply')}


def skip_search(config, asset_id, token, policy, cached, *, first_seen=None):
    """返回跳过原因与是否复用待复核结果；人工预览不调用此判据。"""
    added_later = bool(first_seen and first_seen > policy['new_media_enabled_at'])
    if policy['only_new_media'] and asset_id <= policy['new_media_after_id'] and not added_later:
        return 'StashDB skipped by scan settings', False
    if completed(config, asset_id, token, policy):
        return 'StashDB already up to date', False
    failure = read_record(config.directory('state') / 'stashdb-failures' / f'{asset_id}.json')
    if (policy['skip_failed'] and failure.get('token') == token and failure.get('search_policy') == search_stamp(policy)
            and failure.get('policy') == policy_stamp(policy)):
        return 'StashDB skipped by scan settings', False
    searched_at = cached.get('searched_at', 0)
    fresh = isinstance(searched_at, (float, int)) and time.time() - searched_at < 86400
    reusable = (cached.get('evidence_token') == token and cached.get('search_policy') == search_stamp(policy)
        and (cached.get('candidates') or policy['skip_failed'] or fresh))
    return ('StashDB already up to date', True) if reusable else ('', False)
