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

    # ---- defects fixed in step S4 (were expected failures in S1) ----

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

    def test_C02_truncated_answer_is_an_error(self):
        """C02: done_reason == 'length' is accepted as a complete answer."""
        self.ollama.scenario = "length"
        inp, out = self.tree.work / "input.txt", self.tree.work / "trunc_out.txt"
        inp.write_text("testo lungo", encoding="utf-8")
        rc = self.qc.run_action("rewrite", ["x", str(inp), str(out)])
        self.assertNotEqual(rc, 0)
        self.assertFalse(out.exists())

    def test_C02_stream_without_done_is_an_error(self):
        """C02: a stream that ends without a done chunk is treated as complete."""
        self.ollama.scenario = "no_done"
        self.ollama.text = "risposta interrotta"
        with self.qc.open_stream([{"role": "user", "content": "x"}], "explain") as r:
            with self.assertRaises(RuntimeError):          # K4: StreamIncomplete(RuntimeError)
                list(self.qc.stream_pieces(r))

    def test_C12_rewrite_keeps_a_legitimate_first_line(self):
        """C12: INTRO_RE has no word boundary: 'Okay so the plan is:' is dropped."""
        text = "Okay so the plan is:\n\n- buy milk"
        self.assertEqual(self.qc.clean_answer(text, "rewrite"), text)

    def test_C12_rewrite_keeps_multiple_code_blocks(self):
        """C12: the greedy fence unwrap breaks answers with two code blocks."""
        text = "```lua\nprint(1)\n```\n\nand then\n\n```lua\nprint(2)\n```"
        self.assertEqual(self.qc.clean_answer(text, "rewrite"), text)

    def test_C16_malformed_config_is_reported(self):
        """C16: a duplicate key makes load_config silently fall back to all defaults."""
        with AppTree(config_text="[qwen]\nmodel = mine\nmodel = again\n") as tree:
            tree.load("qwen_client")
            self.assertTrue((tree.work / "config_warning.txt").exists())

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


    # ---- S4: contracts K1 (error.txt), K4 (API), K6 (config warnings), D4, H24 ----

    def test_K4_chat_still_returns_text_and_chat_ex_adds_done_reason(self):
        msgs = [{"role": "user", "content": "x"}]
        self.assertEqual(self.qc.chat(msgs, "rewrite"), "Testo corretto.")
        self.assertEqual(self.qc.chat_ex(msgs, "rewrite"), ("Testo corretto.", "stop"))

    def test_K4_stream_incomplete_is_a_runtime_error(self):
        self.assertTrue(issubclass(self.qc.StreamIncomplete, RuntimeError))

    def run_rewrite(self, text="ciao"):
        inp, out = self.tree.work / "input.txt", self.tree.work / "k1_out.txt"
        if out.exists():
            out.unlink()
        inp.write_text(text, encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            rc = self.qc.run_action("rewrite", ["x", str(inp), str(out)])
        err = self.tree.work / "error.txt"
        line1 = err.read_text(encoding="utf-8").split("\n")[0] if err.exists() else None
        return rc, out.exists(), line1

    def test_K1_missing_model_message(self):
        self.ollama.scenario = "http404"
        rc, wrote, line1 = self.run_rewrite()
        self.assertEqual((rc, wrote), (1, False))
        self.assertEqual(line1, "Model 'test-model:1b' not found: run  ollama pull test-model:1b")

    def test_K1_truncated_answer_message(self):
        self.ollama.scenario = "length"
        rc, wrote, line1 = self.run_rewrite()
        self.assertEqual((rc, wrote), (3, False))
        self.assertIn("cut off", line1)

    def test_K1_too_long_selection_is_refused_before_calling_ollama(self):
        before = len(self.ollama.requests)
        rc, wrote, line1 = self.run_rewrite("a" * (self.qc.max_input_chars("rewrite") + 1))
        self.assertEqual((rc, wrote), (3, False))
        self.assertIn("too long", line1)
        self.assertEqual(len(self.ollama.requests), before)

    def test_K1_success_clears_a_stale_error(self):
        (self.tree.work / "error.txt").write_text("old error\n", encoding="utf-8")
        rc, wrote, line1 = self.run_rewrite()
        self.assertEqual((rc, wrote, line1), (0, True, None))

    def test_K1_ollama_down_message(self):
        with AppTree() as tree:                        # ollama_url points at a closed port
            qc = tree.load("qwen_client")
            inp, out = tree.work / "input.txt", tree.work / "output.txt"
            inp.write_text("ciao", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(qc.run_action("rewrite", ["x", str(inp), str(out)]), 1)
            line1 = (tree.work / "error.txt").read_text(encoding="utf-8").split("\n")[0]
            self.assertEqual(line1, "Ollama is not running: start Ollama, then try again.")

    def test_K6_no_warning_file_for_a_good_config(self):
        self.assertFalse((self.tree.work / "config_warning.txt").exists())

    def test_quoted_paths_in_config_are_unquoted(self):
        with AppTree(todo_file=r'"C:\Notes\To-Do List.md"') as tree:
            self.assertEqual(str(tree.load("qwen_client").todo_file()), r"C:\Notes\To-Do List.md")

    def test_D4_prompts_user_overrides_and_broken_copy_falls_back(self):
        with AppTree() as tree:
            (tree.root / "prompts_user.py").write_text(
                (tree.root / "prompts.py").read_text(encoding="utf-8") + "\nNUM_CTX = 4096\n", encoding="utf-8")
            self.assertEqual(tree.load("qwen_client").prompts.NUM_CTX, 4096)
        with AppTree() as tree:
            (tree.root / "prompts_user.py").write_text("def broken(:\n", encoding="utf-8")
            qc = tree.load("qwen_client")
            self.assertEqual(qc.prompts.NUM_CTX, 16384)
            warning = (tree.work / "config_warning.txt").read_text(encoding="utf-8")
            self.assertIn("prompts_user.py has an error", warning)

    def test_H24_health(self):
        ok, message = self.qc.health()
        self.assertTrue(ok, message)
        self.ollama.version = "0.5.1"
        try:
            ok, message = self.qc.health()
            self.assertFalse(ok)
            self.assertIn("too old", message)
        finally:
            self.ollama.version = "0.12.0"
        cfg = (f"[qwen]\nmodel = other-model:7b\nollama_url = {self.ollama.url}\n")
        with AppTree(config_text=cfg) as tree:
            ok, message = tree.load("qwen_client").health()
            self.assertFalse(ok)
            self.assertIn("ollama pull other-model:7b", message)
        with AppTree() as tree:                       # nothing listening
            # default timeout: Windows takes ~2 s to refuse a closed localhost port
            self.assertEqual(tree.load("qwen_client").health(),
                             (False, "Ollama is not running: start Ollama, then try again."))

    def test_C01_guard_many_blank_lines_is_fast(self):
        import time
        t = time.perf_counter()
        self.qc.clean_answer("## A\n" + "\n" * 5000 + "x", "explain")
        self.assertLess(time.perf_counter() - t, 0.1)


if __name__ == "__main__":
    unittest.main()
