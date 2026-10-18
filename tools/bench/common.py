"""Shared helpers for the S3 benchmark tools (not shipped).

Every run uses a *temporary copy* of the app with its own config.ini and work/,
so the real config.ini, the real work/ folder and port 8888 are never touched.
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "out"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CONFIG_TEMPLATE = """\
[qwen]
model = {model}
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
"""

# No system proxy, ever: everything here is 127.0.0.1 / localhost
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def default_python():
    """The bundled interpreter (python\\python.exe) when present, else the current one."""
    p = REPO / "python" / "python.exe"
    return str(p) if p.exists() else sys.executable


_PYCACHE = tempfile.TemporaryDirectory(prefix="aihk-bench-pyc-")


def child_env():
    """Environment for app processes.

    Bytecode goes to a private PYTHONPYCACHEPREFIX: after the warm-up round every
    module (stdlib, app, curl_cffi) is cached there, like the steady state of a
    real install, and nothing is written into the repo or the linked runtime.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPYCACHEPREFIX=_PYCACHE.name)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "PYTHONPATH", "PYTHONHOME",
              "PYTHONDONTWRITEBYTECODE"):
        env.pop(k, None)
    return env


class TempApp:
    """Temporary copy of the app (root *.py, actions/, static/) with its own config.ini and work/."""

    def __init__(self, ollama_url, model="test-model:1b", keep_alive="30m",
                 web_search="false", searxng_url="http://127.0.0.1:9"):
        self._tmp = tempfile.TemporaryDirectory(prefix="aihk-bench-")
        self.root = Path(self._tmp.name)
        for f in REPO.glob("*.py"):
            if not f.name.startswith("test_"):
                shutil.copy2(f, self.root / f.name)
        shutil.copytree(REPO / "actions", self.root / "actions",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "static", self.root / "static")
        self.work.mkdir()
        self.write_config(ollama_url=ollama_url, model=model, keep_alive=keep_alive,
                          web_search=web_search, searxng_url=searxng_url)

    def write_config(self, **values):
        (self.root / "config.ini").write_text(CONFIG_TEMPLATE.format(**values), encoding="utf-8")

    @property
    def work(self):
        return self.root / "work"

    def close(self):
        for _ in range(5):
            try:
                self._tmp.cleanup()
                return
            except OSError:
                time.sleep(0.5)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run_action(app, action, text, python=None, timeout=900):
    """Run actions/<action>.py like main.ahk does (input/output files in work/).

    Returns a dict with rc, wall_s, out_chars and the first line of error.txt.
    """
    python = python or default_python()
    inp, out = app.work / "input.txt", app.work / "output.txt"
    inp.write_text(text, encoding="utf-8")
    for f in (out, app.work / "error.txt"):
        if f.exists():
            f.unlink()
    t0 = time.perf_counter()
    p = subprocess.run([python, str(app.root / "actions" / f"{action}.py"), str(inp), str(out)],
                       cwd=str(app.root), env=child_env(), capture_output=True, timeout=timeout)
    wall = time.perf_counter() - t0
    res = {"rc": p.returncode, "wall_s": wall, "in_chars": len(text),
           "out_chars": len(out.read_text(encoding="utf-8")) if out.exists() else 0}
    err = app.work / "error.txt"
    if err.exists():
        res["error"] = err.read_text(encoding="utf-8").splitlines()[0][:200]
    return res


def get_json(url, timeout=5):
    with NO_PROXY_OPENER.open(url, timeout=timeout) as r:
        return json.load(r)


def post_json(url, payload, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with NO_PROXY_OPENER.open(req, timeout=timeout) as r:
        return json.load(r)


def loaded_models(ollama_url):
    try:
        return [m.get("name") for m in get_json(ollama_url.rstrip("/") + "/api/ps").get("models", [])]
    except Exception:
        return None


def pct(values, q):
    """Nearest-rank percentile (q in 0..100)."""
    v = sorted(values)
    if not v:
        return None
    k = max(0, min(len(v) - 1, int(round(q / 100 * len(v) + 0.5)) - 1))
    return v[k]


def stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": statistics.median(v), "p90": pct(v, 90), "max": max(v), "min": min(v)}


def interleaved(items, rep):
    """ABAB interleaving with alternating direction (A B C, C B A, ...) to cancel order effects."""
    return list(items) if rep % 2 == 0 else list(reversed(items))


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
