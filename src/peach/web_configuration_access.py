"""配置页与渠道设置共用的管理请求边界。"""
import ipaddress
import os

from fastapi import HTTPException, Request

from . import distribution, tunnel


def managed_configuration():
    return (distribution.standalone() or os.environ.get('PEACH_TRAY_MANAGED') == '1'
            or os.environ.get('PEACH_HEADLESS_MANAGED') == '1')


def tunnel_forwarded(request):
    return tunnel.from_edge(getattr(request.app.state, 'tunnel', None), request.headers)


def local_client(request: Request):
    """桌面限本机，Docker 允许已登录私网客户端，拒绝代理转发。"""
    if not request.client or tunnel_forwarded(request):
        return False
    server = request.scope.get('server')
    try:
        peer = ipaddress.ip_address(request.client.host)
        bound = ipaddress.ip_address(server[0]) if server else None
    except ValueError:
        bound = None
        try:
            peer = ipaddress.ip_address(request.client.host)
        except ValueError:
            return False
    if os.environ.get('PEACH_HEADLESS_MANAGED') == '1':
        if any(header.startswith('x-forwarded-') or header in {'forwarded', 'cf-connecting-ip'}
               for header in request.headers):
            return False
        return peer.is_loopback or (peer.is_private and not any((
            peer.is_link_local, peer.is_reserved, peer.is_unspecified, peer.is_multicast,
        )))
    if not peer.is_loopback and (peer != bound or peer.is_unspecified):
        return False
    if managed_configuration():
        name = request.app.state.settings.mdns_name.lower().removesuffix('.local')
        hosts = {'127.0.0.1', 'localhost', '::1', f'{name}.local'}
        if bound and not bound.is_unspecified:
            hosts.add(str(bound))
        if (request.url.hostname or '').lower().rstrip('.') not in hosts:
            return False
    return True


def local_only(request: Request):
    if not local_client(request):
        raise HTTPException(403, '请在运行 Peach 的电脑上打开配置')
