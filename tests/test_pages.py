"""pages.py: safe JSON inside <script>, HTML escaping, look settings, font paths."""

import json
import unittest

from tests.support import AppTree


class PagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.pages = cls.tree.load("pages")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_script_json_cannot_close_the_script_tag(self):
        data = {"t": "</script><script>alert(1)</script>", "c": "<!-- x", "s": "a b c"}
        out = self.pages.script_json(data)
        self.assertNotIn("</", out)
        self.assertNotIn("<!--", out)
        self.assertNotIn(" ", out)
        self.assertNotIn(" ", out)
        self.assertEqual(json.loads(out.replace("<\\!--", "<!--")), data)

    def test_html_escape(self):
        self.assertEqual(self.pages.html_escape("<a href=\"x\">'&'</a>"),
                         "&lt;a href=&quot;x&quot;&gt;&#x27;&amp;&#x27;&lt;/a&gt;")

    def test_look_settings_defaults_and_clamping(self):
        look = self.pages.look_settings({"tema": "rosa", "testo": "99", "mostra_originale": "sì"})
        self.assertEqual(look["tema"], "scuro")
        self.assertEqual(look["testo"], 20)
        self.assertEqual(look["mostra_originale"], "si")
        self.assertEqual(self.pages.look_settings({"testo": "x"})["testo"], 16)
        self.assertEqual(self.pages.look_settings({"testo": "3"})["testo"], 14)

    def test_font_regex_rejects_traversal(self):
        ok = self.pages.FONT_RE.match
        self.assertTrue(ok("/fonts/ibm-plex-sans-latin-400-normal.woff2"))
        for bad in ("/fonts/../config.ini", "/fonts/..%2fconfig.ini", "/fonts/A.woff2",
                    "/fonts/a.woff", "/fonts/a.woff2.exe", "/fonts/sub/a.woff2"):
            with self.subTest(path=bad):
                self.assertIsNone(ok(bad))


if __name__ == "__main__":
    unittest.main()
