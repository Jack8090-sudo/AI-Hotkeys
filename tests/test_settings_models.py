"""Model picker (MODEL2): Gemma 4 by default, other models only if installed locally, never cloud.

Picker data from a fake Ollama /api/tags, save-time validation, the Ollama-down
fallback, the /api/models endpoint, and the runtime refusal of cloud models.
"""

import contextlib
import http.client
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests.support import AppTree, FakeOllama

TOKEN = "test-token-models-123456"

TAGS = [
    {"name": "gemma4:e4b-it-qat", "details": {"parameter_size": "8.0B", "quantization_level": "Q4_0"}},
    "gemma4:12b-it-qat",
    "qwen3.5:9b",
    "llama3.2",                                            # untagged: Ollama lists it as :latest too
    "gpt-oss:120b-cloud",                                  # cloud by tag suffix
    "glm-4.6:cloud",
    {"name": "kimi-k2:1t", "remote_host": "https://ollama.com:443", "remote_model": "kimi-k2:1t"},
]


class ModelPickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = FakeOllama(models=list(TAGS))
        cls.tree = AppTree(ollama_url=cls.ollama.url)
        cls.s = cls.tree.load("settings")

    @classmethod
    def tearDownClass(cls):
        cls.ollama.close()
        cls.tree.close()

    def setUp(self):
        self.ollama.models = list(TAGS)

    # ---- picker data ----

    def test_choices_put_gemma_first_and_hide_cloud_models(self):
        c = self.s.model_choices()
        self.assertTrue(c["reachable"])
        self.assertEqual(c["default"], "gemma4:e4b-it-qat")
        self.assertEqual([m["name"] for m in c["recommended"]],
                         ["gemma4:e4b-it-qat", "gemma4:e2b-it-qat", "gemma4:12b-it-qat"])
        self.assertEqual([m["installed"] for m in c["recommended"]], [True, False, True])
        self.assertTrue(all(m["label"] for m in c["recommended"]))
        self.assertEqual([m["name"] for m in c["others"]], ["llama3.2", "qwen3.5:9b"])
        self.assertEqual(c["cloud_hidden"], 3)
        self.assertEqual(c["current"], "test-model:1b")
        self.assertEqual(c["cloud_in_config"], "")

    def test_other_model_details_are_passed_on(self):
        self.ollama.models = [{"name": "mistral:7b", "details": {"parameter_size": "7.2B", "quantization_level": "Q4_K_M"}}]
        self.assertEqual(self.s.model_choices()["others"], [{"name": "mistral:7b", "detail": "7.2B · Q4_K_M"}])

    def test_is_cloud_model(self):
        qc = self.tree.load("qwen_client")
        for name in ("gpt-oss:120b-cloud", "glm-4.6:cloud", "QWEN3-CODER:480B-CLOUD", " deepseek-v3.1:671b-cloud "):
            with self.subTest(name=name):
                self.assertTrue(qc.is_cloud_model(name))
        for name in ("gemma4:e4b-it-qat", "qwen3.5:9b", "cloudy:7b", "llama3.2", "", None):
            with self.subTest(name=name):
                self.assertFalse(qc.is_cloud_model(name))

    # ---- validation ----

    def test_validate_accepts_installed_and_recommended_models(self):
        for name in ("qwen3.5:9b", "llama3.2", "llama3.2:latest", "gemma4:e4b-it-qat",
                     "gemma4:e2b-it-qat"):                 # e2b: recommended, not installed yet
            with self.subTest(name=name):
                updates, errors = self.s.validate({"qwen.model": name})
                self.assertEqual(errors, {})
                self.assertEqual(updates["qwen"]["model"], name)

    def test_validate_rejects_cloud_and_unknown_models(self):
        for name, words in (("gpt-oss:120b-cloud", "Cloud models are not allowed"),
                            ("glm-4.6:cloud", "Cloud models are not allowed"),
                            ("kimi-k2:1t", "not installed"),          # remote entry: hidden, so not installed
                            ("mistral:7b", "ollama pull mistral:7b")):
            with self.subTest(name=name):
                updates, errors = self.s.validate({"qwen.model": name})
                self.assertIn(words, errors["qwen.model"])
                self.assertNotIn("qwen", updates)

    def test_validate_keeps_the_other_fields_of_a_bad_model_save(self):
        updates, errors = self.s.validate({"qwen.model": "mistral:7b", "qwen.keep_alive": "1h"})
        self.assertIn("qwen.model", errors)
        self.assertEqual(updates["qwen"], {"keep_alive": "1h"})

    def test_cloud_model_in_config_is_shown_as_the_default(self):
        original = self.tree.config_file.read_bytes()
        self.tree.config_file.write_text("[qwen]\nmodel = gpt-oss:120b-cloud\n", encoding="utf-8")
        try:
            self.assertEqual(self.s.current_values()["qwen.model"], "gemma4:e4b-it-qat")
            self.assertEqual(self.s.model_choices()["cloud_in_config"], "gpt-oss:120b-cloud")
        finally:
            self.tree.config_file.write_bytes(original)

    def test_model_note_after_saving_a_model_that_is_not_downloaded(self):
        self.assertIn("ollama pull gemma4:e2b-it-qat", self.s.model_note({"qwen": {"model": "gemma4:e2b-it-qat"}}))
        self.assertIsNone(self.s.model_note({"qwen": {"model": "gemma4:e4b-it-qat"}}))
        self.assertIsNone(self.s.model_note({"aspetto": {"tema": "nero"}}))


class OllamaDownTest(unittest.TestCase):
    """Ollama not reachable: the recommended list only, and only recommended names can be saved."""

    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()                         # ollama_url points at a closed port
        cls.s = cls.tree.load("settings")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_choices_without_ollama(self):
        c = self.s.model_choices()
        self.assertFalse(c["reachable"])
        self.assertEqual(c["current"], "test-model:1b")
        self.assertEqual(len(c["recommended"]), 3)
        self.assertFalse(any(m["installed"] for m in c["recommended"]))
        self.assertEqual((c["others"], c["cloud_hidden"]), ([], 0))

    def test_validate_without_ollama(self):
        self.assertEqual(self.s.validate({"qwen.model": "gemma4:12b-it-qat"})[1], {})
        _, errors = self.s.validate({"qwen.model": "qwen3.5:9b"})
        self.assertIn("cannot be reached", errors["qwen.model"])
        _, errors = self.s.validate({"qwen.model": "gpt-oss:20b-cloud"})
        self.assertIn("Cloud models are not allowed", errors["qwen.model"])

    def test_page_still_opens_with_the_recommended_list(self):
        page = self.s.build_page(TOKEN)
        self.assertIn('"reachable": false', page)
        self.assertIn("gemma4:e2b-it-qat", page)


class ModelsHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = FakeOllama(models=list(TAGS))
        cls.tree = AppTree(ollama_url=cls.ollama.url)
        cls.s = cls.tree.load("settings")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.s.make_handler(cls.s.State(), TOKEN))
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.ollama.close()
        cls.tree.close()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()

    def test_models_endpoint_needs_the_header_token(self):
        self.assertEqual(self.request("GET", "/api/models")[0], 403)
        self.assertEqual(self.request("GET", f"/api/models?t={TOKEN}")[0], 403)
        status, body = self.request("GET", "/api/models", headers={"X-Token": TOKEN})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual([m["name"] for m in data["others"]], ["llama3.2", "qwen3.5:9b"])
        self.assertNotIn("cloud", body.decode("utf-8").replace("cloud_hidden", "").replace("cloud_in_config", ""))

    def test_page_embeds_the_picker_data(self):
        status, body = self.request("GET", f"/?t={TOKEN}")
        self.assertEqual(status, 200)
        self.assertIn(b'"recommended"', body)
        self.assertNotIn(b"gpt-oss:120b-cloud", body)

    def test_save_cloud_is_rejected_and_writes_nothing(self):
        before = self.tree.config_file.read_bytes()
        status, body = self.request("POST", "/api/save", json.dumps({"qwen.model": "glm-4.6:cloud"}),
                                    {"X-Token": TOKEN, "Content-Type": "application/json"})
        self.assertEqual(status, 422)
        self.assertIn("Cloud models are not allowed", json.loads(body)["errors"]["qwen.model"])
        self.assertEqual(self.tree.config_file.read_bytes(), before)

    def test_save_recommended_not_installed_returns_the_pull_command(self):
        original = self.tree.config_file.read_bytes()
        try:
            status, body = self.request("POST", "/api/save", json.dumps({"qwen.model": "gemma4:e2b-it-qat"}),
                                        {"X-Token": TOKEN, "Content-Type": "application/json"})
            self.assertEqual(status, 200)
            reply = json.loads(body)
            self.assertEqual(reply["values"]["qwen.model"], "gemma4:e2b-it-qat")
            self.assertIn("ollama pull gemma4:e2b-it-qat", reply["model_note"])
            self.assertEqual(reply["models"]["current"], "gemma4:e2b-it-qat")
        finally:
            self.tree.config_file.write_bytes(original)


class RuntimeCloudGuardTest(unittest.TestCase):
    """qwen_client never sends text to a cloud model (K1 message, K6 fallback)."""

    CLOUD = "Cloud models are not allowed: AI-Hotkeys keeps your text on this PC. Choose a local model in Settings."

    def test_hand_edited_cloud_model_falls_back_with_a_warning(self):
        with FakeOllama(models=["gemma4:e4b-it-qat", "gpt-oss:120b-cloud"]) as ollama:
            cfg = f"[qwen]\nmodel = gpt-oss:120b-cloud\nollama_url = {ollama.url}\n"
            with AppTree(config_text=cfg) as tree:
                qc = tree.load("qwen_client")
                self.assertEqual(qc.MODEL, "gemma4:e4b-it-qat")
                qc.report_config_warnings()
                warning = (tree.work / "config_warning.txt").read_text(encoding="utf-8")
                self.assertIn("gpt-oss:120b-cloud", warning)
                self.assertIn("Cloud models are not allowed", warning)
                self.assertIn("gemma4:e4b-it-qat", warning)
                self.assertTrue(qc.health()[0])

    def test_health_and_action_refuse_a_cloud_model(self):
        with FakeOllama(models=["gpt-oss:120b-cloud"]) as ollama, AppTree(ollama_url=ollama.url) as tree:
            qc = tree.load("qwen_client")
            qc.MODEL = "gpt-oss:120b-cloud"           # however it got there
            self.assertEqual(qc.health(), (False, self.CLOUD))
            inp, out = tree.work / "input.txt", tree.work / "output.txt"
            inp.write_text("testo privato", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(qc.run_action("rewrite", ["x", str(inp), str(out)]), 1)
            line1 = (tree.work / "error.txt").read_text(encoding="utf-8").split("\n")[0]
            self.assertEqual(line1, self.CLOUD)
            self.assertFalse(out.exists())
            self.assertEqual(ollama.chat_bodies(), [])      # nothing was sent

    def test_health_refuses_a_remote_entry_with_a_local_looking_name(self):
        tags = [{"name": "test-model:1b", "remote_host": "https://ollama.com:443", "remote_model": "x"}]
        with FakeOllama(models=tags) as ollama, AppTree(ollama_url=ollama.url) as tree:
            self.assertEqual(tree.load("qwen_client").health(), (False, self.CLOUD))


if __name__ == "__main__":
    unittest.main()
