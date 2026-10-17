"""Shared test helpers for AI-Hotkeys.

Every test imports the application from a *temporary copy* of the repository,
with its own config.ini and work/ folder, so the real config.ini, the real
work/ folder (which holds the user's selected text) and the user's running
SearXNG on port 8888 are never touched.

Network: only 127.0.0.1 fakes started here (Ollama, SearXNG, web pages).
"""

import importlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Application modules that live in the repository root
APP_MODULES = ("qwen_client", "prompts", "websearch", "viewer", "settings", "pages", "config_edit")

DEFAULT_CONFIG = """\
[qwen]
model = test-model:1b
ollama_url = {ollama_url}
keep_alive = {keep_alive}

[searxng]
web_search = {web_search}
searxng_url = {searxng_url}
results = 5
pages_to_read = 3

[aspetto]
tema = scuro
colore = ambra
testo = 16

[tasti]
correggi = PgUp
riassumi = PgDn
spiega = End

[comportamento]
sostituisci_testo = si
lunghezza = normale

[obsidian]
todo_file = {todo_file}
window_title = To-Do List -
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def dead_url():
    """A 127.0.0.1 URL where nothing listens."""
    return f"http://127.0.0.1:{free_port()}"


# =========================================================
# TEMPORARY APPLICATION TREE
# =========================================================

class AppTree:
    """A temporary copy of the app with its own config.ini and work/.

        with AppTree(ollama_url=fake.url) as tree:
            qc = tree.load("qwen_client")

    Pass config_text (str or bytes) to write config.ini verbatim.
    """

    def __init__(self, config_text=None, **config):
        self._tmp = tempfile.TemporaryDirectory(prefix="aihk-test-")
        self.root = Path(self._tmp.name)
        for f in REPO.glob("*.py"):
            if not f.name.startswith("test_"):
                shutil.copy2(f, self.root / f.name)
        shutil.copytree(REPO / "actions", self.root / "actions",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "static", self.root / "static")
        (self.root / "work").mkdir()
        if config_text is None:
            values = {
                "ollama_url": dead_url(),
                "keep_alive": "30m",
                "web_search": "false",
                "searxng_url": dead_url(),
                "todo_file": str(self.root / "To-Do List.md"),
            }
            values.update(config)
            config_text = DEFAULT_CONFIG.format(**values)
        if isinstance(config_text, bytes):
            (self.root / "config.ini").write_bytes(config_text)
        else:
            (self.root / "config.ini").write_text(config_text, encoding="utf-8")
        self._saved_path = list(sys.path)
        self._saved_modules = {n: sys.modules.pop(n) for n in list(sys.modules) if n in APP_MODULES}
        sys.path.insert(0, str(self.root))
        self.modules = {}

    @property
    def work(self):
        return self.root / "work"

    @property
    def config_file(self):
        return self.root / "config.ini"

    def load(self, name):
        """Import a root module (qwen_client, viewer, …) from this tree."""
        if name not in self.modules:
            self.modules[name] = importlib.import_module(name)
        return self.modules[name]

    def load_action(self, name):
        """Import actions/<name>.py from this tree (as a private module)."""
        key = "action:" + name
        if key not in self.modules:
            spec = importlib.util.spec_from_file_location(
                f"aihk_action_{name}", self.root / "actions" / f"{name}.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.modules[key] = mod
        return self.modules[key]

    def close(self):
        for n in list(sys.modules):
            if n in APP_MODULES:
                del sys.modules[n]
        sys.modules.update(self._saved_modules)
        sys.path[:] = self._saved_path
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def repo_copy(**kw):
    """Same as AppTree(**kw) (name used in the plan, S1 task 1)."""
    return AppTree(**kw)


def run_with_timeout(code, seconds, cwd=None, env=None):
    """Run Python `code` in a subprocess.

    Returns (returncode, output, elapsed); returncode is None on timeout.
    """
    full_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        full_env.update(env)
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=full_env,
                           capture_output=True, text=True, timeout=seconds)
        return p.returncode, p.stdout + p.stderr, time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return None, "", time.perf_counter() - t0


# =========================================================
# FAKE HTTP SERVERS
# =========================================================

class _FakeServer:
    """ThreadingHTTPServer on 127.0.0.1 with a random port, in a thread."""

    def __init__(self):
        self.requests = []          # (method, path, headers, body bytes)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _handler_class(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def _record(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                fake.requests.append((self.command, self.path, dict(self.headers), body))
                return body

            def do_GET(self):
                fake.handle(self, self._record())

            def do_POST(self):
                fake.handle(self, self._record())

        return Handler

    @staticmethod
    def send(h, status, body, ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(body)


class FakeOllama(_FakeServer):
    """Fake Ollama API.

    scenario (can be changed between requests):
      "ok"          answer `text`, done_reason "stop"
      "length"      answer `text`, done_reason "length" (truncated)
      "error_field" HTTP 200 with {"error": ...}
      "http404"     404 {"error": "model ... not found"}
      "no_done"     stream ends without a done chunk
    delay: seconds to sleep before answering /api/chat
    """

    def __init__(self, text="Risposta di prova.", scenario="ok", delay=0.0):
        self.text = text
        self.scenario = scenario
        self.delay = delay
        super().__init__()

    def chat_bodies(self):
        return [json.loads(b) for m, p, h, b in self.requests if p == "/api/chat"]

    def handle(self, h, body):
        path = h.path.split("?")[0]
        if path == "/api/version":
            return self.send(h, 200, {"version": "0.12.0"})
        if path == "/api/tags":
            return self.send(h, 200, {"models": [{"name": "test-model:1b"}]})
        if path == "/api/generate":
            return self.send(h, 200, {"done": True, "done_reason": "unload"})
        if path != "/api/chat":
            return self.send(h, 404, {"error": "not found"})

        if self.delay:
            time.sleep(self.delay)
        if self.scenario == "http404":
            return self.send(h, 404, {"error": "model 'test-model:1b' not found, try pulling it first"})
        if self.scenario == "error_field":
            return self.send(h, 200, {"error": "something broke"})

        payload = json.loads(body or b"{}")
        reason = "length" if self.scenario == "length" else "stop"
        if not payload.get("stream"):
            return self.send(h, 200, {"message": {"role": "assistant", "content": self.text},
                                      "done": True, "done_reason": reason})

        # NDJSON stream: one chunk per word
        words = self.text.split(" ")
        lines = [json.dumps({"message": {"content": w + (" " if i < len(words) - 1 else "")}, "done": False})
                 for i, w in enumerate(words)]
        if self.scenario != "no_done":
            lines.append(json.dumps({"message": {"content": ""}, "done": True, "done_reason": reason}))
        self.send(h, 200, "\n".join(lines) + "\n", ctype="application/x-ndjson")


class FakeSearx(_FakeServer):
    """Fake SearXNG: /healthz and /search?format=json."""

    def __init__(self, results=None):
        self.results = results or []
        super().__init__()

    def handle(self, h, body):
        path = h.path.split("?")[0]
        if path == "/healthz":
            return self.send(h, 200, "OK", ctype="text/plain")
        if path == "/search":
            return self.send(h, 200, {"results": self.results})
        self.send(h, 404, "")


class StaticPages(_FakeServer):
    """Fixture web pages. routes: {path: (status, content_type, body[, headers])}."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        super().__init__()

    def handle(self, h, body):
        route = self.routes.get(h.path)
        if route is None:
            return self.send(h, 404, "missing", ctype="text/plain")
        status, ctype, content, headers = (tuple(route) + (None,))[:4]
        self.send(h, status, content, ctype=ctype, headers=headers)
