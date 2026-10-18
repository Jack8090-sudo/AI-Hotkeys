"""Results page server (I7, I8): token, Host allowlist, "Ask AI" streaming, escaping."""

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.support import AppTree, FakeOllama

TOKEN = "viewer-token-1234567890"
EVIL = "</script><script>alert(1)</script><!--"


class ViewerHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = FakeOllama(text="Versione migliorata del testo.")
        cls.tree = AppTree(ollama_url=cls.ollama.url)
        cls.v = cls.tree.load("viewer")
        cls.session = cls.v.Session(EVIL, "Risultato " + EVIL, "rewrite", "Fix " + EVIL)
        cls.page = cls.v.build_page(cls.session, TOKEN, "PgUp")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.v.make_handler(cls.session, TOKEN, cls.page))
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.ollama.close()
        cls.tree.close()

    def setUp(self):
        self.ollama.scenario = "ok"

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
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

    def ask(self, question, base=0, token=TOKEN):
        return self.request("POST", "/api/ask", json.dumps({"question": question, "base": base}),
                            {"X-Token": token, "Content-Type": "application/json"})

    @staticmethod
    def ndjson(body):
        return [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]

    # ---- page ----

    def test_page_needs_token_and_valid_host(self):
        self.assertEqual(self.request("GET", "/")[0], 403)
        self.assertEqual(self.request("GET", f"/?t={TOKEN}", host="evil.example")[0], 403)
        status, headers, _ = self.request("GET", f"/?t={TOKEN}")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")

    def test_user_text_cannot_break_out_of_the_page(self):
        # The selected text, result and action name are attacker-influenced
        self.assertNotIn(EVIL, self.page)
        self.assertNotIn("<script>alert(1)</script>", self.page)
        self.assertIn("- AI-Hotkeys", self.page)          # title suffix main.ahk relies on (S8b1)

    def test_ping(self):
        self.assertEqual(self.request("GET", "/api/ping")[0], 403)
        self.assertEqual(self.request("GET", "/api/ping", headers={"X-Token": TOKEN})[0], 200)

    # ---- Ask AI ----

    def test_ask_streams_pieces_and_done(self):
        status, headers, body = self.ask("più formale")
        self.assertEqual(status, 200)
        self.assertIn("ndjson", headers.get("Content-Type", ""))
        events = self.ndjson(body)
        self.assertTrue(any("t" in e for e in events))
        self.assertTrue(events[-1].get("done"))
        self.assertEqual(events[-1]["text"], "Versione migliorata del testo.")
        # the follow-up is streamed and carries the request
        sent = self.ollama.chat_bodies()[-1]
        self.assertTrue(sent["stream"])
        self.assertIn("più formale", sent["messages"][-1]["content"])

    def test_ask_rejects_bad_requests(self):
        self.assertEqual(self.request("POST", "/api/ask", b"", {"X-Token": "nope"})[0], 403)
        self.assertEqual(self.ask("   ")[0], 400)
        self.assertEqual(self.ask("x" * (self.v.MAX_QUESTION + 1))[0], 400)
        self.assertEqual(self.request("POST", "/api/ask", "not json", {"X-Token": TOKEN})[0], 400)
        self.assertEqual(self.request("POST", "/api/ask", json.dumps({"question": "x", "base": "a"}),
                                      {"X-Token": TOKEN})[0], 400)

    def test_ask_reports_ollama_error_field(self):
        self.ollama.scenario = "error_field"
        events = self.ndjson(self.ask("ancora")[2])
        self.assertIn("error", events[-1])

    def test_K4_interrupted_stream_is_reported_as_partial(self):
        self.ollama.scenario = "no_done"
        events = self.ndjson(self.ask("ancora")[2])
        self.assertTrue(any("t" in e for e in events))           # the text already streamed is kept
        self.assertTrue(events[-1].get("partial"))
        self.assertIn("interrupted", events[-1]["error"])

    def test_page_turns_remote_images_into_links(self):
        # marked renderer override (C10, D8); the CSP blocks remote images as well
        self.assertIn("Image: ", self.page)
        self.assertIn("img-src 'self' data:", self.v.pages.CSP)

    def test_idle_clock_is_monotonic(self):
        import time
        self.session.touch()
        self.assertLess(abs(time.monotonic() - self.session.last_seen), 5)

    def test_detect_mode(self):
        self.assertEqual(self.v.detect_mode("Riassunto"), "summarize")
        self.assertEqual(self.v.detect_mode("Spiegazione"), "explain")
        self.assertEqual(self.v.detect_mode("Fix"), "rewrite")
        self.assertEqual(self.v.detect_mode("whatever", "explain"), "explain")

    # ---- known defects ----

    def test_C21_missing_model_is_not_reported_as_ollama_unreachable(self):
        """C21 (fixed in S9): a 404 'model not found' says 'ollama pull', not 'Cannot reach Ollama'."""
        self.ollama.scenario = "http404"
        events = self.ndjson(self.ask("ancora")[2])
        self.assertNotIn("Cannot reach Ollama", events[-1].get("error", ""))
        self.assertIn("pull", events[-1].get("error", "").lower())

    def test_C10_page_sends_content_security_policy(self):
        """C10 (fixed in S7): no CSP header on the results page."""
        _, headers, _ = self.request("GET", f"/?t={TOKEN}")
        self.assertIn("Content-Security-Policy", headers)


if __name__ == "__main__":
    unittest.main()
