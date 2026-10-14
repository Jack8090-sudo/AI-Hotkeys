"""Test di config_edit.set_values: modifica config.ini senza rovinarlo.

Uso: python test_config_edit.py
"""

import tempfile
import unittest
from pathlib import Path

import config_edit

SAMPLE = (
    "﻿; commento in cima\r\n"
    "[qwen]\r\n"
    "; modello\r\n"
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
                "aspetto": {"tema": "chiaro", "colore": "menta"},   # cambia + nuova chiave
                "tasti": {"spiega": "F8"},                          # sezione nuova
            })

            raw = path.read_bytes()
            self.assertTrue(raw.startswith(config_edit.BOM))
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))      # solo CRLF
            text = raw.decode("utf-8-sig")
            self.assertIn("; commento in cima", text)
            self.assertIn("; modello", text)

            values = config_edit.read_values(path)
            self.assertEqual(values["aspetto"], {"tema": "chiaro", "colore": "menta"})
            self.assertEqual(values["tasti"], {"spiega": "F8"})
            self.assertEqual(values["qwen"], {"model": "qwen3.5:9b"})
            self.assertEqual(values["obsidian"], {"window_title": "To-Do"})

            # la chiave nuova sta dentro [aspetto], prima di [obsidian]
            self.assertLess(text.index("colore = menta"), text.index("[obsidian]"))


if __name__ == "__main__":
    unittest.main()
