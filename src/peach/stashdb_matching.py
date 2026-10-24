"""按日期、厂牌、标题、出演者与时长解释 StashDB 候选，不以文件名整串定身份。"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import PureWindowsPath

from .filename_actors import release_actors

DATED = re.compile(r'^(.+?)[._ -](\d{4}|\d{2})[._ -](\d{2})[._ -](\d{2})[._ -](.+)$')


def key(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', str(value or '')).casefold())


def words(value):
    return re.sub(r'[._]+', ' ', str(value or '')).strip()


def hints(row, actors=(), *, ignore_terms=''):
    stem = PureWindowsPath(row['name']).stem
    for term in sorted(filter(None, ignore_terms.splitlines()), key=len, reverse=True):
        stem = re.sub(re.escape(term), ' ' if any(char.isalnum() for char in term) else '', stem, flags=re.I)
    stem = stem.strip(' ._-')
    studio, released, tail = str(row.get('studio') or ''), str(row.get('release_date') or ''), stem
    match = DATED.fullmatch(stem)
    if match:
        prefix, year, month, day, tail = match.groups()
        try:
            parsed = date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day)).isoformat()
        except ValueError:
            parsed = ''
        if parsed:
            released = released or parsed
            studio = studio or words(prefix)
    cast = list(dict.fromkeys([*actors, *release_actors(stem)]))
    title = str(row.get('catalog_title') or row.get('original_title') or '')
    if not title:
        tail = re.split(r'[._ ](?:\d{3,4}p|web[._ -]?dl|[xh]26[45]|hevc|aac)(?:[._ -]|$)', tail, flags=re.I)[0]
        title = words(tail)
        for actor in sorted(cast, key=len, reverse=True):
            title = re.sub(re.escape(actor), ' ', title, flags=re.I)
        title = re.sub(r'\b(?:and|xxx)\b', ' ', title, flags=re.I).strip(' -&')
    return {'title': title[:200], 'date': released[:10], 'studio': studio[:120], 'actors': cast[:12],
            'duration': float(row.get('duration') or 0), 'filename': row['name']}


def performer_names(appearance):
    performer = appearance.get('performer') or {}
    return {key(value) for value in [performer.get('name'), appearance.get('as'), *(performer.get('aliases') or [])] if value}


def _cast_overlap(scene, actors):
    expected = {key(value) for value in actors if key(value)}
    known = set().union(*(performer_names(appearance) for appearance in scene.get('performers') or []))
    return len(expected & known) / len(expected) if expected else 0


def _strong_match(studio, released, cast, title, conflicts):
    return not conflicts and studio and ((released and (cast >= .5 or title >= .85)) or (title >= .95 and cast >= .75))


def rank_scene(scene, evidence):
    if scene.get('deleted'):
        return None
    studio = scene.get('studio') or {}
    studios = {key(studio.get('name')), key((studio.get('parent') or {}).get('name'))} - {''}
    studio_match = bool(evidence['studio'] and key(evidence['studio']) in studios)
    released = scene.get('release_date') or scene.get('date') or ''
    date_match = bool(evidence['date'] and evidence['date'] == released)
    date_conflict = bool(evidence['date'] and released and not date_match)
    studio_conflict = bool(evidence['studio'] and studios and not studio_match)
    title_score = SequenceMatcher(None, key(evidence['title']), key(scene.get('title'))).ratio() if evidence['title'] else 0
    cast_score = _cast_overlap(scene, evidence['actors'])
    duration = float(scene.get('duration') or 0)
    duration_match = bool(duration and evidence['duration'] and abs(duration - evidence['duration']) <= max(30, duration * .05))
    score = min(1, .3 * studio_match + .3 * date_match + .3 * cast_score + .3 * title_score + .05 * duration_match)
    if date_conflict:
        score -= .45
    if studio_conflict:
        score -= .45
    strong = _strong_match(studio_match, date_match, cast_score, title_score, date_conflict or studio_conflict)
    reasons = [label for matched, label in [(studio_match, 'Studio matches'), (date_match, 'Release date matches'),
        (cast_score > 0, 'Actor names or aliases match'), (title_score >= .85, 'Scene title matches'),
        (duration_match, 'Duration matches'), (date_conflict, 'Release date differs'), (studio_conflict, 'Studio differs')] if matched]
    return {'id': scene['id'], 'title': scene.get('title') or '', 'date': released, 'studio': studio.get('name') or '',
            'actors': [(item.get('performer') or {}).get('name') for item in scene.get('performers') or []],
            'score': round(max(0, score), 3), 'strong': strong, 'reasons': reasons,
            'url': f"https://stashdb.org/scenes/{scene['id']}"}


def _studio_ids(client, name):
    studio_ids = []
    if name:
        variants = [name, re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)]
        for term in dict.fromkeys(variants):
            for studio in client.studios(term):
                if key(name) in {key(studio.get('name')), key((studio.get('parent') or {}).get('name'))}:
                    studio_ids.append(studio['id'])
    return list(dict.fromkeys(studio_ids))


def _performer_ids(client, actors, known=None):
    performer_ids = []
    for actor in actors[:4]:
        if (known or {}).get(key(actor)):
            performer_ids.append(known[key(actor)])
            continue
        matches = client.performers(actor)
        performer_ids.extend(item['id'] for item in matches if not item.get('deleted') and
            key(actor) in {key(item.get('name')), *(key(alias) for alias in item.get('aliases') or [])})
    return list(dict.fromkeys(performer_ids))


def search_scenes(client, evidence, *, known_actors=None, minimum_confidence=85):
    client.incomplete = False
    found, filters, truncated = {}, [], False
    studio_ids = _studio_ids(client, evidence['studio'])
    performer_ids = _performer_ids(client, evidence['actors'], known_actors)
    date_filter = {'date': {'value': evidence['date'], 'modifier': 'EQUALS'}} if evidence['date'] else {}
    studio_filter = {'studios': {'value': list(dict.fromkeys(studio_ids)), 'modifier': 'INCLUDES'}} if studio_ids else {}
    actor_filter = {'performers': {'value': list(dict.fromkeys(performer_ids)), 'modifier': 'INCLUDES'}} if performer_ids else {}
    if date_filter and studio_filter:
        filters.append({**date_filter, **studio_filter})
    if actor_filter and date_filter:
        filters.append({**actor_filter, **date_filter})
    if actor_filter and studio_filter:
        filters.append({**actor_filter, **studio_filter})
    if evidence['title']:
        filters.append({'title': evidence['title'][:120], **studio_filter})
    if not filters and date_filter:
        filters.append(date_filter)
    for query in filters[:4]:
        scenes, overflow = client.scenes(query)
        truncated |= overflow
        for scene in scenes:
            found[scene['id']] = scene
    truncated |= bool(getattr(client, 'incomplete', False))
    ranked = sorted(filter(None, (rank_scene(scene, evidence) for scene in found.values())), key=lambda row: (-row['score'], row['id']))
    unique = bool(ranked and ranked[0]['strong'] and ranked[0]['score'] >= minimum_confidence / 100
                  and (len(ranked) == 1 or ranked[0]['score'] - ranked[1]['score'] >= .12) and not truncated)
    return {'hints': evidence, 'candidates': ranked[:20], 'automatic_match': ranked[0]['id'] if unique else None,
            'truncated': truncated, 'review_required': not unique}
