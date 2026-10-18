"""H08: does Ollama stop generating when the action process is killed? (S3, not shipped)

Replays the Esc-hold cancel (main.ahk ProcessClose = TerminateProcess) against
the REAL local Ollama, with the app talking to Ollama directly (no proxy, as in
production) from a temporary app copy. Synthetic corpus only.

For each scenario the action process is killed at `kill_at` seconds, then:
  - a 1-token probe request is sent at once. Ollama runs one slot (n_slots = 1),
    so if the orphaned request kept running, the probe would queue behind it;
  - GPU utilization is sampled with nvidia-smi;
  - new Ollama server-log lines are scanned for the slot release
    ("stop processing: n_tokens = ...") - numbers only, no text.

    python tools/bench/h08_cancel.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import common  # noqa: E402
import corpus  # noqa: E402
from common import TempApp, child_env, default_python  # noqa: E402

LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"
LOG_RE = re.compile(r"(new prompt|release|cancel|abort|truncat|disconnect)", re.IGNORECASE)


class GpuSampler(threading.Thread):
    def __init__(self, period_ms=200):
        super().__init__(daemon=True)
        self.samples = []      # (perf_counter, util%)
        self.proc = subprocess.Popen(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits", f"-lms={period_ms}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def run(self):
        for line in self.proc.stdout:
            try:
                self.samples.append((time.perf_counter(), float(line.strip())))
            except ValueError:
                pass

    def stop(self):
        self.proc.kill()

    def mean(self, t_from, t_to):
        v = [u for t, u in self.samples if t_from <= t <= t_to]
        return round(sum(v) / len(v), 1) if v else None


def probe(upstream, model, keep_alive):
    payload = {"model": model, "messages": [{"role": "user", "content": "ok"}], "stream": False,
               "think": False, "keep_alive": keep_alive, "options": {"num_ctx": 16384, "num_predict": 1}}
    t0 = time.perf_counter()
    common.post_json(upstream + "/api/chat", payload, timeout=600)
    return time.perf_counter() - t0


def log_offset():
    try:
        return LOG.stat().st_size
    except OSError:
        return None


def new_log_lines(offset):
    if offset is None:
        return []
    with open(LOG, "rb") as f:
        f.seek(offset)
        data = f.read().decode("utf-8", "replace")
    return [re.sub(r"[A-Za-z]:\\[^\s]*", "<path>", ln.strip())[:200]
            for ln in data.splitlines() if LOG_RE.search(ln)]


def scenario(app, python, upstream, model, action, text, kill_at):
    inp, out = app.work / "input.txt", app.work / "output.txt"
    inp.write_text(text, encoding="utf-8")
    off = log_offset()
    gpu = GpuSampler()
    gpu.start()
    time.sleep(1.0)
    t_start = time.perf_counter()
    p = subprocess.Popen([python, str(app.root / "actions" / f"{action}.py"), str(inp), str(out)],
                         cwd=str(app.root), env=child_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(kill_at)
    exited_before = p.poll() is not None
    t_kill = time.perf_counter()
    p.kill()            # TerminateProcess, like AHK ProcessClose
    p.wait()
    probe_s = probe(upstream, model, "30m")
    time.sleep(3.0)
    gpu.stop()
    res = {
        "action": action, "in_chars": len(text), "kill_at_s": kill_at, "exited_before_kill": exited_before,
        "probe_latency_s": round(probe_s, 2),
        "gpu_util_before_kill": gpu.mean(t_kill - 1.0, t_kill),
        "gpu_util_1to3s_after_probe": gpu.mean(t_kill + probe_s + 1.0, t_kill + probe_s + 3.0),
        "gpu_util_0to2s_after_kill": gpu.mean(t_kill + 0.3, t_kill + 2.0),
        "since_start_s": round(t_kill - t_start, 2),
        "log": new_log_lines(off),
    }
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--python", default=default_python())
    args = ap.parse_args()
    up = args.upstream.rstrip("/")

    results = []
    with TempApp(up, model=args.model) as app:
        common.run_action(app, "summarize", corpus.text("summarize", "S"), args.python)   # warm the model
        # Uninterrupted reference for the mid-generation scenario
        ref = common.run_action(app, "rewrite", corpus.text("rewrite", "L") + "\n\n" + corpus.text("rewrite", "M"),
                                args.python)
        print("reference rewrite (not killed):", json.dumps(ref), flush=True)
        plans = [
            ("summarize", corpus.long_text(34000), 2.0),   # killed during prefill (~11k prompt tokens)
            ("rewrite", corpus.text("rewrite", "L") + "\n\n" + corpus.text("rewrite", "M"), 2.0),
            ("rewrite", corpus.text("rewrite", "L") + "\n\n" + corpus.text("rewrite", "M"), 10.0),   # mid-generation (reference run takes ~18 s)
        ]
        for action, text, kill_at in plans:
            r = scenario(app, args.python, up, args.model, action, text, kill_at)
            print(json.dumps(r, indent=1), flush=True)
            results.append(r)
    out = common.OUT_DIR / f"{common.stamp()}-h08.json"
    out.write_text(json.dumps({"reference": ref, "scenarios": results}, indent=1), encoding="utf-8")
    print("Written:", out.name)


if __name__ == "__main__":
    main()
