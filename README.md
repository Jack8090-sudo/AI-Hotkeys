# AI-Hotkeys

Global hotkeys for using a local LLM on any selected text:

- **PgUp** → fix the selected text
- **PgDn** → summarize it
- **End** → explain it (with optional web search)

Stack: AutoHotkey v2 (hotkeys + UI) → Python → Ollama → Qwen. Web search
uses a local SearXNG on `127.0.0.1:8888`.

## Requirements

- Windows 10/11 64-bit
- [Ollama](https://ollama.com/download) + model `qwen3.5:9b` (~6.6 GB, Q4_K_M):
  `ollama pull qwen3.5:9b` (~12 GB VRAM card recommended)
- AutoHotkey v2 (bundled in the setup, or installed separately for source use)
- SearXNG only for End's web search (wrapper code in `searxng/`, optional)

## Usage

1. Download a release or clone the sources.
2. Copy `config.esempio.ini` to `config.ini` and set your Obsidian file:
   `todo_file = %USERPROFILE%\Documents\To-Do List.md`
   and the matching title prefix (`window_title = To-Do List -`).
3. Run `main.ahk`, select some text and press PgUp / PgDn / End.
4. Settings: tray icon → Settings (or `config.ini` + "Reload").

From source you need Python 3.x with stdlib modules only
(`configparser`, `urllib`, `http.server` — no external dependencies).

## Behavior

- **Cancel with Esc:** hold Esc for 2 seconds while Qwen is working
  to kill the Python process and clean up half-written files in `work\`.
  A short Esc press behaves normally.
- **PgUp in Obsidian with To-Do List.md open** doesn't fix the selected
  text: it reorganizes the whole file (`actions/obsidian_todo.py`,
  atomic write + `To-Do List.backup_*.md` backup, safety checks that
  block writing when tasks, links or tags go missing).
- **Direct replace:** with `[comportamento] sostituisci_testo = si`,
  the PgUp fix replaces the selected text in Notepad, Obsidian, Word,
  VS Code and Notepad++; PgDn and End always open the results page.
- **Web search (End):** `[searxng] web_search = auto` searches only when
  needed (the model decides from the queries; recognized technical terms
  force a search anyway), `always` always searches, `false` never.
  Sources become clickable `[1] [2]…` citations + a list at the bottom.
- **Ask Qwen:** the results page has a popup for follow-up questions
  (iterative rewriting in fix mode, Q&A with the last 6 question/answer
  pairs in the other modes, sources reused).
- **Length:** `[comportamento] lunghezza = breve | normale | dettagliata`
  (applies to summaries and explanations; values are Italian for
  short / normal / detailed).
- **VRAM:** the model stays in memory for `[qwen] keep_alive` (default
  `30m`); right-click the tray icon → "Libera la VRAM" unloads it
  immediately (`actions/unload.py`).
- **Customizable hotkeys** in `[tasti]` (AutoHotkey syntax; bare letters
  and digits are not allowed since you need them for typing). On the
  Settings page you record hotkeys by pressing them.
- **Secure local pages:** results and settings are servers on
  `127.0.0.1` with a random port and an ephemeral token (`?t=…` +
  `X-Token` header); they shut down by themselves after minutes of
  inactivity (240 s results, 300 s settings). Requests not from
  `127.0.0.1`/`localhost` → 403.
- **Missing keys:** if `config.ini` lacks a key present in
  `config.esempio.ini` (e.g. `[tasti]`, `aspetto.larghezza`), the code
  default applies — no error.

## Layout

- `main.ahk` — hotkeys, dispatcher (`context|slot` → action), tray, SearXNG integration
- `qwen_client.py`, `prompts.py`, `websearch.py` — Ollama client, prompts, search
- `viewer.py`, `settings.py`, `pages.py` — results / settings pages (local 127.0.0.1 servers with ephemeral token)
- `config_edit.py`, `test_config_edit.py` — comment-preserving config editing + tests (`python test_config_edit.py`)
- `actions/` — `rewrite.py`, `summarize.py`, `explain.py`, `obsidian_todo.py`, `unload.py`
- `ahk/` — versioned `license.txt` + local `AutoHotkey64.exe` (the binary ships with the setup, not via git)
- `static/` — `viewer.html`, `settings.html`, `theme.css`, `marked.min.js`, `fonts/`
- `searxng/` — only `avvia_searxng.py`, `settings.yml`, `LICENSE-searxng.txt`
- `installer/sorgente/` — `installer.nsi`, `stop.ps1` (the setup builds its payload from `config.esempio.ini`, never from `config.ini`)

## What is NOT in the repo (and why)

- `config.ini` — personal paths, ignored via `.gitignore`
- `work/` — runtime files (`input.txt`, `output.txt`, logs, pids). Note: it holds
  the latest selected texts in plaintext — never commit it, never back it up
- `python/` (~31 MB), `searxng/app|lib/` (~82 MB), `*.exe`, `*.rar` — distributed via GitHub Releases, not via git
- `graphify-out/`, `__pycache__/` — local derivatives

## Documentation

- Source-generated code map: [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)
- Removal log: [docs/DELETION_LOG.md](docs/DELETION_LOG.md)
- End-user instructions for the installed app (Italian): `installer/AI-Hotkeys/LEGGIMI.txt`

## Third-party licenses

- AutoHotkey: `ahk/license.txt` (GPLv2) — the binary is not versioned
- SearXNG: `searxng/LICENSE-searxng.txt` (AGPLv3) — only wrapper + settings versioned
- `static/marked.min.js` (MIT), Barlow / IBM Plex fonts (`static/fonts/OFL-*.txt`, SIL OFL)
- Own code is MIT (`LICENSE`).
