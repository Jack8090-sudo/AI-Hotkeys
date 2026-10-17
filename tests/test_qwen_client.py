"""qwen_client: request payload, chat/stream/unload against a fake Ollama, answer cleanup,
config loading and run_action (I6, I7, I10, I11)."""

import contextlib
import io
import json
import os
import unittest

from tests.support import AppTree, FakeOllama, run_with_timeout


class QwenClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = FakeOllama(text="Testo corretto.")
        cls.tree = AppTree(ollama_url=cls.ollama.url)
        cls.qc = cls.tree.load("qwen_client")

    @classmethod
    def tearDownClass(cls):
        cls.ollama.close()
        cls.tree.close()

    def setUp(self):
        self.ollama.scenario = "ok"
        self.ollama.text = "Testo corretto."

    # ---- request payload (I10) ----

    def test_request_payload(self):
        req = self.qc._request([{"role": "user", "content": "ciao"}], "rewrite", False)
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "test-model:1b")
        self.assertFalse(payload["think"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["keep_alive"], "30m")
        self.assertEqual(payload["options"]["num_ctx"], self.qc.prompts.NUM_CTX)
        self.assertIn("num_predict", payload["options"])

    def test_numeric_keep_alive_is_sent_as_number(self):
        with AppTree(keep_alive="-1") as tree:
            self.assertEqual(tree.load("qwen_client").KEEP_ALIVE, -1)

    # ---- chat / stream / unload ----

    def test_chat_returns_content(self):
        self.assertEqual(self.qc.chat([{"role": "user", "content": "x"}], "rewrite"), "Testo corretto.")

    def test_chat_raises_on_error_field(self):
        self.ollama.scenario = "error_field"
        with self.assertRaises(RuntimeError):
            self.qc.chat([{"role": "user", "content": "x"}], "rewrite")

    def test_stream_pieces_yields_until_done(self):
        self.ollama.text = "uno due tre"
        with self.qc.open_stream([{"role": "user", "content": "x"}], "explain") as r:
            self.assertEqual("".join(self.qc.stream_pieces(r)), "uno due tre")

    def test_unload_sends_keep_alive_zero(self):
        self.qc.unload()
        method, path, _, body = self.ollama.requests[-1]
        self.assertEqual(path, "/api/generate")
        self.assertEqual(json.loads(body), {"model": "test-model:1b", "keep_alive": 0})

    # ---- clean_answer ----

    def test_clean_answer_rewrite(self):
        ca = self.qc.clean_answer
        self.assertEqual(ca("Ecco il testo corretto:\n\nCiao a tutti.", "rewrite"), "Ciao a tutti.")
        self.assertEqual(ca("<think>bla</think>\nCiao.", "rewrite"), "Ciao.")
        self.assertEqual(ca("```\nCiao.\n```", "rewrite"), "Ciao.")
        self.assertEqual(ca("«Ciao.»", "rewrite"), "Ciao.")
        self.assertEqual(ca("«Riga uno.\nRiga due.»", "rewrite"), "«Riga uno.\nRiga due.»")
        self.assertEqual(ca("<testo>Ciao.</testo>", "rewrite"), "Ciao.")

    def test_clean_answer_explain_drops_translation_and_empty_sections(self):
        text = ("## Spiegazione\nTesto.\n\n## Traduzione\nTranslated.\n\n"
                "## Termini tecnici\nNessuno.\n\n## Da tenere d'occhio\n- Punto.")
        out = self.qc.clean_answer(text, "explain")
        self.assertNotIn("Traduzione", out)
        self.assertNotIn("Termini tecnici", out)
        self.assertIn("## Spiegazione\nTesto.", out)
        self.assertIn("- Punto.", out)

    # ---- config ----

    def test_config_with_bom_defaults_and_todo_file_expansion(self):
        cfg = "\ufeff[qwen]\nmodel = bom-model\n[obsidian]\ntodo_file = %AIHK_TEST_DIR%\\To-Do.md\n"
        with AppTree(config_text=cfg.encode("utf-8")) as tree:
            qc = tree.load("qwen_client")
            self.assertEqual(qc.MODEL, "bom-model")
            self.assertEqual(qc.CONFIG["ollama_url"], "http://localhost:11434")   # default (I11)
            os.environ["AIHK_TEST_DIR"] = "C:\\x"
            try:
                self.assertEqual(str(qc.todo_file()), "C:\\x\\To-Do.md")
            finally:
                del os.environ["AIHK_TEST_DIR"]

    # ---- run_action ----

    def test_run_action_writes_output_and_meta(self):
        inp, out = self.tree.work / "input.txt", self.tree.work / "output.txt"
        inp.write_text("ciao a tuti", encoding="utf-8")
        self.assertEqual(self.qc.run_action("rewrite", ["x", str(inp), str(out)]), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "Testo corretto.")
        meta = json.loads((self.tree.work / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["mode"], "rewrite")
        self.assertIn("ciao a tuti", self.ollama.chat_bodies()[-1]["messages"][-1]["content"])

    def test_run_action_empty_input_fails_without_calling_ollama(self):
        inp, out = self.tree.work / "input.txt", self.tree.work / "empty_out.txt"
        inp.write_text("   \n", encoding="utf-8")
        before = len(self.ollama.requests)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.qc.run_action("rewrite", ["x", str(inp), str(out)]), 1)
        self.assertFalse(out.exists())
        self.assertEqual(len(self.ollama.requests), before)

    def test_run_action_explain_without_web_search(self):
        inp, out = self.tree.work / "input.txt", self.tree.work / "explain_out.txt"
        inp.write_text("Un pensiero personale.", encoding="utf-8")
        self.ollama.text = "## Spiegazione\nSpiegato."
        self.assertEqual(self.qc.run_action("explain", ["x", str(inp), str(out)]), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "## Spiegazione\nSpiegato.")

    # ---- known defects: flipped by step S4 ----

    @unittest.expectedFailure
    def test_C01_empty_section_cleanup_is_not_cubic(self):
        """C01: the explain-mode regex backtracks cubically (800 blank lines ~ 5.8 s)."""
        code = (
            "import sys; sys.path.insert(0, r'%s'); import qwen_client as q, time; "
            "t = time.perf_counter(); q.clean_answer('## A\\n' + '\\n' * 800 + 'x', 'explain'); "
            "print(round(time.perf_counter() - t, 3))" % self.tree.root
        )
        rc, out, _ = run_with_timeout(code, 2.0, cwd=str(self.tree.root))
        self.assertIsNotNone(rc, "timed out after 2 s")
        self.assertLess(float(out.strip().splitlines()[-1]), 0.5)

    @unittest.expectedFailure
    def test_C02_truncated_answer_is_an_error(self):
        """C02: done_reason == 'length' is accepted as a complete answer."""
        self.ollama.scenario = "length"
        inp, out = self.tree.work / "input.txt", self.tree.work / "trunc_out.txt"
        inp.write_text("testo lungo", encoding="utf-8")
        rc = self.qc.run_action("rewrite", ["x", str(inp), str(out)])
        self.assertNotEqual(rc, 0)
        self.assertFalse(out.exists())

    @unittest.expectedFailure
    def test_C02_stream_without_done_is_an_error(self):
        """C02: a stream that ends without a done chunk is treated as complete."""
        self.ollama.scenario = "no_done"
        self.ollama.text = "risposta interrotta"
        with self.qc.open_stream([{"role": "user", "content": "x"}], "explain") as r:
            with self.assertRaises(RuntimeError):          # K4: StreamIncomplete(RuntimeError)
                list(self.qc.stream_pieces(r))

    @unittest.expectedFailure
    def test_C12_rewrite_keeps_a_legitimate_first_line(self):
        """C12: INTRO_RE has no word boundary: 'Okay so the plan is:' is dropped."""
        text = "Okay so the plan is:\n\n- buy milk"
        self.assertEqual(self.qc.clean_answer(text, "rewrite"), text)

    @unittest.expectedFailure
    def test_C12_rewrite_keeps_multiple_code_blocks(self):
        """C12: the greedy fence unwrap breaks answers with two code blocks."""
        text = "```lua\nprint(1)\n```\n\nand then\n\n```lua\nprint(2)\n```"
        self.assertEqual(self.qc.clean_answer(text, "rewrite"), text)

    @unittest.expectedFailure
    def test_C16_malformed_config_is_reported(self):
        """C16: a duplicate key makes load_config silently fall back to all defaults."""
        with AppTree(config_text="[qwen]\nmodel = mine\nmodel = again\n") as tree:
            tree.load("qwen_client")
            self.assertTrue((tree.work / "config_warning.txt").exists())

    @unittest.expectedFailure
    def test_C24_system_proxy_is_not_used_for_ollama(self):
        """C24 / H20: HTTP_PROXY routes the localhost Ollama call through a proxy."""
        code = (
            "import sys; sys.path.insert(0, r'%s'); import qwen_client as q; "
            "print(q.chat([{'role': 'user', 'content': 'x'}], 'rewrite', timeout=5))" % self.tree.root
        )
        dead = "http://127.0.0.1:9"
        rc, out, _ = run_with_timeout(code, 20, cwd=str(self.tree.root),
                                      env={"HTTP_PROXY": dead, "http_proxy": dead,
                                           "NO_PROXY": "", "no_proxy": ""})
        self.assertEqual(rc, 0, out)
        self.assertIn("Testo corretto.", out)


if __name__ == "__main__":
    unittest.main()
