"""公网订阅与下载流：逐跳校验地址，不向目标发送服务凭据。"""
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .http import public_https_url, resolves_publicly
from .user_agent import USER_AGENT


def web_url(value, *, resolve=False, https_only=False):
    url = str(value or '').strip()
    parts = urlsplit(url)
    if parts.scheme not in (('https',) if https_only else ('http', 'https')):
        raise ValueError('Use a public HTTP or HTTPS link.')
    if len(url) > 8192 or not public_https_url(urlunsplit(parts._replace(scheme='https'))):
        raise ValueError('Use a public HTTP or HTTPS link.')
    try:
        if parts.port not in (None, 80, 443):
            raise ValueError('Use a standard HTTP or HTTPS port.')
    except ValueError:
        raise ValueError('Use a standard HTTP or HTTPS port.') from None
    if resolve and not resolves_publicly(parts.hostname):
        raise ValueError('The download host must resolve to public addresses.')
    return url


@contextmanager
def stream(client, url, *, headers=None, https_only=False):
    for _ in range(6):
        web_url(url, resolve=True, https_only=https_only)
        with client.stream('GET', url, headers={'User-Agent': USER_AGENT, **(headers or {})},
                           timeout=30, follow_redirects=False) as response:
            if response.status_code not in (301, 302, 303, 307, 308):
                yield response
                return
            location = response.headers.get('location')
            if not location:
                raise ValueError('The download redirect is missing its target.')
            url = urljoin(url, location)
    raise ValueError('The download has too many redirects.')


def fetch(url, headers=None, *, https_only=False, limit=2 * 1024 * 1024):
    from .http import HttpResponse
    try:
        with httpx.Client() as client, stream(client, url, headers=headers, https_only=https_only) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > limit:
                    raise ValueError('The feed or torrent exceeds the response size limit.')
            return HttpResponse(response.status_code, dict(response.headers), bytes(body), str(response.url))
    except httpx.HTTPError:
        raise ValueError('The feed or download request failed. Try again later.') from None
