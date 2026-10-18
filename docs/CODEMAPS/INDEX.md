# AI-Hotkeys code map

**Last updated:** 2026-10-18 (version 1.1.0)
**Entry points:** `main.ahk`; `actions/*.py`; `viewer.py`; `settings.py`; `searxng/avvia_searxng.py`
**Source of truth:** generated from the sources. If a path or name below no longer exists, regenerate this map.

## Architecture

```
                 +------------------------- main.ahk + lib\*.ahk --------------------------+
                 | hotkeys -> Dispatch (context|slot) -> route; capture (^c, ClipWait)      |
                 | tray menu, toasts, Esc 2 s cancel, config watch + reload, health check   |
                 | work\runs\<id>\ lifecycle, SearXNG start/stop (K5 pid check)             |
                 +----+--------------+----------------+---------------+-------------------+
                      |              |                |               |
          selected text        Obsidian To-Do     Settings        SearXNG lifecycle
                      |              |                |               |
        +-------------v--+  +--------v--------+  +----v--------+  +---v-----------------+
        | actions/        |  | actions/        |  | settings.py |  | searxng/            |
        | rewrite.py      |  | obsidian_todo.py|  | /api/save   |  | avvia_searxng.py    |
        | summarize.py    |  | backup, atomic, |  +----+--------+  | lock, exclusive bind|
        | explain.py      |  | validate        |       |           | Host allowlist      |
        | health.py       |  +--------+--------+  config_edit.py  +---------+-----------+
        | unload.py       |           |                                    |
        +-------+---------+           |                         http://127.0.0.1:8888
                |                     |                                    |
        +-------v---------------------v--+        +------------------------v--------+
        | qwen_client.py                  |        | websearch.py (End only)         |
        | config, chat/stream, errors K1, |<------>| decide queries -> SearXNG ->    |
        | run dirs, clean_answer          |        | SSRF-checked fetch -> sources   |
        +---+-------------------+---------+        +---------------------------------+
            |                   |
   +--------v-------+   +-------v---------+        +---------------------------------+
   | prompt_loader  |   | Ollama          |        | viewer.py (127.0.0.1, token)    |
   | prompts_user / |   | localhost:11434 |<-------| results page + /api/ask         |
   | prompts.py     |   | qwen3.5:9b      |        | ("Ask Qwen" follow-ups)         |
   +----------------+   +-----------------+        +---------------------------------+

Config: config.example.ini -> config.ini (personal, never shipped or overwritten)
        read by lib\Util.ahk ReadConfig, qwen_client.load_config, config_edit.read_values, settings.current_values
State:  work\runs\<run id>\ (per job), work\error.txt, work\config_warning.txt, work\searxng.{pid,lock,log},
        work\server.log, work\obsidian_{status,output}.txt, work\acl.done
```

## Key modules

| Module | Purpose | Main names | Depends on |
|---|---|---|---|
| `main.ahk` | Hotkeys, dispatcher, capture, routes (Console, own pages, Obsidian To-Do, editable apps, default), direct replace, tray, toasts, Esc cancel, config watch, health check, run-folder lifecycle, SearXNG start/stop | `RegisterKeys`, `Dispatch`, `RunSelectionAction`, `RunCapturedJob`, `ReplaceSelection`, `OpenResultsPage`, `RunObsidianTodo`, `WaitPid`, `CheckEscHold`, `DeleteRunDir`, `SweepRuns`, `SecureWorkDir`, `ShowError`, `EditPrompts`, `StartHealthCheck`, `OnExitCleanup`, `StartSearxng`, `StopSearxng` | `lib/*.ahk`, `actions/*.py`, `viewer.py`, `settings.py`, `config.ini`, `work\` |
| `lib/Util.ahk` | Pure helpers, unit-tested: config reading, hotkey validation and resolution, page and console detection, run ids, pid records, error and warning text, the `prompts_user.py` template | `ReadConfig`, `IsNo`, `ValidHotkey`, `ResolveKeys`, `KeyLabel`, `IsAppPageTitle`, `IsConsoleClass`, `ParseClipWaitMs`, `SelectionMatches`, `ParsePidRecord`, `SearxngPidIsOurs`, `ErrorFileLine1`, `WarningSummary`, `PromptsUserTemplate`, `NewRunId`, `IsRunId`, `RunIsStale`, `WorkAclArgs` | none |
| `lib/Proc.ahk` | Process queries through the Win32 API | `ProcessCreationTime`, `ProcessPathOf`, `ProcOpen`, `ProcExitCode`, `ProcClose` | none |
| `actions/rewrite.py`, `summarize.py`, `explain.py` | Thin entry points for the three selection actions | `qwen_client.run_action(mode, argv)` | `qwen_client.py` |
| `actions/health.py` | Startup check: Ollama reachable, version ≥ 0.9.0, model present | `qwen_client.health()` | `qwen_client.py` |
| `actions/unload.py` | Tray "Free VRAM" (`keep_alive: 0`) | `qwen_client.unload()` | `qwen_client.py` |
| `actions/obsidian_todo.py` | Reorganizes the To-Do note with safety checks, a backup in `.ai-hotkeys-backups` (newest 20) and an atomic write with retries | `main`, `ask_qwen`, `normalize`, `validate`, `check_structure`, `changed_tasks`, `make_backup`, `replace_with_retry`, `write_status`, `SafetyError` | `qwen_client.py` |
| `qwen_client.py` | Shared Ollama client (no proxy), config loading and warnings, error mapping and K1 writer, run folders, input limits, answer cleanup, action orchestration | `load_config`, `chat`, `chat_ex`, `open_stream`, `stream_pieces`, `unload`, `health`, `describe_error`, `write_error`, `clear_error`, `parse_action_args`, `is_run_dir`, `sweep_stale_runs`, `remove_run_dir`, `max_input_chars`, `clean_answer`, `run_action`, `todo_file`, `TruncatedAnswer`, `StreamIncomplete`, `MIN_OLLAMA_VERSION` | `prompt_loader.py`, `websearch.py` (explain only) |
| `prompt_loader.py` | Uses `prompts_user.py` when present (name by name, falling back to `prompts.py`), else `prompts.py` | `prompts`, `PROMPTS_WARNING` | `prompts.py`, `prompts_user.py` |
| `prompts.py` | All prompts and Ollama options (user content, edited only through `prompts_user.py`) | `first_messages`, `query_messages`, `followup_rewrite_messages`, `followup_qa_messages`, `OPTIONS`, `NUM_CTX = 16384`, `LENGTH_HINTS` | none |
| `websearch.py` | End's web search: query decision and `query_mode`, SearXNG, SSRF-guarded page fetch with deadlines, HTML extraction, source selection, citations | `decide_queries`, `make_queries`, `parse_queries`, `technical_terms`, `ollama_ready`, `ensure_running`, `searx_search`, `ip_blocked`, `safe_url`, `fetch_page_text`, `fetch_pages`, `html_to_text`, `select_relevant`, `gather_sources`, `sources_block`, `linkify`, `md_url`, `cited_numbers`, `add_sources`, `save_sources`, `load_sources`, `QUERY_MODE`, `LAST_DECISION` (diagnostic) | `qwen_client.py`, `prompt_loader.py`, `searxng/lib` (`curl_cffi`, optional) |
| `viewer.py` | Results page and "Ask Qwen" follow-ups; loads a run folder, then deletes it | `load_run`, `Session`, `detect_mode`, `build_page`, `make_handler`, `read_meta`, `main`; `GET /`, `/api/ping`, `/fonts/*`; `POST /api/ask` (NDJSON) | `pages.py`, `prompt_loader.py`, `qwen_client.py`, `websearch.py`, `static/viewer.html` |
| `settings.py` | Settings page; validates and saves `config.ini` | `CHOICES`, `NUMBERS`, `TEXTS`, `KEYS`, `valid_hotkey`, `current_values`, `defaults`, `validate`, `url_warning`, `build_page`, `make_handler`, `main`; `GET /`, `/api/ping`; `POST /api/save` | `config_edit.py`, `pages.py`, `static/settings.html` |
| `pages.py` | Shared page parts: CSP, token check, `LocalServer` (errors to `work\server.log`, request timeout), look settings, theme CSS, safe JSON, fonts | `CSP`, `token_ok`, `LocalServer`, `log_server_error`, `LOOK`, `TEXT_SIZE`, `look_settings`, `theme_css`, `script_json`, `html_escape`, `try_serve_font` | `static/theme.css`, `static/fonts/` |
| `config_edit.py` | Atomic `config.ini` writer that keeps comments, order, BOM and line endings; also a small CLI used only by developers | `set_values`, `read_values` | none |
| `searxng/avvia_searxng.py` | SearXNG launcher: work-dir lock, exclusive bind, K5 pid file, rotating log, Host allowlist | `main`, `acquire_lock`, `bind_exclusive`, `format_pid_record`, `parse_pid_record`, `HostAllowlist`, `RotatingLog`; args `--port`, `--work-dir`; exit codes 0–5 | `searxng/app`, `searxng/lib` (not in git) |
| `static/` | `viewer.html`, `settings.html`, `theme.css`, `marked.min.js`, `fonts/` | page titles `… - AI-Hotkeys` and `AI-Hotkeys Settings` are matched by `IsAppPageTitle` | none |
| `installer/sorgente/` | NSIS installer and helpers | `installer.nsi`, `manifest.ps1` (upgrade, shortcuts), `stop.ps1`, `ollama-check.ps1`, `legacy-1.0.0.manifest` | `build/out/` (payload, `manifest.txt`, `uninstall.nsh`) |
| `build/` | Reproducible build | `build.ps1`, `pins.json`, `requirements-searxng.txt` (hash lock), `lock-searxng.ps1`, `smoke.ps1`, `h16_probe.py` | network (pinned downloads), NSIS |

## File contracts

| Id | Contract | Writer | Reader |
|---|---|---|---|
| K1 | `error.txt`: line 1 is the user message, then detail. Jobs write `work\runs\<id>\error.txt`; the health check and Free VRAM write `work\error.txt`. | `qwen_client.write_error` | `main.ahk` `ReadErrorLine` |
| K2 | `websearch.gather_sources(...)` signature and return shape are frozen | `websearch.py` | `qwen_client.run_action` |
| K3 | Viewer command line: `viewer.py --run-dir=<dir> "<name>" <mode> [--key=…] [--no-browser]` (old form `<input> <output> …` still works) | `main.ahk` `OpenResultsPage` | `viewer.load_run` |
| K4 | `qwen_client` API stability: `chat()` and `stream_pieces()` keep their signatures; `chat_ex()` returns `(text, done_reason)`; a stream that is cut off or incomplete raises `TruncatedAnswer` / `StreamIncomplete`, which the viewer reports as `{"error", "partial": true}` | `qwen_client` | `websearch.py`, `actions/obsidian_todo.py`, `viewer.py`, `static/viewer.html` |
| K5 | `work\searxng.pid`: `<pid> <creation FILETIME>` (legacy `<pid>` accepted) | `avvia_searxng.py` | `main.ahk` `StopSearxng` |
| K6 | `work\config_warning.txt`: one warning per line, shown once and deleted | `qwen_client.report_config_warnings` | `main.ahk` `TakeConfigWarnings` |
| — | Actions: `actions\<action>.py --run-dir=<work\runs\id>` (old form `<input> <output>` still works). Exit codes: 0 done, 1 error, 3 too long / cut off. | `main.ahk` | `qwen_client.run_action` |

## Data flow

1. **Fix / summarize (PgUp / PgDn):** hotkey → `Dispatch(slot)` → route → copy the selection (`^c`,
   `ClipWait` = `clip_wait_ms`) → new `work\runs\<id>\input.txt` → `actions\<mode>.py --run-dir` →
   `qwen_client.run_action` → length check → `prompts.first_messages` → Ollama `/api/chat` → `clean_answer` →
   `meta.json` + `output.txt` (atomic) → direct replace (fix only, editable apps, `sostituisci_testo = si`,
   window and selection re-checked) or `viewer.py --run-dir`, which loads and deletes the folder.
2. **Explain (End):** as above, plus `websearch.gather_sources` first: `ollama_ready` (2 s) →
   `decide_queries` (technical terms force a search; `query_mode` limits fallbacks) → `ensure_running` →
   `searx_search` → `fetch_pages` (SSRF guard, 12 s per page, 15 s overall) → `select_relevant` →
   `sources_block` in the prompt → answer with `[n]` → `add_sources` → `save_sources` for follow-ups.
3. **Obsidian To-Do (PgUp with the note open):** route `Obsidian:To-Do|correggi` → `RunObsidianTodo`
   (`^s`, then `obsidian_todo.py`) → Qwen reorganizes → `normalize` → `validate` → on success: backup,
   atomic write with retries; on failure: file untouched, reasons in `work\obsidian_status.txt`.
4. **Follow-up ("Ask Qwen"):** page → `POST /api/ask` → `Session.build_messages` → `open_stream` → NDJSON →
   `clean_answer` → `linkify` → `{done, index, text}`; a cut-off or interrupted stream gives
   `{error, partial: true}`; other errors go through `describe_error`.
5. **Settings:** tray → `settings.py` → `GET /?t=token` → `POST /api/save` → `validate` (+ `url_warning`) →
   `config_edit.set_values` → `WatchConfig` in `main.ahk` sees the change and reloads ("Settings applied").
6. **Startup:** `SecureWorkDir`, `LegacyWorkCleanup`, `SweepRuns`, `RegisterKeys` (`ResolveKeys`),
   `StartSearxng`, `StartupNotices`, `StartHealthCheck` (`actions\health.py`, exit code via `GetExitCodeProcess`).

## Tests and tooling

| Path | What |
|---|---|
| `tests/test_*.py` | Python suite (stdlib `unittest`) on a temporary app copy; fakes in `tests/support.py` |
| `tests/ahk/run.ahk` | AutoHotkey unit tests for `lib/Util.ahk` and `lib/Proc.ahk` |
| `tests/fixtures/hotkey_vectors.json` | Shared hotkey vectors (Python and AHK parity) |
| `test_config_edit.py` | Root shim for the old `python test_config_edit.py` entry point |
| `scripts/dev/link-runtime.ps1` | Links the untracked runtime into a worktree |
| `scripts/ci/` | CI helpers: AHK download and runner, hygiene, license presence, coverage remap, installer tests, fake Ollama, source-archive download |
| `tools/bench/` | Performance harness (not shipped); results in `docs/audit/baseline-2026-10.md` |
| `tools/licenses/` | Third-party notice generator and checker (`components.json` registry) |
| `.github/workflows/` | `ci.yml`, `installer.yml`, `release.yml` |

## External dependencies

- **Ollama** at `http://localhost:11434` (minimum 0.9.0) with `qwen3.5:9b`. Not bundled.
- **SearXNG** `6671d89` (AGPL-3.0), bundled by the build in `searxng\app` and `searxng\lib` (32 hash-locked
  wheels, including `curl_cffi`). Not in git.
- **CPython 3.13** embeddable (installer) or a system 3.13 x64 (source). App code is stdlib-only, apart from
  the optional `curl_cffi` reused from `searxng\lib`.
- **AutoHotkey 2.0.19** (GPL-2.0), `ahk\AutoHotkey64.exe`, bundled by the build. Not in git.
- `static/marked.min.js` (MIT); Barlow and IBM Plex fonts (SIL OFL). Notices: `THIRD_PARTY_NOTICES.md`.

## Related

- User docs: `README.md`, `docs/INSTALL.md`, `docs/TROUBLESHOOTING.md`, `docs/CONFIGURATION.md`,
  `docs/guide-it.md`, `PRIVACY.md`, `SECURITY.md`
- Development: `CONTRIBUTING.md`, `plans/ai-hotkeys-production-readiness.md`
- Removal history: `docs/DELETION_LOG.md`
