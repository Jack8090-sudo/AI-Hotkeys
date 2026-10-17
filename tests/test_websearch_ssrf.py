"""websearch page fetching (I9) and the SSRF guard (C11, step S6a).

Uses local fixture pages only. The fixtures listen on 127.0.0.1, which the guard
blocks by design: positive tests open the narrow test seam
`websearch._TEST_LOOPBACK_PORTS` for the one fixture port they need.
curl_cffi is not available in the temporary tree (no searxng/lib), so the
standard-library path is exercised here (the curl_cffi path: test_websearch_fetch).
"""

import unittest
from unittest import mock

from tests.support import AppTree, FakeSearx, StaticPages

PAGE = ("<html><body><main><p>Il paragrafo principale della pagina di prova, "
        "abbastanza lungo da essere tenuto.</p></main></body></html>")

BLOCKED_URLS = [
    "http://127.0.0.1/",
    "http://127.1/",
    "http://0.0.0.0/",
    "http://localhost/",
    "http://app.localhost/",
    "http://[::1]/",
    "http://[::]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:10.0.0.1]/",
    "http://[64:ff9b::a00:1]/",
    "http://[2002:a00:1::]/",
    "http://[fd00::1]/",
    "http://[fe80::1]/",
    "http://[ff02::1]/",
    "http://10.1.2.3/",
    "http://172.16.0.1/",
    "http://172.31.255.255/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://169.254.1.1/",
    "http://224.0.0.1/",
    "http://255.255.255.255/",
    "http://2130706433/",            # 127.0.0.1 as a decimal number
    "http://0x7f000001/",            # hex
    "http://0x7f.0.0.1/",
    "http://0177.0.0.1/",            # octal
    "http://017700000001/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://8.8.8.8:8080/",           # public, but not port 80/443
    "http://8.8.8.8:22/",
    "ftp://8.8.8.8/",
    "file:///C:/Windows/win.ini",
    "javascript:alert(1)",
    "http://user:pw@8.8.8.8/",
    "http:///nohost",
    "http://8.8.8.8:99999/",
]


class SafeUrlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_blocked_corpus(self):
        for url in BLOCKED_URLS:
            with self.subTest(url=url):
                self.assertIsNone(self.ws.safe_url(url))

    def test_public_addresses_are_allowed_and_pinned(self):
        t = self.ws.safe_url("https://8.8.8.8/a/b?q=1#frag")
        self.assertIsNotNone(t)
        self.assertEqual((t.ip, t.port, t.path), ("8.8.8.8", 443, "/a/b?q=1"))
        self.assertIsNotNone(self.ws.safe_url("http://[2001:4860:4860::8888]/"))

    def test_dns_names_resolving_to_private_ranges_are_blocked(self):
        for answer in (["10.0.0.5"], ["192.168.0.10"], ["127.0.0.1"], ["::1"], ["169.254.169.254"],
                       ["93.184.216.34", "10.0.0.5"]):         # one internal address is enough
            with self.subTest(answer=answer), mock.patch.object(self.ws, "_resolve", return_value=answer):
                self.assertIsNone(self.ws.safe_url("https://intranet.example.com/"))

    def test_dns_name_with_public_address_is_pinned_to_that_address(self):
        with mock.patch.object(self.ws, "_resolve", return_value=["93.184.216.34"]):
            t = self.ws.safe_url("https://docs.example.com/x")
        self.assertEqual((t.host, t.ip, t.port), ("docs.example.com", "93.184.216.34", 443))

    def test_unresolvable_host_is_refused(self):
        with mock.patch.object(self.ws, "_resolve", side_effect=OSError("no such host")):
            self.assertIsNone(self.ws.safe_url("https://nope.invalid/"))

    def test_test_seam_is_closed_by_default_and_only_for_127_0_0_1(self):
        self.assertEqual(self.ws._TEST_LOOPBACK_PORTS, frozenset())
        with mock.patch.object(self.ws, "_TEST_LOOPBACK_PORTS", frozenset({5555})):
            self.assertIsNotNone(self.ws.safe_url("http://127.0.0.1:5555/"))
            self.assertIsNone(self.ws.safe_url("http://127.0.0.1:5556/"))
            self.assertIsNone(self.ws.safe_url("http://8.8.8.8:5555/"))
            self.assertIsNone(self.ws.safe_url("http://10.0.0.1:5555/"))


class WebsearchFetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.internal = StaticPages({"/secret": (200, "text/html", PAGE)})
        cls.pages = StaticPages({
            "/page": (200, "text/html; charset=utf-8", PAGE),
            "/json": (200, "application/json", '{"a": 1}'),
            "/redirect-internal": (302, "text/plain", "", {"Location": "/page"}),
            "/redirect-other-port": (302, "text/plain", "", {"Location": cls.internal.url + "/secret"}),
            "/redirect-metadata": (302, "text/plain", "", {"Location": "http://169.254.169.254/latest/"}),
            "/redirect-ipv6": (302, "text/plain", "", {"Location": "http://[::1]/"}),
            "/loop": (302, "text/plain", "", {"Location": "/loop"}),
            "/chain5": (302, "text/plain", "", {"Location": "/chain4"}),
            "/chain4": (302, "text/plain", "", {"Location": "/chain3"}),
            "/chain3": (302, "text/plain", "", {"Location": "/chain2"}),
            "/chain2": (302, "text/plain", "", {"Location": "/chain1"}),
            "/chain1": (301, "text/plain", "", {"Location": "/page"}),
            "/chain6": (307, "text/plain", "", {"Location": "/chain5"}),
        })
        cls.searx = FakeSearx(results=[
            {"url": "https://example.com/a", "title": "A", "content": "snippet a"},
            {"url": "javascript:alert(1)", "title": "bad", "content": ""},
            {"url": "ftp://example.com/x", "title": "bad", "content": ""},
        ])
        cls.tree = AppTree(searxng_url=cls.searx.url)
        cls.ws = cls.tree.load("websearch")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()
        cls.pages.close()
        cls.internal.close()
        cls.searx.close()

    def setUp(self):
        self.pages.requests.clear()
        self.internal.requests.clear()

    def allow_pages(self):
        return mock.patch.object(self.ws, "_TEST_LOOPBACK_PORTS", frozenset({self.pages.port}))

    def test_searx_search_keeps_only_http_results(self):
        results = self.ws.searx_search("x")
        self.assertEqual([r["url"] for r in results], ["https://example.com/a"])

    def test_is_running_uses_healthz(self):
        """The SearXNG URL itself (127.0.0.1) is not subject to the guard."""
        self.assertTrue(self.ws.is_running())

    def test_non_html_pages_are_ignored(self):
        with self.allow_pages():
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/json"), "")
        self.assertEqual(len(self.pages.requests), 1)        # really fetched, then dropped

    def test_allowed_fixture_page_is_read(self):
        with self.allow_pages():
            self.assertIn("paragrafo principale", self.ws.fetch_page_text(self.pages.url + "/page"))

    def test_redirects_are_followed_and_rechecked(self):
        with self.allow_pages():
            self.assertIn("paragrafo principale", self.ws.fetch_page_text(self.pages.url + "/chain5"))

    def test_more_than_five_redirects_are_refused(self):
        with self.allow_pages():
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/chain6"), "")
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/loop"), "")
        self.assertLessEqual(len([r for r in self.pages.requests if r[1] == "/loop"]), 6)

    def test_redirect_chain_into_other_loopback_port_is_blocked(self):
        with self.allow_pages():
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/redirect-other-port"), "")
        self.assertEqual(self.internal.requests, [])           # the internal target saw nothing

    def test_redirect_into_metadata_and_ipv6_loopback_is_blocked(self):
        with self.allow_pages():
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/redirect-metadata"), "")
            self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/redirect-ipv6"), "")

    def test_C11_loopback_pages_are_not_fetched(self):
        """C11: result URLs pointing at 127.0.0.1 / private ranges are never fetched."""
        self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/page"), "")
        self.assertEqual(self.pages.requests, [])

    def test_C11_redirects_into_loopback_are_not_followed(self):
        """C11: a redirect target is checked again (here: the loopback fixture, not allowed)."""
        self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/redirect-internal"), "")
        self.assertEqual(self.pages.requests, [])


if __name__ == "__main__":
    unittest.main()
