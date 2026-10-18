"""
AI-Hotkeys — HTML viewer with "✦ Ask AI" popup.

Usage (called from main.ahk):
    python viewer.py --run-dir=<work\\runs\\id> "<Action name>" [rewrite|summarize|explain]
    python viewer.py <input.txt> <output.txt> "<Action name>" [rewrite|summarize|explain]   (old form, K3)
  options: --key=End (the pressed key), --no-browser (print the URL instead),
           --stream (with --run-dir: only input.txt exists; the page streams the
           first answer from POST /api/first, STREAM1)

Privacy (S9): once the files are loaded they are deleted. A run directory
(work\\runs\\<id>) is removed entirely; with the old form, input/output are
deleted only when they are inside work\\.

How it works:
- Starts a small local server (127.0.0.1 only, random port).
- Opens the page in the browser.
- The page popup sends follow-up requests to this server,
  which forwards them to Ollama with the full context:
      original text + current result + new request
- The server shuts down by itself a few minutes after the tab is closed.
"""

import json
import queue
import secrets
import sys
import threading
import time
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

# How many previous question/answer turns to send to the AI
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
    def __init__(self, original, result, mode, action_name, sources=None, meta=None):
        self.original = original
        self.mode = mode
        self.action_name = action_name
        # Details of the run (time, web search): None = read work/meta.json (old form)
        self.meta = meta

        # Result versions (used by rewrite).
        self.versions = [{"text": result, "request": None}]

        # Conversation (used by summarize and explain).
        self.thread = []

        # Web sources found by End (SearXNG): also needed for follow-ups.
        # sources=None: work/sources.json (old form).
        if mode != "explain":
            self.sources = []
        elif sources is None:
            self.sources = websearch.load_sources()
        else:
            self.sources = sources

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

    def ready(self):
        """True once there is a first answer to ask about (always, outside stream mode)."""
        return self.first is None or self.first.succeeded

    first = None        # FirstRun in stream mode (STREAM1)


# =========================================================
# FIRST ANSWER, STREAMED (stream mode, STREAM1)
# =========================================================
# main.ahk opens the page right after writing input.txt (viewer.py --stream):
# the page asks once for the first answer (POST /api/first) and receives it
# as it is written. The selected text is read and input.txt deleted at once
# (no plaintext stays on disk, S9); the run directory itself stays until the
# first answer ends, as the place where main.ahk drops the Esc-2-s cancel flag.

CANCEL_FLAG = "cancel"
CANCEL_POLL = 0.2
INTERRUPTED = "The answer was interrupted: try again."


class FirstRun:
    """State of the one first answer of a stream-mode page."""

    def __init__(self, run_dir):
        self.run_dir = run_dir
        self.claimed = False            # single use: a reload never generates again
        self.succeeded = False
        self.finished = threading.Event()
        self.cancel = threading.Event()     # Esc 2 s (flag file) or the page went away
        self.t0 = time.monotonic()

    def watch_cancel(self):
        """Poll the run directory for main.ahk's cancel flag until the first answer ends."""
        flag = self.run_dir / CANCEL_FLAG
        while not self.finished.wait(CANCEL_POLL):
            if flag.exists():
                self.cancel.set()
                self.cleanup()
                return

    def cleanup(self):
        """Delete the run directory (only a real work\\runs\\<id>, as load_run does)."""
        if qwen_client.is_run_dir(self.run_dir):
            qwen_client.remove_run_dir(self.run_dir)


def first_answer_events(mode, testo, stop, emit):
    """Produce the first answer as events, the shared pipeline of qwen_client.run_action.

    emit(dict) receives, in order: {"status": text}..., {"t": piece}..., then one of
    {"done": True, "text": final, "meta": {...}, "sources": [...]} or {"error": msg[, "partial": True]}.
    stop (threading.Event) ends the work early: nothing more is emitted.
    """
    try:
        qwen_client.check_input(mode, testo)
    except qwen_client.ActionStop as e:
        emit({"error": e.message})
        return
    if stop.is_set():
        return

    if mode == "explain":
        websearch.STATUS_HOOK = lambda text: stop.is_set() or emit({"status": text})
    try:
        fonti, meta = qwen_client.first_sources(mode, testo, save=False)
    finally:
        websearch.STATUS_HOOK = None
    if stop.is_set():
        return
    if mode != "explain":
        emit({"status": {"rewrite": "The AI is fixing the text…",
                         "summarize": "The AI is writing the summary…"}.get(mode, "The AI is writing…")})

    parts = []
    try:
        messages = qwen_client.first_request_messages(mode, testo, fonti)
        response = qwen_client.open_stream(messages, mode, timeout=600)
        with response:
            for piece in qwen_client.stream_pieces(response):
                if stop.is_set():
                    return              # closing the response stops Ollama
                parts.append(piece)
                emit({"t": piece})
    except qwen_client.TruncatedAnswer:
        emit({"error": qwen_client.TRUNCATED_FIRST, "partial": True})
        return
    except qwen_client.StreamIncomplete:
        emit({"error": INTERRUPTED, "partial": True})
        return
    except Exception as e:
        if not stop.is_set():
            emit({"error": qwen_client.describe_error(e)[0]})
        return

    try:
        final = qwen_client.finish_first(mode, testo, "".join(parts), fonti)
    except qwen_client.ActionStop as e:
        emit({"error": e.message})
        return
    emit({"done": True, "text": final, "meta": meta, "sources": fonti})


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
            path = urlparse(self.path).path
            if path not in ("/api/ask", "/api/first"):
                self.send_error(404)
                return

            if self._bad_host():
                self.send_error(403)
                return

            if not self._authorized():
                self.send_error(403)
                return

            if path == "/api/first":
                self._first_answer()
                return

            if not session.ready():
                self._send_json(409, {"error": "There is no first answer to ask about."})
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

        # ---------------------------------------------

        def _first_answer(self):
            """POST /api/first: the first answer as NDJSON, once per page (stream mode)."""
            first = session.first
            with session.lock:
                claimed = first is None or first.claimed
                if not claimed:
                    first.claimed = True
                    session.active_requests += 1
            if claimed:
                self._send_json(409, {"error": "This page was already used. To start again, "
                                               "select the text and press the hotkey."})
                return
            session.touch()
            try:
                self._stream_first(first)
            finally:
                first.finished.set()
                first.cleanup()
                with session.lock:
                    session.active_requests -= 1
                session.touch()

        def _stream_first(self, first):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # The pipeline runs in its own thread, so a cancel (Esc 2 s) is
            # honoured at once even while it waits for the web or for Ollama
            events = queue.Queue()
            worker = threading.Thread(
                target=first_answer_events,
                args=(session.mode, session.original, first.cancel, events.put),
                daemon=True)
            worker.start()

            while True:
                if first.cancel.is_set():
                    self._safe_emit({"error": "Cancelled.", "cancelled": True})
                    return
                try:
                    event = events.get(timeout=0.1)
                except queue.Empty:
                    if not worker.is_alive() and events.empty():
                        self._safe_emit({"error": INTERRUPTED, "partial": True})
                        return
                    continue
                if event.get("done"):
                    meta = dict(event["meta"], seconds=round(time.monotonic() - first.t0, 1))
                    with session.lock:
                        session.versions[0]["text"] = event["text"]
                        session.meta = meta
                        # As load_sources() would give them: without the full page text
                        session.sources = [{k: v for k, v in s.items() if k != "text"}
                                           for s in event["sources"]] if session.mode == "explain" else []
                        first.succeeded = True
                    self._safe_emit({"done": True, "text": event["text"], "meta": meta})
                    return
                try:
                    self._emit(event)
                except OSError:
                    # The page stopped the answer (Stop, Esc, tab closed)
                    first.cancel.set()
                    return
                if "error" in event:
                    return
                session.touch()

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
            except Exception as e:
                # K1 messages (C21): a 404 "model not found" says "ollama pull",
                # it is not reported as "Ollama is not running"
                self._safe_emit({"error": qwen_client.describe_error(e)[0]})
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
            except Exception as e:
                # e.g. {"error": "model ... not found"} inside the stream (K1)
                self._safe_emit({"error": qwen_client.describe_error(e)[0]})
                return

            answer = qwen_client.clean_answer("".join(parts), session.mode)
            if session.sources:
                answer = websearch.linkify(answer, session.sources)

            if not answer:
                self._safe_emit({"error": "The AI returned an empty answer."})
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

def read_meta(path=None):
    """Details of a run (written by qwen_client.run_action); path None = work/meta.json (old form)."""
    try:
        return json.loads(Path(path or BASE_DIR / "work" / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (OSError, ValueError):
        return False


def load_run(argv):
    """Parse the command line and load the run; the loaded files are then deleted (S9).

    New form:  --run-dir=<work\\runs\\id> "<Action name>" [mode]
    Old form:  <input.txt> <output.txt> "<Action name>" [mode]   (K3)
    Returns a dict: original, result, action_name, mode, key_label, no_browser, meta, sources.
    Raises SystemExit with the usage text on a bad command line.
    """
    options = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    key_label = next((a.split("=", 1)[1] for a in options if a.startswith("--key=")), "")
    run_dir = next((Path(a.split("=", 1)[1]) for a in options if a.startswith("--run-dir=")), None)

    stream = "--stream" in options

    if len(args) < (1 if run_dir else 3) or (stream and run_dir is None):
        print("Usage: viewer.py --run-dir=<dir> <action name> [mode] [--key=End] [--no-browser] [--stream]\n"
              "       viewer.py <input> <output> <action name> [mode] [--key=End] [--no-browser]")
        raise SystemExit(1)

    if stream:
        # Stream mode (STREAM1): only input.txt exists; the page asks for the answer.
        # The selection is kept in memory and input.txt deleted at once (S9); the
        # folder stays (cancel flag) until the first answer ends.
        action_name = args[0]
        mode = detect_mode(action_name, args[1] if len(args) > 1 else None)
        input_file = run_dir / "input.txt"
        try:
            original = input_file.read_text(encoding="utf-8-sig")
        finally:
            if qwen_client.is_run_dir(run_dir):
                try:
                    input_file.unlink()
                except OSError:
                    qwen_client.remove_run_dir(run_dir)
        return {"original": original, "result": "", "action_name": action_name, "mode": mode,
                "key_label": key_label, "no_browser": "--no-browser" in options,
                "meta": {"mode": mode}, "sources": [], "stream": True, "run_dir": run_dir}

    if run_dir is not None:
        input_file, output_file = run_dir / "input.txt", run_dir / "output.txt"
        rest = args
    else:
        input_file, output_file = Path(args[0]), Path(args[1])
        rest = args[2:]
    action_name = rest[0]
    mode = detect_mode(action_name, rest[1] if len(rest) > 1 else None)

    try:
        original = input_file.read_text(encoding="utf-8-sig")
        result = output_file.read_text(encoding="utf-8-sig")
        if run_dir is not None:
            meta = read_meta(run_dir / "meta.json")
            sources = websearch.load_sources(run_dir / "sources.json") if mode == "explain" else []
        else:
            meta, sources = None, None      # Session / build_page read work\ as before
    finally:
        # No plaintext selection stays on disk once it is in memory (C32)
        if run_dir is not None and qwen_client.is_run_dir(run_dir):
            qwen_client.remove_run_dir(run_dir)
        else:
            work = BASE_DIR / "work"
            for f in (input_file, output_file):
                if _inside(f, work):
                    try:
                        f.unlink()
                    except OSError:
                        pass

    return {"original": original, "result": result, "action_name": action_name, "mode": mode,
            "key_label": key_label, "no_browser": "--no-browser" in options,
            "meta": meta, "sources": sources, "stream": False, "run_dir": run_dir}


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
        # Stream mode: the page fetches the first answer from /api/first
        "stream": session.first is not None,
        "time": datetime.now().strftime("%H:%M"),
        "look": pages.look_settings(qwen_client.CONFIG),
        "meta": ((read_meta() if session.meta is None else session.meta)
                 if session.mode in ("explain", "summarize", "rewrite") else {}),
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

def start_session(run):
    """Session for a loaded run; in stream mode also its FirstRun, with the cancel-flag watcher running."""
    session = Session(run["original"], run["result"], run["mode"], run["action_name"],
                      sources=run["sources"], meta=run["meta"])
    if run["stream"]:
        session.first = FirstRun(run["run_dir"])
        threading.Thread(target=session.first.watch_cancel, daemon=True).start()
    return session


def main():
    run = load_run(sys.argv[1:])

    session = start_session(run)
    first = session.first
    if first is not None:
        qwen_client.report_config_warnings()
    token = secrets.token_urlsafe(18)
    page_html = build_page(session, token, run["key_label"])

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

    if run["no_browser"]:
        print(url, flush=True)
        print("Warning: the URL contains a secret token, do not share it.", file=sys.stderr, flush=True)
    else:
        webbrowser.open_new_tab(url)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        if first is not None:
            # The page never asked for the answer (browser closed, idle shutdown)
            first.finished.set()
            first.cleanup()


if __name__ == "__main__":
    main()
