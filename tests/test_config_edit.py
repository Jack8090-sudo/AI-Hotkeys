"""config_edit: edit config.ini without breaking comments, order, BOM or line endings (I12).

Run alone: python -m unittest tests.test_config_edit   (or: python test_config_edit.py)
"""

import configparser
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import AppTree

SAMPLE = (
    "﻿; top comment\r\n"
    "[qwen]\r\n"
    "; model\r\n"
    "model = gemma4:e4b-it-qat\r\n"
    "\r\n"
    "[aspetto]\r\n"
    "tema = scuro\r\n"
    "\r\n"
    "[obsidian]\r\n"
    "window_title = To-Do\r\n"
)


class ConfigEditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ce = cls.tree.load("config_edit")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "config.ini"

    def tearDown(self):
        self._tmp.cleanup()

    def test_keeps_file_and_changes_only_what_asked(self):
        self.path.write_bytes(SAMPLE.encode("utf-8"))
        self.ce.set_values(self.path, {
            "aspetto": {"tema": "chiaro", "colore": "menta"},   # change + new key
            "tasti": {"spiega": "F8"},                          # new section
        })
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(self.ce.BOM))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))      # CRLF only
        text = raw.decode("utf-8-sig")
        self.assertIn("; top comment", text)
        self.assertIn("; model", text)
        values = self.ce.read_values(self.path)
        self.assertEqual(values["aspetto"], {"tema": "chiaro", "colore": "menta"})
        self.assertEqual(values["tasti"], {"spiega": "F8"})
        self.assertEqual(values["qwen"], {"model": "gemma4:e4b-it-qat"})
        self.assertEqual(values["obsidian"], {"window_title": "To-Do"})
        # the new key stays inside [aspetto], before [obsidian]
        self.assertLess(text.index("colore = menta"), text.index("[obsidian]"))

    def test_lf_file_without_bom_stays_lf_without_bom(self):
        self.path.write_bytes(b"[aspetto]\ntema = scuro\n")
        self.ce.set_values(self.path, {"aspetto": {"tema": "nero"}})
        raw = self.path.read_bytes()
        self.assertFalse(raw.startswith(self.ce.BOM))
        self.assertNotIn(b"\r\n", raw)
        self.assertEqual(self.ce.read_values(self.path)["aspetto"]["tema"], "nero")

    def test_section_and_key_match_case_insensitively(self):
        self.path.write_bytes(b"[Aspetto]\nTema = scuro\n")
        self.ce.set_values(self.path, {"aspetto": {"tema": "chiaro"}})
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(text.count("[Aspetto]"), 1)
        self.assertEqual(text.lower().count("tema ="), 1)

    def test_missing_file_is_created(self):
        self.ce.set_values(self.path, {"tasti": {"correggi": "PgUp"}})
        self.assertEqual(self.ce.read_values(self.path), {"tasti": {"correggi": "PgUp"}})

    def test_read_values_skips_comments_and_lowercases_keys(self):
        self.path.write_bytes(b"; c\n# c\n[QWEN]\nModel = x\n")
        self.assertEqual(self.ce.read_values(self.path), {"qwen": {"model": "x"}})
        self.assertEqual(self.ce.read_values(Path(self._tmp.name) / "missing.ini"), {})

    def test_cli_sets_values_and_rejects_bad_arguments(self):
        self.path.write_bytes(b"[aspetto]\ntema = scuro\n")
        script = str(self.tree.root / "config_edit.py")
        ok = subprocess.run([sys.executable, script, str(self.path), "aspetto.tema=chiaro"],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(self.ce.read_values(self.path)["aspetto"]["tema"], "chiaro")
        bad = subprocess.run([sys.executable, script, str(self.path), "nodot=1"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)

    def test_save_leaves_no_temporary_file_and_keeps_trailing_newline(self):
        self.path.write_bytes(b"[aspetto]\ntema = scuro\n")
        self.ce.set_values(self.path, {"aspetto": {"tema": "nero"}})
        self.ce.set_values(self.path, {"aspetto": {"tema": "chiaro"}})
        self.assertEqual(self.path.read_bytes(), b"[aspetto]\ntema = chiaro\n")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["config.ini"])

    def test_invalid_names_are_rejected(self):
        for section, key in (("a]", "k"), ("a", "k=v"), ("a", ""), ("a", "k:v")):
            with self.subTest(section=section, key=key):
                with self.assertRaises(ValueError):
                    self.ce.set_values(self.path, {section: {key: "x"}})
        self.assertFalse(self.path.exists())          # nothing written

    # ---- C17 (fixed in S7) ----

    def test_C17_newline_in_value_is_rejected(self):
        """C17: a value with a newline must not inject new lines/sections."""
        self.path.write_bytes(b"[qwen]\nmodel = x\n")
        with self.assertRaises(ValueError):
            self.ce.set_values(self.path, {"qwen": {"model": "x\n[evil]\nz = 1"}})

    def test_C17_unicode_line_separator_in_comment_survives(self):
        """C17: splitlines() splits on U+2028 and corrupts the file for configparser."""
        self.path.write_bytes("; note tail\n[qwen]\nmodel = x\n".encode("utf-8"))
        self.ce.set_values(self.path, {"qwen": {"model": "y"}})
        parser = configparser.RawConfigParser()
        parser.read(self.path, encoding="utf-8-sig")     # must not raise
        self.assertEqual(parser.get("qwen", "model"), "y")

    def test_C17_colon_style_key_is_updated_not_duplicated(self):
        """C17: 'k: v' lines are not recognised, so a duplicate 'k = v' is appended."""
        self.path.write_bytes(b"[qwen]\nmodel: x\n")
        self.ce.set_values(self.path, {"qwen": {"model": "y"}})
        parser = configparser.RawConfigParser()
        parser.read(self.path, encoding="utf-8-sig")     # DuplicateOptionError today
        self.assertEqual(parser.get("qwen", "model"), "y")


if __name__ == "__main__":
    unittest.main()
