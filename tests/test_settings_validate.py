"""settings.py validation (I2, I11): hotkeys, choices, numbers, texts, legacy values."""

import unittest

from tests.support import AppTree


class SettingsValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.s = cls.tree.load("settings")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_valid_hotkeys(self):
        for key in ("PgUp", "PgDn", "End", "Home", "F8", "^!r", "+F5", "#a", "^Space", "^Numpad1", "!Tab"):
            with self.subTest(key=key):
                self.assertTrue(self.s.valid_hotkey(key))

    def test_invalid_hotkeys(self):
        # bare letters/digits, unknown names, repeated modifiers, junk
        for key in ("a", "1", "Space", "Tab", "Enter", "Foo", "^Foo", "^^a", "", None, "^ a", "Pg Up", "^a;b"):
            with self.subTest(key=key):
                self.assertFalse(self.s.valid_hotkey(key))

    def test_validate_accepts_known_fields_and_ignores_unknown(self):
        updates, errors = self.s.validate({
            "aspetto.tema": "chiaro", "aspetto.testo": "18", "qwen.model": "gemma4:e4b-it-qat",
            "tasti.spiega": "F8", "unknown.field": "x",
        })
        self.assertEqual(errors, {})
        self.assertEqual(updates["aspetto"], {"tema": "chiaro", "testo": "18"})
        self.assertEqual(updates["qwen"], {"model": "gemma4:e4b-it-qat"})
        self.assertEqual(updates["tasti"], {"spiega": "F8"})
        self.assertNotIn("unknown", updates)

    def test_validate_rejects_bad_values(self):
        _, errors = self.s.validate({
            "aspetto.tema": "rosa", "aspetto.testo": "50", "qwen.ollama_url": "ftp://x",
            "tasti.correggi": "a",
        })
        self.assertEqual(set(errors), {"aspetto.tema", "aspetto.testo", "qwen.ollama_url", "tasti.correggi"})

    def test_validate_rejects_newline_injection_through_strip_and_regex(self):
        _, errors = self.s.validate({"qwen.model": "x\nkeep_alive = 0", "aspetto.tema": "scuro\n[evil]"})
        self.assertIn("qwen.model", errors)
        self.assertIn("aspetto.tema", errors)

    def test_validate_detects_duplicate_hotkeys(self):
        _, errors = self.s.validate({"tasti.correggi": "PgDn"})     # PgDn is already riassumi
        self.assertIn("tasti", errors)

    def test_current_values_maps_legacy_values(self):
        original = self.tree.config_file.read_bytes()
        self.tree.config_file.write_text(
            "[aspetto]\nmostra_originale = sì\n[searxng]\nweb_search = true\n[tasti]\nspiega = a\n",
            encoding="utf-8")
        try:
            v = self.s.current_values()
        finally:
            self.tree.config_file.write_bytes(original)
        self.assertEqual(v["aspetto.mostra_originale"], "si")
        self.assertEqual(v["searxng.web_search"], "auto")
        self.assertEqual(v["tasti.spiega"], "End")                 # invalid key -> default (I2)
        self.assertEqual(v["tasti.correggi"], "PgUp")              # missing key -> default (I11)

    def test_query_mode_choice_defaults_validates_and_saves(self):
        """D5 (S10): [searxng] query_mode is optional, defaults to allow_fallback (I11)."""
        self.assertEqual(self.s.defaults()["searxng.query_mode"], "allow_fallback")
        self.assertEqual(self.s.current_values()["searxng.query_mode"], "allow_fallback")   # key missing
        updates, errors = self.s.validate({"searxng.query_mode": "model"})
        self.assertEqual(errors, {})
        self.assertEqual(updates["searxng"], {"query_mode": "model"})
        _, errors = self.s.validate({"searxng.query_mode": "always"})
        self.assertIn("searxng.query_mode", errors)
        original = self.tree.config_file.read_bytes()
        self.tree.config_file.write_text("[searxng]\nquery_mode = bogus\n", encoding="utf-8")
        try:
            self.assertEqual(self.s.current_values()["searxng.query_mode"], "allow_fallback")
        finally:
            self.tree.config_file.write_bytes(original)

    def test_url_warning_only_for_other_computers(self):
        self.assertIsNone(self.s.url_warning({"qwen": {"ollama_url": "http://localhost:11434"}}))
        self.assertIsNone(self.s.url_warning({"qwen": {"ollama_url": "http://127.0.0.1:11434"}}))
        self.assertIsNone(self.s.url_warning({"aspetto": {"tema": "nero"}}))
        self.assertIn("192.168.1.5", self.s.url_warning({"qwen": {"ollama_url": "http://192.168.1.5:11434"}}))

    def test_token_ok_never_raises(self):
        pages = self.tree.load("pages")
        self.assertTrue(pages.token_ok("abc", "abc"))
        for bad in ("abd", "", None, "é", "\udcff", 123):
            with self.subTest(given=bad):
                self.assertFalse(pages.token_ok(bad, "abc"))

    # ---- defects fixed in step S7 (were expected failures in S1) ----

    def test_C36_hotkey_with_trailing_newline_is_rejected(self):
        """C36: KEY_RE ends with $, which also matches before a final newline."""
        self.assertFalse(self.s.valid_hotkey("PgUp\n"))

    def test_C35_non_ascii_digit_is_a_validation_error_not_a_crash(self):
        """C35: '²'.isdigit() is True, then int('²') raises ValueError."""
        _, errors = self.s.validate({"aspetto.testo": "²"})
        self.assertIn("aspetto.testo", errors)


if __name__ == "__main__":
    unittest.main()


class DefaultModelParityTest(unittest.TestCase):
    """The default model is written in five places: they must agree."""

    def test_default_model_is_the_same_everywhere(self):
        import configparser
        import re

        from tests.support import REPO

        tree = AppTree()
        try:
            expected = tree.load("qwen_client").DEFAULTS["model"]
            self.assertEqual(tree.load("settings").TEXTS[("qwen", "model")][0], expected)
        finally:
            tree.close()
        example = configparser.ConfigParser(interpolation=None)
        example.read(REPO / "config.example.ini", encoding="utf-8")
        self.assertEqual(example.get("qwen", "model"), expected)
        nsi = (REPO / "installer" / "sorgente" / "installer.nsi").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'^!define MODEL\s+"([^"]+)"', nsi, re.M).group(1), expected)
        html = (REPO / "static" / "settings.html").read_text(encoding="utf-8")
        self.assertIn(f"ollama pull {expected}", html)
