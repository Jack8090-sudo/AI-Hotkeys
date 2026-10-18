# AI-Hotkeys

Global hotkeys that run a local language model on any text you select, in any Windows program:

- **PgUp**: fix the selected text (spelling, grammar, style)
- **PgDn**: summarize it
- **End**: explain it, optionally with a web search

Everything runs on your PC: AutoHotkey v2 handles the keys and the tray icon, Python talks to
[Ollama](https://ollama.com), and Ollama runs the AI model (Gemma 4 E4B by default). The optional web search for End uses a
private SearXNG on `127.0.0.1:8888`. See [PRIVACY.md](PRIVACY.md) for what leaves your PC when it is on.

Current version: see [`VERSION`](VERSION) (1.1.0). Changes: [CHANGELOG.md](CHANGELOG.md).

## Requirements

| | |
|---|---|
| Windows | Windows 10 or 11, 64-bit (x64). |
| Ollama | [Ollama](https://ollama.com/download) **0.9.0 or newer**. AI-Hotkeys checks this at startup, because older versions do not accept the `think: false` option it sends. Install the current Ollama release: older releases may not know the `gemma4` model family. |
| Model | `gemma4:e4b-it-qat` (Gemma 4 E4B, quantization-aware trained), about a 6 GB download. Get it with `ollama pull gemma4:e4b-it-qat`. Google releases Gemma 4 under the [Apache License 2.0](https://ai.google.dev/gemma/apache_2) (the older [Gemma Terms of Use](https://ai.google.dev/gemma/terms) apply only to Gemma 1-3); it is not part of AI-Hotkeys. You can choose another Ollama model in the settings: `gemma4:e2b-it-qat` as a light option for graphics cards with 4 GB or less or for PCs without a GPU (about 1.7 GB VRAM, faster, shallower explanations), `gemma4:12b-it-qat` for maximum quality, or `qwen3.5:9b` (the previous default, still works). Why this model: [docs/audit/model-choice-2026-10.md](docs/audit/model-choice-2026-10.md). |
| Graphics card | About **3-4 GB of free VRAM** for the model plus its context, so an **8 GB** card fits comfortably and a 6 GB card will likely work. |
| Without enough VRAM | Ollama keeps working, but puts the part of the model that does not fit into system RAM and runs it on the CPU. Answers then get much slower (roughly ten times). |
| Disk | About 6.5 GB: about 6 GB for the model, about 110 MB for AI-Hotkeys itself. |

## Install (Setup.exe)

This is the normal way. Full walkthrough: [docs/INSTALL.md](docs/INSTALL.md).

1. Download `AI-Hotkeys-Setup-<version>.exe` from the project's GitHub Releases page.
   Releases are drafted by the release workflow and published by hand. Until the first one is
   published, build the installer yourself ([CONTRIBUTING.md](CONTRIBUTING.md)).
2. Run it. The installer is not code-signed, so Windows SmartScreen may say "Windows protected your
   PC": choose **More info**, then **Run anyway**.
3. It installs into `%LOCALAPPDATA%\Programs\AI-Hotkeys`, a folder private to your Windows account.
   It bundles its own Python and AutoHotkey, so you need neither.
4. If Ollama is missing, the installer offers to install it. Then run `ollama pull gemma4:e4b-it-qat` once.
5. AI-Hotkeys starts with Windows (you can turn that off in the installer). Its ✦ icon sits in the
   notification area.

Upgrading from v1.0.0 (the Italian build that installed into `C:\AI-Hotkeys`): run the new Setup.
It offers to move your `config.ini` to the new folder, stop the old copy and disable its
shortcuts. See [Migration from v1.0.0](docs/INSTALL.md#migration-from-v100).

Switching to the new default model: an upgrade never changes your `config.ini`, so it keeps the model
it already names (before 1.1.0 the default was `qwen3.5:9b`). To use Gemma 4, run
`ollama pull gemma4:e4b-it-qat`, then open **Settings** from the ✦ icon and set **Model** to
`gemma4:e4b-it-qat` (or write `model = gemma4:e4b-it-qat` under `[qwen]` in `config.ini` and choose
**Reload**). To keep Qwen, change nothing; `ollama rm qwen3.5:9b` frees its disk space once you switch.

Choosing the model: **Settings → Model** lists the three recommended Gemma 4 models first (`gemma4:e4b-it-qat`,
the default; `gemma4:e2b-it-qat`, light; `gemma4:12b-it-qat`, maximum quality), each marked installed or with
its `ollama pull` command, and below them the other models installed in Ollama on this PC. Only those can be
chosen. Ollama cloud models (`:cloud` / `-cloud` tags) are never offered and are refused at run time, because
they would send your selected text off this PC; a `config.ini` that names one falls back to the default with
a warning.

## Run from source

For development or if you prefer not to run an installer.

- **Python 3.13 x64** (CPython). Only 3.13 is supported, because the SearXNG libraries are built for it.
  The app itself uses only the standard library; the one exception is `curl_cffi`, which it reuses
  from SearXNG's `searxng\lib` when that folder is present.
- **AutoHotkey v2.0** (the project pins 2.0.19).
- Ollama and the model, as above.

```
git clone https://github.com/Jack8090-sudo/AI-Hotkeys.git
cd AI-Hotkeys
copy config.example.ini config.ini
```

Then start `main.ahk` with AutoHotkey v2. `main.ahk` uses `python\pythonw.exe` when that folder
exists, otherwise the `pythonw` on your PATH. Every launch uses `-E -s`, so `PYTHONPATH` and
your user site-packages are ignored.

Web search needs the SearXNG runtime (`searxng\app` and `searxng\lib`), which is not in git. Without it,
End explains using only the selected text. To get it, build the payload
(`powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstaller`) and copy
`build\out\payload\app\searxng\app` and `\lib`, plus `build\out\payload\python`, into your checkout.
Details are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Using it

- Select text and press **PgUp**, **PgDn** or **End**.
- **PgUp** replaces the selection directly in Notepad, Notepad++, Obsidian, Word and VS Code
  (`[comportamento] sostituisci_testo = si`, the default). Elsewhere, and for PgDn and End, the result
  opens in a local results page in your browser.
- Before pasting, PgUp checks that the same window is in front and that the selection is still the text
  it sent. If not, nothing is pasted: a message says why, and the result opens in the results page.
  After a successful paste the corrected text stays in the clipboard.
- **Nothing selected**: the key keeps its normal function and your clipboard is restored. In consoles
  (Windows Terminal, cmd, PowerShell, Git Bash) and on AI-Hotkeys' own pages the keys always act
  normally.
- **Cancel**: hold **Esc** for 2 seconds while the AI is working. A short Esc press reaches the app as usual.
- **Ask AI**: the results page has a box for follow-up questions. In fix mode each answer is a new
  version of the text; otherwise it is a conversation that remembers the last 6 questions and answers
  and reuses the web sources.
- **Obsidian To-Do**: PgUp in Obsidian, with the note named in `[obsidian]` open, reorganizes the whole
  note instead. It saves a backup first, writes atomically, and leaves the file untouched if any safety
  check fails (lost tasks, links, tags, paragraphs or headings).
- **Web search (End)**: with `web_search = auto`, the AI decides whether the text needs a search
  (technical terms force one). Sources become clickable `[1] [2]` citations plus a list.
- **Results page**: reloading (F5) is not available, because the access token is removed from the
  address after the page opens. Open the result again with the hotkey instead.

### Tray menu

Right-click the ✦ icon: **Settings**, **Free VRAM** (unloads the model from the graphics card at
once), **Open SearXNG in browser**, **Edit prompts**, **Open config.ini**, **Open folder**, **Reload**, **Exit**.
Reload and Exit ask first when a job is running.

### When something goes wrong

Errors appear as a toast near the mouse, and the hotkeys keep working while it is shown. Examples:

- "Ollama is not running: start Ollama, then try again."
- "Model 'gemma4:e4b-it-qat' not found: run  ollama pull gemma4:e4b-it-qat"
- "Ollama 0.x is too old: update it to 0.9.0 or newer." (checked once at startup)
- "The selected text is too long (N characters, about M at most): select a shorter part."
- "The answer was cut off (too long for the model): select a shorter part." Nothing is pasted in that case.
- A broken `config.ini` gives a warning that names the line, for example "line 3: 'model' appears twice
  in [qwen]". AI-Hotkeys keeps working with the default settings.
- A key that is invalid or used twice in `[tasti]` is reported at startup, and the default key is used.

More in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Your own prompts

Tray → **Edit prompts** opens `prompts_user.py` in the install folder, and creates it the first time as a
commented-out copy of the standard `prompts.py`. Uncomment and change only what you need. Updates never
ship or overwrite this file. If it has an error, the standard prompts are used and a warning appears
after the next reload. Delete the file to go back to the standard prompts. (The Start-menu shortcut
"Edit prompts" still opens `prompts.py`; an upgrade saves a changed `prompts.py` as
`prompts.py.bak-<old version>`.)

## Configuration

Settings live in `config.ini` in the install folder. Most of them can be changed on the Settings page;
the Obsidian settings and a few others are edited in the file (tray → Open config.ini). Changes apply
automatically ("Settings applied"). The section and key names, and values such as `si`/`no`, are Italian
and stay that way for compatibility. The [configuration reference](docs/CONFIGURATION.md) lists every key
with its English meaning. A missing key always falls back to its default.

## Privacy and security

- [PRIVACY.md](PRIVACY.md): what stays on your PC, what the web search sends, when your text is deleted.
- [SECURITY.md](SECURITY.md): how the local pages are protected, the web-fetch rules, and how to report
  a vulnerability.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md): installation, Ollama, first run, Obsidian, migration
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): logs and common problems
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): every `config.ini` key
- [docs/guide-it.md](docs/guide-it.md): guida per l'utente in italiano
- [CONTRIBUTING.md](CONTRIBUTING.md): development, tests, build and CI
- [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md): code map

## Licenses

AI-Hotkeys' own code is under the MIT license ([LICENSE](LICENSE)). The installer also ships Python,
AutoHotkey (GPL-2.0), SearXNG (AGPL-3.0) and other libraries, each under its own license: see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the [`licenses/`](licenses) folder. The source archives
for AutoHotkey 2.0.19, SearXNG, and lxml with the GNU libiconv it bundles are attached to every GitHub
Release as `third-party-sources.*` files, next to the installer. Ollama and the AI model are not included; their own licenses apply.
