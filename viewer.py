"""
AI-Hotkeys — HTML viewer with "✦ Ask Qwen" popup.

Usage (called from main.ahk):
    python viewer.py <input.txt> <output.txt> "<Action name>" [rewrite|summarize|explain]

How it works:
- Starts a small local server (127.0.0.1 only, random port).
- Opens the page in the browser.
- The page popup sends follow-up requests to this server,
  which forwards them to Ollama with the full context:
      original text + current result + new request
- The server shuts down by itself a few minutes after the tab is closed.
"""

import json
import secrets
import sys
import threading
import time
import urllib.error
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pages
import qwen_client
import websearch
from prompt_loader import prompts


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Seconds without a "ping" from the page before the server shuts down.
# (Browsers slow background-tab timers down to
#  1 per minute, so this must be well above 60 seconds.)
IDLE_TIMEOUT = 240

# How many previous question/answer turns to send to Qwen
# in summarize and explain modes.
HISTORY_TURNS = 6

# Anti-DoS limits on HTTP requests (the server is local, but the token
# could leak: no huge bodies or very long questions).
MAX_BODY = 1_000_000
MAX_QUESTION = 4000


# =========================================================
# MODES
# =========================================================

MODES = ("rewrite", "summarize", "explain")


def detect_mode(action_name, explicit=None):
    if explicit in MODES:
        return explicit

    name = action_name.lower()

    if "riassun" in name or "summar" in name:
        return "summarize"

    if "anali" in name or "spieg" in name or "explain" in name:
        return "explain"

    return "rewrite"


# =========================================================
# SESSION STATE
# =========================================================

class Session:
    def __init__(self, original, result, mode, action_name):
        self.original = original
        self.mode = mode
        self.action_name = action_name

        # Result versions (used by rewrite).
        self.versions = [{"text": result, "request": None}]

        # Conversation (used by summarize and explain).
        self.thread = []

        # Web sources found by End (SearXNG): also needed for follow-ups.
        self.sources = websearch.load_sources() if mode == "explain" else []

        self.lock = threading.Lock()
        # monotonic: the idle timer must not jump after sleep/hibernate or a clock change
        self.last_seen = time.monotonic()
        self.active_requests = 0

    def touch(self):
        self.last_seen = time.monotonic()

    # -----------------------------------------------------

    def build_messages(self, question, base_index):
        with self.lock:
            versions = list(self.versions)
            thread = list(self.thread)

        if self.mode == "rewrite":
            base_index = max(0, min(base_index, len(versions) - 1))
            return prompts.followup_rewrite_messages(
                self.original, versions[base_index]["text"], question
            )

        storia = [(t["q"], t["a"]) for t in thread[-HISTORY_TURNS:]]
        fonti = websearch.sources_block(self.sources) if self.sources else None
        return prompts.followup_qa_messages(
            self.mode, self.original, versions[0]["text"], storia, question, fonti
        )

    def save(self, question, answer, base_index):
        with self.lock:
            if self.mode == "rewrite":
                self.versions.append({"text": answer, "request": question})
                return len(self.versions) - 1

            self.thread.append({"q": question, "a": answer})
            return len(self.thread) - 1


# =========================================================
# HTTP SERVER
# =========================================================

def make_handler(session, token, page_html):

    class Handler(BaseHTTPRequestHandler):

        protocol_version = "HTTP/1.0"
        timeout = pages.REQUEST_TIMEOUT

        def log_message(self, *args):
            pass

        # ---------------------------------------------

        def _authorized(self):
            return pages.token_ok(self.headers.get("X-Token", ""), token)

        def _send_json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        # ---------------------------------------------

        def _bad_host(self):
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            return host not in ("127.0.0.1", "localhost")

        def do_GET(self):
            url = urlparse(self.path)

            if self._bad_host():
                self.send_error(403)
                return

            if url.path == "/":
                query = parse_qs(url.query)

                if not pages.token_ok(query.get("t", [""])[0], token):
                    self.send_error(403)
                    return

                session.touch()

                body = page_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", pages.CSP)
                self.end_headers()
                self.wfile.write(body)
                return

            if pages.try_serve_font(self, url.path):
                return

            if url.path == "/api/ping":
                if not self._authorized():
                    self.send_error(403)
                    return

                session.touch()
                self._send_json(200, {"ok": True})
                return

            self.send_error(404)

        # ---------------------------------------------

        def do_POST(self):
            if urlparse(self.path).path != "/api/ask":
                self.send_error(404)
                return

            if self._bad_host():
                self.send_error(403)
                return

            if not self._authorized():
                self.send_error(403)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY:
                    raise ValueError
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                question = str(data.get("question", "")).strip()
                base_index = int(data.get("base", 0))
            except Exception:
                self._send_json(400, {"error": "Invalid request."})
                return

            if not question:
                self._send_json(400, {"error": "Write a request."})
                return

            if len(question) > MAX_QUESTION:
                self._send_json(400, {"error": f"Max {MAX_QUESTION} characters."})
                return

            session.touch()

            with session.lock:
                session.active_requests += 1

            try:
                self._stream_answer(question, base_index)
            finally:
                with session.lock:
                    session.active_requests -= 1
                session.touch()

        # ---------------------------------------------

        def _emit(self, obj):
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

        def _stream_answer(self, question, base_index):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            parts = []
            messages = session.build_messages(question, base_index)

            try:
                response = qwen_client.open_stream(messages, session.mode, timeout=300)
            except urllib.error.URLError:
                self._safe_emit({
                    "error": "Cannot reach Ollama. "
                             "Check that Ollama is running."
                })
                return
            except Exception:
                self._safe_emit({"error": "Internal error, try again."})
                return

            try:
                with response:
                    for piece in qwen_client.stream_pieces(response):
                        parts.append(piece)
                        self._emit({"t": piece})
                        session.touch()

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # The page interrupted generation (stop button).
                return
            except qwen_client.TruncatedAnswer:
                self._safe_emit({"error": "The answer was cut off (too long for the model).", "partial": True})
                return
            except qwen_client.StreamIncomplete:
                self._safe_emit({"error": "The answer was interrupted: try again.", "partial": True})
                return
            except Exception:
                self._safe_emit({"error": "Generation error, try again."})
                return

            answer = qwen_client.clean_answer("".join(parts), session.mode)
            if session.sources:
                answer = websearch.linkify(answer, session.sources)

            if not answer:
                self._safe_emit({"error": "Qwen returned an empty answer."})
                return

            index = session.save(question, answer, base_index)
            self._safe_emit({"done": True, "index": index, "text": answer})

        def _safe_emit(self, obj):
            try:
                self._emit(obj)
            except Exception:
                pass

    return Handler


# =========================================================
# PAGE
# =========================================================

def read_meta():
    """Details of the last run (written by qwen_client.run_action)."""
    try:
        return json.loads((BASE_DIR / "work" / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_page(session, token, key_label=""):
    template = (STATIC_DIR / "viewer.html").read_text(encoding="utf-8")
    marked_js = (STATIC_DIR / "marked.min.js").read_text(encoding="utf-8")

    data = {
        "token": token,
        "mode": session.mode,
        "action": session.action_name,
        "key": key_label,
        "original": session.original,
        "result": session.versions[0]["text"],
        "time": datetime.now().strftime("%H:%M"),
        "look": pages.look_settings(qwen_client.CONFIG),
        "meta": read_meta() if session.mode in ("explain", "summarize", "rewrite") else {},
    }

    return (
        template
        .replace("/*__THEME__*/", pages.theme_css())
        .replace("/*__MARKED__*/", marked_js)
        .replace("__TITLE__", pages.html_escape(session.action_name))
        .replace("/*__DATA__*/null", pages.script_json(data))
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if len([a for a in sys.argv[1:] if not a.startswith("--")]) < 3:
        print("Usage: viewer.py <input> <output> <action name> [mode] [--key=End] [--no-browser]")
        sys.exit(1)

    # Optional args: --key=End (pressed key), --no-browser
    options = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    key_label = next((a.split("=", 1)[1] for a in options if a.startswith("--key=")), "")

    input_file = Path(args[0])
    output_file = Path(args[1])
    action_name = args[2]
    mode = detect_mode(action_name, args[3] if len(args) > 3 else None)

    original = input_file.read_text(encoding="utf-8-sig")
    result = output_file.read_text(encoding="utf-8-sig")

    session = Session(original, result, mode, action_name)
    token = secrets.token_urlsafe(18)
    page_html = build_page(session, token, key_label)

    server = pages.LocalServer(
        ("127.0.0.1", 0),
        make_handler(session, token, page_html),
    )

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?t={token}"

    def watchdog():
        while True:
            time.sleep(5)
            idle = time.monotonic() - session.last_seen
            if session.active_requests == 0 and idle > IDLE_TIMEOUT:
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()

    if "--no-browser" in sys.argv:
        print(url, flush=True)
        print("Warning: the URL contains a secret token, do not share it.", file=sys.stderr, flush=True)
    else:
        webbrowser.open_new_tab(url)

    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
