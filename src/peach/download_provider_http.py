"""用户配置的下载服务端点与有界 JSON 响应。"""
import json
from urllib.parse import urlsplit, urlunsplit

import httpx


def endpoint(value, suffix):
    parts = urlsplit(str(value or '').strip())
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or any(ord(char) < 32 for char in str(value))):
        raise ValueError('Invalid download server URL.')
    path = parts.path.rstrip('/')
    return urlunsplit((parts.scheme, parts.netloc, path if path.endswith('/' + suffix) else path + '/' + suffix, '', ''))


def post(url, *, transport=None, **kwargs):
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False, transport=transport) as client:
        with client.stream('POST', url, **kwargs) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 1_000_000:
                    raise ValueError('Oversized download server response.')
                chunks.append(chunk)
            result = json.loads(b''.join(chunks))
    if not isinstance(result, dict):
        raise ValueError('Invalid download server response.')
    return result
