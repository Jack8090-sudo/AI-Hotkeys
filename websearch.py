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

import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
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

def _clamp(value, low, high):
    return max(low, min(high, value))


SEARX_URL = (CFG.get("searxng_url") or "http://127.0.0.1:8888").rstrip("/")
MAX_RESULTS = _clamp(_int(CFG.get("results"), 5), 1, 10)
PAGES_TO_READ = _clamp(_int(CFG.get("pages_to_read"), 3), 0, 5)

# Wall-clock limits (seconds) for reading result pages: each page, redirects
# included, and the whole parallel fetch phase.
PAGE_DEADLINE = 12.0
FETCH_DEADLINE = 15.0
# Ollama preflight before any web search (C22)
PREFLIGHT_TIMEOUT = 2.0

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


# =========================================================
# SSRF GUARD (C11)
# =========================================================
# Result URLs come from the internet (via SearXNG): a page must never make this
# PC fetch something on itself or on the local network (router admin pages,
# other local services, cloud metadata endpoints). Only the SearXNG URL itself
# (127.0.0.1) is contacted locally, and it does not go through this guard.
#
# Every hop of a redirect chain is checked again, and the connection goes to
# the very IP address that was checked (pinned), so a DNS answer that changes
# between check and connect (DNS rebinding) cannot redirect it:
#   - curl_cffi path: CURLOPT_RESOLVE host:port:ip, system proxies disabled;
#   - stdlib path: the socket is opened to the checked IP by hand
#     (Host header and TLS SNI/certificate check still use the host name).
# There is deliberately no configuration switch to turn this off.

ALLOWED_PORTS = (80, 443)
MAX_REDIRECTS = 5
_REDIRECT_CODES = (301, 302, 303, 307, 308)

_BLOCKED_HOSTS = {
    "localhost", "metadata", "metadata.google.internal", "metadata.goog",
    "instance-data", "instance-data.ec2.internal",
}
_BLOCKED_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4",
    "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8",
)]
# Cloud metadata addresses (most are also inside the ranges above)
_METADATA_IPS = {ipaddress.ip_address(a) for a in (
    "169.254.169.254", "169.254.170.2", "100.100.100.200", "192.0.0.192", "fd00:ec2::254",
)}
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

# Test seam: ports on 127.0.0.1 that the test suite may fetch from its local
# fixture servers. Always empty in the application.
_TEST_LOOPBACK_PORTS = frozenset()


class Target:
    """A URL that passed safe_url(): where to connect and what to ask for."""

    __slots__ = ("url", "scheme", "host", "port", "ip", "path")

    def __init__(self, url, scheme, host, port, ip, path):
        self.url, self.scheme, self.host, self.port, self.ip, self.path = url, scheme, host, port, ip, path

    def __repr__(self):
        return f"Target({self.url!r} -> {self.ip}:{self.port})"


def _embedded_v4(ip):
    """IPv4 address hidden inside an IPv6 one (mapped, compatible, NAT64, 6to4)."""
    if ip.version != 6:
        return None
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip in _NAT64 or int(ip) >> 32 == 0:      # 64:ff9b::a.b.c.d, ::a.b.c.d
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def ip_blocked(ip, port=None):
    """True when the address is not a public internet address."""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip.split("%")[0])
    inner = _embedded_v4(ip)
    if inner is not None and ip_blocked(inner, port):
        return True
    if ip.is_loopback and port in _TEST_LOOPBACK_PORTS and str(ip) == "127.0.0.1":
        return False
    if ip in _METADATA_IPS or any(ip in net for net in _BLOCKED_NETS if net.version == ip.version):
        return True
    return (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast
            or ip.is_unspecified or ip.is_reserved or not ip.is_global)


def _looks_numeric(host):
    """Hosts the URL standard parses as an IPv4 number: 2130706433, 0x7f.1, 127.1…"""
    last = host.rstrip(".").rsplit(".", 1)[-1]
    return bool(re.fullmatch(r"\d+|0[xX][0-9a-fA-F]*", last))


def _resolve(host, port):
    """All addresses of a host name (test seam)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def safe_url(url):
    """A Target when `url` may be fetched, otherwise None.

    Only http(s) on ports 80/443; the host must resolve exclusively to public
    addresses (no loopback, private/ULA, link-local, CGNAT, multicast,
    unspecified, reserved, IPv4-mapped forms of those, or cloud metadata).
    """
    try:
        parts = urllib.parse.urlsplit(url)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        port = parts.port
    except (ValueError, AttributeError):
        return None
    if scheme not in ("http", "https") or not host:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    if port not in ALLOWED_PORTS and port not in _TEST_LOOPBACK_PORTS:
        return None
    if "%" in host or any(c.isspace() for c in host):
        return None
    bare = host.rstrip(".")
    if bare in _BLOCKED_HOSTS or bare.endswith(".localhost"):
        return None

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is None and _looks_numeric(host):
        return None             # decimal / hex / octal / short IPv4 forms: never legitimate here

    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            addresses = _resolve(host, port)
        except (OSError, UnicodeError):
            return None
    if not addresses:
        return None
    try:
        if any(ip_blocked(a, port) for a in addresses):
            return None         # one internal address is enough to refuse
    except ValueError:
        return None
    if port not in ALLOWED_PORTS and any(a != "127.0.0.1" for a in addresses):
        return None             # test ports are only for the 127.0.0.1 fixtures

    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return Target(url, scheme, host, port, addresses[0].split("%")[0], path)


# =========================================================
# DOWNLOAD (redirects by hand, per-page deadline: C11 + C23)
# =========================================================

class _DeadlineExceeded(Exception):
    pass


def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise _DeadlineExceeded()
    return left


def _next_hop(url, location):
    if not location:
        return None
    return urllib.parse.urljoin(url, location.strip())


def _download_cffi(cr, url, deadline):
    """curl_cffi: (html or None, content-type). Raises on transport errors (urllib retries)."""
    from curl_cffi import CurlOpt

    for _hop in range(MAX_REDIRECTS + 1):
        target = safe_url(url)
        if not target:
            return None, ""
        ip = f"[{target.ip}]" if ":" in target.ip else target.ip
        session = cr.Session(curl_options={
            CurlOpt.RESOLVE: [f"{target.host}:{target.port}:{ip}"],
            CurlOpt.NOPROXY: "*",
        })
        try:
            r = session.get(url, impersonate="chrome", timeout=_remaining(deadline),
                            stream=True, allow_redirects=False)
            try:
                if r.status_code in _REDIRECT_CODES:
                    url = _next_hop(url, r.headers.get("location"))
                    if not url:
                        return None, ""
                    continue
                ctype = r.headers.get("content-type", "")
                if r.status_code != 200 or ("html" not in ctype and "text/plain" not in ctype):
                    return None, ctype
                chunks, size = [], 0
                for chunk in r.iter_content():
                    _remaining(deadline)
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_PAGE_BYTES:
                        break
                _remaining(deadline)
                return b"".join(chunks).decode(_charset(ctype), errors="replace"), ctype
            finally:
                r.close()
        finally:
            session.close()
    return None, ""     # too many redirects


_SSL_CONTEXT = None


def _ssl_context():
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


class _Watchdog:
    """Shuts the socket down at the deadline: a server that drips one byte at a
    time (headers included) cannot hold the read open past it."""

    def __init__(self, sock, deadline):
        self.sock = sock
        self.timer = threading.Timer(max(0.0, deadline - time.monotonic()), self._fire)
        self.timer.daemon = True
        self.timer.start()

    def _fire(self):
        try:
            socket.socket.shutdown(self.sock, socket.SHUT_RDWR)
        except Exception:
            pass

    def cancel(self):
        self.timer.cancel()


def _open_pinned(target, deadline):
    """GET target.path over a socket opened to the checked IP. Returns (sock, response, watchdog).

    The response is read straight from our own socket (http.client would close
    it after the headers of a "Connection: close" answer), so the per-read
    timeout and the watchdog keep working on the body.
    """
    timeout = _remaining(deadline)
    sock = socket.create_connection((target.ip, target.port), timeout=timeout)
    watchdog = _Watchdog(sock, deadline)
    try:
        if target.scheme == "https":
            sock = _ssl_context().wrap_socket(sock, server_hostname=target.host)
            watchdog.sock = sock
            conn = http.client.HTTPSConnection(target.host, target.port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(target.host, target.port, timeout=timeout)
        conn.sock = sock
        conn.request("GET", target.path, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Connection": "close",
        })
        response = http.client.HTTPResponse(sock, method="GET")
        response.begin()
        return sock, response, watchdog
    except BaseException:
        watchdog.cancel()
        try:
            sock.close()
        except Exception:
            pass
        raise


def _download_stdlib(url, deadline):
    """Standard library: (html or None, content-type)."""
    for _hop in range(MAX_REDIRECTS + 1):
        target = safe_url(url)
        if not target:
            return None, ""
        sock, r, watchdog = _open_pinned(target, deadline)
        try:
            if r.status in _REDIRECT_CODES:
                url = _next_hop(url, r.getheader("Location"))
                if not url:
                    return None, ""
                continue
            ctype = r.getheader("Content-Type", "") or ""
            if r.status != 200 or ("html" not in ctype and "text/plain" not in ctype):
                return None, ctype
            chunks, size = [], 0
            while size <= MAX_PAGE_BYTES:
                sock.settimeout(_remaining(deadline))
                chunk = r.read1(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            _remaining(deadline)
            raw = b"".join(chunks)[:MAX_PAGE_BYTES]
            return raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace"), ctype
        finally:
            watchdog.cancel()
            r.close()
            sock.close()
    return None, ""     # too many redirects


def _download(url, timeout=None):
    """Returns (html text or None, content-type). `timeout` is the wall-clock
    budget for the whole page, redirects included (default PAGE_DEADLINE)."""
    deadline = time.monotonic() + (PAGE_DEADLINE if timeout is None else timeout)
    if not safe_url(url):
        return None, ""
    cr = _cffi()
    if cr:
        try:
            return _download_cffi(cr, url, deadline)
        except _DeadlineExceeded:
            return None, ""
        except Exception:
            pass  # retry with the standard library
    try:
        return _download_stdlib(url, deadline)
    except Exception:
        return None, ""


def fetch_page_text(url, timeout=None):
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

def ollama_ready(timeout=None):
    """Fast check that Ollama answers (C22): without it the search is wasted work."""
    opener = getattr(qwen_client, "_OPENER", None) or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(qwen_client.OLLAMA_URL + "/api/tags",
                         timeout=PREFLIGHT_TIMEOUT if timeout is None else timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _usable(text):
    return bool(text) and len(text) >= 200


def fetch_pages(urls):
    """Page texts {index: text}, read in parallel.

    Stops as soon as PAGES_TO_READ usable pages are in, and in any case at
    FETCH_DEADLINE; pages still downloading are abandoned (each one ends by
    itself within PAGE_DEADLINE).
    """
    texts = {}
    if not urls:
        return texts
    ex = ThreadPoolExecutor(max_workers=len(urls))
    try:
        futures = {ex.submit(fetch_page_text, u): i for i, u in enumerate(urls)}
        usable = 0
        try:
            for f in as_completed(futures, timeout=FETCH_DEADLINE):
                try:
                    t = f.result()
                except Exception:
                    t = ""
                texts[futures[f]] = t
                if _usable(t):
                    usable += 1
                    if usable >= PAGES_TO_READ:
                        break
        except FuturesTimeout:
            pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return texts


def gather_sources(testo):
    """Returns (sources, queries). sources = [] when searching is not possible."""
    if not ENABLED:
        return [], []

    # First decide whether searching is needed: for a text that explains itself
    # nothing is searched (and SearXNG is not started at all).
    status("Checking whether a search is needed…")
    # Ollama down: no search at all, the final call reports the error (C22)
    if not ollama_ready():
        return [], []
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
        texts = fetch_pages([r["url"] for r in to_fetch])
        read = 0
        for i, r in enumerate(to_fetch):     # search-rank order among the pages that arrived
            t = texts.get(i, "")
            if _usable(t) and read < PAGES_TO_READ:
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
