"""Built-in engine (backend = llama): llama-server on 127.0.0.1, OpenAI-style chat API."""

import unittest

from tests.support import AppTree, FakeLlama, free_port


def llama_config(port, extra=""):
    return f"[qwen]\nbackend = llama\nllama_port = {port}\n{extra}\n[searxng]\nweb_search = false\n"


class LlamaBackendTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeLlama(text="Testo corretto, grazie.")
        self.tree = AppTree(config_text=llama_config(self.fake.port))
        self.qc = self.tree.load("qwen_client")

    def tearDown(self):
        self.tree.close()
        self.fake.close()

    def test_defaults_pick_the_built_in_engine_and_its_prompts(self):
        self.assertEqual(self.qc.BACKEND, "llama")
        self.assertEqual(self.qc.MODEL, "lfm-hotkeys-Q6_K")
        prompts = self.tree.load("prompt_loader").prompts
        msgs = prompts.first_messages("rewrite", "ciao")
        self.assertEqual(len(msgs), 2)              # short prompt, no worked examples
        self.assertIn("correttore", msgs[0]["content"])

    def test_chat_sends_openai_request_with_the_mode_options(self):
        text, reason = self.qc.chat_ex([{"role": "user", "content": "x"}], "rewrite")
        self.assertEqual((text, reason), ("Testo corretto, grazie.", "stop"))
        body = self.fake.chat_bodies()[-1]
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_tokens"], 4096)
        self.assertAlmostEqual(body["temperature"], 0.1)
        self.assertAlmostEqual(body["repeat_penalty"], 1.05)
        self.assertNotIn("model", body)

    def test_stream_pieces_join_to_the_answer(self):
        with self.qc.open_stream([{"role": "user", "content": "x"}], "summarize") as r:
            self.assertEqual("".join(self.qc.stream_pieces(r)), "Testo corretto, grazie.")

    def test_stream_cut_by_length_raises_truncated(self):
        self.fake.scenario = "length"
        with self.qc.open_stream([{"role": "user", "content": "x"}], "explain") as r:
            with self.assertRaises(self.qc.TruncatedAnswer):
                "".join(self.qc.stream_pieces(r))

    def test_stream_without_end_raises_incomplete(self):
        self.fake.scenario = "no_done"
        with self.qc.open_stream([{"role": "user", "content": "x"}], "explain") as r:
            with self.assertRaises(self.qc.StreamIncomplete):
                "".join(self.qc.stream_pieces(r))

    def test_health_ok_without_starting_anything(self):
        ok, message = self.qc.health()
        self.assertTrue(ok, message)
        self.assertIn("lfm-hotkeys-Q6_K", message)

    def test_http_error_is_described_without_mentioning_ollama(self):
        self.fake.scenario = "http500"
        with self.assertRaises(Exception) as cm:
            self.qc.chat_ex([{"role": "user", "content": "x"}], "rewrite")
        message, detail = self.qc.describe_error(cm.exception)
        self.assertIn("HTTP 500", message)
        self.assertNotIn("Ollama", message)

    def test_run_action_writes_the_answer(self):
        d = self.tree.work / "in.txt"
        out = self.tree.work / "out.txt"
        d.write_text("domani nn vengo", encoding="utf-8")
        self.assertEqual(self.qc.run_action("rewrite", ["x", str(d), str(out)]), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "Testo corretto, grazie.")


class LlamaServerStartTest(unittest.TestCase):
    def test_another_program_on_the_port_is_reported(self):
        with FakeLlama(model_path=r"C:\other\some-other-model.gguf") as other:
            with AppTree(config_text=llama_config(other.port)) as tree:
                qc = tree.load("qwen_client")
                ok, message = qc.health()
                self.assertFalse(ok)
                self.assertIn(f"Port {other.port}", message)

    def test_missing_engine_is_reported_with_reinstall(self):
        with AppTree(config_text=llama_config(free_port())) as tree:
            qc = tree.load("qwen_client")           # the test tree has no llama\ folder
            ok, message = qc.health()
            self.assertFalse(ok)
            self.assertIn("reinstall", message)

    def test_command_line_is_local_and_follows_the_settings(self):
        with AppTree(config_text=llama_config(free_port(), "gpu = off\nkeep_alive = 5m")) as tree:
            qc = tree.load("qwen_client")
            cmd = qc.llama_command()
            self.assertEqual(cmd[cmd.index("--host") + 1], "127.0.0.1")
            self.assertEqual(cmd[cmd.index("-ngl") + 1], "0")
            self.assertEqual(cmd[cmd.index("--device") + 1], "none")
            self.assertEqual(cmd[cmd.index("--sleep-idle-seconds") + 1], "300")
            self.assertIn("--no-webui", cmd)

    def test_keep_alive_forever_never_sleeps(self):
        with AppTree(config_text=llama_config(free_port(), "keep_alive = -1")) as tree:
            self.assertNotIn("--sleep-idle-seconds", tree.load("qwen_client").llama_command())

    def test_keep_alive_values(self):
        with AppTree(config_text=llama_config(free_port())) as tree:
            ka = tree.load("qwen_client").keep_alive_seconds
            self.assertEqual([ka("30m"), ka("1h"), ka("45"), ka(0), ka(-1), ka("bogus")],
                             [1800, 3600, 45, 0, -1, 1800])

    def test_stop_without_pid_file_does_nothing(self):
        with AppTree(config_text=llama_config(free_port())) as tree:
            self.assertFalse(tree.load("qwen_client").stop_llama())

    def test_invalid_backend_falls_back_with_a_warning(self):
        with AppTree(config_text="[qwen]\nbackend = gpt\n") as tree:
            qc = tree.load("qwen_client")
            self.assertEqual(qc.BACKEND, "llama")
            self.assertTrue(any("backend" in w for w in qc.CONFIG_WARNINGS))


if __name__ == "__main__":
    unittest.main()
