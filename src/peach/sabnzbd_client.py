"""SABnzbd 官方 API；凭据仅保存在本机，NZB 地址通过表单提交。"""
import httpx

from . import download_provider_http
from .follow_secrets import CredentialStore


def _store(config):
    return CredentialStore(config.directory('secrets'))


def _values(config):
    saved = _store(config).load('sabnzbd')
    return saved.values if saved else {}


def _endpoint(value):
    return download_provider_http.endpoint(value, 'api')


def settings(config):
    values = _values(config)
    return {'url': values.get('url', ''), 'category': values.get('category', ''),
            'configured': bool(values.get('url') and values.get('api_key'))}


def save(config, body):
    values = _values(config)
    url = _endpoint(body.get('url'))
    category = str(body.get('category') or '').strip()
    key = '' if body.get('remove_key') is True else str(body.get('api_key') or values.get('api_key') or '').strip()
    if len(category) > 100 or any(ord(char) < 32 for char in category + key):
        raise ValueError('Check the SABnzbd category and API key.')
    store = _store(config)
    store.root.mkdir(parents=True, exist_ok=True)
    store.save('sabnzbd', {'url': url, 'category': category, 'api_key': key})
    return {'ok': True, **settings(config)}


def request(config, mode, *, nzb_url=None, title='', transport=None):
    values = _values(config)
    if not values.get('api_key'):
        raise ValueError('Configure SABnzbd first.')
    data = {'mode': mode, 'apikey': values['api_key'], 'output': 'json'}
    if mode == 'addurl':
        data.update(name=nzb_url, nzbname=title[:1000], cat=values.get('category', ''), priority='-100', pp='-1')
    else:
        data.update(start='0', limit='1')
    try:
        result = download_provider_http.post(_endpoint(values.get('url')), data=data, transport=transport)
        if not isinstance(result, dict) or result.get('status') is False:
            raise ValueError('SABnzbd rejected the request.')
        if mode == 'addurl':
            ids = result.get('nzo_ids')
            if result.get('status') is not True or not isinstance(ids, list) or not ids:
                raise ValueError('SABnzbd did not accept the NZB.')
            return {'ok': True, 'ids': ids}
        if not isinstance(result.get('queue'), dict):
            raise ValueError('SABnzbd authentication could not be verified.')
        return {'ok': True}
    except (httpx.HTTPError, ValueError, TypeError):
        raise ValueError('Check the SABnzbd server URL, API key and connection.') from None
