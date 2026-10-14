# Code Deletion Log

## [2026-10-14] Refactor Session

### Unused Functions Removed
- `websearch.py::_bool(value, default=True)` — defined L37, zero callers in project code (`*.py`, `actions/*.py`, `static/*.html`, `main.ahk`). Only `__bool__` hits are vendored (`python/`, `searxng/`). No dynamic access (`getattr`/`eval`/`importlib` on this name). Deleted.
- `websearch.py::clear_status()` — defined L82, zero callers. Status lifecycle is write-only: `status()` writes `work/status.txt`, `main.ahk` deletes it (`FileDelete(statusFile)` + `ShowStatus`). Deleted.

### Unused Dependencies Removed
- None. Project has no `package.json`/`requirements.txt`; only stdlib imports (`json`, `re`, `sys`, `threading`, `urllib`, `http.server`, `pathlib`, `concurrent.futures`, `html.parser`) + vendored `searxng/lib`, `python/`, `ahk/`. All top-level imports verified used per-file. No `knip`/`depcheck`/`ts-prune` applicable (not a Node/TS project; equivalent manual import-use audit done).

### Unused Files Deleted
- None. All project-owned files are reachable: `main.ahk` → `actions/*.py` → `qwen_client.py` → `prompts.py`/`websearch.py`; `viewer.py`/`settings.py` → `pages.py` → `static/*`. `work/*` are runtime artifacts, `graphify-out/*` is generated, `installer/`/`searxng/`/`python/`/`ahk/` are vendored — left untouched.

### Duplicate Code Consolidated
- None deleted (conservative). Duplication noted for future work:
  - `viewer.py::make_handler` (~160 lines) vs `settings.py::make_handler` (~70 lines): same token-auth (`secrets.compare_digest` + `X-Token`), `do_GET /` + `/api/ping` + `try_serve_font`, `ThreadingHTTPServer("127.0.0.1", 0)` + watchdog + `--no-browser` pattern. Different payloads (NDJSON stream vs JSON save) so extraction into shared `local_server.py` needs design review — NOT done in this pass.
  - Config reading in 4 places (`main.ahk::ReadConfig`, `qwen_client::load_config`, `config_edit::read_values`, `settings::current_values`) — layered by necessity (AHK vs Python, raw vs validated), not consolidated.

### Minor Dead Branch (left as-is)
- `viewer.py::build_page`: `"meta": read_meta() if session.mode in ("explain","summarize","rewrite") else {}` — `detect_mode()` can only return those three, so `else {}` is unreachable. One-line, harmless, documents intent. Left untouched.

### Remaining (manual review needed, DO NOT auto-remove)
- `websearch.py::LAST_DECISION` — write-only diagnostic global (`make_queries` writes, nobody reads). Could be useful for debugging; needs owner decision.
- `config.ini` missing keys present in `config.esempio.ini` (`[tasti]`, `aspetto.larghezza/mostra_originale/avanzamento`) — falls back to defaults in `settings.py`; verify whether example should be the source of truth.
- `__pycache__/` dirs (`root`, `actions/`) — regenerable, gitignored presumably; not deleted in working tree.

### Impact
- Files deleted: 0
- Functions removed: 2 (`_bool`, `clear_status`)
- Lines of code removed: ~11
- Bundle size reduction: negligible (correctness pass, not size pass)

### Testing
- `python test_config_edit.py` — 1 test, OK (before and after)
- `python -m py_compile` on all 12 project files — OK
- `import websearch, qwen_client, prompts, pages, viewer, settings, config_edit` — OK; `hasattr(websearch,'_bool')=False`, `hasattr(websearch,'clear_status')=False`, `hasattr(websearch,'status')=True`
- Manual grep verification: no references to removed names in `*.py`/`*.ahk`/`static/*`; no dynamic-import path
- `npm run build` / `npm test` / `npm run lint` — N/A (no Node project)
