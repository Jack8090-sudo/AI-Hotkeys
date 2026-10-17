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

    # ---- defects fixed by step S6b ----

    def test_C38_query_starting_with_no_is_not_a_refusal(self):
        """C38: NO_RE treated 'No Man's Sky ...' as the model saying NO."""
        self.assertEqual(self.ws.parse_queries("No Man's Sky mod list"), (False, ["No Man's Sky mod list"]))

    def test_C38_no_re_whole_answer_only(self):
        for answer in ("no!", "NO.", "No - è una nota personale", "NO: niente da cercare", "  **No**  "):
            with self.subTest(answer=answer):
                self.assertEqual(self.ws.parse_queries(answer), (True, []))
        for query in ("no-code tools", "No.js framework", "node js streams", "Nokia 3310 battery",
                      "no man's sky"):
            with self.subTest(query=query):
                self.assertEqual(self.ws.parse_queries(query), (False, [query]))

    def test_C25_linkify_leaves_code_alone(self):
        """C25: indexes inside code became links and unknown numbers were deleted."""
        text = "Usa `parts[1]` e poi arr[0]."
        self.assertEqual(self.ws.linkify(text, SOURCES), text)

    def test_C25_linkify_skips_fenced_code_and_links_prose(self):
        text = "Vedi [1].\n\n```lua\nlocal x = parts[1]\nprint(t [2])\n```\n\nPoi [2] e ``a`[1]`b``."
        out = self.ws.linkify(text, SOURCES)
        self.assertIn("```lua\nlocal x = parts[1]\nprint(t [2])\n```", out)
        self.assertIn("Vedi [\\[1\\]](https://create.roblox.com/docs/data-stores).", out)
        self.assertIn("Poi [\\[2\\]](https://devforum.roblox.com/t/123)", out)
        self.assertIn("``a`[1]`b``", out)

    def test_C25_unclosed_fence_protects_the_rest(self):
        text = "Testo [1].\n~~~\ncodice arr [9]\n"
        out = self.ws.linkify(text, SOURCES)
        self.assertTrue(out.endswith("~~~\ncodice arr [9]\n"))
        self.assertIn("[\\[1\\]](", out)

    def test_C25_glued_known_citation_is_still_linked(self):
        out = self.ws.linkify("Roblox[1] lo dice; arr[7] no.", SOURCES)
        self.assertIn("Roblox[\\[1\\]](https://create.roblox.com/docs/data-stores)", out)
        self.assertIn("arr[7] no.", out)

    def test_C25_cited_numbers_ignore_code_and_indexes(self):
        self.assertEqual(self.ws.cited_numbers("`a[2]` arr[1] vero [1]"), [1])
        self.assertEqual(self.ws.cited_numbers("Roblox[2] e x[9]", SOURCES), [2])

    def test_C25_urls_with_parentheses_and_spaces_are_encoded(self):
        sources = [{"n": 1, "title": "Lua (language)", "url": "https://en.wikipedia.org/wiki/Lua_(programming language)",
                    "body": "b", "text": "t"}]
        out = self.ws.add_sources("Lua [1].", sources)
        url = "https://en.wikipedia.org/wiki/Lua_%28programming%20language%29"
        self.assertIn(f"[\\[1\\]]({url})", out)
        self.assertIn(f"[Lua (language)]({url})", out)
        self.assertNotIn("Lua_(", out)

    def test_C38_fonti_heading_with_more_words_is_kept(self):
        """C38: '## Fonti di lag' and everything after it was deleted as if it were a sources list."""
        out = self.ws.add_sources("Intro [1].\n\n## Fonti di lag\nTroppi script.", SOURCES)
        self.assertIn("Troppi script.", out)

    def test_C38_trailing_sources_list_variants_are_removed(self):
        for tail in ("## Fonti\n- [1] vecchia", "### Fonti:\n1. vecchia\n2. altra\n", "**Fonti:**\n[1] vecchia",
                     "## Sources\n\n- vecchia\n\n"):
            with self.subTest(tail=tail):
                out = self.ws.add_sources("Testo [1].\n\n" + tail, SOURCES)
                self.assertNotIn("vecchia", out)
                self.assertTrue(out.startswith("Testo [\\[1\\]]("))

    def test_C38_fonti_list_in_the_middle_is_kept(self):
        out = self.ws.add_sources("## Fonti\n- una\n\nPoi altro testo [1].", SOURCES)
        self.assertIn("- una", out)
        self.assertIn("Poi altro testo", out)

    def test_C38_charset_parsing(self):
        cs = self.ws._charset
        self.assertEqual(cs('text/html; charset="ISO-8859-1"'), "ISO-8859-1")
        self.assertEqual(cs("text/html; Charset='windows-1252' ; x=y"), "windows-1252")
        self.assertEqual(cs("text/html; charset=no-such-codec"), "utf-8")
        self.assertEqual(cs("text/html; charset=base64"), "utf-8")
        self.assertEqual(cs("text/html"), "utf-8")
        self.assertEqual(cs(None), "utf-8")

    def test_C38_decode_honours_meta_charset(self):
        dec = self.ws._decode
        page = '<html><head><meta charset="iso-8859-1"></head><body>perché</body></html>'.encode("latin-1")
        self.assertIn("perché", dec(page, "text/html"))
        legacy = ('<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'
                  "<p>caffè</p>").encode("cp1252")
        self.assertIn("caffè", dec(legacy, "text/html"))
        # The header wins over the meta tag
        self.assertIn("perché", dec("<meta charset='latin-1'>perché".encode(), "text/html; charset=utf-8"))
        # Unknown names everywhere: UTF-8, no exception
        self.assertIn("ok", dec(b"<meta charset=nope>ok", "text/html; charset=bogus"))

    def test_C38_content_type_is_case_insensitive(self):
        self.assertTrue(self.ws._is_text_type("TEXT/HTML; Charset=UTF-8"))
        self.assertTrue(self.ws._is_text_type("Application/XHTML+XML"))
        self.assertTrue(self.ws._is_text_type("Text/Plain"))
        self.assertFalse(self.ws._is_text_type("application/pdf"))
        self.assertTrue(self.ws._is_plain_text("TEXT/PLAIN"))

    def test_C38_fetch_path_quoted_charset_and_upper_case_type(self):
        from unittest import mock

        from tests.support import StaticPages
        body = ("<html><body><main><p>" + "Questa è una pagina con accenti: perché, città. " * 6
                + "</p></main></body></html>").encode("latin-1")
        pages = StaticPages({"/p": (200, 'TEXT/HTML; charset="ISO-8859-1"', body),
                             "/t": (200, "Text/Plain", "solo testo semplice")})
        try:
            with mock.patch.object(self.ws, "_TEST_LOOPBACK_PORTS", frozenset([pages.port])), \
                    mock.patch.object(self.ws, "_cffi", lambda: None):
                text = self.ws.fetch_page_text(pages.url + "/p")
                plain = self.ws.fetch_page_text(pages.url + "/t")
        finally:
            pages.close()
        self.assertIn("perché, città.", text)
        self.assertEqual(plain, "solo testo semplice")
        self.assertEqual(len(pages.requests), 2)            # one download each, no retry

    def test_C39_text_in_div_only_pages_is_extracted(self):
        """C39: text that is only inside <div>/<span> was dropped."""
        html = "<html><body><div>Questa frase lunga sta solo dentro un div senza paragrafi.</div></body></html>"
        self.assertIn("Questa frase lunga", self.ws.html_to_text(html))

    def test_C39_div_text_keeps_spans_together_and_drops_short_menus(self):
        html = ("<body><div><a href=/>Home</a></div><div><span>Il testo di questa pagina</span> "
                "<span>sta in span dentro div.</span></div><div>Menu</div></body>")
        text = self.ws.html_to_text(html)
        self.assertIn("Il testo di questa pagina sta in span dentro div.", text)
        self.assertNotIn("Home", text)
        self.assertNotIn("Menu", text)

    def test_C39_div_text_is_not_used_when_blocks_have_content(self):
        para = "Paragrafo vero e abbastanza lungo del documento principale. " * 5
        html = f"<body><div>Testo sparso in un div che non serve qui, davvero.</div><p>{para}</p></body>"
        text = self.ws.html_to_text(html)
        self.assertIn("Paragrafo vero", text)
        self.assertNotIn("Testo sparso", text)

    def test_C39_unclosed_skip_tag_ends_with_its_parent(self):
        para = "Questo paragrafo viene dopo un form mai chiuso e deve restare."
        html = (f"<html><body><div><form><input name=q><p>campo</p></div>"
                f"<p>{para}</p><div><nav><ul><li>voce</ul></div><p>{para} Bis.</p></body></html>")
        text = self.ws.html_to_text(html)
        self.assertIn(para, text)
        self.assertIn(para + " Bis.", text)
        self.assertNotIn("campo", text)
        self.assertNotIn("voce", text)

    def test_C39_stray_end_tags_and_implicit_paragraphs(self):
        html = ("<body></span></form><p>Primo paragrafo abbastanza lungo da essere tenuto.<p>"
                "Secondo paragrafo abbastanza lungo da essere tenuto.</div></body>")
        text = self.ws.html_to_text(html)
        self.assertEqual(text.split("\n"), ["Primo paragrafo abbastanza lungo da essere tenuto.",
                                            "Secondo paragrafo abbastanza lungo da essere tenuto."])

    def test_uses_prompt_loader(self):
        import prompt_loader
        self.assertIs(self.ws.prompts, prompt_loader.prompts)


def _config(query_mode=None):
    from tests.support import DEFAULT_CONFIG, dead_url
    text = DEFAULT_CONFIG.format(ollama_url=dead_url(), keep_alive="30m", web_search="auto",
                                 searxng_url=dead_url(), todo_file="x.md")
    if query_mode is not None:
        text = text.replace("pages_to_read = 3\n", f"pages_to_read = 3\nquery_mode = {query_mode}\n")
    return text


TECH = "Uso StreamingEnabled con player_data"
PERSONAL = "Oggi ho pensato a mia nonna e alla sua cucina di quando ero piccolo, che bei ricordi davvero."


class QueryModeTest(unittest.TestCase):
    """D5: [searxng] query_mode = model | allow_fallback (default)."""

    def decide(self, query_mode, testo, answer, always=False):
        from unittest import mock
        tree = AppTree(config_text=_config(query_mode))
        try:
            ws = tree.load("websearch")
            calls = []

            def fake_chat(messages, mode, timeout=None):
                calls.append(messages)
                return answer
            with mock.patch.object(ws.qwen_client, "chat", fake_chat), mock.patch.object(ws, "ALWAYS", always):
                return ws.QUERY_MODE, ws.decide_queries(testo)
        finally:
            tree.close()

    def test_missing_or_invalid_key_falls_back_to_allow_fallback(self):
        for value in (None, "", "bogus"):
            with self.subTest(value=value):
                mode, _ = self.decide(value, "x", "NO")
                self.assertEqual(mode, "allow_fallback")
        self.assertEqual(self.decide(" Model ", "x", "NO")[0], "model")

    def test_allow_fallback_keeps_the_original_fallbacks(self):
        _, d = self.decide("allow_fallback", TECH, "")
        self.assertEqual(d["query"], ["StreamingEnabled player_data"])
        _, d = self.decide(None, PERSONAL, "NO", always=True)
        self.assertEqual(d["query"], [" ".join(PERSONAL.split()[:10])])

    def test_model_mode_never_sends_text_verbatim(self):
        _, d = self.decide("model", TECH, "")
        self.assertEqual(d["query"], [])
        _, d = self.decide("model", PERSONAL, "NO", always=True)
        self.assertEqual(d["query"], [])

    def test_model_mode_uses_model_queries(self):
        _, d = self.decide("model", TECH, "roblox streaming enabled\nroblox datastore")
        self.assertEqual(d["query"], ["roblox streaming enabled", "roblox datastore"])

    def test_model_mode_without_query_skips_the_search(self):
        from unittest import mock
        tree = AppTree(config_text=_config("model"))
        try:
            ws = tree.load("websearch")
            ws.ENABLED = True
            with mock.patch.object(ws, "ollama_ready", lambda: True), \
                    mock.patch.object(ws.qwen_client, "chat", lambda *a, **k: "NO"), \
                    mock.patch.object(ws, "ensure_running") as ensure, \
                    mock.patch.object(ws, "searx_search") as search:
                self.assertEqual(ws.gather_sources(TECH), ([], []))
            ensure.assert_not_called()
            search.assert_not_called()
        finally:
            tree.close()


if __name__ == "__main__":
    unittest.main()
