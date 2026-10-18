"""SEC1: one canonical ASCII host for the SSRF guard's pinning, and a local-only SearXNG URL.

safe_url() turns IDN hosts into punycode and drops a trailing dot, and the URL handed
to curl is rebuilt from the checked parts. The curl_cffi RESOLVE key must name exactly
the host curl will look up, otherwise curl would resolve the name itself (DNS rebinding).
curl_cffi is replaced by a recording fake, so these tests run without searxng/lib.
"""

import sys
import time
import types
import unittest
import urllib.parse
from unittest import mock

from tests.support import AppTree, StaticPages

PAGE = ("<html><body><main><p>Il paragrafo principale della pagina di prova, "
        "abbastanza lungo da essere tenuto.</p></main></body></html>")
PAGE_BYTES = PAGE.encode()
PUBLIC = ["93.184.216.34"]


class _FakeResponse:
    def __init__(self, status=200, headers=None, body=PAGE_BYTES):
        self.status_code = status
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self._body = body

    def iter_content(self):
        yield self._body

    def close(self):
        pass


class _FakeCurl:
    """Records the curl options and the URL of every request."""

    def __init__(self, responses=None):
        self.calls = []          # (curl_options, url)
        self.responses = list(responses or [])

    def Session(self, curl_options=None):         # noqa: N802 (curl_cffi's name)
        fake = self

        class _Session:
            def get(self, url, **_kw):
                fake.calls.append((curl_options, url))
                return fake.responses.pop(0) if fake.responses else _FakeResponse()

            def close(self):
                pass

        return _Session()


def _fake_curl_module():
    mod = types.ModuleType("curl_cffi")
    mod.CurlOpt = types.SimpleNamespace(RESOLVE="RESOLVE", NOPROXY="NOPROXY")
    return mod


class IdnCanonicalHostTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def safe(self, url, answer=PUBLIC):
        with mock.patch.object(self.ws, "_resolve", return_value=answer) as res:
            target = self.ws.safe_url(url)
        return target, res

    def test_unicode_host_becomes_punycode_everywhere(self):
        t, res = self.safe("https://Bücher.example/straße?q=ü#frag")
        self.assertEqual(t.host, "xn--bcher-kva.example")
        res.assert_called_once_with("xn--bcher-kva.example", 443)
        self.assertEqual(urllib.parse.urlsplit(t.url).hostname, t.host)
        self.assertTrue(t.url.isascii())
        self.assertEqual(t.url, "https://xn--bcher-kva.example/stra%C3%9Fe?q=%C3%BC")
        self.assertEqual(t.path, "/stra%C3%9Fe?q=%C3%BC")

    def test_trailing_dot_is_stripped_consistently(self):
        t, res = self.safe("http://docs.example.com./x")
        self.assertEqual(t.host, "docs.example.com")
        res.assert_called_once_with("docs.example.com", 80)
        self.assertEqual(t.url, "http://docs.example.com/x")
        t2, _ = self.safe("https://bücher.example./")
        self.assertEqual((t2.host, t2.url), ("xn--bcher-kva.example", "https://xn--bcher-kva.example/"))

    def test_invalid_idn_and_dot_only_hosts_are_refused(self):
        for url in ("http://a..b/", "http://./", "http://" + "x" * 64 + ".com/", "http://\u00ad\u00ad/",
                    "http://exa mple.com/", "http://localhost./", "http://LOCALHOST/",
                    "http://app.localhost./"):
            with self.subTest(url=url):
                self.assertIsNone(self.safe(url)[0])

    def test_rebuilt_url_drops_credentials_free_parts_and_default_port(self):
        t, _ = self.safe("HTTPS://Example.COM:443/a/b?x=1#frag")
        self.assertEqual(t.url, "https://example.com/a/b?x=1")
        t6 = self.ws.safe_url("http://[2001:4860:4860::8888]/p")
        self.assertEqual((t6.host, t6.url), ("2001:4860:4860::8888", "http://[2001:4860:4860::8888]/p"))

    def test_curl_resolve_key_matches_the_requested_host(self):
        curl = _FakeCurl()
        with mock.patch.dict(sys.modules, {"curl_cffi": _fake_curl_module()}), \
                mock.patch.object(self.ws, "_resolve", return_value=PUBLIC):
            html, _ctype = self.ws._download_cffi(curl, "https://Bücher.example./seite", time.monotonic() + 5)
        self.assertIn("paragrafo principale", html)
        (options, url), = curl.calls
        (entry,) = options["RESOLVE"]
        host, port, ip = entry.rsplit(":", 2)
        self.assertTrue(entry.isascii())
        self.assertEqual(host, "xn--bcher-kva.example")
        self.assertEqual(host, urllib.parse.urlsplit(url).hostname)
        self.assertEqual((port, ip), ("443", PUBLIC[0]))
        self.assertEqual(url, "https://xn--bcher-kva.example/seite")
        self.assertEqual(options["NOPROXY"], "*")

    def test_curl_redirect_hop_is_pinned_with_its_own_ascii_host(self):
        curl = _FakeCurl([_FakeResponse(302, {"location": "http://Ünï.example./b"}), _FakeResponse()])
        with mock.patch.dict(sys.modules, {"curl_cffi": _fake_curl_module()}), \
                mock.patch.object(self.ws, "_resolve", return_value=PUBLIC):
            self.ws._download_cffi(curl, "https://first.example/a", time.monotonic() + 5)
        self.assertEqual(len(curl.calls), 2)
        for options, url in curl.calls:
            host = options["RESOLVE"][0].rsplit(":", 2)[0]
            self.assertEqual(host, urllib.parse.urlsplit(url).hostname)
        self.assertEqual(curl.calls[1][1], "http://" + "ünï.example".encode("idna").decode() + "/b")

    def test_stdlib_sni_uses_the_ascii_host(self):
        seen = {}

        class _Ctx:
            def wrap_socket(self, sock, server_hostname=None):
                seen["sni"] = server_hostname
                raise OSError("stop here")

        t, _ = self.safe("https://bücher.example./")
        with mock.patch.object(self.ws.socket, "create_connection", return_value=mock.MagicMock()), \
                mock.patch.object(self.ws, "_ssl_context", return_value=_Ctx()), \
                self.assertRaises(OSError):
            self.ws._open_pinned(t, time.monotonic() + 5)
        self.assertEqual(seen["sni"], "xn--bcher-kva.example")


class IdnStdlibHostHeaderTest(unittest.TestCase):
    """End to end over the standard-library path: the Host header carries the ASCII host."""

    @classmethod
    def setUpClass(cls):
        cls.pages = StaticPages({"/page": (200, "text/html", PAGE)})
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")
        cls.ws._cffi_requests = False

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()
        cls.pages.close()

    def test_host_header_is_punycode_without_trailing_dot(self):
        url = f"http://bücher.test.:{self.pages.port}/page"
        with mock.patch.object(self.ws, "_TEST_LOOPBACK_PORTS", frozenset({self.pages.port})), \
                mock.patch.object(self.ws, "_resolve", return_value=["127.0.0.1"]) as res, \
                mock.patch.object(self.ws, "_cffi", return_value=None):
            text = self.ws.fetch_page_text(url)
        self.assertIn("paragrafo principale", text)
        res.assert_called_with("xn--bcher-kva.test", self.pages.port)
        headers = self.pages.requests[-1][2]
        host_header = {k.lower(): v for k, v in headers.items()}["host"]
        self.assertEqual(host_header, f"xn--bcher-kva.test:{self.pages.port}")


class LocalSearxUrlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_local_urls_are_kept(self):
        for url, expected in (("http://127.0.0.1:8888", "http://127.0.0.1:8888"),
                              ("http://127.0.0.1:9123/", "http://127.0.0.1:9123"),
                              ("https://localhost", "https://localhost"),
                              ("HTTP://LOCALHOST:8080/searx/", "HTTP://LOCALHOST:8080/searx"),
                              ("  http://127.0.0.1:8888  ", "http://127.0.0.1:8888")):
            with self.subTest(url=url):
                self.assertEqual(self.ws.local_searx_url(url), expected)

    def test_anything_else_falls_back_to_the_default(self):
        for url in ("", None, "http://192.168.1.10:8888", "http://evil.example", "file:///C:/x",
                    "ftp://127.0.0.1/", "http://127.0.0.1.evil.example/", "http://localhost@evil.example/",
                    "http://127.0.0.1:8888@evil.example/", "http://127.0.0.1\\@evil.example/",
                    "javascript:alert(1)", "http://127.0.0.2:8888", "http://localhost:8888/a b",
                    "http://127.0.0.1:8888\n"):
            with self.subTest(url=url):
                self.assertEqual(self.ws.local_searx_url(url), self.ws.DEFAULT_SEARX_URL)

    def test_get_refuses_non_http_schemes(self):
        for url in ("file:///C:/Windows/win.ini", "ftp://127.0.0.1/x", "data:,x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.ws._get(url, 1)

    def test_get_does_not_follow_redirects_to_other_schemes(self):
        pages = StaticPages({"/r": (302, "text/plain", "", {"Location": "ftp://127.0.0.1/x"})})
        try:
            with self.assertRaises(self.ws.urllib.error.HTTPError) as ctx:
                self.ws._get(pages.url + "/r", 2)
            self.assertIn("non-http", str(ctx.exception))
        finally:
            pages.close()


if __name__ == "__main__":
    unittest.main()
