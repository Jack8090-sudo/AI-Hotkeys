"""websearch fetch phase (step S6a): deadlines (C23), Ollama preflight (C22),
clamped settings (C38 part), and the curl_cffi path of the SSRF guard (C11).

Only 127.0.0.1 fixtures; deadlines are shortened so the suite stays fast.
The curl_cffi tests run only when searxng/lib (gitignored runtime) is linked.
"""

import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.support import DEFAULT_CONFIG, AppTree, FakeOllama, FakeSearx, StaticPages, dead_url

LONG_TEXT = "Questa è una frase di prova abbastanza lunga da contare come paragrafo. " * 6
PAGE = f"<html><body><main><p>{LONG_TEXT}</p></main></body></html>"

CFFI_LIB = Path(__file__).resolve().parent.parent / "searxng" / "lib"


def load_cffi():
    if not (CFFI_LIB / "curl_cffi").is_dir():
        return None
    if str(CFFI_LIB) not in sys.path:
        sys.path.append(str(CFFI_LIB))
    try:
        from curl_cffi import requests as cr
        return cr
    except Exception:
        return None


class DripServer:
    """Raw TCP server that answers very slowly, one byte at a time.

    mode "body":    full headers, then the body drips (0.1 s per byte)
    mode "headers": even the status line and headers drip
    """

    def __init__(self, mode="body", interval=0.1, total=60.0):
        self.mode, self.interval, self.total = mode, interval, total
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.closed = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.closed:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        try:
            conn.recv(4096)
            head = b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nContent-Length: 100000\r\n\r\n"
            if self.mode == "body":
                conn.sendall(head)
                head = b""
            data = head + (b"<p>" + b"x" * 99990)
            end = time.monotonic() + self.total
            for b in data:
                if self.closed or time.monotonic() > end:
                    break
                conn.sendall(bytes([b]))
                time.sleep(self.interval)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.closed = True
        self.sock.close()


class DeadlineTest(unittest.TestCase):
    cffi = None    # set by the curl_cffi subclass

    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")
        cls.ws._cffi_requests = cls.cffi if cls.cffi else False

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def allow(self, *ports):
        return mock.patch.object(self.ws, "_TEST_LOOPBACK_PORTS", frozenset(ports))

    def assert_bounded(self, server, deadline=1.5):
        with self.allow(server.port), mock.patch.object(self.ws, "PAGE_DEADLINE", deadline):
            t0 = time.monotonic()
            text = self.ws.fetch_page_text(server.url + "/")
            elapsed = time.monotonic() - t0
        self.assertEqual(text, "")
        self.assertLess(abs(elapsed - deadline), 1.0, f"took {elapsed:.2f}s for a {deadline}s deadline")

    def test_slow_drip_body_is_bounded_by_the_page_deadline(self):
        server = DripServer("body")
        try:
            self.assert_bounded(server)
        finally:
            server.close()

    def test_slow_drip_headers_are_bounded_by_the_page_deadline(self):
        server = DripServer("headers")
        try:
            self.assert_bounded(server)
        finally:
            server.close()

    def test_normal_page_is_read(self):
        pages = StaticPages({"/p": (200, "text/html; charset=utf-8", PAGE)})
        try:
            with self.allow(pages.port):
                self.assertIn("frase di prova", self.ws.fetch_page_text(pages.url + "/p"))
        finally:
            pages.close()

    def test_redirect_into_loopback_is_blocked(self):
        internal = StaticPages({"/secret": (200, "text/html", PAGE)})
        pages = StaticPages({"/r": (302, "text/plain", "", {"Location": internal.url + "/secret"}),
                             "/r2": (302, "text/plain", "", {"Location": "http://127.0.0.1/"})})
        try:
            with self.allow(pages.port):
                self.assertEqual(self.ws.fetch_page_text(pages.url + "/r"), "")
                self.assertEqual(self.ws.fetch_page_text(pages.url + "/r2"), "")
            self.assertEqual(internal.requests, [])
            self.assertEqual(len(pages.requests), 2)
        finally:
            pages.close()
            internal.close()

    def test_loopback_without_seam_is_never_contacted(self):
        pages = StaticPages({"/p": (200, "text/html", PAGE)})
        try:
            self.assertEqual(self.ws.fetch_page_text(pages.url + "/p"), "")
            self.assertEqual(pages.requests, [])
        finally:
            pages.close()


@unittest.skipUnless(load_cffi(), "curl_cffi not available (link searxng/lib to run these)")
class CffiDeadlineTest(DeadlineTest):
    cffi = load_cffi()

    def test_curl_path_is_really_used(self):
        pages = StaticPages({"/p": (200, "text/html", PAGE)})
        try:
            with self.allow(pages.port), \
                    mock.patch.object(self.ws, "_download_stdlib", side_effect=AssertionError("stdlib used")):
                self.assertIn("frase di prova", self.ws.fetch_page_text(pages.url + "/p"))
        finally:
            pages.close()


def config(ollama_url, searxng_url, web_search="auto", results="5", pages_to_read="3"):
    text = DEFAULT_CONFIG.format(ollama_url=ollama_url, keep_alive="30m", web_search=web_search,
                                 searxng_url=searxng_url, todo_file="x.md")
    return (text.replace("results = 5", f"results = {results}")
                .replace("pages_to_read = 3", f"pages_to_read = {pages_to_read}"))


class GatherSourcesTest(unittest.TestCase):
    def setUp(self):
        self.ollama = FakeOllama(text="roblox datastore limits")
        self.addCleanup(self.ollama.close)
        self.drip = DripServer("body")
        self.addCleanup(self.drip.close)
        self.pages = StaticPages({f"/p{i}": (200, "text/html; charset=utf-8", PAGE) for i in range(5)})
        self.addCleanup(self.pages.close)

    def make(self, search_results, **cfg):
        searx = FakeSearx(results=search_results)
        self.addCleanup(searx.close)
        tree = AppTree(config_text=config(cfg.pop("ollama_url", self.ollama.url), searx.url, **cfg))
        self.addCleanup(tree.close)
        ws = tree.load("websearch")
        ws._cffi_requests = False
        return ws, searx

    def result(self, url, title="T"):
        return {"url": url, "title": title, "content": "snippet " + title}

    def test_preflight_ollama_down_means_no_search_request(self):
        ws, searx = self.make([self.result(self.pages.url + "/p0")], ollama_url=dead_url())
        t0 = time.monotonic()
        self.assertEqual(ws.gather_sources("Uso StreamingEnabled e player_data"), ([], []))
        self.assertLess(time.monotonic() - t0, 3.0)
        self.assertEqual([r for r in searx.requests if r[1].startswith("/search")], [])
        self.assertEqual(self.pages.requests, [])

    def test_disabled_web_search_fetches_nothing(self):
        ws, searx = self.make([self.result(self.pages.url + "/p0")], web_search="false")
        self.assertEqual(ws.gather_sources("Uso StreamingEnabled"), ([], []))
        self.assertEqual(searx.requests, [])
        self.assertEqual(self.ollama.requests, [])

    def test_search_reads_pages_and_skips_blocked_ones(self):
        internal = StaticPages({"/secret": (200, "text/html", PAGE)})
        self.addCleanup(internal.close)
        ws, searx = self.make([self.result(internal.url + "/secret", "internal"),
                               self.result(self.pages.url + "/p0", "A"),
                               self.result(self.pages.url + "/p1", "B")])
        with mock.patch.object(ws, "_TEST_LOOPBACK_PORTS", frozenset({self.pages.port})):
            sources, queries = ws.gather_sources("Uso StreamingEnabled e player_data")
        self.assertEqual(queries, ["roblox datastore limits"])
        self.assertEqual(internal.requests, [])
        read = [s["title"] for s in sources if s.get("text")]
        self.assertEqual(read, ["A", "B"])
        self.assertEqual([s["n"] for s in sources], [1, 2, 3])

    def test_stops_once_enough_pages_without_waiting_for_slow_ones(self):
        ws, _ = self.make([self.result(self.drip.url + "/slow", "slow"),
                           self.result(self.pages.url + "/p0", "fast")], pages_to_read="1")
        ports = frozenset({self.pages.port, self.drip.port})
        with mock.patch.object(ws, "_TEST_LOOPBACK_PORTS", ports), \
                mock.patch.object(ws, "PAGE_DEADLINE", 8.0), mock.patch.object(ws, "FETCH_DEADLINE", 8.0):
            t0 = time.monotonic()
            sources, _ = ws.gather_sources("Uso StreamingEnabled")
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 3.0)
        self.assertEqual([s["title"] for s in sources if s.get("text")], ["fast"])

    def test_overall_fetch_deadline(self):
        ws, _ = self.make([self.result(self.drip.url + "/a", "a"), self.result(self.drip.url + "/b", "b")])
        with mock.patch.object(ws, "_TEST_LOOPBACK_PORTS", frozenset({self.drip.port})), \
                mock.patch.object(ws, "PAGE_DEADLINE", 30.0), mock.patch.object(ws, "FETCH_DEADLINE", 1.5):
            t0 = time.monotonic()
            sources, _ = ws.gather_sources("Uso StreamingEnabled")
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 3.0)
        self.assertEqual(len(sources), 2)                          # snippets are still used
        self.assertFalse(any(s.get("text") for s in sources))

    def test_results_and_pages_are_clamped(self):
        for results, pages, expected in (("50", "99", (10, 5)), ("0", "-3", (1, 0)), ("abc", "x", (5, 3))):
            with self.subTest(results=results, pages=pages):
                ws, _ = self.make([], results=results, pages_to_read=pages)
                self.assertEqual((ws.MAX_RESULTS, ws.PAGES_TO_READ), expected)


if __name__ == "__main__":
    unittest.main()
