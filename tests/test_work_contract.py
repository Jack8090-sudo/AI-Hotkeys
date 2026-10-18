"""S9: the work/ contract — per-run directories, cleanup, privacy (C32), H04, orphans (C18)."""

import http.client
import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from tests.support import AppTree, FakeOllama

RUN_A = "20261018120000-00000000000000aa"
RUN_B = "20261018120001-00000000000000bb"


def make_run(tree, run_id, text):
    d = tree.work / "runs" / run_id
    d.mkdir(parents=True)
    (d / "input.txt").write_text(text, encoding="utf-8")
    return d


def files_under(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*") if p.is_file())


class ViewerProcess:
    """viewer.py --no-browser in a subprocess: the URL it prints, then the page."""

    def __init__(self, tree, args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        self.p = subprocess.Popen([sys.executable, "-E", "-s", str(tree.root / "viewer.py"), *args, "--no-browser"],
                                  cwd=tree.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8")
        line = self.p.stdout.readline().strip()
        if not line.startswith("http://127.0.0.1:"):
            self.close()
            raise AssertionError(f"viewer did not start: {line!r} {self.p.stderr.read()!r}")
        m = re.match(r"http://127\.0\.0\.1:(\d+)(/\?t=.*)", line)
        self.port, self.path = int(m.group(1)), m.group(2)

    def page(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", self.path)
            r = conn.getresponse()
            return r.status, r.read().decode("utf-8")
        finally:
            conn.close()

    def close(self):
        self.p.kill()
        self.p.wait(10)
        self.p.stdout.close()
        self.p.stderr.close()


def run_script(tree, action, *args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-E", "-s", str(tree.root / "actions" / f"{action}.py"), *args],
                          cwd=tree.root, env=env, capture_output=True, text=True, timeout=60).returncode


class RunDirTest(unittest.TestCase):
    def setUp(self):
        self.ollama = FakeOllama(text="ALPHA-RESULT")
        self.tree = AppTree(ollama_url=self.ollama.url)
        self.qc = self.tree.load("qwen_client")

    def tearDown(self):
        self.ollama.close()
        self.tree.close()

    # ---- writers ----

    def test_run_dir_receives_output_meta_and_nothing_in_work_root(self):
        d = make_run(self.tree, RUN_A, "ALPHA-INPUT")
        self.assertEqual(self.qc.run_action("summarize", ["x", f"--run-dir={d}"]), 0)
        self.assertEqual((d / "output.txt").read_text(encoding="utf-8"), "ALPHA-RESULT")
        self.assertEqual(json.loads((d / "meta.json").read_text(encoding="utf-8"))["mode"], "summarize")
        self.assertFalse((d / "error.txt").exists())
        # nothing in work\ itself (only config warnings may go there, K6)
        self.assertEqual([p.name for p in self.tree.work.iterdir() if p.is_file()], [])
        self.assertEqual([p.name for p in d.iterdir() if p.name.endswith(".tmp")], [])

    def test_K1_error_goes_to_the_run_dir(self):
        self.ollama.scenario = "http404"
        d = make_run(self.tree, RUN_A, "testo")
        self.assertEqual(self.qc.run_action("rewrite", ["x", f"--run-dir={d}"]), 1)
        self.assertIn("ollama pull", (d / "error.txt").read_text(encoding="utf-8").split("\n")[0])
        self.assertFalse((d / "output.txt").exists())
        self.assertFalse((self.tree.work / "error.txt").exists())

    def test_explain_sources_and_status_stay_in_the_run_dir(self):
        d = make_run(self.tree, RUN_A, "testo da spiegare")
        self.assertEqual(self.qc.run_action("explain", ["x", f"--run-dir={d}"]), 0)
        self.assertTrue((d / "sources.json").exists())
        self.assertFalse((self.tree.work / "sources.json").exists())
        self.assertFalse((self.tree.work / "status.txt").exists())

    def test_old_argv_form_still_writes_to_work(self):
        inp, out = self.tree.work / "input.txt", self.tree.work / "output.txt"
        inp.write_text("testo", encoding="utf-8")
        self.assertEqual(self.qc.run_action("rewrite", ["x", str(inp), str(out)]), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "ALPHA-RESULT")
        self.assertTrue((self.tree.work / "meta.json").exists())

    def test_missing_run_dir_is_never_created(self):
        d = self.tree.work / "runs" / RUN_A
        self.assertEqual(self.qc.run_action("rewrite", ["x", f"--run-dir={d}"]), 1)
        self.assertFalse(d.exists())

    def test_bad_command_line_is_reported(self):
        self.assertEqual(self.qc.run_action("rewrite", ["x"]), 1)
        self.assertTrue((self.tree.work / "error.txt").exists())

    # ---- orphans (C18) ----

    def test_orphan_writing_late_cannot_affect_a_newer_run(self):
        """Run A is cancelled (its folder deleted) while Ollama answers; run B starts meanwhile."""
        self.ollama.delay = 1.0
        a = make_run(self.tree, RUN_A, "ALPHA-INPUT")
        rc = {}
        t = threading.Thread(target=lambda: rc.setdefault("a", self.qc.run_action("rewrite", ["x", f"--run-dir={a}"])))
        t.start()
        time.sleep(0.4)                       # A has read its input and waits for Ollama
        self.qc.remove_run_dir(a)             # Esc / Exit: main.ahk deletes A's folder
        t.join(30)
        self.assertNotEqual(rc["a"], 0)
        self.assertFalse(a.exists(), "a late writer must not recreate its run folder")

        self.ollama.delay = 0
        self.ollama.text = "BETA-RESULT"
        b = make_run(self.tree, RUN_B, "BETA-INPUT")
        self.assertEqual(self.qc.run_action("rewrite", ["x", f"--run-dir={b}"]), 0)
        self.assertEqual((b / "output.txt").read_text(encoding="utf-8"), "BETA-RESULT")
        self.assertFalse((self.tree.work / "output.txt").exists())

    # ---- sweep ----

    def test_stale_run_sweep(self):
        old = make_run(self.tree, RUN_A, "vecchio")
        new = make_run(self.tree, RUN_B, "nuovo")
        other = self.tree.work / "runs" / "not-a-run"
        other.mkdir()
        two_hours_ago = time.time() - 7200
        for p in (old, other):
            os.utime(p, (two_hours_ago, two_hours_ago))
        self.assertEqual(self.qc.sweep_stale_runs(), [RUN_A])
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertTrue(other.exists(), "only folders named like a run id are deleted")
        # keep= protects the current run even when it looks old
        os.utime(new, (two_hours_ago, two_hours_ago))
        self.assertEqual(self.qc.sweep_stale_runs(keep=new), [])
        self.assertTrue(new.exists())

    def test_a_run_sweeps_stale_runs(self):
        old = make_run(self.tree, RUN_A, "vecchio")
        os.utime(old, (time.time() - 7200,) * 2)
        b = make_run(self.tree, RUN_B, "nuovo")
        self.assertEqual(self.qc.run_action("rewrite", ["x", f"--run-dir={b}"]), 0)
        self.assertFalse(old.exists())

    def test_is_run_dir(self):
        self.assertTrue(self.qc.is_run_dir(self.tree.work / "runs" / RUN_A))
        self.assertFalse(self.qc.is_run_dir(self.tree.work / "runs" / "x"))
        self.assertFalse(self.qc.is_run_dir(self.tree.root / RUN_A))
        self.assertFalse(self.qc.is_run_dir(self.tree.work / "runs" / RUN_A / RUN_B))


class ViewerContractTest(unittest.TestCase):
    """End to end: actions and viewer as subprocesses, like main.ahk starts them."""

    def setUp(self):
        self.ollama = FakeOllama(text="ALPHA-RESULT")
        self.tree = AppTree(ollama_url=self.ollama.url)
        self.viewers = []

    def tearDown(self):
        for v in self.viewers:
            v.close()
        self.ollama.close()
        self.tree.close()

    def viewer(self, *args):
        v = ViewerProcess(self.tree, list(args))
        self.viewers.append(v)
        return v

    def test_C32_no_plaintext_selection_in_work_after_the_viewer_loaded(self):
        d = make_run(self.tree, RUN_A, "SECRET-SELECTION")
        self.assertEqual(run_script(self.tree, "summarize", f"--run-dir={d}"), 0)
        v = self.viewer(f"--run-dir={d}", "Summary", "summarize", "--key=PgDn")
        status, page = v.page()
        self.assertEqual(status, 200)
        self.assertIn("SECRET-SELECTION", page)
        self.assertIn("ALPHA-RESULT", page)
        self.assertFalse(d.exists())
        for f in files_under(self.tree.work):
            text = (self.tree.work / f).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("SECRET-SELECTION", text, f)
            self.assertNotIn("ALPHA-RESULT", text, f)

    def test_H04_two_runs_back_to_back_give_correct_pairs(self):
        a = make_run(self.tree, RUN_A, "ALPHA-INPUT")
        self.assertEqual(run_script(self.tree, "rewrite", f"--run-dir={a}"), 0)
        self.ollama.text = "BETA-RESULT"
        b = make_run(self.tree, RUN_B, "BETA-INPUT")
        self.assertEqual(run_script(self.tree, "rewrite", f"--run-dir={b}"), 0)
        # A's viewer starts only after B finished: it used to show B's files
        va = self.viewer(f"--run-dir={a}", "Fix", "rewrite")
        vb = self.viewer(f"--run-dir={b}", "Fix", "rewrite")
        pa, pb = va.page()[1], vb.page()[1]
        self.assertIn("ALPHA-INPUT", pa)
        self.assertIn("ALPHA-RESULT", pa)
        self.assertNotIn("BETA", pa)
        self.assertIn("BETA-INPUT", pb)
        self.assertIn("BETA-RESULT", pb)
        self.assertNotIn("ALPHA", pb)

    def test_old_argv_form_still_works(self):
        inp, out = self.tree.work / "input.txt", self.tree.work / "output.txt"
        inp.write_text("OLD-INPUT", encoding="utf-8")
        out.write_text("OLD-RESULT", encoding="utf-8")
        v = self.viewer(str(inp), str(out), "Fix", "rewrite", "--key=PgUp")
        page = v.page()[1]
        self.assertIn("OLD-INPUT", page)
        self.assertIn("OLD-RESULT", page)
        self.assertFalse(inp.exists())        # inside work\: deleted once loaded
        self.assertFalse(out.exists())

    def test_old_form_never_deletes_files_outside_work(self):
        inp, out = self.tree.root / "mine-in.txt", self.tree.root / "mine-out.txt"
        inp.write_text("A", encoding="utf-8")
        out.write_text("B", encoding="utf-8")
        self.viewer(str(inp), str(out), "Fix", "rewrite")
        self.assertTrue(inp.exists())
        self.assertTrue(out.exists())

    def test_run_dir_outside_work_runs_is_not_deleted(self):
        d = self.tree.root / RUN_A
        d.mkdir()
        (d / "input.txt").write_text("A", encoding="utf-8")
        (d / "output.txt").write_text("B", encoding="utf-8")
        self.viewer(f"--run-dir={d}", "Fix", "rewrite")
        self.assertTrue((d / "input.txt").exists())

    def test_load_run_usage(self):
        v = self.tree.load("viewer")
        with self.assertRaises(SystemExit):
            v.load_run(["--run-dir=x"])
        with self.assertRaises(SystemExit):
            v.load_run(["a", "b"])


if __name__ == "__main__":
    unittest.main()
