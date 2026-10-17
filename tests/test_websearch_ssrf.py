"""websearch page fetching (I9) and the SSRF defect C11.

Uses local fixture pages only. curl_cffi is not available in the temporary tree
(no searxng/lib), so the urllib path is exercised.
"""

import unittest

from tests.support import AppTree, FakeSearx, StaticPages

PAGE = ("<html><body><main><p>Il paragrafo principale della pagina di prova, "
        "abbastanza lungo da essere tenuto.</p></main></body></html>")


class WebsearchFetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = StaticPages({
            "/page": (200, "text/html; charset=utf-8", PAGE),
            "/json": (200, "application/json", '{"a": 1}'),
            "/redirect-internal": (302, "text/plain", "", {"Location": "/page"}),
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
        cls.searx.close()

    def test_searx_search_keeps_only_http_results(self):
        results = self.ws.searx_search("x")
        self.assertEqual([r["url"] for r in results], ["https://example.com/a"])

    def test_is_running_uses_healthz(self):
        self.assertTrue(self.ws.is_running())

    def test_non_html_pages_are_ignored(self):
        self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/json"), "")

    # ---- known defect C11: flipped by step S6a ----

    @unittest.expectedFailure
    def test_C11_loopback_pages_are_not_fetched(self):
        """C11: result URLs pointing at 127.0.0.1 / private ranges are fetched (SSRF)."""
        self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/page"), "")

    @unittest.expectedFailure
    def test_C11_redirects_into_loopback_are_not_followed(self):
        """C11: redirects are followed with no re-check of the target."""
        self.assertEqual(self.ws.fetch_page_text(self.pages.url + "/redirect-internal"), "")


if __name__ == "__main__":
    unittest.main()
