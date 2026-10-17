"""
AI-Hotkeys — start local SearXNG (search engine for End).

Launched in the background by main.ahk at startup and, if needed, by websearch.py.
Uses AI-Hotkeys' portable Python: no Docker, no WSL.

    searxng\\app\\searx\\   SearXNG code
    searxng\\lib\\          required libraries
    searxng\\settings.yml   settings
    work\\searxng.lock      held for the whole life of the running instance
    work\\searxng.log       log (appended; rotated to searxng.log.1 at 5 MB)
    work\\searxng.pid       "<pid> <creation time as Windows FILETIME UTC>" (contract K5)

Usage:  avvia_searxng.py [--port N] [--work-dir DIR]
    --port      default: port of searxng_url in config.ini, otherwise 8888
    --work-dir  default: work\\ next to the app

Exit codes:
    0  stopped cleanly
    1  unexpected error (details in the log)
    2  searxng\\app\\searx is missing
    3  another launcher already owns this work dir (lock held): nothing to do
    4  the port is held by a process that is not this SearXNG
    5  invalid command line
"""

import argparse
import configparser
import os
import secrets
import socket
import sys
import threading
import types
import warnings
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
DEFAULT_WORK = BASE / "work"

HOST = "127.0.0.1"
DEFAULT_PORT = 8888
DEFAULT_URL = f"http://{HOST}:{DEFAULT_PORT}"

LOG_MAX_BYTES = 5 * 1024 * 1024

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_APP = 2
EXIT_ALREADY_RUNNING = 3
EXIT_PORT_FOREIGN = 4
EXIT_USAGE = 5

# Host header values accepted by the server (any port): blocks DNS rebinding (H10).
ALLOWED_HOSTS = ("127.0.0.1", "localhost")

# Kept open for the process lifetime: closing it would release the lock.
_lock_fd = None


# ---------------------------------------------------------------------------
# Configuration and command line
# ---------------------------------------------------------------------------

def searxng_url():
    parser = configparser.RawConfigParser()
    try:
        parser.read(BASE / "config.ini", encoding="utf-8-sig")
        url = parser.get("searxng", "searxng_url", fallback="").strip()
    except Exception:
        url = ""
    return url or DEFAULT_URL


def port_from_url(url):
    try:
        port = urlparse(url).port
    except ValueError:
        port = None
    return port or DEFAULT_PORT


class _ArgParser(argparse.ArgumentParser):
    def error(self, message):
        try:
            self.print_usage(sys.stderr)
            sys.stderr.write(f"{self.prog}: error: {message}\n")
        except Exception:
            pass  # pythonw: no stderr
        raise SystemExit(EXIT_USAGE)


def _port_arg(text):
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port number: {text!r}") from None
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError(f"port out of range: {value}")
    return value


def parse_args(argv=None):
    parser = _ArgParser(prog="avvia_searxng.py", description="Start the local SearXNG for AI-Hotkeys.")
    parser.add_argument("--port", type=_port_arg, default=None,
                        help="TCP port on 127.0.0.1 (default: from config.ini searxng_url, else 8888)")
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="folder for searxng.lock/.pid/.log (default: work next to the app)")
    args = parser.parse_args(argv)
    if args.port is None:
        args.port = port_from_url(searxng_url())
    args.work_dir = Path(args.work_dir).resolve() if args.work_dir else DEFAULT_WORK
    return args


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

def acquire_lock(path):
    """Return an fd holding an exclusive lock on `path`, or None if another process holds it.

    The OS releases the lock when the process dies, so a crash never leaves a stale lock.
    Other OSErrors (folder not writable, …) propagate.
    """
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - the app is Windows-only
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


# ---------------------------------------------------------------------------
# Process identity (contract K5)
# ---------------------------------------------------------------------------

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _filetime_of(handle):
    import ctypes
    from ctypes import wintypes

    times = [wintypes.FILETIME() for _ in range(4)]
    ok = ctypes.windll.kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times])
    if not ok:
        return None
    created = times[0]
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def own_creation_time():
    """Creation time of this process as a Windows FILETIME (100 ns since 1601, UTC); 0 if unknown."""
    if sys.platform != "win32":
        return 0
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return _filetime_of(ctypes.c_void_p(kernel32.GetCurrentProcess())) or 0


def process_creation_time(pid):
    """FILETIME creation time of a live process, or None if it is not running or not accessible."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    handle = ctypes.c_void_p(handle)
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != _STILL_ACTIVE:
            return None
        return _filetime_of(handle)
    finally:
        kernel32.CloseHandle(handle)


def format_pid_record(pid, ctime):
    return f"{int(pid)} {int(ctime)}"


def parse_pid_record(text):
    """Parse a pid file: "<pid> <filetime>" (K5) or the legacy "<pid>". Returns (pid, ctime|None) or None."""
    parts = (text or "").split()
    if not 1 <= len(parts) <= 2 or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    pid = int(parts[0])
    if pid <= 0:
        return None
    return pid, (int(parts[1]) if len(parts) == 2 else None)


def read_pid_file(path):
    try:
        return parse_pid_record(Path(path).read_text(encoding="ascii", errors="replace"))
    except OSError:
        return None


def write_pid_file(path, pid, ctime):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(format_pid_record(pid, ctime), encoding="ascii")
    os.replace(tmp, path)


def remove_pid_file_if_ours(path, pid, ctime):
    """Delete the pid file only if it still names this process (another instance may own it now)."""
    if read_pid_file(path) == (pid, ctime):
        try:
            Path(path).unlink()
        except OSError:
            pass
        return True
    return False


def pid_file_names_live_process(path):
    """True if the pid file names a running process (K5: same pid and creation time)."""
    record = read_pid_file(path)
    if record is None:
        return False
    pid, ctime = record
    live = process_creation_time(pid)
    if live is None:
        return False
    return ctime is None or ctime == live


# ---------------------------------------------------------------------------
# Log: append, rotate at 5 MB keeping one old file
# ---------------------------------------------------------------------------

class RotatingLog:
    """File-like object used as sys.stdout/sys.stderr. Thread safe; rotates to <name>.1."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, path, max_bytes=LOG_MAX_BYTES):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = threading.RLock()
        try:
            size = self.path.stat().st_size
        except OSError:
            size = 0
        self._limit = max_bytes
        if size >= max_bytes:
            self._rotate_file()
        self._open()

    def _open(self):
        self._file = open(self.path, "a", encoding="utf-8", errors="replace", buffering=1)
        try:
            self._size = self.path.stat().st_size
        except OSError:
            self._size = 0

    def _rotate_file(self):
        try:
            os.replace(self.path, self.path.with_name(self.path.name + ".1"))
            self._limit = self.max_bytes
        except OSError:
            # Someone holds the file open: try again after another MB instead of on every write.
            self._limit += 1024 * 1024

    def write(self, text):
        with self._lock:
            n = self._file.write(text)
            self._size += len(text.encode("utf-8", "replace"))
            if self._size >= self._limit:
                self._file.close()
                self._rotate_file()
                self._open()
            return n

    def flush(self):
        with self._lock:
            self._file.flush()

    def fileno(self):
        return self._file.fileno()

    def isatty(self):
        return False

    def writable(self):
        return True

    def close(self):
        with self._lock:
            self._file.close()

    @property
    def closed(self):
        return self._file.closed


# ---------------------------------------------------------------------------
# Host header allowlist (H10: SearXNG accepts any Host -> DNS rebinding)
# ---------------------------------------------------------------------------

def host_allowed(host):
    host = (host or "").strip().lower()
    if not host:
        return False
    name, sep, port = host.rpartition(":")
    if sep and port.isascii() and port.isdigit():
        host = name
    return host in ALLOWED_HOSTS


class HostAllowlist:
    """WSGI middleware: 403 unless the Host header is 127.0.0.1 or localhost (any port)."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if not host_allowed(environ.get("HTTP_HOST")):
            body = b"Forbidden: unexpected Host header.\n"
            start_response("403 Forbidden", [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ])
            return [body]
        return self.app(environ, start_response)


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------

def port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def bind_exclusive(host, port):
    """Bind (no listen yet) so that no other socket can share the port.

    Werkzeug sets SO_REUSEADDR, which on Windows lets a second process bind a port that is
    already in use (H09). SO_EXCLUSIVEADDRUSE forbids that in both directions.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _windows_tweaks():
    # SearXNG targets Linux: it imports the "pwd" module (Unix-only)
    # even when not using Valkey. An empty module is enough.
    try:
        import pwd  # noqa: F401
    except ImportError:
        stub = types.ModuleType("pwd")

        def getpwuid(uid):
            raise KeyError(uid)

        stub.getpwuid = getpwuid
        sys.modules["pwd"] = stub

    # curl_cffi (engine requests) wants the asyncio "selector" loop;
    # on Windows the default is "proactor".
    if sys.platform == "win32":
        import asyncio
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main(argv=None):
    global _lock_fd

    try:
        args = parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_USAGE

    host, port, work = HOST, args.port, args.work_dir
    lock_file = work / "searxng.lock"
    log_file = work / "searxng.log"
    pid_file = work / "searxng.pid"

    try:
        work.mkdir(parents=True, exist_ok=True)
        _lock_fd = acquire_lock(lock_file)
    except OSError:
        return EXIT_ERROR
    if _lock_fd is None:
        # Another launcher (starting or running) owns this work dir: leave its log and pid alone.
        return EXIT_ALREADY_RUNNING

    # pythonw has no console: everything SearXNG writes goes to the log.
    log = RotatingLog(log_file)
    sys.stdout = log
    sys.stderr = log

    if not (HERE / "app" / "searx").is_dir():
        print("ERROR: missing folder searxng\\app\\searx", flush=True)
        return EXIT_NO_APP

    if port_in_use(host, port):
        if pid_file_names_live_process(pid_file):
            # An instance started by an older launcher (no lock) is serving: nothing to do.
            print(f"SearXNG already running on http://{host}:{port}", flush=True)
            return EXIT_ALREADY_RUNNING
        print(f"ERROR: port {port} on {host} is used by another program, not AI-Hotkeys' SearXNG. "
              f"Stop it or change searxng_url in config.ini [searxng].", flush=True)
        return EXIT_PORT_FOREIGN

    try:
        sock = bind_exclusive(host, port)
    except OSError as e:
        print(f"ERROR: cannot use port {port} on {host} ({e.strerror or e}): another program holds it. "
              f"Stop it or change searxng_url in config.ini [searxng].", flush=True)
        return EXIT_PORT_FOREIGN

    pid, ctime = os.getpid(), own_creation_time()
    server = None
    try:
        write_pid_file(pid_file, pid, ctime)
        print(f"SearXNG on http://{host}:{port}  (pid {pid})", flush=True)

        sys.path.insert(0, str(HERE / "app"))
        sys.path.insert(0, str(HERE / "lib"))
        _windows_tweaks()

        os.environ["SEARXNG_SETTINGS_PATH"] = str(HERE / "settings.yml")
        os.environ["SEARXNG_DISABLE_ETC_SETTINGS"] = "1"
        os.environ["SEARXNG_BIND_ADDRESS"] = host
        os.environ["SEARXNG_PORT"] = str(port)
        # New key on every start: only used to sign preference cookies.
        os.environ.setdefault("SEARXNG_SECRET", secrets.token_hex(32))

        from searx import webapp  # importing it initializes SearXNG
        from werkzeug.serving import make_server

        # Werkzeug takes over a duplicate of the already-bound socket and skips its own bind.
        server = make_server(host, port, HostAllowlist(webapp.app), threaded=True, fd=sock.fileno())
        sock.close()
        sock = None
        server.socket.listen(server.request_queue_size)
        print("Ready.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback
        traceback.print_exc()
        return EXIT_ERROR
    finally:
        if server is not None:
            try:
                server.server_close()
            except Exception:
                pass
        if sock is not None:
            sock.close()
        remove_pid_file_if_ours(pid_file, pid, ctime)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
