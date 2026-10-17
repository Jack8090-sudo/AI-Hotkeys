"""Hotkey validation parity (S8a, I2).

tests/fixtures/hotkey_vectors.json is asserted here against settings.valid_hotkey
(the authority) and by tests/ahk/run.ahk against ValidHotkey in lib/Util.ahk, so the
settings page and main.ahk accept exactly the same [tasti] keys.
"""

import json
import unittest

from tests.support import FIXTURES, AppTree

VECTORS = json.loads((FIXTURES / "hotkey_vectors.json").read_text(encoding="utf-8"))


class HotkeyParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.settings = cls.tree.load("settings")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_vectors_are_well_formed(self):
        valid, invalid = VECTORS["valid"], VECTORS["invalid"]
        self.assertGreater(len(valid), 10)
        self.assertGreater(len(invalid), 10)
        self.assertFalse(set(valid) & set(invalid), "a vector is listed as both valid and invalid")
        self.assertEqual(len(valid), len(set(valid)), "duplicate valid vector")
        self.assertEqual(len(invalid), len(set(invalid)), "duplicate invalid vector")
        # The AHK runner only decodes these JSON escapes: keep the fixture within them
        raw = (FIXTURES / "hotkey_vectors.json").read_text(encoding="utf-8")
        for esc in ("\\b", "\\f", "\\r", "\\/"):
            self.assertNotIn(esc, raw)

    def test_valid_vectors(self):
        for key in VECTORS["valid"]:
            with self.subTest(key=key):
                self.assertTrue(self.settings.valid_hotkey(key))

    def test_invalid_vectors(self):
        for key in VECTORS["invalid"]:
            with self.subTest(key=key):
                self.assertFalse(self.settings.valid_hotkey(key))

    def test_defaults_are_valid(self):
        # I1: the default keys must pass validation, or the fallback would be invalid too
        for default in self.settings.KEYS.values():
            with self.subTest(key=default):
                self.assertIn(default, VECTORS["valid"])


if __name__ == "__main__":
    unittest.main()
