"""已登录用户的 RSS 与 debrid 下载接口。"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from . import debrid_client, settings_file, web_feeds, web_rss
from .routes_auth import require_auth
from .web_configuration_access import local_only

router = APIRouter()


def _writable(request):
    if bool(getattr(getattr(request.app.state, 'sync', None), 'read_only', False)):
        raise HTTPException(403, 'This library is read-only.')


@router.get('/api/rss')
def rss(request: Request, offset: int = 0, limit: int = 20, _auth=Depends(require_auth)):
    return {**web_rss.snapshot(request.app.state.web_contract, max(0, min(offset, 100000)), max(1, min(limit, 100))),
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
