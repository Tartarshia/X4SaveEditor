import gzip
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

import web_server


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = web_server.make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_address[1])
        cls.token = cls.call('/api/session')['token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.state.close()
        cls.server.server_close()
        cls.thread.join(2)

    @classmethod
    def call(cls, path, data=None, headers=None, raw=False):
        h = {'X-X4-Token': getattr(cls, 'token', '')}
        if headers:
            h.update(headers)
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            h['Content-Type'] = 'application/json'
        request = urllib.request.Request(cls.base+path, data=data, headers=h)
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            return body if raw else json.loads(body)

    def job(self, action, **kwargs):
        response = self.call('/api/jobs', {'action': action, **kwargs})
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            result = self.call('/api/job?id='+response['id'])
            if result['status'] == 'error':
                self.fail(result['error'])
            if result['status'] == 'done':
                return result['result']
            time.sleep(.03)
        self.fail('Job timed out')

    def test_roundtrip_upload_page_edit_download(self):
        xml = ('<savegame><player name="测试 &amp; 保留" money="42"/>' + '<item/>'*450 + '</savegame>').encode()
        result = self.call('/api/upload?name=test.xml.gz', gzip.compress(xml))
        source = Path(result['path'])
        original = source.read_bytes()
        opened = self.job('open', path=str(source))
        revision = opened['revision']
        rows = self.job('query', revision=revision, mode='tag', value='item')
        self.assertEqual(len(rows), 201)
        next_rows = self.job('query', revision=revision, mode='tag', value='item', after=rows[199][0])
        self.assertEqual(next_rows[0][0], rows[200][0])
        details = self.job('details', revision=revision, node=2)
        self.assertEqual(details[0]['name'], '测试 & 保留')
        exported = self.job('export', revision=revision, changes={'2': {'money': '999'}}, name='edited.xml.gz')
        payload = gzip.decompress(self.call(exported['url'], raw=True))
        self.assertEqual(payload, xml.replace(b'money="42"', b'money="999"'))
        self.assertEqual(source.read_bytes(), original)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('/api/jobs', {'action': 'details', 'node': 2, 'revision': 'stale'})
        self.assertEqual(error.exception.code, 400)

    def test_cross_origin_and_token_rejected(self):
        for headers in [{'X-X4-Token': 'wrong'}, {'Origin': 'https://example.com'}, {'Host': 'example.com'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/api/saves', headers=headers)
            self.assertEqual(error.exception.code, 403)

    def test_no_arbitrary_static_file_or_download(self):
        for path in ['/../LICENSE', '/api/download?id=missing']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call(path)
            self.assertEqual(error.exception.code, 404)

    def test_upload_path_traversal_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('/api/upload?name=..%2Foutside.xml', b'<savegame/>')
        self.assertEqual(error.exception.code, 400)

    def test_second_server_cannot_bind_same_port(self):
        with self.assertRaises(OSError):
            server = web_server.LocalHTTPServer(self.server.server_address, web_server.Handler)
            server.server_close()


if __name__ == '__main__':
    unittest.main()
