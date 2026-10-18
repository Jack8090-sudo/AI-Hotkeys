"""Explain (End) phase split and H23 data (S3, not shipped).

Runs the explain action with web_search = auto from a temporary app copy,
through the recording proxy, against the REAL local Ollama:

  - default: a FakeSearx on 127.0.0.1 that returns no results. No internet
    traffic; this isolates the query-decision LLM call (mode "query",
    num_predict 60) from the final answer;
  - --searxng: additionally one pass with a real SearXNG started on a free
    ALTERNATE port (never 8888) with a temporary --work-dir, to split
    decision / search+fetch / answer with real web pages.

For H23 it records, per text, the technical terms found by
websearch.technical_terms() (which force a search) next to the queries the
model produced, so the fallback query can be compared with the model's.

    python tools/bench/explain_split.py [--reps 5] [--searxng]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import common  # noqa: E402
import corpus  # noqa: E402
from common import REPO, TempApp, child_env, default_python, stats  # noqa: E402

PERSONAL = (
    "Oggi mi sono reso conto che passo troppo tempo a rispondere ai messaggi invece di concentrarmi sul "
    "lavoro importante. Da domani provo a controllare la posta solo due volte al giorno e vediamo come va."
)

TEXTS = {
    "tech_S": corpus.text("explain", "S"),
    "tech_M": corpus.text("explain", "M"),
    "personal": PERSONAL,
}


def run_pass(app, proxy, python, reps, label):
    rows = []
    for rep in range(reps):
        for name in common.interleaved(list(TEXTS), rep):
            start = len(proxy.records)
            res = common.run_action(app, "explain", TEXTS[name], python)
            chats = [r for r in proxy.records[start:] if r.get("path") == "/api/chat"]
            q = [c for c in chats if (c.get("options") or {}).get("num_predict") == 60]
            main_ = [c for c in chats if (c.get("options") or {}).get("num_predict") != 60]
            try:
                queries = json.loads((app.work / "sources.json").read_text(encoding="utf-8")).get("queries", [])
                n_sources = len(json.loads((app.work / "sources.json").read_text(encoding="utf-8"))["sources"])
            except (OSError, ValueError, KeyError):
                queries, n_sources = [], 0
            row = {"pass": label, "text": name, "rep": rep, **res,
                   "query_call_s": q[0]["total_s"] if q else None,
                   "query_eval_count": q[0].get("eval_count") if q else None,
                   "answer_call_s": main_[-1]["total_s"] if main_ else None,
                   "answer_prompt_eval_count": main_[-1].get("prompt_eval_count") if main_ else None,
                   "queries": queries, "n_sources": n_sources}
            row["search_and_fetch_s"] = (None if not (q and main_) else
                                         row["wall_s"] - row["query_call_s"] - row["answer_call_s"])
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return rows


def main():
    from proxy import OllamaProxy
    from tests.support import FakeSearx

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--searxng", action="store_true", help="also one pass with a real SearXNG on a free port")
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--model", default="gemma4:e4b-it-qat")
    ap.add_argument("--python", default=default_python())
    args = ap.parse_args()

    import websearch      # repo copy, only for technical_terms() (pure function)
    terms = {k: websearch.technical_terms(v) for k, v in TEXTS.items()}
    print("technical terms:", json.dumps(terms, ensure_ascii=False))

    rows = []
    with OllamaProxy(args.upstream) as proxy, FakeSearx(results=[]) as searx, \
            TempApp(proxy.url, model=args.model, web_search="auto", searxng_url=searx.url) as app:
        common.run_action(app, "summarize", corpus.text("summarize", "S"), args.python)   # warm the model
        rows += run_pass(app, proxy, args.python, args.reps, "fake-searx")

        if args.searxng:
            port = common_free_port()
            assert port != 8888
            wd = app.root / "searx-work"
            wd.mkdir()
            env = dict(child_env(), PYTHONDONTWRITEBYTECODE="1")
            env.pop("PYTHONPYCACHEPREFIX", None)
            sx = subprocess.Popen([args.python, str(REPO / "searxng" / "avvia_searxng.py"), "--port", str(port),
                                   "--work-dir", str(wd)], cwd=str(REPO), env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                url = f"http://127.0.0.1:{port}"
                ok = False
                for _ in range(120):
                    time.sleep(0.5)
                    try:
                        with common.NO_PROXY_OPENER.open(url + "/healthz", timeout=2) as r:
                            ok = r.status == 200
                    except OSError:
                        pass
                    if ok or sx.poll() is not None:
                        break
                print("real SearXNG up:", ok, flush=True)
                if ok:
                    app.write_config(ollama_url=proxy.url, model=args.model, keep_alive="30m",
                                     web_search="auto", searxng_url=url)
                    rows += run_pass(app, proxy, args.python, 1, "real-searx")
            finally:
                subprocess.run(["taskkill", "/PID", str(sx.pid), "/T", "/F"], capture_output=True)

    summary = {}
    for label in dict.fromkeys(r["pass"] for r in rows):
        for name in TEXTS:
            rs = [r for r in rows if r["pass"] == label and r["text"] == name]
            if rs:
                summary[f"{label}/{name}"] = {k: stats([r[k] for r in rs]) for k in
                                              ("wall_s", "query_call_s", "answer_call_s", "search_and_fetch_s")}
                summary[f"{label}/{name}"]["queries"] = [r["queries"] for r in rs]
    out = common.OUT_DIR / f"{common.stamp()}-explain-split.json"
    out.write_text(json.dumps({"terms": terms, "summary": summary, "rows": rows}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print("Written:", out.name)


def common_free_port():
    from tests.support import free_port
    p = free_port()
    while p == 8888:
        p = free_port()
    return p


if __name__ == "__main__":
    main()
