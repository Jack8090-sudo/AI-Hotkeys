# SEC1: Security review fixes

This step fixes the findings of a security review. Files changed: `websearch.py`, `main.ahk`,
`lib/Util.ahk`, `installer/sorgente/installer.nsi` and `installer/sorgente/stop.ps1`. New:
`tests/test_websearch_idn.py`. `tests/ahk/run.ahk` gained new test groups.

## 1. HIGH: IDN hosts and DNS rebinding on the curl_cffi path (`websearch.safe_url`)

- `safe_url` now builds one canonical ASCII host:
  - It strips a trailing dot.
  - IDN labels become punycode (`host.encode("idna")`). A `UnicodeError` rejects the URL.
  - Only `[a-z0-9_.-]` may remain.
  - The `localhost` / `*.localhost` / metadata block list is checked on that form, so
    `localhost.` is refused too.
- This ASCII host is used everywhere:
  - `Target.host`
  - the name that is resolved
  - the `CURLOPT_RESOLVE` key (`host:port:ip`)
  - the URL handed to curl
  - the stdlib path's `Host` header and TLS SNI
  - the base for resolving a redirect `Location`
- The URL that is actually requested (`Target.url`) is rebuilt from the validated parts only:
  scheme, ASCII host (IPv6 in brackets), the port only when it is not the default, and the
  percent-encoded path and query. Credentials and the fragment are dropped.
- Effect: curl always finds the pinned address under the exact name it looks up. It can no
  longer do a second DNS lookup for a different spelling of the name (DNS rebinding).

## 4. LOW: local-only SearXNG URL

- **`main.ahk` → Open SearXNG** opens `searxng_url` only if it matches
  `^https?://(127\.0\.0\.1|localhost)(:\d{1,5})?(/[^\s\\]*)?$` (case-insensitive, no
  trailing newline). This is `IsLocalSearxUrl` in `lib/Util.ahk`. For any other value it shows
  an error toast and runs nothing.
- **`websearch`** uses `local_searx_url()`, which applies the same rule. It falls back to
  `http://127.0.0.1:8888` for anything else (another host, a file path, credentials, `\`, spaces).
- **`websearch._get`** raises `ValueError` for a non-http(s) URL. Its opener follows redirects
  only to http(s); urllib alone would also follow `ftp://`.

## 5. LOW: `SecureWorkDir`

- It uses the user's SID, the same way the installer does:
  - It runs `whoami /user /fo csv /nh` through `%ComSpec%`, writing to a temp file in `%TEMP%`
    that is deleted afterwards.
  - `SidFromWhoamiCsv` parses the output and `IsSid` validates it.
  - `WorkAclArgs(dir, sid)` grants `*<SID>`, and returns `""` for anything that is not a SID.
- `work\acl.done` (`ok <timestamp>`) is written only after both icacls steps succeed. A failure,
  or no SID, writes nothing, so the next start retries.
- Older `acl.done` files keep suppressing the retry. That includes the "grant failed" lines that
  the S9 version wrote. Delete the file to force a retry.

## 6. LOW: key label on the viewer command line

- `--key=` now gets `CmdArgSafe(keyLbl)`.
- `CmdArgSafe` removes every `"` and any trailing `\`. For Python's argv parser, `\"` escapes
  the closing quote.

## 7. LOW: recursive deletes never go through a reparse point

- `DeleteRunDir` and `SweepRuns` go through the new `DeleteRunTree`. It calls `DirDelete(dir, true)`
  only if both the run folder and its parent `work\runs` are real directories.
- The pure helper `TreeDeletable(attr)` checks the `FileExist`/`DirExist` attribute string:
  `D` must be present and `L` absent.
- It has unit tests, including a real junction made with `mklink /J`: AutoHotkey reports `L` for
  it, and the target survives.

## 9. LOW: legacy SearXNG pid records

- `SearxngPidIsOurs` now returns false for a pid record without a creation time. Before, it
  trusted a matching interpreter path.
- `StopSearxng` leaves such a process running and keeps the pid file. It logs one line to
  `work\searxng.log` and to `OutputDebug`.
- Only the K5 format (pid plus creation time) is ever closed.

## 2 and 3. MEDIUM: installer folder rules and path canonicalisation (`installer.nsi`)

- **New `AihCanonDir`.** It rejects these first:
  - UNC and device paths (`\\server\share`, `\\?\`, `\\.\`, `//…`)
  - root-relative paths (`\foo`)
  - drive-relative paths (`C:`, `C:foo`)
  - empty segments (`\\`), and `.` / `..` segments
  - segments that end with a dot or a space
  - `: * ? " < > |`. A `:` would be an NTFS alternate data stream.

  It then canonicalises the path with `GetFullPathNameW` through the System plugin.
  `AihCheckDir` runs all its other checks on the canonical path: drive root, profile root, git
  parent, emptiness and writability. The main section replaces `$INSTDIR` with the canonical form
  before anything is created. `AihSecureDir`'s `AihIsUnder` profile and LocalAppData tests
  therefore see the canonical path.
- **The user profile folder itself** (`$PROFILE`) is refused.
- **Existing folders must be ours.** The new `AihDirState` classifies a folder:
  - 0: missing
  - 1: empty
  - 2: only what an uninstall leaves behind: `config.ini`, `work\`, `prompts_user.py`,
    `prompts.local.py`, `prompts.py.bak-*`, `Uninstall.exe*`
  - 3: an AI-Hotkeys installation: `.manifest`, or `main.ahk` together with `qwen_client.py`
  - 4: anything else

  State 4 is refused with "… already contains other files. Choose an empty or new folder, such
  as <folder>\AI-Hotkeys."
  - **UX decision:** refuse rather than silently append `\AI-Hotkeys`. Changing `$INSTDIR`
    inside `.onVerifyInstDir`, which runs on every keystroke, would fight the user's typing.
    It would also hide where the files go in silent `/D=` installs. The Browse button already
    appends `\AI-Hotkeys` (NSIS default behaviour).
  - **Stricter than the brief:** `main.ahk` alone (a personal AutoHotkey script) is not
    accepted. It needs `qwen_client.py` too, which every version since v1.0.0 ships.
  - Reinstalling into a folder that a previous uninstall left with `config.ini` and `work\` is
    still allowed (state 2).
- **icacls `/T`** (the removal of the Everyone, Authenticated Users and Users grants) runs
  recursively only for state 0–2: a folder the installer creates, an empty one, or uninstall
  leftovers. For an existing installation (state 3), it applies to the folder itself only.
  The non-recursive `/inheritance:r /grant:r` step is unchanged.
- **`/PURGE` and the interactive "delete data"** use the new `AihRemoveWork` macro. If
  `$INSTDIR\work` is a junction or symbolic link (`FILE_ATTRIBUTE_REPARSE_POINT`), only the link
  is removed (`RMDir` without `/r`). Otherwise `RMDir /r` runs as before.
- **The directory page text** now states the rules.

### `stop.ps1`

The process matching is narrowed to what AI-Hotkeys itself starts:

- `python*.exe` directly in `<Dir>\python\`
- `AutoHotkey*.exe` directly in `<Dir>\ahk\`
- AutoHotkey whose command line contains `<Dir>\main.ahk`, as before
- `python*.exe` whose command line runs `<Dir>\<name>.py[w]` (top-level script), or something
  under `<Dir>\actions\` or `<Dir>\searxng\`

Before, any process with an executable anywhere under `<Dir>\python\` or `<Dir>\ahk\` matched,
and so did any python whose command line merely mentioned `<Dir>\`. The new `-SelfTest`
switch checks the rules on 13 synthetic cases and does not list or stop any process. The exit
codes are unchanged.

## 8. LOW: winget

- The Ollama install command now includes `--source winget`, so the msstore source is never
  used.

## Validation

- Python: 236 tests OK (12 new in `tests/test_websearch_idn.py`; curl_cffi is replaced by a
  recording fake). `ruff check .` is clean.
- AHK runner: 470 assertions, 0 failures. New groups: `TestSid`, `TestCmdArgSafe`,
  `TestTreeDeletable` and `TestIsLocalSearxUrl`; `TestWorkAclArgs` and `TestSearxngPidIsOurs`
  were updated.
- `/validate` was run on a copy of `main.ahk` + `lib\` outside the repo (exit 0). `main.ahk`
  itself was never run.
- `build\build.ps1 -AllowDirty -SkipSmoke` builds the installer. `makensis /WX` on the staged
  script reports 0 warnings and 0 errors.
- The installer's folder functions (`AihCanonDir`, `AihDirState`, `AihCheckDir`) and
  `AihRemoveWork` were extracted into a throw-away NSIS harness in the session scratchpad. It
  installs nothing, and it ran against scratch folders, including a junction. Every case gave
  the expected result. The real installer and uninstaller were never run.
- The PowerShell parser reports no errors in `stop.ps1`, and `stop.ps1 -SelfTest` passes 13/13.

## Manual checks (Windows Sandbox or VM only)

1. Installing to `C:\Users\<you>\Documents` is refused ("already contains other files"), while
   `…\Documents\AI-Hotkeys` is accepted. `\\server\share\x`, `C:foo`, `C:\a\..\b` and `C:\a.\b`
   are refused on the directory page, and also with `/S /D=`.
2. Upgrading an existing custom-folder installation still works (state 3), and so does
   reinstalling after an uninstall that kept `config.ini`.
3. `Uninstall.exe /S /PURGE`, with `work` replaced by a junction to a folder holding a file:
   the file survives and the junction is gone.
4. Start AI-Hotkeys with `searxng_url = https://example.com` and use Open SearXNG: an error toast
   appears and no browser opens. End still searches through `http://127.0.0.1:8888`.
5. Delete `work\acl.done` and start AI-Hotkeys: `icacls work` shows your SID with full control,
   SYSTEM and Administrators, and `acl.done` says `ok`.

## Recommendations for the user (not code)

- **Release workflow.** Protect `release.yml` with a GitHub Environment (for example `release`)
  that has required reviewers, so a draft release can only be built after a manual approval.
  Add tag protection, a ruleset for `v*` tags, so only maintainers can create or move release
  tags.
- **Hash-pinned developer tools.** Install the CI and dev tools (ruff, and any pip-installed
  helpers) from a requirements file with `--require-hashes`, just as the SearXNG wheels already
  are. Pin GitHub Actions to commit SHAs.
- **Nonce-based CSP (future hardening).** The results and settings pages could send a
  `Content-Security-Policy` with a per-response nonce (`script-src 'nonce-…'`), with no
  `unsafe-inline`. This would contain any future HTML-injection bug in the rendered model
  output.

## Notes for other steps

- S15:
  - Document the install-folder rules: new, empty or an existing AI-Hotkeys folder; no UNC, no
    profile root.
  - Document the local-only `searxng_url`.
  - Explain that `acl.done` now means "succeeded".
  - The README privacy section should mention that a failed ACL is retried at each start.
- S13a/S13b contract changes:
  - `AihCheckDir` is stricter, and `$INSTDIR` is canonicalised in the main section.
  - `stop.ps1` matches fewer processes. The `-Dir` contract and exit codes are unchanged.
