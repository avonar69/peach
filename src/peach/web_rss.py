"""RSS 来源、条目与下载队列的应用契约。"""
import json

from . import feeds, public_download_http, rss_feeds


def poll_source(contract, source):
    report = {'source': source['id'], 'name': source['name'] or 'RSS feed', 'ok': True, 'added': 0, 'codes': []}
    try:
        headers = {'Accept': 'application/rss+xml,application/atom+xml,application/xml,text/xml'}
        if source['etag']:
            headers['If-None-Match'] = source['etag']
        if source['last_modified']:
            headers['If-Modified-Since'] = source['last_modified']
        response = public_download_http.fetch(source['url'], headers)
        with contract.database.write_transaction() as connection:
            if response.status == 304:
                feeds.settle(connection, source['id'], error=None, interval_minutes=source['interval_minutes'])
                return {**report, 'not_modified': True}
            if response.status != 200:
                raise ValueError('The RSS feed could not be fetched.')
            result = rss_feeds.poll(connection, source, response.body)
            feeds.settle(connection, source['id'], error=None, interval_minutes=source['interval_minutes'],
                etag=response.headers.get('etag'), last_modified=response.headers.get('last-modified'),
                seen=result['seen'], new=result['added'], page_name=result['name'])
        report.update(added=result['added'], seen=result['seen'])
    except (ValueError, OSError):
        message = 'The RSS feed could not be fetched or parsed. Check its URL and try again.'
        with contract.database.write_transaction() as connection:
            feeds.settle(connection, source['id'], error=message, interval_minutes=source['interval_minutes'])
        report.update(ok=False, error=message)
    return report


def snapshot(contract, offset=0):
    from . import debrid_client, settings_file
    with contract.database.read_connection() as connection:
        sources = [row for row in feeds.sources(connection) if row['kind'] == 'rss']
    return {**rss_feeds.items(contract.database, offset=offset), 'sources': sources,
            **debrid_client.settings(settings_file.active()), 'jobs': contract.debrid.snapshot()}


def source_action(contract, body):
    action = body.get('action')
    with contract.database.write_transaction() as connection:
        if action == 'add':
            url = public_download_http.web_url(body.get('url'))
            return {'id': feeds.add_source(connection, url=url, name=str(body.get('name') or 'RSS feed')[:200], kind='rss')}
        identity = body.get('id')
        if type(identity) is not int or identity <= 0:
            raise ValueError('Choose an RSS feed.')
        row = connection.execute("SELECT id FROM feed_source WHERE id=? AND kind='rss'", (identity,)).fetchone()
        if not row:
            raise ValueError('Choose an RSS feed.')
        if action == 'remove':
            feeds.remove_source(connection, identity)
        elif action == 'enabled' and type(body.get('enabled')) is bool:
            feeds.set_enabled(connection, identity, body['enabled'])
        else:
            raise ValueError('Choose a valid RSS feed action.')
    return {'ok': True}


def resolve(contract, body):
    identity, index = body.get('entry_id'), body.get('link_index')
    if type(identity) is not int or type(index) is not int or index < 0:
        raise ValueError('Choose an RSS download link.')
    with contract.database.read_connection() as connection:
        row = connection.execute("SELECT i.download_links_json FROM feed_item i JOIN feed_source s ON s.id=i.source_id "
            "WHERE i.id=? AND s.kind='rss'", (identity,)).fetchone()
    links = json.loads(row[0]) if row else []
    if index >= len(links):
        raise ValueError('Choose an RSS download link.')
    job = contract.debrid.submit(identity, links[index], str(body.get('provider') or ''))
    return {'ok': True, 'id': job['id']}
