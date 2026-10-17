# S6c — SearXNG launcher robustness

User-visible:
- Starting SearXNG twice (login + End, or Reload) can no longer leave two servers, an orphan
  that "Exit" cannot stop, or a wiped log. The second launcher exits at once and touches nothing.
- `work\searxng.log` is no longer cleared on every start: it is appended to and rotated to
  `searxng.log.1` at 5 MB (one old file kept).
- If another program already uses the SearXNG port, the log gets one clear line:
  `ERROR: port <n> on 127.0.0.1 is used by another program, not AI-Hotkeys' SearXNG. Stop it or
  change searxng_url in config.ini [searxng].`
- SearXNG now answers 403 to requests whose Host header is not `127.0.0.1` or `localhost` (any
  port). Opening it in the browser via those two names still works.

Internal (`searxng/avvia_searxng.py`):
- Exclusive lock on `work\searxng.lock` (msvcrt.locking, held for the process lifetime, released
  by the OS on crash), taken before anything else and before `searx` is imported (C19).
- The port is bound with `SO_EXCLUSIVEADDRUSE` before the `searx` import; werkzeug receives the
  bound socket (`fd=`) so its `SO_REUSEADDR` bind is skipped.
- Pid file written only after a successful bind, atomically, in the K5 format
  `<pid> <creation time as Windows FILETIME UTC>` (GetProcessTimes). On clean exit it is removed
  only if it still names this process. Readers must keep accepting the legacy `<pid>` form (S8b2).
- Port already answering while we hold the lock: if `searxng.pid` names a live process (legacy
  launcher without the lock) -> exit 3 quietly; otherwise -> exit 4 (foreign holder).
- New arguments `--port N` (default: port of `searxng_url` in config.ini, else 8888) and
  `--work-dir DIR` (default: `work\` next to the app). Without arguments behaviour is as before.
- Host allowlist WSGI middleware wraps `webapp.app`; `searx/` is unmodified.

Exit codes: 0 stopped cleanly · 1 unexpected error (traceback in the log) · 2 `searxng\app\searx`
missing · 3 another launcher owns this work dir (or a legacy instance is serving) · 4 port held by
a foreign process · 5 invalid command line. main.ahk and `websearch.ensure_running` ignore the
code, so nothing else changes for them (before this step "already running" returned 0).

Hypotheses:
- **H09 — confirmed (old launcher).** Isolated tree, free port, bundled Python 3.13:
  - 2 s apart: the first instance was already listening, the second saw the port and exited 0.
  - 200 ms apart: both processes stayed alive and both logged "Ready." (werkzeug's SO_REUSEADDR
    let the second bind too); Get-NetTCPConnection listed one listener (the first), but
    `searxng.pid` named the second process and the log was truncated and interleaved.
  - With the new launcher (0 / 200 / 500 ms / 2 s apart): exactly one listener, owned by the
    first process; the second exits 3; the K5 pid file names the listener with a matching
    creation time; the log keeps a pre-seeded marker line and has a single "Ready.".
- **H10 — confirmed.** Old launcher: `GET /search?q=t&format=json` with `Host: evil.example`
  returned 200 application/json (it also ran a real search). New launcher: 403 for
  `evil.example` and `evil.example:<port>`, 200 for `/healthz` with `localhost:<port>` and
  `127.0.0.1`.

Tests: `tests/test_searxng_launcher.py` (21 tests). The real-SearXNG cases need
`searxng\app|lib` and `python\python.exe` and are skipped otherwise; they use a temp work dir, a
free port and a temp `TMP`, and kill only the processes they start.

Notes for other steps:
- SearXNG keeps its sqlite cache in `%TEMP%\sxng_cache_*.db`, shared by every instance, and an
  instance started with a different secret truncates it. Tests therefore set TMP/TEMP to their
  temp dir; S11's `build/smoke.ps1` should do the same (or pass `--work-dir`/`--port`).
- `scripts/dev/link-runtime.ps1`: the `-To` default uses `$PSScriptRoot` inside `param()`, which
  is empty in Windows PowerShell 5.1; pass `-To <worktree>` explicitly until S1's owner fixes it.
