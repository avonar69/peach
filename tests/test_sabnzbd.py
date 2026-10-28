"""使用临时凭据、脱敏 NZB 与假 HTTP 响应验证下载交接。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx

from peach import nzbget_client, rss_feeds, sabnzbd_client


class SABnzbdTests(unittest.TestCase):
    def test_nzbget_rpc_authenticates_without_credentials_in_url_and_preserves_signed_url(self):
        import base64
        import json
        with tempfile.TemporaryDirectory() as directory:
            config = SimpleNamespace(directory=lambda _: Path(directory))
            saved = nzbget_client.save(config, {'url': 'http://nzbget:6789/base', 'username': 'demo',
                'password': 'example-password', 'category': 'movies'})
            self.assertTrue(saved['configured'])
            self.assertNotIn('password', saved)
            kept = nzbget_client.save(config, {'url': 'http://nzbget:6789/base', 'username': 'demo', 'password': '', 'category': 'movies'})
            self.assertTrue(kept['configured'])

            def handle(request):
                self.assertEqual(str(request.url), 'http://nzbget:6789/base/jsonrpc')
                self.assertEqual(request.headers['authorization'], 'Basic ' + base64.b64encode(b'demo:example-password').decode())
                body = json.loads(request.content)
                if body['method'] == 'version':
                    self.assertEqual(body['params'], [])
                    return httpx.Response(200, json={'id': 1, 'result': '25.4'})
                self.assertEqual(body['params'], ['', 'https://example.org/release.nzb?key=example', 'movies', 0, False, False, '', 0, 'SCORE'])
                return httpx.Response(200, json={'id': 1, 'result': 123})

            transport = httpx.MockTransport(handle)
            self.assertTrue(nzbget_client.request(config, 'version', transport=transport)['ok'])
            self.assertEqual(nzbget_client.request(config, 'append', nzb_url='https://example.org/release.nzb?key=example', transport=transport)['ids'], [123])
            for response in ({'id': 1, 'result': 0}, {'id': 1, 'result': True}, {'id': 1, 'error': {'message': 'private-error'}}, {'id': 2, 'result': 123}):
                with self.subTest(response=response), self.assertRaisesRegex(ValueError, '^Check the NZBGet server URL, username, password and connection.$'):
                    nzbget_client.request(config, 'append', nzb_url='https://example.org/demo.nzb', transport=httpx.MockTransport(lambda _, payload=response: httpx.Response(200, json=payload)))
            nzbget_client.save(config, {'url': 'http://nzbget:6789', 'username': 'demo', 'remove_key': True})
            self.assertFalse(nzbget_client.settings(config)['configured'])

    def test_signed_nzb_is_distinct_from_details_and_thumbnail(self):
        identity = 'a' * 40
        page = f'https://drunkenslug.com/details/{identity}'
        download = f'https://drunkenslug.com/getnzb/{identity}.nzb&i=123&r=example'
        body = f'''<rss version="2.0"><channel><title>DS</title><item>
        <title>Example.Release</title><guid>{page}</guid><link>{download.replace('&', '&amp;')}</link>
        <enclosure url="{download.replace('&', '&amp;')}" type="application/x-nzb"/>
        <description><![CDATA[<a href="https://drunkenslug.com/browse?t=1">Category</a>]]></description>
        </item></channel></rss>'''.encode()
        _, rows = rss_feeds.parse(body, 'https://drunkenslug.com/rss')
        self.assertEqual(rows[0]['link'], page)
        self.assertEqual(rows[0]['links'], [{'url': download, 'kind': 'nzb'}])
        self.assertEqual(rows[0]['images']['main'], {
            'src': f'https://drunkenslug.com/covers/sample/{identity}_thumb.jpg', 'href': page})
        _, rows = rss_feeds.parse(body.replace(b'drunkenslug.com/details/', b'example.org/details/'), 'https://drunkenslug.com/rss')
        self.assertNotIn('main', rows[0]['images'])

    def test_nzb_enclosure_classifies_download_api_without_filename_extension(self):
        body = b'''<rss version="2.0"><channel><title>Indexer</title><item><title>Example</title>
        <link>https://example.org/api?t=get&amp;id=example</link>
        <enclosure url="https://example.org/api?t=get&amp;id=example" type="application/x-nzb"/>
        </item></channel></rss>'''
        _, rows = rss_feeds.parse(body, 'https://example.org/rss')
        self.assertEqual(rows[0]['links'], [{'url': 'https://example.org/api?t=get&id=example', 'kind': 'nzb'}])

    def test_api_form_keeps_credentials_and_signed_link_out_of_request_url(self):
        with tempfile.TemporaryDirectory() as directory:
            config = SimpleNamespace(directory=lambda _: Path(directory))
            sabnzbd_client.save(config, {'url': 'http://sabnzbd:8080', 'api_key': 'demo-secret', 'category': 'movies'})
            saved = sabnzbd_client.save(config, {'url': 'http://sabnzbd:8080', 'category': 'movies', 'api_key': ''})
            self.assertTrue(saved['configured'])
            self.assertNotIn('api_key', saved)
            calls = []

            def handle(request):
                calls.append(request)
                form = parse_qs(request.content.decode())
                self.assertEqual(str(request.url), 'http://sabnzbd:8080/api')
                self.assertEqual(request.method, 'POST')
                self.assertEqual(form['apikey'], ['demo-secret'])
                if form['mode'] == ['queue']:
                    return httpx.Response(200, json={'queue': {'slots': []}})
                self.assertEqual(form['name'], ['https://example.org/movie.nzb?token=example'])
                self.assertEqual(form['cat'], ['movies'])
                return httpx.Response(200, json={'status': True, 'nzo_ids': ['SABnzbd_nzo_demo']})

            transport = httpx.MockTransport(handle)
            self.assertTrue(sabnzbd_client.request(config, 'queue', transport=transport)['ok'])
            result = sabnzbd_client.request(config, 'addurl', nzb_url='https://example.org/movie.nzb?token=example', transport=transport)
            self.assertEqual(result['ids'], ['SABnzbd_nzo_demo'])
            self.assertEqual(len(calls), 2)
            failed = httpx.MockTransport(lambda _: httpx.Response(200, json={'status': False, 'error': 'demo-secret'}))
            with self.assertRaisesRegex(ValueError, '^Check the SABnzbd server URL, API key and connection.$'):
                sabnzbd_client.request(config, 'queue', transport=failed)
            sabnzbd_client.save(config, {'url': 'http://sabnzbd:8080', 'remove_key': True})
            self.assertFalse(sabnzbd_client.settings(config)['configured'])

    def test_server_url_rejects_embedded_credentials_and_query(self):
        for url in ('ftp://example.org', 'http://user:password@example.org', 'http://example.org?apikey=example'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sabnzbd_client._endpoint(url)
