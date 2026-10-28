"""已登录用户的 RSS 与 debrid 下载接口。"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from . import debrid_client, nzbget_client, sabnzbd_client, settings_file, web_feeds, web_rss
from .routes_auth import require_auth
from .web_configuration_access import local_only

router = APIRouter()


def _writable(request):
    if bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False)):
        raise HTTPException(403, 'This library is read-only.')


@router.get('/api/rss')
def rss(request: Request, offset: int = 0, limit: int = 20, sources: str = '', _auth=Depends(require_auth)):
    selected = None
    if sources:
        if sources == 'none':
            selected = []
        elif len(sources) <= 2000 and all(value.isdecimal() and int(value) > 0 for value in sources.split(',')):
            selected = list(dict.fromkeys(map(int, sources.split(','))))
        else:
            raise HTTPException(400, 'Choose valid RSS feeds.')
    return {**web_rss.snapshot(request.app.state.web_contract, max(0, min(offset, 100000)), max(1, min(limit, 100)), selected),
        'read_only': bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False))}


@router.get('/api/rss/jobs')
def rss_jobs(request: Request, _auth=Depends(require_auth)):
    return {'jobs': request.app.state.web_contract.debrid.snapshot(),
        **debrid_client.settings(settings_file.active()),
        'read_only': bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False))}


@router.post('/api/rss/{action}')
def rss_action(request: Request, action: str, body: dict = Body(default_factory=dict), _auth=Depends(require_auth)):
    _writable(request)
    contract = request.app.state.web_contract
    try:
        if action == 'source':
            result = web_rss.source_action(contract, body)
            if body.get('action') == 'add':
                web_feeds._fetch_now(contract, [result['id']])
            return result
        if action == 'check':
            with contract.database.read_connection() as connection:
                ids = [row[0] for row in connection.execute("SELECT id FROM feed_source WHERE kind='rss'")]
            if not ids:
                return {'ok': True, 'checked': 0, 'added': 0}
            return web_feeds.w_feed_check(contract, {'sources': ids, 'background': True, 'rss_only': True})
        if action == 'resolve':
            return web_rss.resolve(contract, body)
        if action in ('sabnzbd', 'nzbget'):
            _, link = web_rss.download_link(contract, body)
            if link['kind'] != 'nzb':
                raise ValueError('Choose an NZB download link.')
            provider, method = (sabnzbd_client, 'addurl') if action == 'sabnzbd' else (nzbget_client, 'append')
            return provider.request(settings_file.active(), method, nzb_url=link['url'])
        if action == 'download':
            return {'ok': True, 'id': contract.debrid.download(str(body.get('id') or ''), body.get('file_index'))['id']}
        if action == 'cancel':
            return contract.debrid.cancel(str(body.get('id') or ''))
        if action == 'clear-finished':
            return contract.debrid.clear_finished()
        if action == 'import':
            return contract.debrid.retry_import(str(body.get('id') or ''))
        raise ValueError('Choose a valid RSS action.')
    except (ValueError, OSError):
        raise HTTPException(400, 'The RSS or download action could not be completed. Check the feed, provider and folder settings.') from None


@router.get('/api/configuration/debrid')
def debrid_settings(request: Request, _auth=Depends(require_auth)):
    local_only(request)
    return {**debrid_client.settings(settings_file.active()),
        'available': not bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False))}


@router.post('/api/configuration/debrid/{provider}/{action}')
def debrid_action(request: Request, provider: str, action: str, body: dict = Body(default_factory=dict), _auth=Depends(require_auth)):
    local_only(request)
    _writable(request)
    config = settings_file.active()
    try:
        if action == 'settings':
            return debrid_client.save(config, provider, body)
        if action == 'check':
            client = debrid_client.Client(config, provider)
            try:
                return client.check()
            finally:
                client.close()
        raise ValueError('Choose a valid debrid action.')
    except (ValueError, OSError):
        raise HTTPException(400, 'Check the debrid API key, account and download folder, then try again.') from None


def _nzb_provider(name):
    if name not in ('sabnzbd', 'nzbget'):
        raise HTTPException(404, 'Download provider not found.')
    return sabnzbd_client if name == 'sabnzbd' else nzbget_client


def _nzb_settings(request, provider):
    local_only(request)
    return {**_nzb_provider(provider).settings(settings_file.active()),
            'available': not bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False))}


def _nzb_action(request, provider, action, body):
    local_only(request)
    _writable(request)
    service = _nzb_provider(provider)
    try:
        if action == 'settings':
            return service.save(settings_file.active(), body)
        if action == 'check':
            return service.request(settings_file.active(), 'queue' if provider == 'sabnzbd' else 'version')
        raise ValueError('Choose a valid SABnzbd action.')
    except (ValueError, OSError):
        message = ('Check the SABnzbd server URL, API key and connection.' if provider == 'sabnzbd'
                   else 'Check the NZBGet server URL, username, password and connection.')
        raise HTTPException(400, message) from None


@router.get('/api/configuration/sabnzbd')
def sabnzbd_settings(request: Request, _auth=Depends(require_auth)):
    return _nzb_settings(request, 'sabnzbd')


@router.get('/api/configuration/nzbget')
def nzbget_settings(request: Request, _auth=Depends(require_auth)):
    return _nzb_settings(request, 'nzbget')


@router.post('/api/configuration/sabnzbd/{action}')
def sabnzbd_action(request: Request, action: str, body: dict = Body(default_factory=dict), _auth=Depends(require_auth)):
    return _nzb_action(request, 'sabnzbd', action, body)


@router.post('/api/configuration/nzbget/{action}')
def nzbget_action(request: Request, action: str, body: dict = Body(default_factory=dict), _auth=Depends(require_auth)):
    return _nzb_action(request, 'nzbget', action, body)
