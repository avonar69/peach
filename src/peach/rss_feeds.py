"""RSS/Atom 下载条目复用订阅调度、来源和条目去重。"""
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser

from . import feeds
from .public_download_http import web_url

KIND = 'rss'


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.links.extend(value for name, value in attrs if name == 'href' and value)

    def handle_data(self, data):
        self.links.extend(re.findall(r'''(?:https?://|magnet:\?)[^\s<>"']+''', data))


def _link(url, base, media_type=''):
    address = urljoin(base, str(url or '').strip())
    if address.startswith('magnet:?'):
        from .downloads import parse_magnet
        try:
            parse_magnet(address)
        except (ValueError, TypeError):
            return None
        return {'url': address, 'kind': 'magnet'}
    try:
        web_url(address)
    except ValueError:
        return None
    torrent = 'bittorrent' in media_type or urlsplit(address).path.lower().endswith('.torrent')
    return {'url': address, 'kind': 'torrent' if torrent else 'link'}


def _links(item, base):
    candidates = [(link.get('href'), link.get('type', '')) for link in item.get('links', [])]
    candidates.extend((link.get('href'), link.get('type', '')) for link in item.get('enclosures', []))
    html = _Anchors()
    html.feed(str(item.get('summary') or '')[:100_000])
    for content in item.get('content', [])[:5]:
        html.feed(str(content.get('value') or '')[:100_000])
    candidates.extend((url, '') for url in html.links)
    found = {}
    for url, kind in candidates[:300]:
        link = _link(url, base, kind)
        if link:
            found.setdefault(link['url'], link)
    return list(found.values())[:50]


def parse(body, url):
    # 只传字节，feedparser 不负责网络；DTD 与外部实体在入口拒绝。
    declarations = body.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in declarations or b'<!ENTITY' in declarations:
        raise ValueError('Feeds containing DTDs or entities are not supported.')
    document = feedparser.parse(body)
    if not document.get('version'):
        raise ValueError('This address did not return an RSS or Atom feed.')
    rows = []
    for item in document.entries[:feeds.MAX_ENTRIES]:
        title = str(item.get('title') or 'Untitled item')[:1000]
        links = _links(item, url)
        key = str(item.get('id') or item.get('link') or title)[:4096]
        published = item.get('published_parsed') or item.get('updated_parsed')
        try:
            date = datetime.fromtimestamp(calendar.timegm(published), timezone.utc).isoformat() if published else None
        except (ValueError, OverflowError, OSError):
            date = None
        rows.append({'key': hashlib.sha256(key.encode()).hexdigest(), 'title': title,
                     'link': next((link['url'] for link in links if link['kind'] == 'link'), None),
                     'published_at': date, 'links': links})
    return str(document.feed.get('title') or '')[:200], rows


def poll(connection, source, body):
    name, rows = parse(body, source['url'])
    added = 0
    for row in rows:
        entry = feeds.FeedEntry(row['key'], row['title'], row['link'], row['published_at'])
        added += feeds.record_entry(connection, source['id'], entry, code=None)
        connection.execute('UPDATE feed_item SET title=?,link=?,published_at=?,download_links_json=? '
            'WHERE source_id=? AND item_key=?', (row['title'], row['link'], row['published_at'],
            json.dumps(row['links']), source['id'], row['key']))
    return {'name': name, 'seen': len(rows), 'added': added}


def items(database, *, offset=0):
    with database.read_connection() as connection:
        result = [dict(row) for row in connection.execute(
            "SELECT i.id,i.source_id,i.title,i.link,i.published_at,i.first_seen,i.download_links_json,s.name AS feed_name "
            "FROM feed_item i JOIN feed_source s ON s.id=i.source_id WHERE s.kind='rss' "
            'ORDER BY COALESCE(i.published_at,i.first_seen) DESC,i.id DESC LIMIT 50 OFFSET ?', (offset,))]
        total = connection.execute("SELECT count(*) FROM feed_item i JOIN feed_source s ON s.id=i.source_id WHERE s.kind='rss'").fetchone()[0]
    for row in result:
        row['links'] = json.loads(row.pop('download_links_json'))
    return {'items': result, 'total': total, 'offset': offset}
