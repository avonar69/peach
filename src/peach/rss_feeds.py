"""RSS/Atom 下载条目复用订阅调度、来源和条目去重。"""
import calendar
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser

from . import feeds
from .public_download_http import web_url

KIND = 'rss'
VISIBLE = "s.kind='rss' AND i.rss_expired_at IS NULL AND i.rss_merged_into IS NULL"


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.anchor = None
        self.images = []
        self.preview = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.links.extend(value for name, value in attrs if name == 'href' and value)
            self.anchor = dict(attrs).get('href')
        elif tag.lower() == 'img' and len(self.images) < 100:
            values = dict(attrs)
            self.images.append({'src': values.get('src') or values.get('data-src'), 'href': self.anchor,
                                'preview': self.preview, 'width': values.get('width'), 'height': values.get('height')})

    def handle_endtag(self, tag):
        if tag.lower() == 'a':
            self.anchor = None

    def handle_data(self, data):
        if re.fullmatch(r'\s*(?:previews?|screenshots?)\s*:\s*', data, re.I):
            self.preview = True
        elif re.fullmatch(r'\s*(?:downloads?|download links|links|info|information)\s*:\s*', data, re.I):
            self.preview = False
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


def _content(item):
    html = _Anchors()
    # 完整正文优先，使摘要中的重复缩略图不占用主图位置。
    for content in item.get('content', [])[:5]:
        html.feed(str(content.get('value') or '')[:100_000])
    html.feed(str(item.get('summary') or '')[:100_000])
    return html


def _images(item, html, base):
    found, previews, seen = {}, [], set()
    candidates = html.images + [{'src': row.get('url')} for row in item.get('media_thumbnail', [])[:5]]
    for row in candidates:
        if not str(row.get('src') or '').strip():
            continue
        try:
            src = web_url(urljoin(base, str(row.get('src') or '')))
            href = web_url(urljoin(base, str(row.get('href') or src)))
        except ValueError:
            continue
        width, height = str(row.get('width') or ''), str(row.get('height') or '')
        if width.isdigit() and height.isdigit() and max(int(width[:6]), int(height[:6])) <= 32:
            continue
        identity = (src, href)
        if identity in seen:
            continue
        image = {'src': src, 'href': href}
        if row.get('preview'):
            previews.append(image)
        elif 'main' not in found:
            found['main'] = image
        else:
            continue
        seen.add(identity)
    return {**found, 'previews': previews}


def _links(item, base, html):
    candidates = [(link.get('href'), link.get('type', '')) for link in item.get('links', [])]
    candidates.extend((link.get('href'), link.get('type', '')) for link in item.get('enclosures', []))
    candidates.extend((url, '') for url in html.links)
    image_links = {urljoin(base, str(row[field])) for row in html.images for field in ('src', 'href') if row.get(field)}
    found = {}
    for url, kind in candidates[:300]:
        if urljoin(base, str(url or '')) in image_links or kind.startswith('image/'):
            continue
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
        html = _content(item)
        links = _links(item, url, html)
        key = str(item.get('id') or item.get('link') or title)[:4096]
        published = item.get('published_parsed') or item.get('updated_parsed')
        try:
            date = datetime.fromtimestamp(calendar.timegm(published), timezone.utc).isoformat() if published else None
        except (ValueError, OverflowError, OSError):
            date = None
        rows.append({'key': hashlib.sha256(key.encode()).hexdigest(), 'title': title,
                     'post_url': item.get('link'),
                     'link': next((link['url'] for link in links if link['kind'] == 'link'), None),
                     'published_at': date, 'links': links, 'images': _images(item, html, url)})
    return str(document.feed.get('title') or '')[:200], rows


def _identities(key, url):
    values = ['key:' + key]
    try:
        parts = urlsplit(web_url(url))
        address = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/') or '/', parts.query, ''))
        values.append('url:' + hashlib.sha256(address.encode()).hexdigest())
    except (ValueError, TypeError):
        pass
    return values


def _remember(connection, source_id, item_id, identities):
    connection.executemany('INSERT OR IGNORE INTO rss_item_identity(source_id,identity,item_id) VALUES(?,?,?)',
                           [(source_id, value, item_id) for value in identities])


def _seed_identities(connection, source_id):
    rows = connection.execute('SELECT id,item_key,link FROM feed_item i WHERE source_id=? '
        'AND rss_merged_into IS NULL AND NOT EXISTS(SELECT 1 FROM rss_item_identity a WHERE a.item_id=i.id)', (source_id,)).fetchall()
    for row in rows:
        _remember(connection, source_id, row['id'], _identities(row['item_key'], row['link']))


def _combined(rows, field, incoming, limit):
    values = []
    for row in rows:
        values.extend(json.loads(row[field]))
    return list({value['url']: value for value in [*values, *incoming]}.values())[:limit]


def _combined_images(rows, incoming):
    main, previews = None, {}
    for value in [*(json.loads(row['rss_images_json']) for row in rows), incoming]:
        main = value.get('main') or main
        previews.update({(item['src'], item['href']): item for item in value.get('previews', [])})
    return {**({'main': main} if main else {}), 'previews': list(previews.values())[:100]}


def _save_item(connection, source_id, row):
    identities = _identities(row['key'], row['post_url'])
    marks = ','.join('?' * len(identities))
    existing = connection.execute('SELECT * FROM feed_item WHERE source_id=? AND '
        f'(item_key=? OR id IN(SELECT item_id FROM rss_item_identity WHERE source_id=? AND identity IN({marks}))) '
        'AND rss_merged_into IS NULL ORDER BY id', (source_id, row['key'], source_id, *identities)).fetchall()
    added = not existing
    if added:
        entry = feeds.FeedEntry(row['key'], row['title'], row['link'], row['published_at'])
        feeds.record_entry(connection, source_id, entry, code=None)
        existing = connection.execute('SELECT * FROM feed_item WHERE source_id=? AND item_key=?',
                                       (source_id, row['key'])).fetchall()
    target = existing[0]
    target_id = target['id']
    expired = next((item['rss_expired_at'] for item in existing if item['rss_expired_at']), None)
    for duplicate in existing[1:]:
        connection.execute('UPDATE rss_item_identity SET item_id=? WHERE item_id=?', (target_id, duplicate['id']))
        connection.execute("UPDATE feed_item SET rss_merged_into=?,title=NULL,link=NULL,download_links_json='[]',rss_images_json='{}' WHERE id=?",
                           (target_id, duplicate['id']))
    _remember(connection, source_id, target_id, identities)
    first_seen = min(item['first_seen'] for item in existing)
    if expired:
        connection.execute("UPDATE feed_item SET rss_expired_at=?,first_seen=?,title=NULL,link=NULL,published_at=NULL,download_links_json='[]',rss_images_json='{}' WHERE id=?",
                           (expired, first_seen, target_id))
    else:
        connection.execute('UPDATE feed_item SET title=?,link=COALESCE(?,link),published_at=COALESCE(?,published_at),'
            'first_seen=?,download_links_json=?,rss_images_json=? WHERE id=?',
            (row['title'], row['link'], row['published_at'], first_seen,
             json.dumps(_combined(existing, 'download_links_json', row['links'], 50)),
             json.dumps(_combined_images(existing, row['images'])), target_id))
    return int(added)


def retention_cutoff(now, count, unit):
    if unit == 'days':
        return now - timedelta(days=count)
    months = count * (12 if unit == 'years' else 1)
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    return now.replace(year=year, month=month + 1, day=min(now.day, calendar.monthrange(year, month + 1)[1]))


def expire(connection, *, now=None, source_id=None):
    """到期正文清退，最小身份记忆继续阻止重复条目重新出现。"""
    now = now or datetime.now(timezone.utc)
    query = "SELECT id,rss_retention_count,rss_retention_unit FROM feed_source WHERE kind='rss' AND rss_retention_count IS NOT NULL"
    params = ()
    if source_id is not None:
        query += ' AND id=?'
        params = (source_id,)
    removed = 0
    for source in connection.execute(query, params).fetchall():
        _seed_identities(connection, source['id'])
        cutoff = retention_cutoff(now, source['rss_retention_count'], source['rss_retention_unit'])
        removed += connection.execute("UPDATE feed_item SET rss_expired_at=?,title=NULL,link=NULL,published_at=NULL,download_links_json='[]',rss_images_json='{}' "
            'WHERE source_id=? AND rss_expired_at IS NULL AND rss_merged_into IS NULL AND julianday(first_seen)<=julianday(?)',
            (feeds.stamp(now), source['id'], feeds.stamp(cutoff))).rowcount
    return removed


def poll(connection, source, body):
    name, rows = parse(body, source['url'])
    _seed_identities(connection, source['id'])
    expire(connection, source_id=source['id'])
    added = sum(_save_item(connection, source['id'], row) for row in rows)
    return {'name': name, 'seen': len(rows), 'added': added}


def count_items(database):
    with database.read_connection() as connection:
        return connection.execute(f"SELECT count(*) FROM feed_item i JOIN feed_source s ON s.id=i.source_id WHERE {VISIBLE}").fetchone()[0]


def items(database, *, offset=0, limit=20):
    with database.read_connection() as connection:
        result = [dict(row) for row in connection.execute(
            "SELECT i.id,i.source_id,i.title,i.link,i.published_at,i.first_seen,i.download_links_json,i.rss_images_json,s.name AS feed_name "
            f"FROM feed_item i JOIN feed_source s ON s.id=i.source_id WHERE {VISIBLE} "
            'ORDER BY COALESCE(i.published_at,i.first_seen) DESC,i.id DESC LIMIT ? OFFSET ?', (limit, offset))]
        total = connection.execute(f"SELECT count(*) FROM feed_item i JOIN feed_source s ON s.id=i.source_id WHERE {VISIBLE}").fetchone()[0]
    for row in result:
        row['links'] = json.loads(row.pop('download_links_json'))
        row['images'] = json.loads(row.pop('rss_images_json'))
    return {'items': result, 'total': total, 'offset': offset}
