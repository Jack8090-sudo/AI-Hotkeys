"""
AI-Hotkeys — web search with local SearXNG for the End key.

Flow:
  1. Qwen writes 1-2 search queries from the selected text.
  2. SearXNG (http://127.0.0.1:8888) returns results as JSON.
  3. The text of the top pages is read too, not just the snippet.
  4. Sources go into the prompt numbered [1], [2]...; in the answer
     citations become links and a "Sources" list is appended at the end.

If SearXNG does not respond, End works as before (no web).
"""

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

import prompts
import qwen_client

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
STATUS_FILE = WORK_DIR / "status.txt"
SOURCES_FILE = WORK_DIR / "sources.json"
LAUNCHER = BASE_DIR / "searxng" / "avvia_searxng.py"

CFG = qwen_client.CONFIG


def _int(value, default):
    try:
        return int(str(value).strip())
    except Exception:
        return default


# web_search: auto (search only when needed) · always (always search) · false
_MODE = (CFG.get("web_search") or "auto").strip().lower()
ENABLED = _MODE not in ("0", "false", "no", "off", "")
ALWAYS = _MODE in ("always", "sempre")

SEARX_URL = (CFG.get("searxng_url") or "http://127.0.0.1:8888").rstrip("/")
MAX_RESULTS = _int(CFG.get("results"), 5)
PAGES_TO_READ = _int(CFG.get("pages_to_read"), 3)

# Sources budget in the prompt, in characters (4 chars ≈ 1 token):
# with NUM_CTX = 16384 there is room left for the selected text and the answer.
SOURCES_BUDGET = 10000
TOTAL_INPUT_CHARS = 36000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


# =========================================================
# STATUS (read by main.ahk for the tooltip near the mouse)
# =========================================================

def status(text):
    try:
        WORK_DIR.mkdir(exist_ok=True)
        STATUS_FILE.write_text(text, encoding="utf-8")
    except Exception:
        pass


# =========================================================
# SearXNG
# =========================================================

def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # No system proxy for 127.0.0.1
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def is_running(timeout=1.5):
    try:
        with _get(SEARX_URL + "/healthz", timeout) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_running(wait=25):
    """If SearXNG is off, try to start it and wait until it responds."""
    if is_running():
        return True
    if not LAUNCHER.exists():
        return False

    status("Starting the search engine…")
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else python)

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            [exe, str(LAUNCHER)],
            cwd=str(BASE_DIR),
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        return False

    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        if is_running():
            return True
        # The launcher exited without starting anything (error, or port taken
        # by another program): no point waiting. Details in work\searxng.log
        if proc.poll() is not None:
            return is_running()
    return False


def searx_search(query, timeout=12):
    params = urllib.parse.urlencode({"q": query, "format": "json", "safesearch": 0})
    with _get(f"{SEARX_URL}/search?{params}", timeout) as r:
        data = json.load(r)
    out = []
    for item in data.get("results", []):
        url = item.get("url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        out.append({
            "title": " ".join((item.get("title") or url).split()),
            "url": url,
            "snippet": " ".join((item.get("content") or "").split()),
        })
    return out


# =========================================================
# PAGE TEXT
# =========================================================

class _TextExtractor(HTMLParser):
    """Extracts readable text: paragraphs, headings, lists, code, tables.

    - Tables become "cell | cell | cell" rows (bare cells
      are too short and would be lost).
    - If the page has a long enough main content (<main> or <article>),
      only that is kept: menus, banners and sidebars stay out.
    - include_noscript: some sites (e.g. the Roblox DevForum, built with
      Discourse) put all the text inside <noscript>.
    """

    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "svg",
            "button", "select", "template", "iframe", "dialog"}
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
             "dd", "dt", "figcaption", "summary", "caption"}
    # Tags that separate words: without a space "<li>A</li><li>B</li>" becomes "AB"
    SPACE = {"br", "div", "li", "p", "td", "th", "dd", "dt", "tr", "img", "hr"}

    def __init__(self, include_noscript=False):
        super().__init__(convert_charrefs=True)
        self.skip_tags = set(self.SKIP) if include_noscript else self.SKIP | {"noscript"}
        self.skip = 0
        self.block = 0
        self.main = 0
        self.article = 0
        self.buf = []
        self.row = None    # cells of the current table row
        self.cell = None   # text of the current cell
        self.parts = []    # (text, inside_main, inside_article)

    # -----------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip += 1
            return
        if tag == "main":
            self.main += 1
        elif tag == "article":
            self.article += 1
        if self.skip:
            return

        if tag == "tr":
            self._end_row()
            self._flush()
            self.row = []
        elif tag in ("td", "th"):
            if self.row is None:
                self._flush()
                self.row = []
            self._end_cell()
            self.cell = []
        elif self.cell is not None:
            if tag in self.SPACE or tag in self.BLOCK:
                self.cell.append(" ")
        elif tag in self.BLOCK:
            self._flush()
            self.block += 1
        elif tag in self.SPACE:
            self.buf.append(" ")

    def handle_startendtag(self, tag, attrs):
        if self.skip:
            return
        if tag in self.SPACE:
            (self.cell if self.cell is not None else self.buf).append(" ")

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "main":
            self.main = max(0, self.main - 1)
        elif tag == "article":
            self.article = max(0, self.article - 1)
        if self.skip:
            return

        if tag in ("td", "th"):
            self._end_cell()
        elif tag in ("tr", "table"):
            self._end_row()
        elif self.cell is not None:
            if tag in self.BLOCK or tag in self.SPACE:
                self.cell.append(" ")
        elif tag in self.BLOCK:
            self._flush()
            self.block = max(0, self.block - 1)

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.block > 0:
            self.buf.append(data)

    # -----------------------------------------------------

    def _add(self, text):
        self.parts.append((text, self.main > 0, self.article > 0))

    def _flush(self):
        text = " ".join("".join(self.buf).split())
        self.buf = []
        # Drop menu and button fragments
        if len(text) >= 40 or (text and text[-1:] in ".:?!"):
            self._add(text)

    def _end_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
        self.cell = None

    def _end_row(self):
        self._end_cell()
        if self.row:
            cells = [c for c in self.row if c]
            # a single short-cell row is almost always an empty header
            if len(cells) > 1 or (cells and len(cells[0]) >= 40):
                self._add(" | ".join(cells))
        self.row = None

    def text(self):
        self._flush()
        self._end_row()
        parts = self.parts
        for flag in (1, 2):   # <main> first, then <article>
            chosen = [p for p in parts if p[flag]]
            if sum(len(p[0]) for p in chosen) >= 500:
                parts = chosen
                break
        seen, out = set(), []
        for text, *_ in parts:
            if text not in seen and not _is_boilerplate(text):
                seen.add(text)
                out.append(text)
        return "\n".join(out)


# Cookie banners, signup invites, legal notices
BOILERPLATE_RE = re.compile(
    r"\b(cookies?|consent|consenso|privacy policy|informativa|user agreement|"
    r"terms of (?:service|use)|termini e condizioni|sign in|sign up|log in|"
    r"accedi|iscriviti|registrati|subscribe|newsletter|accept all|accetta tutt[io])\b",
    re.IGNORECASE,
)


def _is_boilerplate(text):
    hits = {m.group(1).lower() for m in BOILERPLATE_RE.finditer(text)}
    return len(hits) >= 2


def html_to_text(html):
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    text = parser.text()
    if len(text) < 400 and "<noscript" in html:
        # Discourse and similar: the content for users without JavaScript lives in <noscript>
        parser = _TextExtractor(include_noscript=True)
        try:
            parser.feed(html)
            parser.close()
        except Exception:
            pass
        alt = parser.text()
        if len(alt) > len(text):
            text = alt
    return text


# Pages longer than this are not needed (and a huge PDF should not be downloaded)
MAX_PAGE_BYTES = 3_000_000
MAX_PAGE_TEXT = 60_000

_cffi_requests = None


def _cffi():
    """curl_cffi (bundled with SearXNG) poses as a real Chrome: many sites block Python requests (403 error) but not browser ones."""
    global _cffi_requests
    if _cffi_requests is None:
        lib = str(BASE_DIR / "searxng" / "lib")
        if lib not in sys.path:
            sys.path.append(lib)
        try:
            from curl_cffi import requests as cr
            _cffi_requests = cr
        except Exception:
            _cffi_requests = False
    return _cffi_requests or None


def _charset(ctype, default="utf-8"):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.IGNORECASE)
    return m.group(1) if m else default


def _download(url, timeout):
    """Returns (html text or None, content-type)."""
    cr = _cffi()
    if cr:
        try:
            r = cr.get(url, impersonate="chrome", timeout=timeout, stream=True, allow_redirects=True)
            try:
                ctype = r.headers.get("content-type", "")
                if r.status_code != 200 or ("html" not in ctype and "text/plain" not in ctype):
                    return None, ctype
                chunks, size = [], 0
                for chunk in r.iter_content():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_PAGE_BYTES:
                        break
                return b"".join(chunks).decode(_charset(ctype), errors="replace"), ctype
            finally:
                r.close()
        except Exception:
            pass  # retry with urllib

    try:
        with _get(url, timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text/plain" not in ctype:
                return None, ctype
            raw = r.read(MAX_PAGE_BYTES)
            return raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace"), ctype
    except Exception:
        return None, ""


def fetch_page_text(url, timeout=8):
    """All readable text of the page ("" if it cannot be read)."""
    html, ctype = _download(url, timeout)
    if not html:
        return ""
    text = html if "text/plain" in ctype else html_to_text(html)
    return text.strip()[:MAX_PAGE_TEXT]


# =========================================================
# PICKING THE USEFUL PARTS OF A PAGE
# =========================================================

_STOPWORDS = set("""
the and for with that this from are was were you your can not but all any has have had into
will would there their what when where which while who how why also may more most other some
such than then them they these those our out over only own same both each few very just about
after again because been before being below between could did does doing down during further
here his its let like made make many might must off once onto per should since still through
too under until upon via yet use used using get set new one two
che non per con una uno del della delle dei degli gli dal dalla dai come anche più sono era
alla alle allo agli nel nella nei nelle negli sul sulla sui questo questa questi queste quello
quella quelli quelle essere stato stata stati hanno ha ho tra fra loro suo sua suoi sue cosa
quando dove perché quindi però ogni molto poi già solo tutto tutti tutte fare fatto può
""".split())


def _terms(text):
    return {w for w in re.findall(r"[a-zà-ÿ0-9_]{3,}", text.lower()) if w not in _STOPWORDS}


def select_relevant(text, query_terms, text_terms, max_chars):
    """Pick the most useful paragraphs instead of the first max_chars characters.

    The first paragraph (usually title or introduction) is always kept; then
    paragraphs with the most words in common with the queries (weight 2) and with
    the selected text (weight 1) are added, restored to page order.
    """
    paras = [p for p in text.split("\n") if p.strip()]
    if not paras:
        return ""
    if sum(len(p) + 1 for p in paras) <= max_chars:
        return "\n".join(paras)

    def cut(p, n):
        if len(p) <= n:
            return p
        c = p.rfind(" ", 0, n)
        return p[: c if c > 0 else n] + " […]"

    first = cut(paras[0], max_chars // 3)
    chosen = {0: first}
    budget = max_chars - len(first) - 1

    scored = []
    for i, p in enumerate(paras[1:], start=1):
        t = _terms(p)
        score = 2 * len(t & query_terms) + len(t & text_terms)
        if score:
            scored.append((score, i))
    scored.sort(key=lambda x: (-x[0], x[1]))

    for score, i in scored:
        if budget < 80:
            break
        p = paras[i]
        if len(p) + 1 > budget:
            p = cut(p, budget - 1)
        chosen[i] = p
        budget -= len(p) + 1

    # If space remains, the rest from the start of the page
    i = 1
    while budget >= 80 and i < len(paras):
        if i not in chosen:
            p = paras[i] if len(paras[i]) + 1 <= budget else cut(paras[i], budget - 1)
            chosen[i] = p
            budget -= len(p) + 1
        i += 1

    out, prev = [], None
    for i in sorted(chosen):
        if prev is not None and i != prev + 1:
            out.append("[…]")
        out.append(chosen[i])
        prev = i
    return "\n".join(out)


# =========================================================
# QUERY
# =========================================================

# "NO", "**NO**", "No." and also "NO, il testo si spiega da sé": a real
# query never starts with the word "no" ("node js" is untouched).
NO_RE = re.compile(r"^\W*no\b", re.IGNORECASE)


# ---------------------------------------------------------
# Technical terms recognizable without asking the model
# ---------------------------------------------------------
# A text with names like StreamingEnabled, DataStore:GetAsync(),
# ServerScriptService.Main:42: or player_data talks about specific things that
# can be found on the web: there the search always runs. The model alone tends
# to say NO even for these (as tests showed).

# CamelCase names so common they alone do not deserve a search
_COMMON_NAMES = {
    "youtube", "iphone", "ipad", "imac", "macbook", "airpods", "whatsapp", "tiktok",
    "linkedin", "playstation", "powerpoint", "onedrive", "chatgpt", "paypal", "facetime",
}
# Everyday acronyms
_COMMON_ACRONYMS = {
    "OK", "NO", "SI", "TV", "PC", "PDF", "USB", "CEO", "FAQ", "LOL", "BTW", "FYI", "ASAP",
    "DM", "PM", "AM", "GB", "MB", "KB", "TB", "HD", "FPS", "IVA", "UE", "USA", "UK", "ID",
    "CV", "WC", "SMS", "GPS", "VIP", "DJ", "NB", "PS", "OMG", "WTF", "EU",
}

_TECH_PATTERNS = [
    # Line-number error: "Script:42: attempt to index nil" -> the message
    re.compile(r"\w:\d+:\s*([^\n]{5,90})"),
    # Member access with at least one uppercase letter: game:GetService, player.Name, Workspace.Car.Script
    re.compile(r"\b[A-Za-z_]\w+(?:[.:][A-Za-z_]\w+)+"),
    # Function call: GetAsync(, pcall(
    re.compile(r"\b[A-Za-z_]\w{2,}\("),
    # CamelCase: StreamingEnabled, MemoryStoreService, gRPC, getAsync
    re.compile(r"\b(?:[A-Z][a-z0-9]+[A-Z]\w*|[a-z]+[A-Z]\w*)\b"),
    # snake_case: player_data, max_retries
    re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b"),
    # Code file names
    re.compile(r"\b\w+\.(?:lua|luau|py|js|ts|json|rbxl|rbxm|cs|cpp|java|go|rs|yml|yaml|toml)\b"),
    # Technical acronyms: LOD, TTL, HTTP, RTX
    re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b"),
]


_KEYWORDS = {"function", "if", "for", "while", "return", "elseif", "and", "or", "not", "local"}


def technical_terms(testo):
    """The technical terms found in the text (empty list if none)."""
    found = []
    for i, pattern in enumerate(_TECH_PATTERNS):
        for m in pattern.finditer(testo):
            tok = (m.group(1) if i == 0 else m.group(0)).strip().rstrip("(")
            if i == 1 and not re.search(r"[A-Z]", tok):
                continue          # "www.sito.it", "e.g": no uppercase, no code
            if i == 1 and any(len(part) < 2 for part in re.split(r"[.:]", tok)):
                continue          # "U.S", "p.es"
            if i == 2 and tok in _KEYWORDS:
                continue
            if tok.lower() in _COMMON_NAMES:
                continue
            if i == 6 and (tok in _COMMON_ACRONYMS or tok.isdigit()):
                continue
            if tok not in found:
                found.append(tok)
    return found


def decide_queries(testo):
    """Decide whether to search and with which queries. Returns a dict with
    'query' (empty = no search), 'via' (how it was decided), 'termini'
    and 'risposta' (Qwen's raw answer)."""
    terms = technical_terms(testo)
    force = bool(terms) or ALWAYS
    try:
        answer = qwen_client.chat(prompts.query_messages(testo, force=force), "query", timeout=60)
    except Exception:
        answer = ""
    said_no, queries = parse_queries(answer)

    if force and not queries:
        # The model said NO anyway: search with the found terms,
        # or with the start of the text
        if terms:
            queries = [" ".join(terms[:5])]
        else:
            queries = [" ".join(" ".join(testo.split()).split(" ")[:10])]

    via = "termini tecnici" if terms else ("sempre" if ALWAYS else "decide Qwen")
    return {"query": queries, "via": via, "termini": terms, "risposta": answer}


LAST_DECISION = {}   # the last decision taken (for diagnostics)


def make_queries(testo):
    """The queries to search, or [] when the text explains itself: for a
    personal thought or note the found pages would be off-topic
    and the explanation would end up talking about something else."""
    global LAST_DECISION
    LAST_DECISION = decide_queries(testo)
    return LAST_DECISION["query"]


# Labels the model sometimes repeats from the prompt examples
LABEL_RE = re.compile(r"^\s*(?:risposta|query(?:\s+di\s+ricerca)?|answer)\s*:\s*", re.IGNORECASE)


def parse_queries(answer):
    """Reads Qwen's answer. Returns (said_no, queries)."""
    queries = []
    for line in answer.replace("\r", "").split("\n"):
        line = LABEL_RE.sub("", line)
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
        line = line.strip().strip('"«»“”*`').strip()
        if not line:
            continue
        if NO_RE.match(line):
            return True, []
        if 2 <= len(line) <= 120 and line.lower() not in (q.lower() for q in queries):
            queries.append(line)
        if len(queries) == 2:
            break
    return False, queries


# =========================================================
# FULL SEARCH
# =========================================================

def gather_sources(testo):
    """Returns (sources, queries). sources = [] when searching is not possible."""
    if not ENABLED:
        return [], []

    # First decide whether searching is needed: for a text that explains itself
    # nothing is searched (and SearXNG is not started at all).
    status("Checking whether a search is needed…")
    queries = make_queries(testo)
    if not queries:
        return [], []

    if not ensure_running():
        return [], queries

    status("Searching the web: " + queries[0][:60])
    results, seen = [], set()
    per_query = []
    with ThreadPoolExecutor(max_workers=len(queries)) as ex:
        futures = [ex.submit(searx_search, q) for q in queries]
        for f in futures:
            try:
                per_query.append(f.result())
            except Exception:
                per_query.append([])

    # Alternate query results: 1st of the first, 1st of the second, ...
    for i in range(max((len(r) for r in per_query), default=0)):
        for r in per_query:
            if i < len(r):
                key = r[i]["url"].split("#")[0].rstrip("/")
                if key not in seen:
                    seen.add(key)
                    results.append(r[i])
    results = prefer_docs(results, MAX_RESULTS)

    if not results:
        return [], queries

    # Page texts, in parallel. A couple extra are downloaded:
    # if a page is blocked (403) or is a PDF, the next one takes its place.
    to_fetch = results[: min(len(results), PAGES_TO_READ + 2)]
    if to_fetch and PAGES_TO_READ > 0:
        status(f"Reading {min(len(to_fetch), PAGES_TO_READ)} pages…")
        with ThreadPoolExecutor(max_workers=len(to_fetch)) as ex:
            texts = list(ex.map(lambda r: fetch_page_text(r["url"]), to_fetch))
        read = 0
        for r, t in zip(to_fetch, texts):
            if t and len(t) >= 200 and read < PAGES_TO_READ:
                r["text"] = t
                read += 1

    # Space in the prompt: snippets stay short, read pages
    # share the rest and only the most useful parts go in.
    budget = min(SOURCES_BUDGET, max(2000, TOTAL_INPUT_CHARS - len(testo)))
    snippets = [r for r in results if not r.get("text")]
    pages = [r for r in results if r.get("text")]
    for r in snippets:
        r["body"] = r["snippet"][:300]
    if pages:
        share = max(800, (budget - sum(len(r["body"]) for r in snippets)) // len(pages))
        q_terms = _terms(" ".join(queries))
        t_terms = _terms(testo[:4000])
        for r in pages:
            r["body"] = select_relevant(r["text"], q_terms, t_terms, share)
    for i, r in enumerate(results, start=1):
        r["n"] = i
        r["kind"] = source_kind(r["url"])

    return results, queries


# ---------------------------------------------------------
# Source type: a forum is not worth as much as documentation
# ---------------------------------------------------------

_FORUM_HINTS = ("devforum.", "forum", "reddit.com", "stackoverflow.com", "stackexchange.com",
                "superuser.com", "serverfault.com", "quora.com", "/t/", "community.", "answers.",
                "discord.com", "discussions.")
# Only typical real-documentation paths: "/guides/" or "/blog/"
# are also used by random third-party sites
_DOC_HINTS = ("/docs/", "/doc/", "/documentation", "/reference/", "/manual/", "/api/")
_DOC_HOSTS = ("docs.", "developer.", "developers.", "learn.microsoft.com", "luau.org",
              "luau-lang.org", "lua.org", "devdocs.io")
_VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "twitch.tv", "tiktok.com")


def source_kind(url):
    u = url.lower()
    host = urllib.parse.urlparse(u).netloc
    if any(h in host for h in _VIDEO_HOSTS):
        return "video"
    if any(h in u for h in _FORUM_HINTS):
        return "forum"
    if host.endswith("wikipedia.org"):
        return "enciclopedia"
    if any(host.startswith(h) or h in host for h in _DOC_HOSTS) or any(h in u for h in _DOC_HINTS):
        return "documentazione"
    if ".gov." in host or host.endswith(".gov") or host.endswith(".gov.it") or host.endswith(".europa.eu"):
        return "sito istituzionale"
    if "fandom.com" in host or "wiki" in host:
        return "wiki di appassionati"
    return "pagina web"


def prefer_docs(results, n, window=10, max_docs=2):
    """Among the first `window` results, up to `max_docs` documentation,
    encyclopedia or institutional-site pages go first; then the rest in order."""
    good = ("documentazione", "enciclopedia", "sito istituzionale")
    docs = [r for r in results[:window] if source_kind(r["url"]) in good][:max_docs]
    rest = [r for r in results if r not in docs]
    return (docs + rest)[:n]


def sources_block(sources):
    parts = []
    for s in sources:
        kind = s.get("kind") or source_kind(s["url"])
        parts.append(f"[{s['n']}] ({kind}) {s['title']} — {s['url']}\n{s['body']}")
    return "\n\n".join(parts)


# =========================================================
# CITATIONS
# =========================================================

CITE_RE = re.compile(r"\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\](?!\()")
CITE_WS_RE = re.compile(r"([ \t]*)\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\](?!\()")


def linkify(text, sources):
    """[1] → link to source 1. Non-existent numbers are removed."""
    by_n = {s["n"]: s for s in sources}

    def repl(m):
        nums = [int(x) for x in re.split(r"\s*[,;]\s*", m.group(2))]
        links = [f"[\\[{n}\\]]({by_n[n]['url']})" for n in nums if n in by_n]
        # Invented citation: the space before it goes too
        return m.group(1) + "".join(links) if links else ""

    return CITE_WS_RE.sub(repl, text)


def cited_numbers(text):
    nums = []
    for m in CITE_RE.finditer(text):
        for x in re.split(r"\s*[,;]\s*", m.group(1)):
            n = int(x)
            if n not in nums:
                nums.append(n)
    return nums


def _domain(url):
    host = urllib.parse.urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def add_sources(text, sources):
    """Links in citations + list at the end: first the cited sources, then the
    other pages read (even if Qwen did not cite them, the links are useful)."""
    if not sources:
        return text

    by_n = {s["n"]: s for s in sources}
    cited = [n for n in cited_numbers(text) if n in by_n]
    read = [s["n"] for s in sources if s.get("text") and s["n"] not in cited]

    # The model sometimes still writes its own "Fonti" section: remove it.
    text = re.sub(r"(?ims)^#{1,4}\s*fonti\b.*\Z", "", text).rstrip()
    text = linkify(text, sources)

    def line(n):
        src = by_n[n]
        title = src["title"].replace("[", "(").replace("]", ")")
        kind = src.get("kind") or source_kind(src["url"])
        return f"- **[{n}]** [{title}]({src['url']}) ({_domain(src['url'])}, {kind})"

    lines = []
    if cited:
        lines += ["", "", "## Sources"] + [line(n) for n in sorted(cited)]
    if read:
        lines += ["", "", "## Other pages read" if cited else "## Pages read"]
        lines += [line(n) for n in sorted(read)]
    return text + "\n".join(lines)


def save_sources(sources, queries):
    # The viewer does not need full page text (it uses "body")
    light = [{k: v for k, v in s.items() if k != "text"} for s in sources]
    try:
        SOURCES_FILE.write_text(
            json.dumps({"queries": queries, "sources": light}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_sources():
    try:
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        return data.get("sources", [])
    except Exception:
        return []
