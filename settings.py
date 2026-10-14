"""
AI-Hotkeys — settings page.

Started from the tray-icon menu ("Settings"). Opens a local page
(127.0.0.1 only) that reads and writes config.ini. When config.ini changes,
AI-Hotkeys reloads itself and applies the new hotkeys.

Usage: python settings.py [--no-browser]
"""

import json
import re
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_edit
import pages

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.ini"
IDLE_TIMEOUT = 300

# Anti-DoS cap on POST request bodies (local, but token-gated).
MAX_BODY = 1_000_000


# =========================================================
# FIELDS: section, key, default, control
# =========================================================

# tema, colore, larghezza, mostra_originale and testo: single list in pages.py
CHOICES = {
    **{("aspetto", k): v for k, v in pages.LOOK.items()},
    ("aspetto", "avanzamento"): ("si", ["si", "no"]),
    ("comportamento", "sostituisci_testo"): ("si", ["si", "no"]),
    ("comportamento", "lunghezza"): ("normale", ["breve", "normale", "dettagliata"]),
    ("searxng", "web_search"): ("auto", ["auto", "always", "false"]),
    ("qwen", "keep_alive"): ("30m", ["5m", "10m", "30m", "1h", "-1", "0"]),
}

NUMBERS = {
    ("aspetto", "testo"): pages.TEXT_SIZE,
    ("searxng", "results"): (5, 3, 8),
    ("searxng", "pages_to_read"): (3, 0, 5),
}

TEXTS = {
    ("qwen", "model"): ("qwen3.5:9b", re.compile(r"^[\w.:\-/]{1,80}$")),
    ("qwen", "ollama_url"): ("http://localhost:11434", re.compile(r"^https?://[\w.\-]+(:\d{1,5})?(/[\w.\-/]*)?$")),
}

KEYS = {
    ("tasti", "correggi"): "PgUp",
    ("tasti", "riassumi"): "PgDn",
    ("tasti", "spiega"): "End",
}

# Keys allowed without Ctrl/Alt/Shift/Win: not needed for typing
SPECIAL_KEYS = {"PgUp", "PgDn", "End", "Home", "Ins", "Del", "Pause", "ScrollLock", "AppsKey",
                *(f"F{i}" for i in range(1, 25))}
KEY_RE = re.compile(r"^([\^!+#]*)([A-Za-z0-9]+)$")
NAMED_KEYS = SPECIAL_KEYS | {"Space", "Tab", "Enter", "Backspace", "Up", "Down", "Left", "Right",
                             *(f"Numpad{i}" for i in range(10)),
                             "NumpadAdd", "NumpadSub", "NumpadMult", "NumpadDiv", "NumpadDot", "NumpadEnter"}


def valid_hotkey(value):
    m = KEY_RE.match(value or "")
    if not m:
        return False
    mods, key = m.groups()
    if len(set(mods)) != len(mods):
        return False
    if len(key) == 1:
        return bool(mods) and key.isalnum()          # letters and digits only with a modifier
    if key not in NAMED_KEYS:
        return False
    return bool(mods) or key in SPECIAL_KEYS


def current_values():
    raw = config_edit.read_values(CONFIG_FILE)
    out = {}
    for (sec, key), (default, allowed) in CHOICES.items():
        v = raw.get(sec, {}).get(key, default).lower()
        if v in ("sì", "true", "yes"):
            v = "si" if "si" in allowed else v
        if v == "true" and key == "web_search":
            v = "auto"
        out[f"{sec}.{key}"] = v if v in allowed else default
    for (sec, key), (default, lo, hi) in NUMBERS.items():
        try:
            v = int(raw.get(sec, {}).get(key, default))
        except ValueError:
            v = default
        out[f"{sec}.{key}"] = max(lo, min(hi, v))
    for (sec, key), (default, rx) in TEXTS.items():
        v = raw.get(sec, {}).get(key, default)
        out[f"{sec}.{key}"] = v if rx.match(v) else default
    for (sec, key), default in KEYS.items():
        v = raw.get(sec, {}).get(key, default)
        out[f"{sec}.{key}"] = v if valid_hotkey(v) else default
    return out


def defaults():
    out = {f"{s}.{k}": d for (s, k), (d, _) in CHOICES.items()}
    out.update({f"{s}.{k}": d for (s, k), (d, _, _) in NUMBERS.items()})
    out.update({f"{s}.{k}": d for (s, k), (d, _) in TEXTS.items()})
    out.update({f"{s}.{k}": d for (s, k), d in KEYS.items()})
    return out


def validate(data):
    """Returns (updates for config_edit, errors per field)."""
    updates, errors = {}, {}
    for name, value in data.items():
        sec, _, key = name.partition(".")
        value = str(value).strip()
        if (sec, key) in CHOICES:
            if value not in CHOICES[(sec, key)][1]:
                errors[name] = "Value not allowed."
                continue
        elif (sec, key) in NUMBERS:
            _, lo, hi = NUMBERS[(sec, key)]
            if not value.lstrip("-").isdigit() or not lo <= int(value) <= hi:
                errors[name] = f"Choose a number from {lo} to {hi}."
                continue
        elif (sec, key) in TEXTS:
            if not TEXTS[(sec, key)][1].match(value):
                errors[name] = "Invalid format."
                continue
        elif (sec, key) in KEYS:
            if not valid_hotkey(value):
                errors[name] = "Key not allowed."
                continue
        else:
            continue  # unknown fields: ignored
        updates.setdefault(sec, {})[key] = value

    # New keys plus saved ones: the page only sends what changed
    current = current_values()
    keys = [updates.get("tasti", {}).get(k) or current[f"tasti.{k}"] for k in ("correggi", "riassumi", "spiega")]
    if len(keys) != len(set(k.lower() for k in keys)):
        errors["tasti"] = "Two actions have the same key."
    return updates, errors


# =========================================================
# SERVER
# =========================================================

class State:
    def __init__(self):
        self.last_seen = time.time()

    def touch(self):
        self.last_seen = time.time()


def build_page(token):
    template = (pages.STATIC_DIR / "settings.html").read_text(encoding="utf-8")
    values = current_values()
    look = {
        "tema": values["aspetto.tema"], "colore": values["aspetto.colore"],
        "testo": values["aspetto.testo"], "larghezza": values["aspetto.larghezza"],
    }
    data = {"token": token, "values": values, "defaults": defaults(), "look": look}
    return (
        template
        .replace("/*__THEME__*/", pages.theme_css())
        .replace("/*__DATA__*/null", pages.script_json(data))
    )


def make_handler(state, token):

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def _authorized(self):
            return secrets.compare_digest(self.headers.get("X-Token", ""), token)

        def _send(self, status, body, ctype):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, data):
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _bad_host(self):
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            return host not in ("127.0.0.1", "localhost")

        def do_GET(self):
            url = urlparse(self.path)
            if self._bad_host():
                self.send_error(403)
                return
            if url.path == "/":
                if not secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], token):
                    self.send_error(403)
                    return
                state.touch()
                # The page is built on every open: it always reads the current config
                self._send(200, build_page(token).encode("utf-8"), "text/html; charset=utf-8")
                return
            if pages.try_serve_font(self, url.path):
                return
            if url.path == "/api/ping":
                if not self._authorized():
                    self.send_error(403)
                    return
                state.touch()
                self._json(200, {"ok": True})
                return
            self.send_error(404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/save":
                self.send_error(404)
                return
            if self._bad_host():
                self.send_error(403)
                return
            if not self._authorized():
                self.send_error(403)
                return
            state.touch()
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY:
                    raise ValueError
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                self._json(400, {"error": "Invalid request."})
                return

            updates, errors = validate(data)
            if errors:
                self._json(422, {"errors": errors})
                return
            try:
                config_edit.set_values(CONFIG_FILE, updates)
            except Exception:
                self._json(500, {"error": "Cannot save, try again."})
                return
            self._json(200, {"ok": True, "values": current_values()})

    return Handler


def main():
    state = State()
    token = secrets.token_urlsafe(18)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, token))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"

    def watchdog():
        while True:
            time.sleep(5)
            if time.time() - state.last_seen > IDLE_TIMEOUT:
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()

    if "--no-browser" in sys.argv:
        print(url, flush=True)
    else:
        webbrowser.open_new_tab(url)
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
