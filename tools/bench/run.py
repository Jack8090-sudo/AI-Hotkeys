"""S3 benchmark runner (not shipped).

    python tools/bench/run.py --fake --n 20
        Pipeline overhead against tests.support.FakeOllama: interpreter start-up,
        imports, each action end to end (rewrite / summarize / explain) and the
        viewer's time to first byte. No model, no GPU.

    python tools/bench/run.py --real [--cold 3] [--warm 10]
        Real-model protocol through the recording proxy (tools/bench/proxy.py)
        against the local Ollama: cold runs (model unloaded first with
        actions/unload.py), then warm runs, on the fixed corpus (3 sizes per
        action), plus a streamed-TTFT probe. Web search is off.

Every run uses a temporary copy of the app and a temporary config.ini; the real
config.ini and work/ are never touched. Phases are interleaved per repetition
(A B C, C B A, ...). Output: tools/bench/out/<stamp>-<kind>.jsonl and
<stamp>-<kind>-summary.json, plus a table on stdout.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import common  # noqa: E402
import corpus  # noqa: E402
from common import REPO, TempApp, child_env, default_python, interleaved, stats  # noqa: E402

ACTIONS = ("rewrite", "summarize", "explain")


# =========================================================
# FAKE: pipeline overhead
# =========================================================

def _time_cmd(cmd, cwd):
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env=child_env(), capture_output=True)
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        raise RuntimeError(f"{cmd} failed: {p.stderr.decode('utf-8', 'replace')[-300:]}")
    return dt


def viewer_ttfb(app, python):
    """Spawn viewer.py --no-browser like main.ahk; time to the URL line and to the first page byte."""
    (app.work / "input.txt").write_text(corpus.text("summarize", "M"), encoding="utf-8")
    (app.work / "output.txt").write_text("- Punto uno\n- Punto due\n", encoding="utf-8")
    cmd = [python, str(app.root / "viewer.py"), str(app.work / "input.txt"), str(app.work / "output.txt"),
           "Riassunto", "summarize", "--key=PgDn", "--no-browser"]
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, cwd=str(app.root), env=child_env(), stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    try:
        url = p.stdout.readline().decode().strip()
        t_url = time.perf_counter() - t0
        with common.NO_PROXY_OPENER.open(url, timeout=10) as r:
            r.read(1)
            t_byte = time.perf_counter() - t0
            r.read()
        return {"viewer_url_s": t_url, "viewer_ttfb_s": t_byte}
    finally:
        p.kill()
        p.wait()


def run_fake(args):
    from tests.support import FakeOllama

    python = args.python
    lib = REPO / "searxng" / "lib"
    rows = []
    with FakeOllama(text="Testo di prova riscritto dal modello finto. " * 5) as fake, \
            TempApp(fake.url) as app:
        cwd = str(app.root)
        phases = {
            "startup": lambda: {"wall_s": _time_cmd([python, "-c", "pass"], cwd)},
            "startup_-E_-s": lambda: {"wall_s": _time_cmd([python, "-E", "-s", "-c", "pass"], cwd)},
            "import_qwen_client": lambda: {"wall_s": _time_cmd([python, "-c", "import qwen_client"], cwd)},
            "import_websearch": lambda: {"wall_s": _time_cmd([python, "-c", "import websearch"], cwd)},
            "viewer": lambda: viewer_ttfb(app, python),
        }
        if lib.exists():
            code = f"import sys; sys.path.append({str(lib)!r}); from curl_cffi import requests"
            phases["import_curl_cffi"] = lambda: {"wall_s": _time_cmd([python, "-c", code], cwd)}
        for a in ACTIONS:
            phases[f"action_{a}"] = (lambda a=a: common.run_action(app, a, corpus.text(a, "M"), python))
        names = list(phases)

        for name in names:          # warm-up round (disk cache, .pyc-less imports), not recorded
            phases[name]()
        for rep in range(args.n):
            for name in interleaved(names, rep):
                res = phases[name]()
                if res.get("rc", 0) not in (0,):
                    raise RuntimeError(f"{name} failed: {res}")
                rows.append({"kind": "fake", "phase": name, "rep": rep, **res})
    return rows


def summarize_fake(rows):
    out = {}
    for name in dict.fromkeys(r["phase"] for r in rows):
        rs = [r for r in rows if r["phase"] == name]
        if name == "viewer":
            out["viewer_url"] = stats([r["viewer_url_s"] for r in rs])
            out["viewer_ttfb"] = stats([r["viewer_ttfb_s"] for r in rs])
        else:
            out[name] = stats([r["wall_s"] for r in rs])
    return out


# =========================================================
# REAL: model protocol through the proxy
# =========================================================

STREAM_SNIPPET = r"""
import sys
sys.path.insert(0, sys.argv[1])
import qwen_client
from prompt_loader import prompts
text = open(sys.argv[3], encoding="utf-8").read()
msgs = prompts.first_messages(sys.argv[2], text, None, lunghezza="normale")
n = 0
for piece in qwen_client.stream_pieces(qwen_client.open_stream(msgs, sys.argv[2])):
    n += len(piece)
print(n)
"""


def unload_and_wait(app, python, upstream, timeout=60):
    subprocess.run([python, str(app.root / "actions" / "unload.py")], cwd=str(app.root),
                   env=child_env(), capture_output=True, timeout=120)
    end = time.time() + timeout
    while time.time() < end:
        if not common.loaded_models(upstream):
            return True
        time.sleep(0.5)
    return False


def _chat_records(proxy, start):
    return [r for r in proxy.records[start:] if r.get("path") == "/api/chat"]


def run_real(args):
    from proxy import OllamaProxy

    python = args.python
    upstream = args.upstream.rstrip("/")
    tags = common.get_json(upstream + "/api/tags")
    if args.model not in [m.get("name") for m in tags.get("models", [])]:
        raise SystemExit(f"Model {args.model} not found in {upstream}/api/tags")
    sizes = args.sizes.split(",")
    configs = [(a, s) for a in ACTIONS for s in sizes]
    rows = []
    out_path = args.out

    def record(row):
        rows.append(row)
        common.write_jsonl(out_path, [row])
        srv = row.get("chat") or {}
        print(f"{row['phase']:6} {row['action']:9} {row['size']} rc={row['rc']} wall={row['wall_s']:.2f}s "
              f"load={srv.get('load_s', 0):.2f} pe={srv.get('prompt_eval_count')}/{srv.get('prompt_eval_s', 0):.2f}s "
              f"ev={srv.get('eval_count')}/{srv.get('eval_s', 0):.2f}s {srv.get('done_reason')}", flush=True)

    with OllamaProxy(upstream) as proxy, \
            TempApp(proxy.url, model=args.model, keep_alive=args.keep_alive) as app:

        def one(phase, action, size, rep):
            text = corpus.text(action, size)
            start = len(proxy.records)
            res = common.run_action(app, action, text, python)
            chats = _chat_records(proxy, start)
            row = {"kind": "real", "phase": phase, "action": action, "size": size, "rep": rep, **res,
                   "chat": chats[-1] if chats else None, "n_chat_requests": len(chats)}
            record(row)

        # Cold: model unloaded before every run
        for rep in range(args.cold):
            for action, size in interleaved(configs, rep):
                if not unload_and_wait(app, python, upstream):
                    print("warning: model still loaded after unload", flush=True)
                one("cold", action, size, rep)

        # Warm: one unrecorded warm-up, then interleaved repetitions
        common.run_action(app, "summarize", corpus.text("summarize", "S"), python)
        for rep in range(args.warm):
            for action, size in interleaved(configs, rep):
                one("warm", action, size, rep)

        # Streamed first answer (what E1 / D7 would give): TTFT vs total, warm, size M
        snippet = app.root / "_stream_probe.py"
        snippet.write_text(STREAM_SNIPPET, encoding="utf-8")
        for rep in range(args.stream):
            for action in interleaved(ACTIONS, rep):
                tf = app.work / "stream_in.txt"
                tf.write_text(corpus.text(action, "M"), encoding="utf-8")
                start = len(proxy.records)
                t0 = time.perf_counter()
                p = subprocess.run([python, str(snippet), str(app.root), action, str(tf)], cwd=str(app.root),
                                   env=child_env(), capture_output=True, timeout=900)
                chats = _chat_records(proxy, start)
                record({"kind": "real", "phase": "stream", "action": action, "size": "M", "rep": rep,
                        "rc": p.returncode, "wall_s": time.perf_counter() - t0,
                        "chat": chats[-1] if chats else None, "n_chat_requests": len(chats)})
    return rows


def summarize_real(rows):
    out = {}
    keys = dict.fromkeys((r["phase"], r["action"], r["size"]) for r in rows)
    for phase, action, size in keys:
        rs = [r for r in rows if (r["phase"], r["action"], r["size"]) == (phase, action, size)]
        chats = [r["chat"] for r in rs if r.get("chat")]
        tps = [c["eval_count"] / c["eval_s"] for c in chats if c.get("eval_s")]
        pps = [c["prompt_eval_count"] / c["prompt_eval_s"] for c in chats if c.get("prompt_eval_s")]
        out[f"{phase}/{action}/{size}"] = {
            "in_chars": rs[0].get("in_chars"),
            "rc": sorted({r["rc"] for r in rs}),
            "wall": stats([r["wall_s"] for r in rs]),
            "proxy_total": stats([c.get("total_s") for c in chats]),
            "ttft": stats([c.get("ttft_s") for c in chats]),
            "load": stats([c.get("load_s") for c in chats]),
            "prompt_eval_count": stats([c.get("prompt_eval_count") for c in chats]),
            "prompt_eval": stats([c.get("prompt_eval_s") for c in chats]),
            "eval_count": stats([c.get("eval_count") for c in chats]),
            "eval": stats([c.get("eval_s") for c in chats]),
            "prompt_tok_per_s": stats(pps),
            "gen_tok_per_s": stats(tps),
            "done_reason": sorted({str(c.get("done_reason")) for c in chats}),
            # Process + HTTP overhead around the model call
            "overhead": stats([r["wall_s"] - r["chat"]["total_s"] for r in rs if r.get("chat")]),
        }
    return out


# =========================================================
# OUTPUT
# =========================================================

def print_table(summary):
    def f(x):
        return "-" if x is None else (f"{x * 1000:.1f}" if isinstance(x, float) and x < 10 else f"{x:.3g}")

    for key, s in summary.items():
        if "median" in s:
            print(f"{key:28} n={s['n']:3}  median={f(s['median'])}  p90={f(s['p90'])}  max={f(s['max'])}"
                  "  (ms when < 10 s)")
        else:
            w, ld = s["wall"], s["load"]
            print(f"{key:24} wall med={w.get('median', 0):.2f}s p90={w.get('p90', 0):.2f}s  "
                  f"load med={ld.get('median') or 0:.2f}s  ttft med={s['ttft'].get('median') or 0:.2f}s  "
                  f"pe={s['prompt_eval_count'].get('median')}  ev={s['eval_count'].get('median')}  "
                  f"gen={s['gen_tok_per_s'].get('median') or 0:.1f} tok/s  done={s['done_reason']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true", help="pipeline overhead against FakeOllama")
    mode.add_argument("--real", action="store_true", help="real model through the recording proxy")
    ap.add_argument("--n", type=int, default=20, help="repetitions (fake)")
    ap.add_argument("--cold", type=int, default=3, help="cold repetitions per action/size (real)")
    ap.add_argument("--warm", type=int, default=10, help="warm repetitions per action/size (real)")
    ap.add_argument("--stream", type=int, default=3, help="streamed-TTFT repetitions per action (real)")
    ap.add_argument("--sizes", default="S,M,L", help="corpus sizes (real)")
    ap.add_argument("--model", default="gemma4:e4b-it-qat")
    ap.add_argument("--keep-alive", default="30m")
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--python", default=default_python(), help="interpreter that runs the app")
    ap.add_argument("--tag", default="", help="suffix for the output file names")
    args = ap.parse_args()

    kind = "fake" if args.fake else "real"
    base = common.OUT_DIR / f"{common.stamp()}-{kind}{('-' + args.tag) if args.tag else ''}"
    args.out = base.with_suffix(".jsonl")
    if args.fake:
        rows = run_fake(args)
        common.write_jsonl(args.out, rows)
        summary = summarize_fake(rows)
    else:
        rows = run_real(args)
        summary = summarize_real(rows)
    meta = {"kind": kind, "python": "bundled" if "python" in Path(args.python).parts[-2:-1] else "other",
            "args": {k: v for k, v in vars(args).items() if k not in ("python", "out")}}
    Path(str(base) + "-summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=1),
                                                 encoding="utf-8")
    print_table(summary)
    print(f"\nWritten: {args.out.name} and {Path(str(base) + '-summary.json').name} in tools/bench/out/")


if __name__ == "__main__":
    urllib.request.install_opener(common.NO_PROXY_OPENER)
    main()
