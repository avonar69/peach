"""逐目录确认媒体是否仍在；权限与临时读取错误保留记录。"""
import os
from pathlib import Path


def scan_directory_presence(item: tuple[Path, dict[str, list[int]]]) -> tuple[list[int], int]:
    parent, expected = item
    present: set[str] = set()
    unreadable = 0
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                key = entry.name.casefold()
                if key not in expected:
                    continue
                try:
                    if entry.is_file():
                        present.add(key)
                except OSError:
                    present.add(key)
                    unreadable += len(expected[key])
    except FileNotFoundError:
        return [asset_id for ids in expected.values() for asset_id in ids], 0
    except OSError:
        return [], sum(len(ids) for ids in expected.values())
    return ([asset_id for key, ids in expected.items() if key not in present for asset_id in ids], unreadable)
