# S8a — main.ahk: pure helpers extracted to lib/Util.ahk, AHK unit tests

## What changed

- `ReadConfig`, `IsNo`, `ValidHotkey`, `KeyLabel`, `HexToColorRef` and `CIMap` moved verbatim from
  `main.ahk` to the new `lib/Util.ahk`. It has no top-level code. `main.ahk` includes it with
  `#Include %A_ScriptDir%\lib\Util.ahk` and has no other change. The dispatch, cancel and wait
  region is untouched.
- **C37, `ReadConfig(key, default := "", section := "", path := "")`.** Every existing call
  (`ReadConfig(key, default)`) works unchanged.
  - `section` given: only lines inside `[section]` count. The match is case-insensitive and
    tolerates spaces inside the brackets. Lines before the first header belong to no section.
    No section: the first `key =` line anywhere in the file, as before.
  - Inline comments: a `;` preceded by a space or tab ends the value. A `;` with no whitespace
    before it is kept (`a;b`). A value that is only a comment returns the default.
  - The key is compared literally and case-insensitively against the text before the first `=`.
    It is never spliced into a regex, so keys like `a.b` or `c(d` are safe.
  - CR, LF and CRLF line endings are all handled, and `\r`, spaces and tabs are trimmed from the
    value. A UTF-8 BOM is fine.
  - As before, the first matching line wins and an empty value returns the default.
  - `path = ""` means `A_ScriptDir "\config.ini"`, the same file as `main.ahk`'s `CONFIG`.
    AHK 2.0 only allows constant parameter defaults, so `path := CONFIG` is not possible.
- **Hotkey parity.** `ValidHotkey` now applies exactly the rules of `settings.valid_hotkey`, the
  authority:
  - Each modifier `^ ! + #` may appear at most once.
  - A single letter or digit needs a modifier.
  - Longer names must be in the settings page's list, and the match is case-sensitive.
  - Without a modifier, only PgUp, PgDn, End, Home, Ins, Del, Pause, ScrollLock, AppsKey and
    F1–F24 are allowed.

  The shared vectors are in `tests/fixtures/hotkey_vectors.json` (44 valid, 76 invalid).
  `tests/test_hotkey_parity.py` checks them in Python, and `tests/ahk/run.ahk` checks them in AHK.
- New `tests/ahk/run.ahk`: 237 assertions covering every `lib/Util.ahk` function. It covers LF,
  CRLF and CR files, each with and without BOM, plus inline comments, duplicate keys in other
  sections, missing and empty sections, missing keys and a missing file. Fixtures go to a private
  folder in `%TEMP%` that is deleted afterwards. The runner prints one line per assertion and
  exits with the failure count. Each test group is isolated, so one exception does not hide the
  other groups.
  - Run against the old helpers, the suite fails 63 checks: the C37 cases and every now-rejected
    key.

## User-visible behaviour changes (deliberate: C37 and parity)

### 1. Inline comments are stripped

This applies to every `config.ini` value that `main.ahk` reads: `sostituisci_testo`,
`avanzamento`, `window_title`, `tema`, `colore`, `searxng_url`, `web_search` and the `[tasti]` keys.
- Example: `correggi = ^!r ; mine` now gives `^!r`. It used to give `^!r ; mine`, which was invalid
  and so fell back to PgUp.
- A value that really contains ` ;` is now cut at that point.
- The Python readers (`config_edit.read_values`) do **not** strip inline comments, so the settings
  page still shows such a hotkey as invalid. Follow-up for a Python-owning step if parity is wanted.

### 2. Hotkeys that are now rejected

`main.ahk` used to accept these in `[tasti]`; they now fall back to the default key (I2). S8b3 adds
a warning toast for them. They fall into three groups.

**(a) Real AutoHotkey keys that used to work and are now rejected.** These are the ones users
notice.
- Unmodified non-special named keys:
  - `Space`, `Tab`, `Enter`, `Backspace`
  - `Up`, `Down`, `Left`, `Right`
  - `Numpad0`–`Numpad9`, `NumpadAdd`, `NumpadSub`, `NumpadMult`, `NumpadDiv`, `NumpadDot`,
    `NumpadEnter`
- Wrong case of an allowed name. AutoHotkey's key names are case-insensitive, but the settings page
  is not. Examples: `pgup`, `PGUP`, `pgdn`, `end`, `home`, `f1`, `^space`, `^numpad1`.
- Key names the settings page does not offer, with or without modifiers. Examples: `Esc`,
  `Escape`, `Delete`, `Insert`, `CapsLock`, `NumLock`, `PrintScreen`, `LButton`, `RButton`,
  `MButton`, `XButton1`, `WheelUp`, `LWin`, `RCtrl`, `LShift`, and scan/virtual codes such as
  `sc029`, `vk41`, `^vk41`.
- Repeated modifiers, e.g. `^^a`, `!!PgUp`, `++F5`, `##a`, `^!^r`.

**(b) Strings that AutoHotkey itself rejects.** `Hotkey()` threw for these and `RegisterKeys`
already fell back to the default, so nothing changes for users. Examples: `Foo`, `^Foo`, `F0`,
`F25`, `F99`, `12`, `^12`, `ab`, `PageUp`.

**(c) Values with a trailing newline,** e.g. `PgUp` followed by a newline. `ReadConfig` and the
`Trim` in `RegisterKeys` never produce these, so the change has no effect in practice.

## Hypotheses settled

### H01: refuted

AHK's PCRE does **not** leave a trailing `\r`. AHK v2 regexes treat CR, LF and CRLF as newlines by
default, so `$` in `m)` mode matches before the `\r`. The probe ran the **old** `ReadConfig` regex
on CRLF, LF and CR-only fixtures, and `StrLen(ReadConfig("correggi"))` was 4 (`PgUp`) in all three.
The new `ReadConfig` normalises line endings and trims `\r` anyway. `tests/ahk/run.ahk` keeps the
CRLF `StrLen` assertion as a regression check.

### H13: confirmed for AutoHotkey 2.0.19

- `/validate` loads the script and exits without running the auto-execute section or registering
  hotkeys.
- It exits **0** on success and **2** on a load error, such as a syntax error or a missing
  `#Include` file.
- With `/ErrorStdOut`, the error text goes to **stderr**. `FileAppend(…, "*")` output goes to
  stdout.
- Caveat: a load-time **warning**, such as a call to an undefined function, is shown as a dialog
  even with `/ErrorStdOut`. The process then hangs until the dialog is closed or the process is
  killed. CI must therefore run `/validate` with a timeout and treat a timeout as a failure.
  `main.ahk` currently produces no warning.
- No `--selftest` fallback is needed.

## Validated commands (for S2 CI)

### PowerShell 5.1

Run from the repository root. `$t` is any temp dir, never the repo. Cache `.Handle`, or 5.1 returns
an empty `ExitCode` when you do not use `-Wait`.

```powershell
$t = $env:RUNNER_TEMP   # or $env:TEMP locally

# AHK unit tests: exit code = number of failures
$p = Start-Process ahk\AutoHotkey64.exe -ArgumentList '/ErrorStdOut','tests\ahk\run.ahk' -PassThru -NoNewWindow `
       -RedirectStandardOutput "$t\ahk-unit.out" -RedirectStandardError "$t\ahk-unit.err"
$null = $p.Handle
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'ahk-unit timed out' }
Get-Content "$t\ahk-unit.out","$t\ahk-unit.err"; exit $p.ExitCode

# AHK syntax check: 0 = ok, 2 = load error; a timeout means a warning dialog
$p = Start-Process ahk\AutoHotkey64.exe -ArgumentList '/ErrorStdOut','/validate','main.ahk' -PassThru -NoNewWindow `
       -RedirectStandardOutput "$t\ahk-validate.out" -RedirectStandardError "$t\ahk-validate.err"
$null = $p.Handle
if (-not $p.WaitForExit(60000)) { $p.Kill(); throw 'ahk-validate timed out (warning dialog?)' }
Get-Content "$t\ahk-validate.err"; exit $p.ExitCode
```

`-Wait` instead of `WaitForExit` also works, as in the plan's §0.6 form, but it has no timeout.

### Git Bash

MSYS path conversion rewrites `/ErrorStdOut` and `/validate` into Windows paths. AHK then exits 2
with no output, and can hang on a "file not found" dialog. Disable the conversion:

```bash
MSYS_NO_PATHCONV=1 ahk/AutoHotkey64.exe /ErrorStdOut tests/ahk/run.ahk 2>&1 | cat   # ${PIPESTATUS[0]} = failures
MSYS_NO_PATHCONV=1 ahk/AutoHotkey64.exe /ErrorStdOut /validate main.ahk 2>&1 | cat  # ${PIPESTATUS[0]} = 0 / 2
```

### Python

```
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -t .   # 136 tests, OK (7 expected failures)
python -m unittest tests.test_hotkey_parity
python -m ruff check .
```

## Not done here / notes for later steps

- **`main.ahk` still calls `ReadConfig(key, default)` without sections.** The brief limited
  `main.ahk` to the extraction. S8b can pass the section at each call site, e.g.
  `ReadConfig(slot, def, "tasti")`. In `config.example.ini` every key `main.ahk` reads is unique, so
  this does not matter today.
- **Manual smoke test not run.** The acceptance criteria ask for each default hotkey in Notepad and
  the tray menu. It would register global hotkeys on the desktop, so it was not run here; do it
  before merging.
- **`scripts/dev/link-runtime.ps1` (S1-owned) fails** under `powershell -File` on this machine:
  `$PSScriptRoot` is empty in the `param()` default of `-To`. Workaround: pass
  `-To <worktree path>`.
