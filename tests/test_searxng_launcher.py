"""Tests for searxng/avvia_searxng.py (step S6c: C19, H09, H10, contract K5).

Safety (plan §1): every launcher run uses a temp work dir and a free port, never 8888 or the
live work\\ folder, and only processes spawned here are killed. The SearXNG integration tests
need the vendored searxng/app + searxng/lib and the bundled python\\python.exe (cp313 wheels);
they are skipped when those are absent.
"""

import contextlib
import http.client
import importlib.util
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import REPO, free_port

LAUNCHER = REPO / "searxng" / "avvia_searxng.py"
BUNDLED_PY = REPO / "python" / "python.exe"
HAVE_SEARXNG = (REPO / "searxng" / "app" / "searx").is_dir() and (REPO / "searxng" / "lib").is_dir()
WIN = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _load_launcher():
    spec = importlib.util.spec_from_file_location("avvia_searxng_under_test", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _load_launcher()


def _safe_port():
    port = free_port()
    assert port != 8888
    return port


def _isolated_env(tmp):
    env = dict(os.environ)
    # SearXNG keeps its sqlite cache in tempfile.gettempdir(): keep it off the user's live cache.
    env.update(TMP=str(tmp), TEMP=str(tmp), TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
    env.pop("SEARXNG_SECRET", None)
    return env


def _http_status(port, path, host_header, timeout=30):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Host": host_header})
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class PidRecordTests(unittest.TestCase):
    def test_parse_k5_and_legacy(self):
        self.assertEqual(L.parse_pid_record("1234 133000000000000000"), (1234, 133000000000000000))
        self.assertEqual(L.parse_pid_record("1234\r\n"), (1234, None))
        for bad in ("", "abc", "12 x", "1 2 3", "-5", "0 1", "²"):
            self.assertIsNone(L.parse_pid_record(bad), bad)

    def test_write_read_remove_only_if_ours(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "searxng.pid"
            L.write_pid_file(pid_file, 42, 1000)
            self.assertEqual(pid_file.read_text(encoding="ascii"), "42 1000")
            self.assertEqual(L.read_pid_file(pid_file), (42, 1000))
            self.assertFalse(L.remove_pid_file_if_ours(pid_file, 42, 999))
            self.assertFalse(L.remove_pid_file_if_ours(pid_file, 43, 1000))
            self.assertTrue(pid_file.exists())
            self.assertTrue(L.remove_pid_file_if_ours(pid_file, 42, 1000))
            self.assertFalse(pid_file.exists())
            self.assertFalse(list(Path(tmp).iterdir()), "no tmp file left behind")


@unittest.skipUnless(WIN, "Windows process API")
class ProcessIdentityTests(unittest.TestCase):
    def test_own_creation_time_matches_lookup(self):
        ctime = L.own_creation_time()
        self.assertGreater(ctime, 116444736000000000)  # after 1970 in FILETIME units
        self.assertEqual(L.process_creation_time(os.getpid()), ctime)

    def test_exited_process_is_not_live(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=NO_WINDOW)
        p.wait(30)  # the Popen handle keeps the pid from being reused
        self.assertIsNone(L.process_creation_time(p.pid))

    def test_pid_file_names_live_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "searxng.pid"
            self.assertFalse(L.pid_file_names_live_process(pid_file))
            L.write_pid_file(pid_file, os.getpid(), L.own_creation_time())
            self.assertTrue(L.pid_file_names_live_process(pid_file))
            L.write_pid_file(pid_file, os.getpid(), L.own_creation_time() + 1)
            self.assertFalse(L.pid_file_names_live_process(pid_file), "pid reused by another process")
            pid_file.write_text(str(os.getpid()), encoding="ascii")
            self.assertTrue(L.pid_file_names_live_process(pid_file), "legacy format accepted")


class LockTests(unittest.TestCase):
    def test_second_lock_fails_until_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "searxng.lock"
            fd = L.acquire_lock(path)
            self.assertIsNotNone(fd)
            try:
                self.assertIsNone(L.acquire_lock(path))
            finally:
                os.close(fd)
            fd2 = L.acquire_lock(path)
            self.assertIsNotNone(fd2)
            os.close(fd2)


class RotatingLogTests(unittest.TestCase):
    def test_appends_and_rotates_keeping_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "searxng.log"
            path.write_text("previous run\n", encoding="utf-8")
            log = L.RotatingLog(path, max_bytes=200)
            log.write("first line\n")
            log.flush()
            self.assertEqual(path.read_text(encoding="utf-8"), "previous run\nfirst line\n")
            for i in range(30):
                log.write(f"line {i:02d} xxxxxxxxxx\n")
            log.close()
            old = path.with_name("searxng.log.1")
            self.assertTrue(old.exists())
            self.assertLessEqual(path.stat().st_size, 200)
            self.assertFalse(path.with_name("searxng.log.2").exists())
            self.assertIn("line 29", path.read_text(encoding="utf-8") + old.read_text(encoding="utf-8"))

    def test_rotates_oversized_file_at_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "searxng.log"
            path.write_text("x" * 300, encoding="utf-8")
            log = L.RotatingLog(path, max_bytes=200)
            log.write("new\n")
            log.close()
            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(path.with_name("searxng.log.1").stat().st_size, 300)


class HostAllowlistTests(unittest.TestCase):
    def test_host_allowed(self):
        for ok in ("127.0.0.1", "127.0.0.1:8888", "localhost", "LOCALHOST:1", " localhost:5 "):
            self.assertTrue(L.host_allowed(ok), ok)
        for bad in (None, "", "evil.example", "evil.example:8888", "127.0.0.1.evil.example",
                    "localhost.evil.example", "127.0.0.2", "[::1]:8888", "localhost:x", "0.0.0.0"):
            self.assertFalse(L.host_allowed(bad), bad)

    def test_middleware(self):
        calls = []

        def app(environ, start_response):
            calls.append(environ["HTTP_HOST"])
            start_response("200 OK", [])
            return [b"ok"]

        mw = L.HostAllowlist(app)
        seen = {}

        def start_response(status, headers):
            seen["status"] = status

        self.assertEqual(mw({"HTTP_HOST": "evil.example"}, start_response)[0][:9], b"Forbidden")
        self.assertTrue(seen["status"].startswith("403"))
        self.assertEqual(calls, [])
        self.assertEqual(mw({"HTTP_HOST": "localhost:1234"}, start_response), [b"ok"])
        self.assertEqual(seen["status"], "200 OK")


class ArgsTests(unittest.TestCase):
    def test_explicit_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = L.parse_args(["--port", "12345", "--work-dir", tmp])
            self.assertEqual(args.port, 12345)
            self.assertEqual(args.work_dir, Path(tmp).resolve())

    def test_defaults_follow_config(self):
        orig = L.searxng_url
        try:
            L.searxng_url = lambda: "http://127.0.0.1:9123"
            self.assertEqual(L.parse_args([]).port, 9123)
            L.searxng_url = lambda: "http://localhost"
            self.assertEqual(L.parse_args([]).port, 8888)
            L.searxng_url = lambda: "http://127.0.0.1:notaport"
            self.assertEqual(L.parse_args([]).port, 8888)
        finally:
            L.searxng_url = orig
        self.assertEqual(L.parse_args([]).work_dir, L.DEFAULT_WORK)

    def test_bad_port_is_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in (["--port", "0"], ["--port", "70000"], ["--port", "abc"], ["--bogus"]):
                with self.assertRaises(SystemExit) as cm:
                    L.parse_args(argv)
                self.assertEqual(cm.exception.code, L.EXIT_USAGE)
            self.assertEqual(L.main(["--port", "0"]), L.EXIT_USAGE)


# ---------------------------------------------------------------------------
# Launcher subprocess, without SearXNG (copy of the launcher in a temp tree)
# ---------------------------------------------------------------------------

class LauncherEarlyExitTests(unittest.TestCase):
    """Paths that exit before SearXNG is imported: any Python works, a fake app dir is enough."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aih-s6c-"))
        (self.tmp / "searxng" / "app" / "searx").mkdir(parents=True)
        shutil.copy2(LAUNCHER, self.tmp / "searxng" / "avvia_searxng.py")
        self.work = self.tmp / "work"
        self.port = _safe_port()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_launcher(self):
        return subprocess.run(
            [sys.executable, "-B", str(self.tmp / "searxng" / "avvia_searxng.py"),
             "--port", str(self.port), "--work-dir", str(self.work)],
            cwd=str(self.tmp), env=_isolated_env(self.tmp), capture_output=True, timeout=60,
            creationflags=NO_WINDOW,
        ).returncode

    def test_foreign_port_holder(self):
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", self.port))
            holder.listen(1)
            self.assertEqual(self.run_launcher(), L.EXIT_PORT_FOREIGN)
        log = (self.work / "searxng.log").read_text(encoding="utf-8")
        self.assertIn(f"ERROR: port {self.port} on 127.0.0.1 is used by another program", log)
        self.assertEqual(len(log.strip().splitlines()), 1)
        self.assertFalse((self.work / "searxng.pid").exists())

    @unittest.skipUnless(WIN, "SO_EXCLUSIVEADDRUSE semantics")
    def test_bound_but_not_listening_port(self):
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", self.port))  # connect fails, bind must still fail
            self.assertEqual(self.run_launcher(), L.EXIT_PORT_FOREIGN)
        self.assertIn("ERROR: cannot use port", (self.work / "searxng.log").read_text(encoding="utf-8"))

    def test_lock_held_exits_quietly(self):
        self.work.mkdir()
        (self.work / "searxng.log").write_text("winner's log\n", encoding="utf-8")
        fd = L.acquire_lock(self.work / "searxng.lock")
        try:
            self.assertEqual(self.run_launcher(), L.EXIT_ALREADY_RUNNING)
        finally:
            os.close(fd)
        self.assertEqual((self.work / "searxng.log").read_text(encoding="utf-8"), "winner's log\n")
        self.assertFalse((self.work / "searxng.pid").exists())

    def test_missing_app(self):
        shutil.rmtree(self.tmp / "searxng" / "app")
        self.assertEqual(self.run_launcher(), L.EXIT_NO_APP)
        self.assertIn("missing folder", (self.work / "searxng.log").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Real SearXNG: H09 (double launch) and H10 (Host header)
# ---------------------------------------------------------------------------

def _listeners(port):
    """Owning PIDs of sockets listening on 127.0.0.1:<port> (Get-NetTCPConnection)."""
    cmd = (f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue "
           "| ForEach-Object { $_.OwningProcess }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                         timeout=60, creationflags=NO_WINDOW).stdout
    return [int(x) for x in out.split() if x.isdigit()]


@unittest.skipUnless(WIN and HAVE_SEARXNG and BUNDLED_PY.exists(),
                     "needs Windows, vendored searxng/app + searxng/lib and python\\python.exe")
class DoubleLaunchTests(unittest.TestCase):
    MARKER = "marker line written before the launches\n"

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aih-s6c-h09-"))
        cls.work = cls.tmp / "work"
        cls.work.mkdir()
        (cls.work / "searxng.log").write_text(cls.MARKER, encoding="utf-8")
        cls.port = _safe_port()
        cmd = [str(BUNDLED_PY), "-B", str(LAUNCHER), "--port", str(cls.port), "--work-dir", str(cls.work)]
        kw = dict(cwd=str(cls.tmp), env=_isolated_env(cls.tmp), stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        cls.procs = []
        cls.first = subprocess.Popen(cmd, **kw)
        cls.procs.append(cls.first)
        time.sleep(2)
        cls.second = subprocess.Popen(cmd, **kw)
        cls.procs.append(cls.second)
        cls.second_rc = cls.second.wait(60)
        cls.healthy = False
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and cls.first.poll() is None:
            try:
                if _http_status(cls.port, "/healthz", f"127.0.0.1:{cls.port}", timeout=3) == 200:
                    cls.healthy = True
                    break
            except OSError:
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:  # only the processes started here
            if p.poll() is None:
                p.kill()
                p.wait(30)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_h09_single_instance(self):
        self.assertTrue(self.healthy, (self.work / "searxng.log").read_text(encoding="utf-8", errors="replace"))
        self.assertEqual(self.second_rc, L.EXIT_ALREADY_RUNNING)
        self.assertIsNone(self.first.poll())
        self.assertEqual(_listeners(self.port), [self.first.pid])
        with self.assertRaises(OSError):  # nobody else can bind the port, even with SO_REUSEADDR
            s = socket.socket()
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", self.port))
            finally:
                s.close()

    def test_h09_pid_file_is_k5_and_live(self):
        record = L.read_pid_file(self.work / "searxng.pid")
        self.assertIsNotNone(record)
        pid, ctime = record
        self.assertEqual(pid, self.first.pid)
        self.assertIsNotNone(ctime)
        self.assertEqual(L.process_creation_time(pid), ctime)

    def test_h09_log_not_truncated(self):
        log = (self.work / "searxng.log").read_text(encoding="utf-8", errors="replace")
        self.assertTrue(log.startswith(self.MARKER))
        self.assertIn(f"(pid {self.first.pid})", log)
        self.assertNotIn(f"(pid {self.second.pid})", log)
        self.assertEqual(log.count("Ready."), 1)

    def test_h10_foreign_host_rejected(self):
        self.assertTrue(self.healthy)
        # Rejected before SearXNG sees it, so no search leaves the machine.
        self.assertEqual(_http_status(self.port, "/search?q=t&format=json", "evil.example"), 403)
        self.assertEqual(_http_status(self.port, "/healthz", f"evil.example:{self.port}"), 403)
        self.assertEqual(_http_status(self.port, "/healthz", f"localhost:{self.port}"), 200)
        self.assertEqual(_http_status(self.port, "/healthz", "127.0.0.1"), 200)


if __name__ == "__main__":
    unittest.main()
