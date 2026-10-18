"""H11: what happens to prompts longer than num_ctx = 16384? (S3, not shipped)

Real local Ollama, through the recording proxy, from a temporary app copy.
Synthetic corpus only.

  1. guard   - the summarize action with a ~45k-character selection: does the
               app's own max_input_chars() guard stop it before Ollama?
  2. app     - the app's summarize request (prompts.first_messages + the app's
               options, num_ctx 16384) sent directly, bypassing the guard,
               at 45k and 75k characters: prompt_eval_count, done_reason.
  3. canary  - a system prompt that demands a fixed first word, followed by
               the long text: if Ollama truncates from the front, the system
               prompt is lost and the canary word disappears.
Ollama server-log lines ("truncated = N", numbers only) are captured too.

    python tools/bench/h11_truncation.py
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import common  # noqa: E402
import corpus  # noqa: E402
from common import TempApp, child_env, default_python  # noqa: E402
from h08_cancel import log_offset, new_log_lines  # noqa: E402

SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import qwen_client
from prompt_loader import prompts
text = open(sys.argv[2], encoding="utf-8").read()
kind = sys.argv[3]
if kind == "app":
    msgs = prompts.first_messages("summarize", text, None, lunghezza="normale")
    answer, reason = qwen_client.chat_ex(msgs, "summarize")
else:
    msgs = [{"role": "system", "content": "Regola assoluta: la tua risposta deve iniziare con la parola ZEBRA42, "
                                          "poi una sola frase in italiano."},
            {"role": "user", "content": text + "\n\nRiassumi il testo qui sopra in una frase."}]
    answer, reason = qwen_client.chat_ex(msgs, "query")   # num_predict 60, num_ctx from prompts.NUM_CTX
print(json.dumps({"done_reason": reason, "starts_with_canary": answer.strip().startswith("ZEBRA42"),
                  "answer_chars": len(answer), "answer_head": answer.strip()[:120]}))
"""


def main():
    from proxy import OllamaProxy

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--model", default="gemma4:e4b-it-qat")
    ap.add_argument("--python", default=default_python())
    args = ap.parse_args()

    results = []
    with OllamaProxy(args.upstream) as proxy, TempApp(proxy.url, model=args.model) as app:
        # 1. guard
        g = common.run_action(app, "summarize", corpus.long_text(45000), args.python)
        g["ollama_requests"] = len([r for r in proxy.records if r.get("path") == "/api/chat"])
        results.append({"test": "guard", **g})
        print(json.dumps(results[-1]), flush=True)

        snippet = app.root / "_h11.py"
        snippet.write_text(SNIPPET, encoding="utf-8")
        for kind, chars in (("canary", 1000), ("canary", 45000), ("app", 45000), ("canary", 75000), ("app", 75000)):
            tf = app.work / "h11_in.txt"
            tf.write_text(corpus.long_text(chars), encoding="utf-8")
            start, off = len(proxy.records), log_offset()
            p = subprocess.run([args.python, str(snippet), str(app.root), str(tf), kind], cwd=str(app.root),
                               env=child_env(), capture_output=True, timeout=900)
            out = p.stdout.decode("utf-8", "replace").strip().splitlines()
            chats = [r for r in proxy.records[start:] if r.get("path") == "/api/chat"]
            c = chats[-1] if chats else {}
            row = {"test": kind, "in_chars": chars, "rc": p.returncode,
                   "result": json.loads(out[-1]) if p.returncode == 0 and out else
                   p.stderr.decode("utf-8", "replace").strip().splitlines()[-1:],
                   "num_ctx": (c.get("options") or {}).get("num_ctx"),
                   "prompt_chars": c.get("prompt_chars"), "prompt_eval_count": c.get("prompt_eval_count"),
                   "eval_count": c.get("eval_count"), "done_reason": c.get("done_reason"),
                   "status": c.get("status"), "error": c.get("error"), "total_s": c.get("total_s"),
                   "log": new_log_lines(off)}
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    out = common.OUT_DIR / f"{common.stamp()}-h11.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Written:", out.name)


if __name__ == "__main__":
    main()
