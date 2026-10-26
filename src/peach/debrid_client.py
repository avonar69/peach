"""AllDebrid 与 Real-Debrid 官方接口：凭据隔离、限流和可续查的远端身份。"""
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from .fsutil import atomic_write_text
from .public_download_http import fetch, web_url
from .user_agent import USER_AGENT

PROVIDERS = {'alldebrid': 'AllDebrid', 'realdebrid': 'Real-Debrid'}
BASE = {'alldebrid': 'https://api.alldebrid.com', 'realdebrid': 'https://api.real-debrid.com/rest/1.0'}
_LOCK = threading.Lock()
_SETTINGS_LOCK = threading.RLock()
_LAST = {}


def _retry_delay(value):
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        try:
            return max(60, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 60


def saved(config):
    try:
        data = json.loads((config.directory('secrets') / 'debrid.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def settings(config):
    values = saved(config)
    try:
        hosts = json.loads((config.directory('state') / 'debrid-hosts.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        hosts = {}
    return {'providers': [{'id': key, 'label': name, 'configured': bool(values.get(key, {}).get('api_key')),
        'download_folder': values.get(key, {}).get('download_folder', ''),
        'max_concurrent_downloads': values.get(key, {}).get('max_concurrent_downloads', 3),
        'auto_import': values.get(key, {}).get('auto_import') is True, 'hosts': hosts.get(key, [])} for key, name in PROVIDERS.items()]}


def save(config, provider, body):
    with _SETTINGS_LOCK:
        return _save_settings(config, provider, body)


def _save_settings(config, provider, body):
    if provider not in PROVIDERS:
        raise ValueError('Choose a debrid provider.')
    values = saved(config)
    row = values.setdefault(provider, {})
    key = body.get('api_key', '')
    if not isinstance(key, str) or len(key) > 4096 or any(char.isspace() for char in key):
        raise ValueError('Enter a valid API key.')
    if body.get('remove_key'):
        row.pop('api_key', None)
    elif key:
        row['api_key'] = key
    if 'download_folder' in body:
        folder = str(body['download_folder'] or '').strip()
        if folder and (not Path(folder).is_absolute() or not Path(folder).is_dir()):
            raise ValueError('Choose an existing absolute download folder visible to Peach.')
        row['download_folder'] = str(Path(folder).resolve()) if folder else ''
    if 'auto_import' in body:
        if type(body['auto_import']) is not bool:
            raise ValueError('Choose whether to import completed downloads.')
        row['auto_import'] = body['auto_import']
    if 'max_concurrent_downloads' in body:
        limit = body['max_concurrent_downloads']
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError('Choose between 1 and 10 concurrent downloads.')
        row['max_concurrent_downloads'] = limit
    if row.get('auto_import'):
        from .debrid_import import import_target
        if not row.get('download_folder'):
            raise ValueError('Choose a download folder inside a configured media library to enable automatic import.')
        import_target(config, Path(row['download_folder']))
    path = config.directory('secrets') / 'debrid.json'
    atomic_write_text(path, json.dumps(values))
    path.chmod(0o600)
    return settings(config)


def key_stamp(config, provider):
    return hashlib.sha256(str(saved(config).get(provider, {}).get('api_key', '')).encode()).hexdigest()


class Client:
    def __init__(self, config, provider, *, client=None, active=lambda: True):
        if provider not in PROVIDERS:
            raise ValueError('Choose a debrid provider.')
        self.provider, self.config, self.active = provider, config, active
        self.key = saved(config).get(provider, {}).get('api_key')
        if not self.key:
            raise ValueError('Save the debrid API key in Download providers first.')
        self.client = client or httpx.Client(timeout=25, follow_redirects=False)

    def close(self):
        self.client.close()

    def call(self, method, path, *, data=None, content=None, files=None):
        if not self.active():
            raise InterruptedError('Download cancelled.')
        cooldown = self.config.directory('state') / f'debrid-{self.provider}-cooldown.json'
        with _LOCK:
            try:
                until = json.loads(cooldown.read_text()).get('until', 0)
            except (OSError, ValueError):
                until = 0
            if until > time.time():
                raise ValueError('The debrid provider is rate limited. Try again after its cooldown.')
            time.sleep(max(0, 1 - (time.monotonic() - _LAST.get(self.provider, 0))))
            _LAST[self.provider] = time.monotonic()
        try:
            with self.client.stream(method, BASE[self.provider] + path, data=data, content=content, files=files,
                    headers={'Authorization': 'Bearer ' + self.key, 'User-Agent': USER_AGENT}) as response:
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 4 * 1024 * 1024:
                        raise ValueError('The debrid response exceeds the size limit.')
                if response.status_code == 429:
                    delay = _retry_delay(response.headers.get('retry-after'))
                    atomic_write_text(cooldown, json.dumps({'until': time.time() + delay}))
                if response.status_code not in (200, 201, 202, 204):
                    raise ValueError(f'Debrid request failed (HTTP {response.status_code}). Check the account and link.')
        except httpx.HTTPError:
            raise ValueError('The debrid connection failed. Try again later.') from None
        value = json.loads(payload) if payload else {}
        if not isinstance(value, (dict, list)):
            raise ValueError('The debrid provider returned an invalid response.')
        if self.provider == 'alldebrid':
            if value.get('status') != 'success':
                raise ValueError('AllDebrid could not process this request. Check the account and link.')
            return value.get('data') or {}
        return value

    def check(self):
        data = self.call('GET', '/v4/user' if self.provider == 'alldebrid' else '/user')
        user = data.get('user', data)
        domains = self.call('GET', '/v4/hosts/domains' if self.provider == 'alldebrid' else '/hosts/domains')
        if isinstance(domains, dict):
            domains = domains.get('hosts', []) + domains.get('streams', []) + domains.get('redirectors', [])
        path = self.config.directory('state') / 'debrid-hosts.json'
        try:
            hosts = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            hosts = {}
        hosts[self.provider] = [str(host).lower() for host in domains[:2000]]
        atomic_write_text(path, json.dumps(hosts))
        return {'ok': True, 'account': str(user.get('username') or ''), 'hosts': hosts[self.provider]}

    def unlock(self, url, *, previous=None, persist=lambda values: None):
        web_url(url)
        path = '/v4/link/unlock' if self.provider == 'alldebrid' else '/unrestrict/link'
        delayed = (previous or {}).get('delayed')
        if delayed and self.provider == 'alldebrid':
            data = self.call('POST', '/v4/link/delayed', data={'id': delayed})
            if data.get('status') == 1:
                return None
            if data.get('status') == 3:
                raise ValueError('AllDebrid could not prepare this delayed link.')
        else:
            data = self.call('POST', path, data={'link': url})
        if data.get('delayed'):
            persist({'delayed': data['delayed'], 'filename': str(data.get('filename') or 'download.bin'),
                     'size': int(data.get('filesize') or 0)})
            return None
        link = data.get('link') if self.provider == 'alldebrid' else data.get('download')
        if not link:
            raise ValueError('This link is delayed or needs a quality selection. Open it on the provider website.')
        return {'url': web_url(link), 'filename': str(data.get('filename') or (previous or {}).get('filename') or 'download.bin'),
                'size': int(data.get('filesize') or (previous or {}).get('size') or 0), 'host_link': url}

    def create_torrent(self, link):
        if link['kind'] == 'magnet':
            path = '/v4/magnet/upload' if self.provider == 'alldebrid' else '/torrents/addMagnet'
            field = 'magnets[]' if self.provider == 'alldebrid' else 'magnet'
            data = self.call('POST', path, data={field: link['url']})
        else:
            response = fetch(link['url'], https_only=False)
            if response.status != 200:
                raise ValueError('The torrent file could not be fetched.')
            if self.provider == 'alldebrid':
                data = self.call('POST', '/v4/magnet/upload/file',
                    files={'files[]': ('feed.torrent', response.body, 'application/x-bittorrent')})
            else:
                data = self.call('PUT', '/torrents/addTorrent', content=response.body)
        item = (data.get('magnets') or data.get('files') or [data])[0]
        if item.get('error') or not item.get('id'):
            raise ValueError('The debrid provider rejected this torrent.')
        return str(item['id'])

    def torrent_links(self, remote_id):
        identity = quote(str(remote_id), safe='')
        if self.provider == 'realdebrid':
            data = self.call('GET', '/torrents/info/' + identity)
            if data.get('status') == 'waiting_files_selection':
                self.call('POST', '/torrents/selectFiles/' + identity, data={'files': 'all'})
                return None
            if data.get('status') in ('error', 'magnet_error', 'virus', 'dead'):
                raise ValueError('The provider could not prepare this torrent.')
            return data.get('links', []) if data.get('status') == 'downloaded' else None
        data = self.call('POST', '/v4.1/magnet/status', data={'id': remote_id})
        magnets = data.get('magnets') or []
        item = magnets if isinstance(magnets, dict) else next((row for row in magnets if str(row.get('id')) == remote_id), {})
        if int(item.get('statusCode', 0)) > 4:
            raise ValueError('The provider could not prepare this torrent.')
        if item.get('statusCode') != 4:
            return None
        data = self.call('POST', '/v4/magnet/files', data={'id[]': remote_id})
        return _file_links((data.get('magnets') or [{}])[0].get('files') or [])


def _file_links(files):
    result, pending = [], list(files)
    while pending and len(result) <= 100:
        item = pending.pop()
        pending.extend(item.get('e') or [])
        if item.get('l'):
            result.append(item['l'])
        if len(pending) > 10000:
            raise ValueError('This torrent contains too many files.')
    if len(result) > 100:
        raise ValueError('This torrent contains too many files.')
    return result
