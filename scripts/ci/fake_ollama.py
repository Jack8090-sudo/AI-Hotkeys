"""Fake Ollama on a fixed port, for the installer E2E job (plan step S14, hypothesis H14).

    python scripts/ci/fake_ollama.py --port 11434 --text "Rewritten by the fake." --log fake.jsonl

Reuses tests/support.py FakeOllama (same answers as the unit tests), but listens on the given
port instead of a random one, so an installed main.ahk with its default ollama_url finds it.
Every request is appended to --log as one JSON line ({"method", "path", "t"}). The server stops
after --seconds (default 900) so a forgotten process cannot outlive the CI job by much.
Never point it at the port of a real Ollama on a developer machine: it refuses a busy port.
"""
import argparse
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.support import FakeOllama  # noqa: E402


class LoggingFakeOllama(FakeOllama):
    def __init__(self, log_path, **kwargs):
        self.log_path = log_path
        self._lock = threading.Lock()
        super().__init__(**kwargs)

    def handle(self, h, body):
        if self.log_path:
            line = json.dumps({"method": h.command, "path": h.path, "t": time.time()})
            with self._lock, open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return super().handle(h, body)


class _ExclusiveServer(ThreadingHTTPServer):
    # HTTPServer sets SO_REUSEADDR, which on Windows lets a second socket bind a port that is
    # already in use (it would hijack a real Ollama). Refuse a busy port instead.
    allow_reuse_address = False
    daemon_threads = True


def serve(port, text, log_path, seconds, ready_file=None):
    fake = LoggingFakeOllama(log_path, text=text)
    fake.close()  # the random-port server FakeOllama starts by itself is not needed
    server = _ExclusiveServer(("127.0.0.1", port), fake._handler_class())
    print(f"fake Ollama listening on http://127.0.0.1:{server.server_address[1]}", flush=True)
    if ready_file:
        Path(ready_file).write_text(str(server.server_address[1]), encoding="utf-8")
    timer = threading.Timer(seconds, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return fake


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=11434)
    ap.add_argument("--text", default="Rewritten by the fake Ollama.")
    ap.add_argument("--log", default="")
    ap.add_argument("--ready-file", default="")
    ap.add_argument("--seconds", type=float, default=900.0)
    args = ap.parse_args(argv)
    try:
        serve(args.port, args.text, args.log, args.seconds, args.ready_file or None)
    except OSError as e:
        print(f"error: cannot listen on 127.0.0.1:{args.port}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
