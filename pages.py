"""
AI-Hotkeys — shared parts of the local pages (results and settings):
fonts, shared style and appearance settings from config.ini.
"""

import json
import re
import secrets
import traceback
from http.server import ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
SERVER_LOG = BASE_DIR / "work" / "server.log"
SERVER_LOG_MAX = 1_000_000

# The pages only need their own inline script/style, fonts and requests to this server.
# No remote images, frames or forms: model output and web text cannot load anything.
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

# Seconds a client may take to send its request (slow or stuck connections are dropped)
REQUEST_TIMEOUT = 30


def token_ok(given, token):
    """Constant-time token check that never raises (non-ASCII input simply fails)."""
    try:
        return secrets.compare_digest(str(given or "").encode("utf-8", "surrogatepass"),
                                      token.encode("utf-8"))
    except Exception:
        return False


def log_server_error(text):
    """Append to work/server.log (restarted when it passes SERVER_LOG_MAX)."""
    try:
        SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if SERVER_LOG.exists() and SERVER_LOG.stat().st_size > SERVER_LOG_MAX else "a"
        with open(SERVER_LOG, mode, encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
    except OSError:
        pass


class LocalServer(ThreadingHTTPServer):
    """127.0.0.1 server whose request errors go to work/server.log, not to a hidden console."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        log_server_error(traceback.format_exc())

FONT_RE = re.compile(r"^/fonts/([a-z0-9-]+\.woff2)$")

# Allowed values and defaults for the [aspetto] section
LOOK = {
    "tema": ("scuro", ("scuro", "nero", "chiaro", "sistema")),
    "colore": ("ambra", ("ambra", "ghiaccio", "menta", "corallo", "viola", "neutro")),
    "larghezza": ("normale", ("stretta", "normale", "ampia")),
    "mostra_originale": ("si", ("si", "no")),
}
TEXT_SIZE = (16, 14, 20)   # default, minimum, maximum (px)


def _yes_no(value):
    v = str(value or "").strip().lower()
    if v in ("si", "sì", "yes", "true", "1", "on"):
        return "si"
    if v in ("no", "false", "0", "off"):
        return "no"
    return None


def look_settings(config):
    """Validated appearance settings, ready for the page."""
    out = {}
    for key, (default, allowed) in LOOK.items():
        value = str(config.get(key, default)).strip().lower()
        if key == "mostra_originale":
            value = _yes_no(value) or default
        out[key] = value if value in allowed else default
    try:
        size = int(str(config.get("testo", TEXT_SIZE[0])).strip())
    except ValueError:
        size = TEXT_SIZE[0]
    out["testo"] = max(TEXT_SIZE[1], min(TEXT_SIZE[2], size))
    return out


def theme_css():
    return (STATIC_DIR / "theme.css").read_text(encoding="utf-8")


def script_json(data):
    """JSON to put inside <script>: no "</script>" closing the tag."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        .replace("<!--", "<\\!--")
    )


def html_escape(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def try_serve_font(handler, path):
    """Serve fonts from static/fonts. True if the request was for a font."""
    m = FONT_RE.match(path)
    if not m:
        return False
    f = FONTS_DIR / m.group(1)
    if not f.is_file():
        handler.send_error(404)
        return True
    body = f.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "font/woff2")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "max-age=86400")
    handler.end_headers()
    handler.wfile.write(body)
    return True
