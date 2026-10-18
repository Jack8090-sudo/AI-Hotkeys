"""Recording reverse proxy for Ollama (S3 benchmark tool, not shipped).

Forwards every request to the upstream Ollama (default http://localhost:11434)
and records, per request:

  - client-side timings: TTFB (first response byte), TTFT (first non-empty
    "content" piece; for a non-streamed answer this equals the time to the
    whole body), total time;
  - Ollama's final-chunk stats: total/load/prompt_eval/eval durations (seconds)
    and counts, done_reason;
  - a request summary without any message text: model, stream, keep_alive,
    options, number of messages and prompt characters.

Streaming is passed through chunk by chunk. A client that disconnects is
propagated upstream (the upstream socket is closed), also while a non-streamed
answer is still being computed, so cancellation behaves as without the proxy.

Usage (standalone):
    python tools/bench/proxy.py --port 11500 --log tools/bench/out/proxy.jsonl
then point a *temporary* config.ini at  ollama_url = http://127.0.0.1:11500.
Never edit the real config.ini for this.

In-process (run.py):
    with OllamaProxy(upstream) as p: ...  p.url, p.records
"""

import argparse
import http.client
import json
import select
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NS = 1e9
_HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
                "proxy-connection", "content-length", "host"}


def summarize_request(path, body):
    """Request facts without message text."""
    info = {"path": path, "req_bytes": len(body)}
    if not body:
        return info
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return info
    if not isinstance(payload, dict):
        return info
    msgs = payload.get("messages") or []
    info.update({
        "model": payload.get("model"),
        "stream": payload.get("stream", True),
        "think": payload.get("think"),
        "keep_alive": payload.get("keep_alive"),
        "options": payload.get("options"),
        "n_messages": len(msgs),
        "prompt_chars": sum(len(str(m.get("content", ""))) for m in msgs if isinstance(m, dict))
        + len(str(payload.get("prompt", ""))),
    })
    return info


def final_stats(chunk):
    """Ollama's final stats (durations converted from ns to s)."""
    out = {"done_reason": chunk.get("done_reason")}
    for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        if k in chunk:
            out[k.replace("_duration", "_s")] = chunk[k] / NS
    for k in ("prompt_eval_count", "eval_count"):
        if k in chunk:
            out[k] = chunk[k]
    if chunk.get("error"):
        out["error"] = str(chunk["error"])[:300]
    return out


class _Watch(threading.Thread):
    """Closes the upstream connection as soon as the client goes away."""

    def __init__(self, client_sock, upstream_conn):
        super().__init__(daemon=True)
        self.client_sock = client_sock
        self.upstream_conn = upstream_conn
        self.stop = threading.Event()
        self.client_gone_at = None

    def run(self):
        while not self.stop.is_set():
            try:
                r, _, _ = select.select([self.client_sock], [], [], 0.1)
                if not r:
                    continue
                data = self.client_sock.recv(1, socket.MSG_PEEK)
                if data:          # pipelined bytes: not expected, just keep waiting
                    time.sleep(0.1)
                    continue
            except (OSError, ValueError):
                pass
            self.client_gone_at = time.perf_counter()
            try:
                if self.upstream_conn.sock:
                    self.upstream_conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.upstream_conn.close()
            except OSError:
                pass
            return


class OllamaProxy:
    def __init__(self, upstream="http://localhost:11434", port=0, log_path=None, quiet=True):
        u = urllib.parse.urlsplit(upstream)
        self.up_host = u.hostname
        self.up_port = u.port or 80
        self.records = []
        self.log_path = log_path
        self.quiet = quiet
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = None

    # -- lifecycle -------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    def _record(self, rec):
        with self._lock:
            self.records.append(rec)
            if self.log_path:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
        if not self.quiet:
            print(json.dumps(rec), flush=True)

    # -- handler ---------------------------------------------------------
    def _handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def do_GET(self):
                self._forward()

            def do_POST(self):
                self._forward()

            def do_DELETE(self):
                self._forward()

            def _forward(self):
                t0 = time.perf_counter()
                wall = time.time()
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                rec = {"wall": wall, **summarize_request(self.path.split("?")[0], body)}
                headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_HEADERS}
                headers["Content-Length"] = str(len(body))
                conn = http.client.HTTPConnection(proxy.up_host, proxy.up_port, timeout=900)
                watch = None
                try:
                    conn.request(self.command, self.path, body=body, headers=headers)
                    watch = _Watch(self.connection, conn)
                    watch.start()
                    resp = conn.getresponse()
                    rec["status"] = resp.status
                    t_headers = time.perf_counter()
                    self.send_response(resp.status)
                    for k, v in resp.getheaders():
                        if k.lower() not in _HOP_HEADERS:
                            self.send_header(k, v)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self._relay(resp, rec, t0)
                    rec["headers_s"] = t_headers - t0
                except (OSError, http.client.HTTPException) as e:
                    rec["error"] = f"{type(e).__name__}: {e}"[:300]
                    if watch and watch.client_gone_at:
                        rec["client_aborted"] = True
                        rec["client_gone_s"] = watch.client_gone_at - t0
                finally:
                    if watch:
                        watch.stop.set()
                    conn.close()
                    rec["total_s"] = time.perf_counter() - t0
                    proxy._record(rec)

            def _relay(self, resp, rec, t0):
                buf = b""
                last = None
                first_byte = first_token = None
                while True:
                    data = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                    if not data:
                        break
                    now = time.perf_counter()
                    if first_byte is None:
                        first_byte = now - t0
                    try:
                        self.wfile.write(data)
                        self.wfile.flush()
                    except OSError:
                        rec["client_aborted"] = True
                        rec["client_gone_s"] = now - t0
                        break
                    buf += data
                    # Parse complete NDJSON lines (or one JSON body at the end)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        obj = _json(line)
                        if obj is None:
                            continue
                        last = obj
                        if first_token is None and (obj.get("message", {}) or {}).get("content"):
                            first_token = now - t0
                        if first_token is None and obj.get("response"):
                            first_token = now - t0
                if buf.strip():
                    obj = _json(buf)
                    if obj is not None:
                        last = obj
                        if first_token is None:
                            first_token = time.perf_counter() - t0
                rec["ttfb_s"] = first_byte
                rec["ttft_s"] = first_token
                if isinstance(last, dict) and (last.get("done") or "error" in last):
                    rec.update(final_stats(last))
                elif rec.get("path") in ("/api/chat", "/api/generate"):
                    rec["incomplete"] = True

        return Handler


def _json(raw):
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--port", type=int, default=0, help="listen port on 127.0.0.1 (0 = free port)")
    ap.add_argument("--log", default=None, help="append one JSON record per request to this file")
    args = ap.parse_args()
    p = OllamaProxy(args.upstream, args.port, args.log, quiet=False)
    print(f"Proxy on {p.url} -> {args.upstream}", flush=True)
    try:
        p.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        p.server.server_close()


if __name__ == "__main__":
    main()
