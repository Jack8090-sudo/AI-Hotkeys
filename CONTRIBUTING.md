# Contributing to AI-Hotkeys

Thanks for helping. This page explains how the repository is laid out, how to run the tests, how to
build the installer, and what CI checks.

## Ground rules

- **Windows only.** The app is AutoHotkey v2 plus Python on Windows 10/11 x64. Scripts must run under
  Windows PowerShell 5.1 (`powershell`, not `pwsh`).
- **Runtime Python stays standard-library only.** The single exception is `curl_cffi`, reused from
  SearXNG's `searxng\lib` when present. Dev tools (ruff, coverage, pip-audit) are dev-only:
  `python -m pip install -r requirements-dev.txt`.
- **Python 3.13 x64** for development and for source installs (the SearXNG wheels are cp313). Keep the app
  code compatible with 3.11 where that costs nothing (`pyproject.toml` sets `target-version = "py311"`).
- **The config format is frozen.** Keys and values in `config.ini` stay Italian (`[tasti]`, `si`/`no`,
  `scuro`, …). Never rename or remove a key. A new key must be optional, have a default in code, and be
  documented in `config.example.ini` and [docs/CONFIGURATION.md](docs/CONFIGURATION.md). The UI language
  is English.
- **Never commit** `config.ini` (personal paths), `work\` (it holds selected text in plaintext),
  `prompts_user.py`, `*.exe`, `*.rar`, `python\`, `searxng\app`, `searxng\lib` or `graphify-out\`. CI
  rejects most of these.
- **Never run `Uninstall.exe` or any installer against a source checkout.** Installer tests run in CI, a VM
  or Windows Sandbox. The installer itself refuses folders inside a git repository.
- **Tests never touch the live app.** No test may use the real `config.ini`, the real `work\`, port 8888
  or the real Ollama model. Use the fakes in `tests/support.py`.
- Set `PYTHONDONTWRITEBYTECODE=1` for ad-hoc runs inside the repository.

## Repository layout

See the [code map](docs/CODEMAPS/INDEX.md). In short: `main.ahk` and `lib/*.ahk` (hotkeys, tray,
process lifecycle), `actions/*.py` (one entry point per action), `qwen_client.py` (Ollama client and the
`work\` contract), `websearch.py` (End's web search), `viewer.py` / `settings.py` / `pages.py` (local
pages), `static/` (page assets), `searxng/` (launcher and settings), `build/` (reproducible build),
`installer/sorgente/` (NSIS installer), `tests/`, `scripts/` (CI and dev helpers), `tools/` (benchmarks,
license tooling).

## Getting the runtime

Git holds only the sources. The portable Python (`python\`), `ahk\AutoHotkey64.exe` and SearXNG
(`searxng\app`, `searxng\lib`) are not tracked. Without them the Python tests still run (the ones that need
SearXNG or the bundled Python are skipped), but you cannot run the app with web search.

Two ways to get them:

- **From an existing install or checkout:** see [Worktrees](#worktrees) below; `link-runtime.ps1` works
  for any target folder.
- **From the build:** `powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstaller`
  produces `build\out\payload\`. Copy `payload\python\`, `payload\ahk\AutoHotkey64.exe` and
  `payload\app\searxng\app` and `\lib` into your checkout.

## Worktrees

Parallel work happens in git worktrees, one branch each:

```
git worktree add ..\aih-<topic> -b <branch> main
cd ..\aih-<topic>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\link-runtime.ps1 -From C:\AI-Hotkeys
```

`scripts\dev\link-runtime.ps1` creates directory junctions (no admin rights needed) from the source
folder's `python\`, `searxng\app` and `searxng\lib`, and copies `ahk\AutoHotkey64.exe`. It writes nothing
into the source folder and refuses to run when source and target are the same folder. `-To <folder>`
chooses the target; the default is the checkout that contains the script.

## Tests

### Python

```
python -m unittest discover -s tests -t .
python -m unittest tests.test_websearch_ssrf        # one module
python test_config_edit.py                           # old entry point, still works
```

The suite imports the app from a temporary copy (`tests/support.py: AppTree`) with its own `config.ini`
and `work\`. Fake Ollama, SearXNG and web servers run on random `127.0.0.1` ports. Tests that need the
real SearXNG runtime or `python\python.exe` are skipped when those are missing.

Coverage, as CI measures it (the tests run copies of the files, so a remap step is needed):

```
python -m coverage run --rcfile=scripts/ci/coverage.ini -m unittest discover -s tests -t .
python scripts/ci/coverage_remap.py
python -m coverage report --rcfile=scripts/ci/coverage.ini --fail-under=72
```

The exact sequence is in `.github/workflows/ci.yml`; the threshold only goes up.

### Lint

```
python -m ruff check .
```

The rule set (`E9`, `F`, `B`) and exclusions are in `pyproject.toml`.

### AutoHotkey

`tests\ahk\run.ahk` unit-tests the pure helpers in `lib\Util.ahk` and `lib\Proc.ahk`. It prints one line
per assertion and exits with the number of failures. `/validate` loads a script without running it and
exits 0 when it is fine, 2 on a load error. `main.ahk` itself is never started by tests.

AutoHotkey is a GUI program, so its output must be captured explicitly.

PowerShell 5.1:

```powershell
$p = Start-Process ahk\AutoHotkey64.exe -ArgumentList '/ErrorStdOut','tests\ahk\run.ahk' -PassThru -NoNewWindow `
       -RedirectStandardOutput "$env:TEMP\ahk-unit.out" -RedirectStandardError "$env:TEMP\ahk-unit.err"
$null = $p.Handle
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'timed out' }
Get-Content "$env:TEMP\ahk-unit.out","$env:TEMP\ahk-unit.err"; $p.ExitCode
```

Git Bash: MSYS path conversion turns `/ErrorStdOut` and `/validate` into Windows paths, and AutoHotkey then
fails silently or hangs on a dialog. Turn the conversion off:

```bash
MSYS_NO_PATHCONV=1 ahk/AutoHotkey64.exe /ErrorStdOut tests/ahk/run.ahk 2>&1 | cat   # ${PIPESTATUS[0]} = failures
MSYS_NO_PATHCONV=1 ahk/AutoHotkey64.exe /ErrorStdOut /validate main.ahk 2>&1 | cat  # 0 = ok, 2 = load error
```

CI uses `scripts\ci\ahk-run.ps1`, which adds a timeout: a load-time *warning* opens a dialog even with
`/ErrorStdOut`, and the process then waits forever.

### Shared contracts

Some behaviour is checked on both sides:

- Hotkey validation: `tests/fixtures/hotkey_vectors.json` is checked by `tests/test_hotkey_parity.py`
  (Python, `settings.valid_hotkey`) and by `tests/ahk/run.ahk` (AHK, `ValidHotkey`).
- The SearXNG pid file format is parsed by `searxng/avvia_searxng.py` and `lib/Util.ahk`.
- The `work\runs\<id>\` contract is covered by `tests/test_work_contract.py`.

### Manual checks

Hotkeys, focus and the clipboard cannot be tested automatically. Before a release, run the manual Windows
checklist in the plan (`plans/ai-hotkeys-production-readiness.md`, section 7.2) on Windows 10 and 11.

## Building the installer

```
powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1
```

It needs git, `tar.exe` and a Python with pip (`-HostPython <exe>` to choose one). The build:

1. requires a clean working tree, and exports the sources with `git archive HEAD`;
2. downloads Python 3.13 (embeddable), AutoHotkey 2.0.19, SearXNG and NSIS, each checked against the SHA-256
   in `build\pins.json`, into `build\cache\`;
3. downloads the hash-locked SearXNG wheels (`build\requirements-searxng.txt`);
4. assembles `build\out\payload\` from an explicit allowlist and audits it;
5. writes `build\out\manifest.txt` and the generated uninstall list, and checks the third-party notices
   (`tools\licenses\check_notices.py`);
6. compiles `build\out\AI-Hotkeys-Setup-<VERSION>.exe` with NSIS and writes `SHA256SUMS.txt`;
7. runs a smoke test with the payload's own interpreter.

Builds from the same commit are reproducible: identical `manifest.txt` and, on the same machine, an identical
Setup.exe.

Switches: `-SkipInstaller` (payload only), `-AllowDirty` (skip the clean-tree check; still builds `HEAD`),
`-SkipSmoke`, `-AllowMissingNotices` (never for releases).

The version comes from [`VERSION`](VERSION). Bump it in the same change as the `CHANGELOG.md` entry.
To change a pinned dependency, edit `build\pins.json` (URL and SHA-256 from the upstream's published digest)
or run `build\lock-searxng.ps1` for the wheels, then regenerate the notices with
`python tools/licenses/gen_notices.py --lib <lib folder>` and review the license changes.

## CI

All workflows pin actions by commit SHA and downloads by SHA-256.

- **`.github/workflows/ci.yml`** (every push and pull request): ruff and `compileall`; the unit tests on
  windows-latest and windows-2022 with a coverage ratchet; `/validate` of `main.ahk` plus a negative test;
  the AHK unit tests; gitleaks and repository hygiene (no tracked `config.ini`, `work\`, binaries or personal
  paths); license presence and notice freshness; pip-audit of the SearXNG lock (advisory for now).
- **`.github/workflows/installer.yml`** (changes to the payload, the build or the installer): a full build on
  two Windows images, a manifest reproducibility comparison, silent install / upgrade / uninstall tests with
  file, registry, shortcut and ACL assertions, an optional upgrade test from v1.0.0, and an experimental
  Notepad end-to-end test against a fake Ollama.
- **`.github/workflows/release.yml`** (a `v*` tag, or manual): checks that the tag equals `v` + `VERSION`,
  runs in the `release` GitHub Environment (required reviewers), builds without cache, downloads and
  verifies the third-party source archives pinned in `scripts/ci/third-party-sources.json`, attests the build
  provenance, and creates a **draft** GitHub release with the Setup, `manifest.txt`, the
  `third-party-sources.*` archives and `SHA256SUMS.txt`. Publishing is always a manual step.

## Documentation and changelog

- Update [CHANGELOG.md](CHANGELOG.md) under the unreleased version for every user-visible change.
- When behaviour changes, update the README, the docs in `docs/` and, for Italian users,
  [docs/guide-it.md](docs/guide-it.md).
- Regenerate [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) when modules, entry points or file contracts
  change.

## Pull requests

- One topic per pull request, with tests for behaviour changes.
- `python -m unittest discover -s tests -t .` and `python -m ruff check .` must pass; for AHK changes, also
  `/validate` and `tests\ahk\run.ahk`.
- Describe any manual checks you ran (hotkeys cannot be tested in CI).
