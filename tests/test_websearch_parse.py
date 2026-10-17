"""websearch parsing (I9): query decision, technical terms, citations, sources list."""

import unittest

from tests.support import AppTree

SOURCES = [
    {"n": 1, "title": "Data Stores", "url": "https://create.roblox.com/docs/data-stores", "body": "b", "text": "t"},
    {"n": 2, "title": "Forum [thread]", "url": "https://devforum.roblox.com/t/123", "body": "b", "text": "t"},
]


class WebsearchParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ws = cls.tree.load("websearch")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def test_parse_queries_no_variants(self):
        for answer in ("NO", "**NO**", "No.", "no, il testo si spiega da sé", "Risposta: NO"):
            with self.subTest(answer=answer):
                self.assertEqual(self.ws.parse_queries(answer), (True, []))

    def test_parse_queries_reads_up_to_two_clean_queries(self):
        answer = 'Query: "roblox datastore limits"\n- roblox datastore limits\n2. node js streams\n3. terza'
        self.assertEqual(self.ws.parse_queries(answer),
                         (False, ["roblox datastore limits", "node js streams"]))

    def test_technical_terms(self):
        terms = self.ws.technical_terms("Uso StreamingEnabled e player_data con DataStore:GetAsync() su YouTube")
        self.assertIn("StreamingEnabled", terms)
        self.assertIn("player_data", terms)
        self.assertTrue(any("GetAsync" in t for t in terms))
        self.assertNotIn("YouTube", terms)
        self.assertEqual(self.ws.technical_terms("Oggi ho pensato a mia nonna."), [])

    def test_linkify_known_and_invented_citations(self):
        out = self.ws.linkify("Vero [1]. Anche [1, 2]. Inventato [9].", SOURCES)
        self.assertIn("[\\[1\\]](https://create.roblox.com/docs/data-stores)", out)
        self.assertIn("[\\[2\\]](https://devforum.roblox.com/t/123)", out)
        self.assertNotIn("[9]", out)
        self.assertIn("Inventato.", out)                      # the space before [9] goes too

    def test_cited_numbers_and_add_sources(self):
        self.assertEqual(self.ws.cited_numbers("a [2] b [1; 2]"), [2, 1])
        out = self.ws.add_sources("Testo [1].\n\n## Fonti\n- vecchia lista", SOURCES)
        self.assertNotIn("vecchia lista", out)
        self.assertIn("## Sources", out)
        self.assertIn("## Other pages read", out)               # source 2 was read but not cited
        self.assertIn("Forum (thread)", out)                    # brackets in titles are neutralised

    def test_source_kind(self):
        self.assertEqual(self.ws.source_kind("https://it.wikipedia.org/wiki/X"), "enciclopedia")
        self.assertEqual(self.ws.source_kind("https://www.youtube.com/watch?v=1"), "video")
        self.assertEqual(self.ws.source_kind("https://example.com/x"), "pagina web")

    def test_disabled_web_search_returns_nothing(self):
        self.assertFalse(self.ws.ENABLED)                       # web_search = false in the test config
        self.assertEqual(self.ws.gather_sources("StreamingEnabled"), ([], []))

    def test_html_to_text_keeps_paragraphs_and_drops_scripts(self):
        html = ("<html><head><script>var x=1;</script><style>p{}</style></head><body>"
                "<nav>menu</nav><main><h1>Titolo</h1><p>Primo paragrafo utile del documento.</p>"
                "</main></body></html>")
        text = self.ws.html_to_text(html)
        self.assertIn("Primo paragrafo utile del documento.", text)
        self.assertNotIn("var x", text)

    # ---- known defects: flipped by step S6b ----

    @unittest.expectedFailure
    def test_C38_query_starting_with_no_is_not_a_refusal(self):
        """C38: NO_RE treats 'No Man's Sky ...' as the model saying NO."""
        self.assertEqual(self.ws.parse_queries("No Man's Sky mod list"), (False, ["No Man's Sky mod list"]))

    @unittest.expectedFailure
    def test_C25_linkify_leaves_code_alone(self):
        """C25: indexes inside code become links and unknown numbers are deleted."""
        text = "Usa `parts[1]` e poi arr[0]."
        self.assertEqual(self.ws.linkify(text, SOURCES), text)

    @unittest.expectedFailure
    def test_C38_fonti_heading_with_more_words_is_kept(self):
        """C38: '## Fonti di lag' and everything after it is deleted as if it were a sources list."""
        out = self.ws.add_sources("Intro [1].\n\n## Fonti di lag\nTroppi script.", SOURCES)
        self.assertIn("Troppi script.", out)

    @unittest.expectedFailure
    def test_C39_text_in_div_only_pages_is_extracted(self):
        """C39: text that is only inside <div>/<span> is dropped."""
        html = "<html><body><div>Questa frase lunga sta solo dentro un div senza paragrafi.</div></body></html>"
        self.assertIn("Questa frase lunga", self.ws.html_to_text(html))


if __name__ == "__main__":
    unittest.main()
