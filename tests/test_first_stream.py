"""STREAM1: the first answer streamed into the results page (viewer.py --stream, POST /api/first).

The page must give exactly what qwen_client.run_action gives for the same answer
(shared pipeline), in NDJSON order status -> pieces -> done, map errors through
describe_error (K1), work once per page, honour the Esc-2-s cancel flag (I5) and
leave no plaintext selection in work\\ (S9).
"""

import http.client
import json
import secrets
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.support import DEFAULT_CONFIG, AppTree, FakeOllama, FakeSearx, StaticPages

TOKEN = "first-stream-token-123456"
LONG_TEXT = "Questa è una frase di prova abbastanza lunga da contare come paragrafo. " * 6
PAGE = f"<html><body><main><p>{LONG_TEXT}</p></main></body></html>"


def post(port, path, body=b"", token=TOKEN, timeout=20):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"X-Token": token, "Content-Type": "application/json"})
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def ndjson(body):
    return [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]


class StreamPage:
    """A stream-mode results page on a run folder of tree, served in a thread (like viewer.main)."""

    def __init__(self, tree, mode, text, name=None):
        self.tree = tree
        self.v = tree.load("viewer")
        self.run_dir = tree.work / "runs" / ("20261018120000-" + secrets.token_hex(8))
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "input.txt").write_text(text, encoding="utf-8")
        name = name or {"rewrite": "Fix", "summarize": "Summary", "explain": "Explanation"}[mode]
        self.run = self.v.load_run([f"--run-dir={self.run_dir}", name, mode, "--stream", "--no-browser"])
        self.session = self.v.start_session(self.run)
        self.page = self.v.build_page(self.session, TOKEN, "End")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.v.make_handler(self.session, TOKEN, self.page))
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def first(self):
        status, body = post(self.port, "/api/first")
        return status, ndjson(body) if status == 200 else json.loads(body)

    def ask(self, question):
        status, body = post(self.port, "/api/ask", json.dumps({"question": question, "base": 0}).encode())
        return status, ndjson(body) if status == 200 else json.loads(body)

    def close(self):
        self.session.first.finished.set()
        self.server.shutdown()
        self.server.server_close()


class FirstStreamTest(unittest.TestCase):
    answer = "Ecco il testo corretto:\n\nIl testo è stato corretto bene."

    def setUp(self):
        self.ollama = FakeOllama(text=self.answer)
        self.addCleanup(self.ollama.close)
        self.tree = AppTree(ollama_url=self.ollama.url)
        self.addCleanup(self.tree.close)
        self.qc = self.tree.load("qwen_client")

    def page(self, mode, text):
        p = StreamPage(self.tree, mode, text)
        self.addCleanup(p.close)
        return p

    def run_action_output(self, mode, text):
        """What the non-streaming path (actions/*.py, direct replace, tools/bench) writes."""
        d = self.tree.work / "runs" / ("20261018120001-" + secrets.token_hex(8))
        d.mkdir(parents=True)
        (d / "input.txt").write_text(text, encoding="utf-8")
        self.assertEqual(self.qc.run_action(mode, ["x", f"--run-dir={d}"]), 0)
        out = (d / "output.txt").read_text(encoding="utf-8")
        self.qc.remove_run_dir(d)
        return out

    # ---- order and parity ----

    def test_stream_order_status_then_pieces_then_done(self):
        p = self.page("summarize", "Un testo da riassumere.")
        status, events = p.first()
        self.assertEqual(status, 200)
        kinds = ["status" if "status" in e else "t" if "t" in e else "done" if e.get("done") else "other"
                 for e in events]
        self.assertEqual(kinds[0], "status")
        self.assertEqual(kinds[-1], "done")
        self.assertNotIn("other", kinds)
        first_piece = kinds.index("t")
        self.assertTrue(all(k == "status" for k in kinds[:first_piece]))
        self.assertTrue(all(k == "t" for k in kinds[first_piece:-1]))
        self.assertEqual("".join(e["t"] for e in events if "t" in e), self.answer)
        # One streamed request to Ollama
        bodies = self.ollama.chat_bodies()
        self.assertEqual(len(bodies), 1)
        self.assertTrue(bodies[0]["stream"])
        self.assertIn("seconds", events[-1]["meta"])
        self.assertEqual(events[-1]["meta"]["mode"], "summarize")

    def test_final_text_equals_run_action_for_each_mode(self):
        for mode in ("rewrite", "summarize", "explain"):
            with self.subTest(mode=mode):
                text = "Il testo selezionato per la prova."
                status, events = self.page(mode, text).first()
                self.assertEqual(status, 200)
                self.assertTrue(events[-1].get("done"), events[-1])
                self.assertEqual(events[-1]["text"], self.run_action_output(mode, text))

    def test_same_prompt_as_run_action(self):
        text = "Il testo selezionato per la prova."
        self.page("explain", text).first()
        self.run_action_output("explain", text)
        streamed, whole = self.ollama.chat_bodies()
        self.assertEqual(streamed["messages"], whole["messages"])
        self.assertEqual(streamed["options"], whole["options"])

    def test_page_is_built_in_stream_mode(self):
        p = self.page("explain", "testo")
        self.assertIn('"stream": true', p.page)
        self.assertEqual(p.session.versions[0]["text"], "")

    # ---- single use, follow-ups ----

    def test_single_use_guard(self):
        p = self.page("summarize", "Un testo.")
        self.assertEqual(p.first()[0], 200)
        status, data = p.first()
        self.assertEqual(status, 409)
        self.assertIn("already used", data["error"])
        self.assertEqual(len(self.ollama.chat_bodies()), 1)          # a reload never generates again

    def test_first_needs_the_token(self):
        p = self.page("summarize", "Un testo.")
        self.assertEqual(post(p.port, "/api/first", token="nope")[0], 403)
        self.assertEqual(p.first()[0], 200)                           # the refused call did not use it up

    def test_followups_wait_for_the_first_answer_then_work(self):
        p = self.page("rewrite", "Testo da correggere.")
        self.assertEqual(p.ask("più formale")[0], 409)
        p.first()
        status, events = p.ask("più formale")
        self.assertEqual(status, 200)
        self.assertTrue(events[-1].get("done"))
        self.assertEqual(p.session.versions[0]["text"], self.run_action_output("rewrite", "Testo da correggere."))

    def test_old_page_without_stream_has_no_first_answer_endpoint(self):
        v = self.tree.load("viewer")
        session = v.Session("orig", "result", "rewrite", "Fix")
        server = ThreadingHTTPServer(("127.0.0.1", 0), v.make_handler(session, TOKEN, "page"))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.assertEqual(post(server.server_address[1], "/api/first")[0], 409)
        self.assertEqual(post(server.server_address[1], "/api/ask",
                              json.dumps({"question": "q"}).encode())[0], 200)

    # ---- privacy (S9) ----

    def test_no_plaintext_left_in_work_after_done(self):
        secret = "Testo segreto unico 7f3a9c per il controllo."
        p = self.page("summarize", secret)
        self.assertFalse((p.run_dir / "input.txt").exists())          # deleted as soon as it is in memory
        self.assertTrue(p.run_dir.is_dir())                           # kept for the cancel flag
        self.assertEqual(p.first()[0], 200)
        self.assertFalse(p.run_dir.exists())
        for f in self.tree.work.rglob("*"):
            if f.is_file():
                self.assertNotIn(secret[:20], f.read_text(encoding="utf-8", errors="replace"), f)

    def test_run_dir_removed_after_an_error_too(self):
        self.ollama.scenario = "http404"
        p = self.page("summarize", "Un testo.")
        p.first()
        self.assertFalse(p.run_dir.exists())

    # ---- errors (K1) ----

    def test_ollama_down(self):
        tree = AppTree()                                               # ollama_url = a dead port
        self.addCleanup(tree.close)
        p = StreamPage(tree, "summarize", "Un testo.")
        self.addCleanup(p.close)
        status, events = p.first()
        self.assertEqual(status, 200)
        self.assertIn("Ollama is not running", events[-1]["error"])
        self.assertFalse(p.run_dir.exists())

    def test_model_not_found_404(self):
        self.ollama.scenario = "http404"
        events = self.page("summarize", "Un testo.").first()[1]
        self.assertIn("ollama pull test-model:1b", events[-1]["error"])
        self.assertNotIn("partial", events[-1])

    def test_text_too_long_never_reaches_ollama(self):
        text = "x" * (self.qc.max_input_chars("rewrite") + 1)
        events = self.page("rewrite", text).first()[1]
        self.assertEqual(len(events), 1)
        self.assertIn("too long", events[0]["error"])
        self.assertEqual(self.ollama.chat_bodies(), [])

    def test_empty_selection(self):
        events = self.page("rewrite", "   ").first()[1]
        self.assertIn("Nothing selected", events[-1]["error"])

    def test_length_truncation_is_partial(self):
        self.ollama.scenario = "length"
        events = self.page("summarize", "Un testo.").first()[1]
        self.assertTrue(any("t" in e for e in events))                # what was written stays visible
        self.assertEqual(events[-1]["error"], self.qc.TRUNCATED_FIRST)
        self.assertTrue(events[-1]["partial"])

    def test_interrupted_stream_is_partial(self):
        self.ollama.scenario = "no_done"
        events = self.page("summarize", "Un testo.").first()[1]
        self.assertTrue(events[-1]["partial"])
        self.assertIn("interrupted", events[-1]["error"])

    def test_error_field_inside_the_stream(self):
        self.ollama.scenario = "error_field"
        events = self.page("summarize", "Un testo.").first()[1]
        self.assertIn("error", events[-1])

    def test_cloud_model_is_refused_before_any_request(self):
        # MODEL2 guard in qwen_client._request also covers the streamed first answer
        with mock.patch.object(self.qc, "MODEL", "glm-4.6:cloud"):
            events = self.page("summarize", "Un testo.").first()[1]
        self.assertEqual(events[-1]["error"], self.qc.CLOUD_MODEL_MESSAGE)
        self.assertEqual(self.ollama.chat_bodies(), [])

    def test_no_followups_after_a_failed_first_answer(self):
        self.ollama.scenario = "http404"
        p = self.page("summarize", "Un testo.")
        p.first()
        self.ollama.scenario = "ok"
        self.assertEqual(p.ask("e poi?")[0], 409)

    # ---- cancel (I5) ----

    def test_cancel_flag_stops_the_answer_and_cleans(self):
        self.ollama.delay = 3.0
        p = self.page("summarize", "Un testo.")
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("r", p.first()))
        t0 = time.monotonic()
        t.start()
        time.sleep(0.4)
        (p.run_dir / self.tree.load("viewer").CANCEL_FLAG).write_text("", encoding="utf-8")
        t.join(10)
        self.assertLess(time.monotonic() - t0, 2.5)                  # not after Ollama's 3 s
        status, events = result["r"]
        self.assertTrue(events[-1].get("cancelled"))
        self.assertFalse(any("t" in e for e in events))
        self.assertFalse(p.run_dir.exists())

    def test_cancel_before_the_page_asked(self):
        p = self.page("summarize", "Un testo.")
        (p.run_dir / "cancel").write_text("", encoding="utf-8")
        deadline = time.monotonic() + 3
        while p.run_dir.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(p.run_dir.exists())
        events = p.first()[1]
        self.assertTrue(events[-1].get("cancelled"))
        self.assertEqual(self.ollama.chat_bodies(), [])

    # ---- command line (K3 compatibility) ----

    def test_stream_needs_a_run_dir(self):
        v = self.tree.load("viewer")
        with self.assertRaises(SystemExit):
            v.load_run(["in.txt", "out.txt", "Fix", "rewrite", "--stream"])


def search_config(ollama_url, searxng_url, web_search):
    return DEFAULT_CONFIG.format(ollama_url=ollama_url, keep_alive="30m", web_search=web_search,
                                 searxng_url=searxng_url, todo_file="x.md")


class FirstStreamExplainTest(unittest.TestCase):
    """End with the web search: disabled, and with a fake SearXNG plus fixture pages."""

    def setUp(self):
        self.ollama = FakeOllama(text="roblox datastore limits")
        self.addCleanup(self.ollama.close)
        self.pages = StaticPages({f"/p{i}": (200, "text/html; charset=utf-8", PAGE) for i in range(3)})
        self.addCleanup(self.pages.close)
        self.searx = FakeSearx(results=[{"url": f"{self.pages.url}/p{i}", "title": f"Pagina {i}",
                                         "content": f"snippet {i}"} for i in range(3)])
        self.addCleanup(self.searx.close)

    def tree(self, web_search):
        tree = AppTree(config_text=search_config(self.ollama.url, self.searx.url, web_search))
        self.addCleanup(tree.close)
        ws = tree.load("websearch")
        ws._cffi_requests = False
        return tree

    def test_web_search_disabled(self):
        tree = self.tree("false")
        p = StreamPage(tree, "explain", "Uso StreamingEnabled e player_data")
        self.addCleanup(p.close)
        events = p.first()[1]
        self.assertTrue(events[-1].get("done"))
        self.assertIs(events[-1]["meta"]["web"], False)
        self.assertTrue(any("no web" in e.get("status", "") for e in events))
        self.assertEqual(self.searx.requests, [])

    def test_web_search_with_sources(self):
        tree = self.tree("always")
        ws = tree.load("websearch")
        qc = tree.load("qwen_client")
        text = "Uso StreamingEnabled e player_data"
        with mock.patch.object(ws, "_TEST_LOOPBACK_PORTS", frozenset({self.pages.port})):
            p = StreamPage(tree, "explain", text)
            self.addCleanup(p.close)
            events = p.first()[1]
            statuses = [e["status"] for e in events if "status" in e]
            self.assertTrue(any(s.startswith("Searching the web") for s in statuses), statuses)
            self.assertTrue(any(s.startswith("Reading") for s in statuses), statuses)
            done = events[-1]
            self.assertTrue(done.get("done"), done)
            self.assertIs(done["meta"]["web"], True)
            self.assertGreater(done["meta"]["fonti"], 0)
            self.assertIn(self.pages.url, done["text"])               # sources linked (add_sources)
            # follow-ups reuse the sources, without the full page text
            self.assertTrue(p.session.sources)
            self.assertFalse(any("text" in s for s in p.session.sources))
            # nothing about the search was written to work\ (no sources.json, no status.txt)
            self.assertEqual([f for f in tree.work.rglob("*") if f.is_file()
                              and f.name != "config_warning.txt"], [])

            # Same final text as run_action on the same search and answer
            d = tree.work / "runs" / ("20261018120001-" + secrets.token_hex(8))
            d.mkdir(parents=True)
            (d / "input.txt").write_text(text, encoding="utf-8")
            self.assertEqual(qc.run_action("explain", ["x", f"--run-dir={d}"]), 0)
            self.assertEqual((d / "output.txt").read_text(encoding="utf-8"), done["text"])
        self.assertIsNone(ws.STATUS_HOOK)


if __name__ == "__main__":
    unittest.main()
