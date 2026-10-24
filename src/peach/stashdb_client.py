"""StashDB 只读 GraphQL 客户端：固定端点、凭据隔离、有界请求与退避。"""
from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from contextlib import closing
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from .fsutil import atomic_write_text
from .http import HttpRequest, HttpResponse, public_https_url, resolves_publicly
from .user_agent import USER_AGENT

ENDPOINT = 'https://stashdb.org/graphql'
POLICY_KEYS = ('enabled', 'actor_images', 'scene_images', 'correct_cast', 'auto_apply', 'skip_failed', 'only_new_media')
DEFAULTS = dict(enabled=False, actor_images=True, scene_images=True, correct_cast=False, auto_apply=False,
    skip_failed=False, only_new_media=False)
_LOCK = threading.Lock()
_LAST = 0.0
PERFORMER_FIELDS = 'id name disambiguation aliases deleted images{id url width height}'
SCENE_FIELDS = f'''id title release_date duration deleted studio{{id name parent{{id name}}}}
images{{id url width height}} performers{{as performer{{{PERFORMER_FIELDS}}}}}'''


def settings(config, *, secret=False):
    try:
        saved = json.loads((config.directory('secrets') / 'stashdb.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    result = {key: saved.get(key) if type(saved.get(key)) is bool else value for key, value in DEFAULTS.items()}
    result['ignore_terms'] = saved.get('ignore_terms') if isinstance(saved.get('ignore_terms'), str) else ''
    confidence = saved.get('minimum_confidence', 85)
    result['minimum_confidence'] = confidence if type(confidence) is int and 50 <= confidence <= 100 else 85
    cutoff = saved.get('new_media_after_id', 0)
    result['new_media_after_id'] = cutoff if type(cutoff) is int and cutoff >= 0 else 0
    result['new_media_enabled_at'] = str(saved.get('new_media_enabled_at') or '')
    key = saved.get('api_key') if isinstance(saved.get('api_key'), str) else ''
    result.update(endpoint=ENDPOINT, api_key_set=bool(key))
    if secret:
        result['api_key'] = key
    return result


def save_settings(config, body, *, database=None):
    previous = settings(config, secret=True)
    was_new_only = previous['only_new_media']
    for key in POLICY_KEYS:
        if key in body:
            if type(body[key]) is not bool:
                raise ValueError('Choose a valid StashDB option.')
            previous[key] = body[key]
    if previous['only_new_media'] and not was_new_only:
        previous['new_media_enabled_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        if database is not None:
            with database.read_connection() as connection:
                previous['new_media_after_id'] = connection.execute('SELECT COALESCE(MAX(id),0) FROM asset').fetchone()[0]
        else:
            path = config.directory('database') / 'ledger.db'
            if path.is_file():
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
                    previous['new_media_after_id'] = connection.execute('SELECT COALESCE(MAX(id),0) FROM asset').fetchone()[0]
    if 'ignore_terms' in body:
        terms = body['ignore_terms']
        if not isinstance(terms, str) or len(terms) > 2000 or len(terms.splitlines()) > 64:
            raise ValueError('Enter up to 64 filename ignore terms, one per line (2,000 characters maximum).')
        previous['ignore_terms'] = '\n'.join(dict.fromkeys(term.strip() for term in terms.splitlines() if term.strip()))
    if 'minimum_confidence' in body:
        value = body['minimum_confidence']
        if type(value) is not int or not 50 <= value <= 100:
            raise ValueError('Choose an automatic match confidence from 50 to 100 percent.')
        previous['minimum_confidence'] = value
    if 'api_key' in body:
        value = body['api_key']
        if not isinstance(value, str) or len(value) > 4096 or any(c.isspace() for c in value):
            raise ValueError('Enter a valid StashDB API key.')
        previous['api_key'] = value
    if previous['enabled'] and not previous['api_key']:
        raise ValueError('Save a StashDB API key before enabling this source.')
    payload = {key: previous[key] for key in (*POLICY_KEYS, 'ignore_terms', 'minimum_confidence', 'new_media_after_id', 'new_media_enabled_at', 'api_key')}
    path = config.directory('secrets') / 'stashdb.json'
    atomic_write_text(path, json.dumps(payload) + '\n')
    path.chmod(0o600)
    return settings(config)


class RateLimited(ValueError):
    pass


def retry_delay(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        try:
            return max(1, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 60


class Client:
    def __init__(self, config, *, transport=None, interval=1.0):
        self.config = config
        self.policy = settings(config, secret=True)
        if not self.policy['api_key']:
            raise ValueError('Configure your StashDB API key in Sources & subscriptions.')
        self.client = httpx.Client(follow_redirects=False, headers={'User-Agent': USER_AGENT}) if transport is None else None
        self.transport = transport or self._transport
        self.interval = interval
        self.cooldown = config.directory('state') / 'stashdb-cooldown.json'
        self.cache = OrderedDict()
        self.incomplete = False

    def _transport(self, request, timeout, limit):
        with self.client.stream(request.method, request.url, headers=request.headers,
                                content=request.body, timeout=timeout, follow_redirects=False) as response:
            chunks, count = [], 0
            for chunk in response.iter_bytes():
                count += len(chunk)
                if count > limit:
                    raise ValueError('StashDB response exceeds the size limit.')
                chunks.append(chunk)
            return HttpResponse(response.status_code, dict(response.headers), b''.join(chunks), str(response.url))

    def close(self):
        if self.client:
            self.client.close()

    def _request(self, request, limit):
        from .processing_control import checkpoint
        checkpoint('network')
        global _LAST
        with _LOCK:
            try:
                until = float(json.loads(self.cooldown.read_text(encoding='utf-8')).get('until', 0))
            except (OSError, ValueError, TypeError, AttributeError):
                until = 0
            if until > time.time():
                raise RateLimited('StashDB is rate limited. Try again after its cooldown.')
            time.sleep(max(0, self.interval - (time.monotonic() - _LAST)))
            try:
                response = self.transport(request, 20, limit)
            except (httpx.HTTPError, OSError) as from_error:
                raise ValueError('StashDB connection failed. Check the source settings and try again.') from from_error
            finally:
                _LAST = time.monotonic()
            checkpoint()
            if response.status == 429:
                delay = retry_delay(response.headers.get('retry-after'))
                atomic_write_text(self.cooldown, json.dumps({'until': time.time() + delay}))
                raise RateLimited('StashDB is rate limited. Its Retry-After cooldown has been saved.')
            if len(response.body) > limit:
                raise ValueError('StashDB response exceeds the size limit.')
            return response

    def query(self, query, variables=None):
        if not query.lstrip().startswith('query'):
            raise ValueError('StashDB supports read-only queries in Peach.')
        cache_key = json.dumps([query, variables], sort_keys=True)
        if cache_key in self.cache:
            return self.cache[cache_key]
        response = self._request(HttpRequest('POST', ENDPOINT,
            {'ApiKey': self.policy['api_key'], 'Content-Type': 'application/json', 'User-Agent': USER_AGENT},
            json.dumps({'query': query, 'variables': variables or {}}).encode()), 4 * 1024 * 1024)
        if response.status in (401, 403):
            raise ValueError('StashDB rejected the API key. Check your account access and saved key.')
        if response.status != 200 or (response.url and response.url != ENDPOINT):
            raise ValueError(f'StashDB request failed (HTTP {response.status}).')
        try:
            payload = json.loads(response.body)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('StashDB returned an invalid response.') from exc
        if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('data'), dict):
            raise ValueError('StashDB could not complete the query. Check API access and try again.')
        self.cache[cache_key] = payload['data']
        if len(self.cache) > 128:
            self.cache.popitem(last=False)
        return payload['data']

    def check(self):
        return self.query('query PeachStashDBCheck { me { id name } }').get('me') or {}

    def performers(self, name):
        query = f'query PeachPerformers($input:PerformerQueryInput!){{queryPerformers(input:$input){{count performers{{{PERFORMER_FIELDS}}}}}}}'
        result = self.query(query, {'input': {'names': name[:120], 'per_page': 25}})['queryPerformers']
        self.incomplete |= result.get('count', len(result['performers'])) > 25
        return result['performers']

    def studios(self, name):
        query = 'query PeachStudios($input:StudioQueryInput!){queryStudios(input:$input){count studios{id name parent{id name}}}}'
        result = self.query(query, {'input': {'names': name[:120], 'per_page': 25}})['queryStudios']
        self.incomplete |= result.get('count', len(result['studios'])) > 25
        return result['studios']

    def scenes(self, filters):
        query = f'query PeachScenes($input:SceneQueryInput!){{queryScenes(input:$input){{count scenes{{{SCENE_FIELDS}}}}}}}'
        data = self.query(query, {'input': {**filters, 'per_page': 50}})['queryScenes']
        return data['scenes'], data['count'] > 50

    def scene(self, identity):
        return self.query(f'query PeachScene($id:ID!){{findScene(id:$id){{{SCENE_FIELDS}}}}}', {'id': identity}).get('findScene')

    def performer(self, identity):
        return self.query(f'query PeachPerformer($id:ID!){{findPerformer(id:$id){{{PERFORMER_FIELDS}}}}}', {'id': identity}).get('findPerformer')

    def image(self, url):
        host = (urlsplit(url).hostname or '').lower()
        if not public_https_url(url) or not resolves_publicly(host):
            raise ValueError('StashDB image host is not allowed.')
        response = self._request(HttpRequest('GET', url, {'User-Agent': USER_AGENT}), 12 * 1024 * 1024)
        if response.status != 200 or (response.url and response.url != url):
            raise ValueError('StashDB image could not be downloaded.')
        return response.body
