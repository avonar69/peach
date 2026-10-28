"""文件名匹配的字面忽略词；不改写路径或文件。"""
import re
from pathlib import PureWindowsPath


def terms(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError('Enter up to 64 filename ignore terms, one per line (2,000 characters maximum).')
    rows = list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))
    if len(rows) > 64:
        raise ValueError('Enter up to 64 filename ignore terms, one per line (2,000 characters maximum).')
    return rows


def clean(value, ignored):
    for term in sorted(terms(ignored), key=len, reverse=True):
        value = re.sub(re.escape(term), ' ' if any(char.isalnum() for char in term) else '', value, flags=re.I)
    return value


def matching_assets(database, ignored, selected=None):
    needles = [term.casefold() for term in terms(ignored)]
    if not needles:
        raise ValueError('Add filename ignore text before rematching.')
    chosen = None if selected is None else set(selected)
    with database.read_connection() as connection:
        rows = connection.execute("SELECT id,name,path,first_seen FROM asset WHERE medium='video' AND disposal IS NULL ORDER BY id").fetchall()
    found = [dict(row) for row in rows if (chosen is None or row['id'] in chosen)
             and any(term in PureWindowsPath(str(row['path'] or row['name'] or '')).name.casefold() for term in needles)]
    if not found:
        raise ValueError('No library filenames contain the configured ignore text.')
    return found
