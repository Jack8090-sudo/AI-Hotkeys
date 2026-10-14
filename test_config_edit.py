"""Test for config_edit.set_values: edit config.ini without breaking it.

Usage: python test_config_edit.py
"""

import tempfile
import unittest
from pathlib import Path

import config_edit

SAMPLE = (
    "﻿; top comment\r\n"
    "[qwen]\r\n"
    "; model\r\n"
    "model = qwen3.5:9b\r\n"
    "\r\n"
    "[aspetto]\r\n"
    "tema = scuro\r\n"
    "\r\n"
    "[obsidian]\r\n"
    "window_title = To-Do\r\n"
)


class SetValuesTest(unittest.TestCase):
    def test_keeps_file_and_changes_only_what_asked(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.ini"
            path.write_bytes(SAMPLE.encode("utf-8"))

            config_edit.set_values(path, {
                "aspetto": {"tema": "chiaro", "colore": "menta"},   # change + new key
                "tasti": {"spiega": "F8"},                          # new section
            })

            raw = path.read_bytes()
            self.assertTrue(raw.startswith(config_edit.BOM))
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))      # CRLF only
            text = raw.decode("utf-8-sig")
            self.assertIn("; top comment", text)
            self.assertIn("; model", text)

            values = config_edit.read_values(path)
            self.assertEqual(values["aspetto"], {"tema": "chiaro", "colore": "menta"})
            self.assertEqual(values["tasti"], {"spiega": "F8"})
            self.assertEqual(values["qwen"], {"model": "qwen3.5:9b"})
            self.assertEqual(values["obsidian"], {"window_title": "To-Do"})

            # the new key stays inside [aspetto], before [obsidian]
            self.assertLess(text.index("colore = menta"), text.index("[obsidian]"))


if __name__ == "__main__":
    unittest.main()
