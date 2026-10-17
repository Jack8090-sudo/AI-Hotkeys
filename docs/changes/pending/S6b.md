# S6b — Web search: parsing, citations, extraction and query mode

User-visible:
- Citations in the End explanation are no longer turned into links inside code. `parts[1]`
  inside a code span or a fenced block (``` or ~~~) is left untouched (C25). Outside code, an
  index glued to a word, such as `arr[0]`, is left alone too. A glued number that is a real
  source, such as `Roblox[1]`, is still linked.
- Source URLs that contain `(`, `)` or spaces (for example Wikipedia pages like
  `Lua_(programming_language)`) now give working links. Those characters are percent-encoded,
  both in the citations and in the sources list.
- A search query that starts with the word "no" ("No Man's Sky mod list", "no-code tools") is
  searched. Only an answer that is just NO, or NO followed by punctuation and an explanation, means
  "no search" (C38).
- A heading like "## Fonti di lag" and the text under it are kept. Only a sources section the
  model writes itself at the end ("## Fonti", "## Sources" or "**Fonti:**", followed only by list
  lines) is removed. The real list is still added (C38).
- Pages are decoded with the right character set more often. Quoted charsets
  (`charset="ISO-8859-1"`) work, unknown or non-text charsets fall back to UTF-8 instead of
  failing (which used to cause a second download), and `<meta charset>` /
  `<meta http-equiv="Content-Type">` is used when the HTTP header has no charset. Content-type
  checks ignore case (`TEXT/HTML`) (C38).
- Pages whose text sits only in `<div>`/`<span>` elements are now read. That loose text is used
  only when the page's paragraphs, headings and lists hold less than 200 characters (C39).
- An unclosed `<form>`, `<nav>` or other skipped element no longer hides the rest of the page.
  It ends when its parent element closes. Stray end tags are ignored, and `<p>a<p>b` /
  `<li>a<li>b` close the previous element as browsers do (C39).
- New optional setting `[searxng] query_mode` (D5):
  - `allow_fallback` (default, today's behaviour): when a search is forced (technical terms or
    `web_search = always`) and the model writes no query, the technical terms found in the
    text, or its first 10 words, are searched.
  - `model`: only queries written by the model are sent to the search engine. Nothing is ever
    taken verbatim from the selected text. With no model query, there is no search and End
    explains without the web.
  - A missing or unknown value means `allow_fallback` (I11). S15 documents the key in
    `config.example.ini`. S10 adds it to the settings page, together with validation in
    `settings.py` `CHOICES`.
- The query prompt now comes from `prompt_loader`, so `prompts_user.py` (D4) is also used for the
  web-search query prompt.

Internal:
- `pyproject.toml` no longer has per-file ignores for `websearch.py` (B007 fixed with `_score`;
  B905 no longer applies, since there are no `zip()` calls left).
- `cited_numbers(text, sources=None)` takes an optional `sources` argument, so it counts the same
  citations that `linkify` links. Existing calls are unchanged.
- New helpers: `md_url`, `_decode`, `_is_text_type`, `_is_plain_text`, `_valid_charset`.
  `_charset` keeps its signature.

Tests: `tests/test_websearch_parse.py`. S1's 4 expected failures are now regular tests. New
tests cover code fences and spans, glued indexes, URL encoding, NO variants, the
trailing-sources detection, charset parsing (header, quotes, unknown, base64, meta), case-
insensitive content types, a stdlib fetch with a quoted Latin-1 charset (one download), div-only
pages, unclosed and stray tags, the `prompt_loader` import, and `query_mode` (default, invalid
value, allow_fallback fallbacks, model mode, no search without a model query).

Manual check still to do: an End run with the real SearXNG on a technical text and on a
personal note, with both `query_mode` values.
