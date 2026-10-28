"""NZBGet JSON-RPC 的本机凭据与 NZB URL 入队。"""
import httpx

from . import download_provider_http
from .follow_secrets import CredentialStore


def _values(config):
    saved = CredentialStore(config.directory('secrets')).load('nzbget')
    return saved.values if saved else {}


def settings(config):
    values = _values(config)
    return {key: values.get(key, '') for key in ('url', 'username', 'category')} | {
        'configured': bool(values.get('url') and values.get('username') and values.get('password'))}


def save(config, body):
    values = _values(config)
    url = download_provider_http.endpoint(body.get('url'), 'jsonrpc')
    user, category = str(body.get('username') or '').strip(), str(body.get('category') or '').strip()
    password = '' if body.get('remove_key') is True else str(body.get('password') or values.get('password') or '')
    if not user or len(user) > 200 or len(category) > 100 or any(ord(char) < 32 for char in user + category + password):
        raise ValueError('Check the NZBGet username, password and category.')
    store = CredentialStore(config.directory('secrets'))
    store.root.mkdir(parents=True, exist_ok=True)
    store.save('nzbget', {'url': url, 'username': user, 'password': password, 'category': category})
    return {'ok': True, **settings(config)}


def request(config, method, *, nzb_url=None, transport=None):
    values = _values(config)
    if not settings(config)['configured']:
        raise ValueError('Configure NZBGet first.')
    params = ['', nzb_url, values.get('category', ''), 0, False, False, '', 0, 'SCORE'] if method == 'append' else []
    try:
        result = download_provider_http.post(download_provider_http.endpoint(values['url'], 'jsonrpc'),
            json={'method': method, 'params': params, 'id': 1},
            auth=httpx.BasicAuth(values['username'], values['password']), transport=transport)
        if result.get('error') or result.get('id') != 1:
            raise ValueError('NZBGet rejected the request.')
        value = result.get('result')
        if method == 'append':
            if type(value) is not int or value <= 0:
                raise ValueError('NZBGet did not accept the NZB.')
            return {'ok': True, 'ids': [value]}
        if not isinstance(value, str) or not value:
            raise ValueError('NZBGet authentication could not be verified.')
        return {'ok': True}
    except (httpx.HTTPError, ValueError, TypeError):
        raise ValueError('Check the NZBGet server URL, username, password and connection.') from None
