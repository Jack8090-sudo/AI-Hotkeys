"""H04: a second action started right after the viewer is spawned (S3, not shipped).

Replays main.ahk's sequence in a temporary app copy against FakeOllama, with
synthetic text only:

  run 1 finished:  work/input.txt = A, work/output.txt = A-result
                   spawn  viewer.py input output ... --no-browser       (viewer 1)
  after `delay`:   run 2 starts: input.txt = B, output.txt deleted,
                   actions/summarize.py runs (FakeOllama, `--model-delay` s)
  then:            what does viewer 1 show?  A/A (correct), B/B (run 2's pair,
                   run 1's result lost), A/B or B/A (mismatched pair), or crash.

    python tools/bench/h04_viewer_race.py --reps 10
"""

import argparse
import collections
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import common  # noqa: E402
from common import TempApp, child_env, default_python  # noqa: E402

DELAYS_MS = (0, 25, 50, 100, 150, 200, 250, 300, 400, 600, 1000)


def classify(page, err):
    if page is None:
        last = err.strip().splitlines()[-1] if err.strip() else "no output"
        return "crash: " + re.sub(r"'[^']*'", "<path>", last)[:80]      # no user paths in the output
    orig = "A" if "ORIGINALE-AAA" in page else ("B" if "ORIGINALE-BBB" in page else "?")
    res = "A" if "RISULTATO-AAA" in page else ("B" if "RISULTATO-BBB" in page else "?")
    return f"{orig}/{res}"


def one(app, python, delay, fake):
    work = app.work
    (work / "input.txt").write_text("ORIGINALE-AAA testo di prova del primo lancio.", encoding="utf-8")
    (work / "output.txt").write_text("RISULTATO-AAA risposta del primo lancio.", encoding="utf-8")
    t0 = time.perf_counter()
    viewer = subprocess.Popen(
        [python, str(app.root / "viewer.py"), str(work / "input.txt"), str(work / "output.txt"),
         "Riassunto", "summarize", "--key=PgDn", "--no-browser"],
        cwd=str(app.root), env=child_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    line = {}
    reader = threading.Thread(target=lambda: line.setdefault("url", viewer.stdout.readline().decode().strip()),
                              daemon=True)
    reader.start()

    time.sleep(delay / 1000)
    # Run 2, as RunSelectionAction does it
    (work / "input.txt").write_text("ORIGINALE-BBB testo di prova del secondo lancio.", encoding="utf-8")
    if (work / "output.txt").exists():
        (work / "output.txt").unlink()
    fake.text = "RISULTATO-BBB risposta del secondo lancio."
    subprocess.run([python, str(app.root / "actions" / "summarize.py"), str(work / "input.txt"),
                    str(work / "output.txt")], cwd=str(app.root), env=child_env(), capture_output=True)

    reader.join(10)
    page, err = None, ""
    url = line.get("url", "")
    if url.startswith("http"):
        with common.NO_PROXY_OPENER.open(url, timeout=10) as r:
            page = r.read().decode("utf-8", "replace")
    else:
        viewer.wait(10)
        err = viewer.stderr.read().decode("utf-8", "replace")
    viewer.kill()
    viewer.wait()
    return classify(page, err), time.perf_counter() - t0


def main():
    from tests.support import FakeOllama

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--model-delay", type=float, default=0.0, help="FakeOllama answer delay for run 2 (s)")
    ap.add_argument("--python", default=default_python())
    args = ap.parse_args()

    table = {}
    with FakeOllama(delay=args.model_delay) as fake, TempApp(fake.url) as app:
        one(app, args.python, 1000, fake)               # warm-up (bytecode cache)
        for rep in range(args.reps):
            for d in common.interleaved(DELAYS_MS, rep):
                outcome, _ = one(app, args.python, d, fake)
                table.setdefault(d, collections.Counter())[outcome] += 1
    print(f"model delay for run 2: {args.model_delay}s, reps per delay: {args.reps}")
    for d in DELAYS_MS:
        print(f"delay {d:5} ms: " + ", ".join(f"{k} x{v}" for k, v in sorted(table[d].items())))
    out = common.OUT_DIR / f"{common.stamp()}-h04.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model_delay": args.model_delay, "reps": args.reps,
                               "table": {d: dict(c) for d, c in table.items()}}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
