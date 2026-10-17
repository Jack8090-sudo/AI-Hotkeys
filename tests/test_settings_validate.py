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
            "aspetto.tema": "chiaro", "aspetto.testo": "18", "qwen.model": "qwen3.5:9b",
            "tasti.spiega": "F8", "unknown.field": "x",
        })
        self.assertEqual(errors, {})
        self.assertEqual(updates["aspetto"], {"tema": "chiaro", "testo": "18"})
        self.assertEqual(updates["qwen"], {"model": "qwen3.5:9b"})
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
