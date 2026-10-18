# Changelog

All notable changes to AI-Hotkeys. Versions follow [`VERSION`](VERSION).

## [1.1.0] - unreleased

The production-readiness release: first public build, English UI, a private install folder, specific
error messages, data-safety and privacy fixes, a hardened web search, and a reproducible, tested build.
Plan: `plans/ai-hotkeys-production-readiness.md`. Step ids (S1–S15) refer to it.

### Upgrade notes

- **New install folder.** The default is `%LOCALAPPDATA%\Programs\AI-Hotkeys` (private to your account),
  not `C:\AI-Hotkeys`. Setup offers to migrate a v1.0.0 installation: it copies `config.ini`, stops the old
  copy, disables its uninstaller and removes its Italian shortcuts. The old folder is left for you to delete.
  An in-place upgrade (`/D=C:\AI-Hotkeys`) also works. See [docs/INSTALL.md](docs/INSTALL.md#migration-from-v100).
- **Your prompts.** Customize prompts in `prompts_user.py` (tray → Edit prompts) instead of `prompts.py`.
  Upgrades back up a changed `prompts.py` as `prompts.py.bak-<old version>`.
- **Stricter hotkeys.** `[tasti]` keys now follow exactly the Settings page rules. Keys that used to work
  but are now rejected (for example `Space`, `Esc`, a lowercase `pgup`, `Numpad1` without a modifier) fall
  back to the default, and a startup toast says so.
- **Inline comments.** `main.ahk` now strips ` ; comment` from `config.ini` values.
- **Obsidian backups** move to the hidden folder `.ai-hotkeys-backups` next to the note. Old
  `To-Do List.backup_*.md` files are left untouched.
- **Requirements.** Ollama 0.9.0 or newer (checked at startup). Source installs need Python 3.13 x64.

### Added

- Specific error messages instead of "Qwen did not respond…": Ollama not running, model missing (with the
  `ollama pull` command), Ollama too old, text too long, answer cut off, Ollama stopped while answering,
  nothing selected. Follow-up questions use the same messages. (S4, S8b3, S9)
- A health check at startup reports Ollama problems before the first key press. (S4, S8b3)
- Warnings for a broken `config.ini` (with the line number) or `prompts_user.py`, shown once per reload; the
  app keeps working with the defaults. (S4, S8b3)
- Startup warnings for invalid or duplicate hotkeys; the tray tooltip shows each action's real key. (S8b3)
- Optional `prompts_user.py`, never shipped or overwritten; tray → Edit prompts creates it as a commented
  copy of `prompts.py`. A broken copy falls back to the standard prompts. (S4, S8b3, D4)
- `[searxng] query_mode`: `allow_fallback` (default) or `model`, which never sends your text verbatim to the
  search engines. On the Settings page as "Search words". (S6b, S10, D5)
- `[comportamento] clip_wait_ms`: how long a key waits for the copy, 100–10000 ms, default 2000. (S8b1, D12)
- A "What leaves this PC" notice on the Settings page and the installer's finish page. (S10, S13b)
- Tray Reload and Exit ask for confirmation while a job is running. (S8b2)
- Installer: license page, `/NOOLLAMA`, `Uninstall.exe /PURGE`, version metadata, uninstall registry
  details, and a finish page with the model, VRAM and web-search notes. (S13b)
- Documentation: [INSTALL](docs/INSTALL.md), [TROUBLESHOOTING](docs/TROUBLESHOOTING.md),
  [CONFIGURATION](docs/CONFIGURATION.md), [PRIVACY](PRIVACY.md), [SECURITY](SECURITY.md),
  [CONTRIBUTING](CONTRIBUTING.md), and the Italian user guide [docs/guide-it.md](docs/guide-it.md), which
  replaces the untracked `LEGGIMI.txt`. (S15)

### Changed

- **The user interface is in English.** Config keys and values stay Italian. (I11)
- Holding a key with nothing selected no longer stalls: repeats and the other two keys act natively during
  the copy. (S8b1, C03)
- Consoles (Windows Terminal, conhost, mintty) never receive Ctrl+C, and the keys act natively there and on
  AI-Hotkeys' own pages. (S8b1, C03, C04)
- Errors are non-modal toasts: the hotkeys keep working while one is shown, and the progress toast comes
  back after "Qwen is still working". (S8b3, C27)
- Web search: citations are no longer linked inside code; URLs with `(`, `)` or spaces work; queries starting
  with "no" are searched; a "## Fonti di lag" heading is kept; character sets are detected more reliably;
  `<div>`-only pages are read; an unclosed `<form>` no longer hides the rest of the page. (S6b, C25, C38,
  C39)
- `[searxng] results` is clamped to 1–10 and `pages_to_read` to 0–5. (S6a)
- `work\searxng.log` is appended and rotated at 5 MB instead of being cleared on every start. (S6c)
- Results page: answers stream smoothly (one render every 150 ms instead of every frame); screen readers
  announce progress and results; the question field keeps the focus; incomplete answers are marked. (S10,
  C40)
- Settings page: accessible hotkey recorder (names, announcements, Tab/Shift+Tab never recorded, Ctrl+C and
  similar refused), format hints and focus on the first invalid field, a warning for an Ollama address on
  another computer, WCAG 1.4.11 contrast in every theme, Windows high-contrast support. (S10, C34)
- Obsidian To-Do: a UTF-8 BOM is preserved; every failure gives a reason; extra checks for frontmatter,
  paragraphs, table rows, headings and rewritten tasks; Qwen's copy is deleted after success. (S5, C13,
  C14)
- Python launches use `-E -s`, and the bundled Python is the official embeddable package with a `._pth`
  file, so `PYTHONPATH` and user site-packages are ignored. (S8b2, S11, C28)
- Ollama requests ignore the system proxy. (S4, C24)
- Quoted paths in `config.ini` (`todo_file = "C:\..."`) work. (S4)

### Fixed

- A truncated answer is never pasted or shown as complete. (S4, C02)
- PgUp keeps a first line such as "Okay so the plan is:" and answers with several code blocks. (S4, C12)
- The explanation cleanup could hang on degenerate model output (cubic regex); it is now linear. (S4, C01)
- A broken `config.ini` no longer silently resets every setting. (S4, C16)
- Direct replace no longer pastes into the wrong window or over a changed selection; it falls back to the
  results page. (S8b1, C05)
- The results page no longer re-runs the action on its own text or lags 2 s on PgUp/PgDn/End. (S8b1, C04)
- Reload and Exit no longer leave an orphaned Python job, and a late job can no longer overwrite a newer
  result. (S8b2, S9, C18)
- Exit no longer kills an unrelated program that reused SearXNG's process id. (S8b2, C20)
- Starting SearXNG twice can no longer leave two servers or an orphan. (S6c, C19, H09)
- Two jobs back to back always show their own text and result. (S9, H04)
- A follow-up with a missing model says so instead of "Cannot reach Ollama". (S9, C21)
- Obsidian backups are no longer indexed by Obsidian (duplicate tasks and tags). (S5, C15)
- File errors in `work\` are reported instead of raising AutoHotkey error dialogs. (S8b2)
- `config_edit`: atomic save, rejects line breaks and invalid names, handles `key: value` lines and splits
  only on real line breaks. (S7, C17)

### Security

- Install folder private to the user; custom folders outside the profile get an explicit ACL; folders inside a
  git repository, drive roots and unwritable folders are refused. (S13a, C09, D1)
- `work\` is private, and the selected text no longer stays on disk: each job uses `work\runs\<id>\`, deleted
  as soon as the result is shown, pasted, cancelled or failed; crash leftovers older than 1 hour are swept.
  (S9, C32)
- Content-Security-Policy on both local pages; remote images in answers are shown as a link, never loaded;
  the token is removed from the address bar; non-ASCII tokens and slow clients are handled. (S7, C10, C35,
  D8)
- Web-page fetching is limited to public internet addresses on ports 80/443, with re-checked redirects,
  DNS-rebinding protection and wall-clock deadlines. If Ollama is down, End fails fast without searching.
  (S6a, C11, C22, C23)
- SearXNG binds its port exclusively and rejects foreign `Host` headers (DNS rebinding). (S6c, H10)
- Installer: Ollama detection never runs a planted `ollama.exe`; silent installs never open a browser or run
  winget; winget's terms and exit code are handled; `stop.ps1` matches folders exactly. (S13b, C31, C44,
  C45)

### Build, packaging and licenses

- Reproducible build (`build\build.ps1`): every download pinned by SHA-256, hash-locked SearXNG wheels,
  allowlisted payload, manifest, smoke test. The vendored SearXNG was verified identical to upstream
  `6671d89`. (S11, C07, H16, H17)
- Manifest-driven install, upgrade and uninstall: upgrades remove obsolete files, the uninstaller removes
  everything it installed (including the ~82 MB SearXNG tree). (S13b, C08, C30)
- `THIRD_PARTY_NOTICES.md` and `licenses\` cover every bundled component; the MIT `LICENSE` is installed;
  the AutoHotkey and SearXNG source archives are attached to every release as `third-party-sources.*`
  assets. (S12, S13b, S14, C29)

### Development

- Test suite (`python -m unittest discover -s tests -t .`, stdlib only) running against a temporary copy of
  the app with fake Ollama, SearXNG and web servers; AutoHotkey unit tests for `lib\Util.ahk` and
  `lib\Proc.ahk`; a shared hotkey-validation fixture for Python and AHK. (S1, S8a)
- Pure AHK helpers extracted to `lib\Util.ahk` and `lib\Proc.ahk`. (S8a, S8b1–S8b3, S9)
- CI: lint, unit tests on two Windows images with a coverage ratchet, AHK validation and unit tests, secret
  scanning, repository hygiene, license checks, dependency audit. (S2)
- Installer CI (build, reproducibility, install / upgrade / uninstall, ACL checks) and a draft-release
  workflow with build provenance. (S14)
- Performance baseline and hypothesis results: [docs/audit/baseline-2026-10.md](docs/audit/baseline-2026-10.md).
  (S3)
- `scripts/dev/link-runtime.ps1` links the untracked runtime into git worktrees. (S1)

### Known issues

- The Start-menu shortcut "Edit prompts" still opens `prompts.py`; use tray → Edit prompts for
  `prompts_user.py`.
- `/PURGE` keeps `prompts_user.py` and `prompts.py.bak-*`.
- The 2 s default of `clip_wait_ms` was not lowered, because clipboard latency has not been measured on
  real applications yet.
- Follow-up questions on the results page have no input-size guard; a very long conversation can exceed the
  model's context, which Ollama truncates silently.
- `pip-audit` of the SearXNG lock is advisory in CI.

## [1.0.0]

Italian-language build, distributed privately and not published on GitHub. Installed into `C:\AI-Hotkeys`.
