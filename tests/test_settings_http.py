"""Settings server (I8): token, Host allowlist, save flow, limits, fonts."""

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.support import AppTree

TOKEN = "test-token-1234567890"


class SettingsHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.s = cls.tree.load("settings")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.s.make_handler(cls.s.State(), TOKEN))
        cls.server.daemon_threads = True
        cls.server.handle_error = lambda request, address: None   # C35 traceback noise
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tree.close()

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host if host is not None else f"127.0.0.1:{self.port}")
            for k, v in (headers or {}).items():
                conn.putheader(k, v)
            data = body.encode("utf-8") if isinstance(body, str) else body
            if data is not None:
                conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data)
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()

    def save(self, data, token=TOKEN, host=None):
        return self.request("POST", "/api/save", json.dumps(data),
                            {"X-Token": token, "Content-Type": "application/json"}, host=host)

    # ---- page and auth ----

    def test_page_needs_token(self):
        self.assertEqual(self.request("GET", "/")[0], 403)
        self.assertEqual(self.request("GET", "/?t=wrong")[0], 403)
        status, headers, body = self.request("GET", f"/?t={TOKEN}")
        self.assertEqual(status, 200)
        self.assertIn(b"AI-Hotkeys Settings", body)        # title main.ahk relies on (S8b1)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")

    def test_bad_host_is_rejected(self):
        for host in ("evil.example", "127.0.0.1.evil.example", "localhost.evil.example", "", "[::1]"):
            with self.subTest(host=host):
                self.assertEqual(self.request("GET", f"/?t={TOKEN}", host=host)[0], 403)
                self.assertEqual(self.save({"aspetto.tema": "nero"}, host=host)[0], 403)

    def test_ping_needs_header_token(self):
        self.assertEqual(self.request("GET", "/api/ping")[0], 403)
        self.assertEqual(self.request("GET", f"/api/ping?t={TOKEN}")[0], 403)   # query token is not enough
        self.assertEqual(self.request("GET", "/api/ping", headers={"X-Token": TOKEN})[0], 200)

    def test_save_without_token_is_rejected_and_writes_nothing(self):
        before = self.tree.config_file.read_bytes()
        self.assertEqual(self.save({"aspetto.tema": "nero"}, token="nope")[0], 403)
        self.assertEqual(self.tree.config_file.read_bytes(), before)

    def test_save_valid_updates_config(self):
        status, _, body = self.save({"aspetto.colore": "menta"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["values"]["aspetto.colore"], "menta")
        self.assertIn("colore = menta", self.tree.config_file.read_text(encoding="utf-8"))

    def test_save_invalid_returns_422(self):
        status, _, body = self.save({"aspetto.tema": "rosa"})
        self.assertEqual(status, 422)
        self.assertIn("aspetto.tema", json.loads(body)["errors"])

    def test_bad_bodies_return_400(self):
        self.assertEqual(self.request("POST", "/api/save", "not json", {"X-Token": TOKEN})[0], 400)
        self.assertEqual(self.request("POST", "/api/save", "[1, 2]", {"X-Token": TOKEN})[0], 400)
        self.assertEqual(self.request("POST", "/api/save", b"", {"X-Token": TOKEN})[0], 400)

    def test_unknown_paths_and_methods(self):
        self.assertEqual(self.request("GET", "/nope")[0], 404)
        self.assertEqual(self.request("POST", "/api/other", "{}", {"X-Token": TOKEN})[0], 404)
        status, headers, _ = self.request("OPTIONS", "/api/save", headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 501)
        self.assertFalse(any(k.lower().startswith("access-control") for k in headers))

    def test_fonts(self):
        status, headers, _ = self.request("GET", "/fonts/ibm-plex-sans-latin-400-normal.woff2")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "font/woff2")
        for bad in ("/fonts/../config.ini", "/fonts/..%2fconfig.ini", "/fonts/missing.woff2"):
            with self.subTest(path=bad):
                self.assertEqual(self.request("GET", bad)[0], 404)

    # ---- known defects: flipped by step S7 ----

    @unittest.expectedFailure
    def test_C35_non_ascii_token_gets_403_instead_of_a_dropped_connection(self):
        """C35: compare_digest raises TypeError on non-ASCII str, killing the handler."""
        self.assertEqual(self.request("GET", "/api/ping", headers={"X-Token": "é"})[0], 403)

    @unittest.expectedFailure
    def test_C10_page_sends_content_security_policy(self):
        """C10: no CSP header on HTML responses."""
        _, headers, _ = self.request("GET", f"/?t={TOKEN}")
        self.assertIn("Content-Security-Policy", headers)


if __name__ == "__main__":
    unittest.main()
