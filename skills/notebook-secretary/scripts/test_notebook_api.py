"""Isolated contract tests; never connect to the user's running notebook.

Invariant: the secretary client only talks to an explicit numeric loopback origin,
cannot impersonate a human, and cannot mutate without an explicit apply flag.
Breaking inputs: https://example.com, /../confirm IDs, confirm:true / human actor,
duplicate JSON keys, NaN, oversized JSON, and a server redirect.
"""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from notebook_api import Client, ApiError, parse_json
except ImportError:
    Client = ApiError = parse_json = None



class SecretaryClientTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Client, 'bounded secretary API client is not implemented yet')

    def test_reject_remote_or_ambiguous_origins(self):
        for base in ['https://example.com', 'http://127.0.0.1:8876' + '@evil.test',
                     'http://127.0.0.1:8876/path', 'http://127.0.0.1:8876?x=1']:
            with self.assertRaises(ValueError):
                Client(base)

    def test_reject_human_identity_or_acknowledgement_before_network(self):
        c = Client('http://127.0.0.1:1')
        for body in [{'confirm': True}, {'actor': {'name': '我', 'kind': 'human'}},
                     {'needsReview': False}]:
            with self.assertRaises(ValueError):
                c.write('create', dict(body, title='x', requestId='R-1'), apply=True)
        with self.assertRaises(ValueError):
            c.get('detail', '../confirm')
        with self.assertRaises(ValueError):
            c.write('confirm', {'requestId': 'R-1'}, apply=True)

    def test_reject_ambiguous_or_unbounded_json(self):
        for raw in ['{"title":"a","title":"b"}', '{"x":NaN}', '[' * 1500,
                    '"' + 'x' * (256 * 1024) + '"']:
            with self.assertRaises(ValueError):
                parse_json(raw)

    def test_no_apply_is_offline_preview(self):
        c = Client('http://127.0.0.1:1')
        p = c.write('create', {'title': '只预览', 'requestId': 'PREVIEW-1'})
        self.assertTrue(p['preview'])
        self.assertEqual(p['body']['actor'], {'name': 'AI秘书', 'kind': 'ai'})

    def test_redirect_is_not_followed(self):
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', 'http://example.com/private')
                self.end_headers()
            def log_message(self, *_): pass
        s = HTTPServer(('127.0.0.1', 0), Redirect)
        t = threading.Thread(target=s.serve_forever, daemon=True); t.start()
        try:
            with self.assertRaises(ApiError) as caught:
                Client('http://127.0.0.1:' + str(s.server_port)).get('health')
            self.assertEqual(caught.exception.status, 302)
        finally:
            s.shutdown(); s.server_close(); t.join()

    def test_cached_bootstrap_cannot_bypass_version_guard(self):
        class OldServer(BaseHTTPRequestHandler):
            posts = 0
            def do_GET(self):
                raw = json.dumps({'version': '3.legacy', 'csrfToken': 'fixture-only'}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(raw)
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                OldServer.posts += 1
                self.send_response(200); self.send_header('Content-Length', '2')
                self.end_headers(); self.wfile.write(b'{}')
            def log_message(self, *_): pass
        s = HTTPServer(('127.0.0.1', 0), OldServer)
        t = threading.Thread(target=s.serve_forever, daemon=True); t.start()
        try:
            c = Client('http://127.0.0.1:' + str(s.server_port))
            c.get('bootstrap')
            with self.assertRaises(ValueError):
                c.write('create', {'title': 'wrong version', 'requestId': 'OLD-1'}, apply=True)
            self.assertEqual(OldServer.posts, 0)
        finally:
            s.shutdown(); s.server_close(); t.join()


if __name__ == '__main__':
    unittest.main()
