# AI-Hotkeys

Global hotkeys that run a local language model on any text you select, in any Windows program:

- **PgUp**: fix the selected text (spelling, grammar, style)
- **PgDn**: summarize it
- **End**: explain it, optionally with a web search

Everything runs on your PC: AutoHotkey v2 handles the keys and the tray icon, Python talks to the AI,
and the AI is a small model that ships with AI-Hotkeys: LFM2.5-230M, fine-tuned for these three keys
and run by llama.cpp's `llama-server` on `127.0.0.1`. Nothing else to install. If you already use
[Ollama](https://ollama.com), you can switch the engine to it in the settings. The optional web search for
End uses a private SearXNG on `127.0.0.1:8888`. See [PRIVACY.md](PRIVACY.md) for what leaves your PC when it
is on.

Current version: see [`VERSION`](VERSION) (1.1.0). Changes: [CHANGELOG.md](CHANGELOG.md).

## Requirements

| | |
|---|---|
| Windows | Windows 10 or 11, 64-bit (x64). |
| AI model | Included: `models\lfm-hotkeys-Q6_K.gguf` (about 190 MB), a version of [LiquidAI/LFM2.5-230M](https://huggingface.co/LiquidAI/LFM2.5-230M) trained for AI-Hotkeys' tasks, under the LFM Open License v1.0 ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#11-the-ai-model-lfm25-230m-fine-tuned-for-ai-hotkeys)). |
| Graphics card | Not required. With one (any brand, through Vulkan) the model writes about 500 tokens/s and uses about 0.5 GB of video memory; on the processor alone about 200 tokens/s. |
| Memory | About 0.5 GB while the model is loaded; it unloads itself after 30 minutes without use. |
| Disk | About 400 MB in all. |
| Ollama (optional) | Only if you switch the engine to Ollama: [Ollama](https://ollama.com/download) 0.9.0 or newer and a model such as `gemma4:e4b-it-qat` (about 6 GB, 3-4 GB of VRAM). Bigger models write richer explanations; the built-in one is much lighter and faster. Comparison: [docs/audit/model-choice-2026-11.md](docs/audit/model-choice-2026-11.md). |

## Install (Setup.exe)

This is the normal way. Full walkthrough: [docs/INSTALL.md](docs/INSTALL.md).

1. Download `AI-Hotkeys-Setup-<version>.exe` from the
   [latest release](https://github.com/Jack8090-sudo/AI-Hotkeys/releases/latest).
2. Run it. The installer is not code-signed, so Windows SmartScreen may say "Windows protected your
   PC": choose **More info**, then **Run anyway**.
3. It installs into `%LOCALAPPDATA%\Programs\AI-Hotkeys`, a folder private to your Windows account.
   It bundles the AI model and its engine, Python and AutoHotkey, so you need nothing else.
4. AI-Hotkeys starts with Windows (you can turn that off in the installer). Its ✦ icon sits in the
   notification area.

Upgrading from v1.0.0 (the Italian build that installed into `C:\AI-Hotkeys`): run the new Setup.
It offers to move your `config.ini` to the new folder, stop the old copy and disable its
shortcuts. See [Migration from v1.0.0](docs/INSTALL.md#migration-from-v100).

Upgrading from 1.1.0 (Ollama and Gemma): after the upgrade AI-Hotkeys uses the built-in model, because a
1.1.0 `config.ini` does not name an engine. To keep Gemma, open **Settings** from the ✦ icon and set
**Model → Engine** to **Ollama** (or write `backend = ollama` under `[qwen]` in `config.ini`). Your Ollama
model setting is kept either way.

Choosing the engine: **Settings → Model → Engine**. **Built-in (LFM)** needs nothing else; **Graphics card**
chooses between using the GPU when there is one and the processor only. **Ollama** shows the Ollama model
list: the recommended Gemma 4 models first, then the other models installed in Ollama on this PC. Ollama cloud
models (`:cloud` / `-cloud` tags) are never offered and are refused at run time, because they would send your
selected text off this PC.

## Run from source

For development or if you prefer not to run an installer.

- **Python 3.13 x64** (CPython). Only 3.13 is supported, because the SearXNG libraries are built for it.
  The app itself uses only the standard library; the one exception is `curl_cffi`, which it reuses
  from SearXNG's `searxng\lib` when that folder is present.
- **AutoHotkey v2.0** (the project pins 2.0.19).
- The engine and the model, which are not in git: `llama\` (llama-server and its DLLs from the
  llama.cpp release pinned in `build\pins.json`) and `models\lfm-hotkeys-Q6_K.gguf`. The build puts them in
  `build\out\payload\app\llama` and `\models`: copy them into your checkout. Or set `backend = ollama`.

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
- **Web search (End)**: with `web_search = auto`, the AI decides whether the text needs a search
  (technical terms force one). Sources become clickable `[1] [2]` citations plus a list.
- **Results page**: reloading (F5) is not available, because the access token is removed from the
  address after the page opens. Open the result again with the hotkey instead.

### Tray menu

Right-click the ✦ icon: **Settings**, **Free VRAM** (unloads the model at once; the next key loads it
again), **Open SearXNG in browser**, **Edit prompts**, **Open config.ini**, **Open folder**, **Reload**, **Exit**.
Reload and Exit ask first when a job is running.

### When something goes wrong

Errors appear as a toast near the mouse, and the hotkeys keep working while it is shown. Examples:

- "The AI engine is not responding: try again" (details in `work\llama-server.log`).
- "Port 8095 is used by another program: change llama_port in config.ini."
- With the Ollama engine: "Ollama is not running: start Ollama, then try again.", "Model '…' not found:
  run  ollama pull …", "Ollama 0.x is too old: update it to 0.9.0 or newer."
- "The selected text is too long (N characters, about M at most): select a shorter part."
- "The answer was cut off (too long for the model): select a shorter part." Nothing is pasted in that case.
- A broken `config.ini` gives a warning that names the line, for example "line 3: 'model' appears twice
  in [qwen]". AI-Hotkeys keeps working with the default settings.
- A key that is invalid or used twice in `[tasti]` is reported at startup, and the default key is used.

More in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Your own prompts

Tray → **Edit prompts** opens `prompts_user.py` in the install folder, and creates it the first time as a
commented-out copy of the standard `prompts.py`. Uncomment and change only what you need. With the
built-in model, keep in mind that it was trained on the short prompts in `prompts_lfm.py`: a different
prompt usually gives worse answers. Updates never
ship or overwrite this file. If it has an error, the standard prompts are used and a warning appears
after the next reload. Delete the file to go back to the standard prompts. (The Start-menu shortcut
"Edit prompts" still opens `prompts.py`; an upgrade saves a changed `prompts.py` as
`prompts.py.bak-<old version>`.)

## Configuration

Settings live in `config.ini` in the install folder. Most of them can be changed on the Settings page;
a few others are edited in the file (tray → Open config.ini). Changes apply
automatically ("Settings applied"). The section and key names, and values such as `si`/`no`, are Italian
and stay that way for compatibility. The [configuration reference](docs/CONFIGURATION.md) lists every key
with its English meaning. A missing key always falls back to its default.

## Privacy and security

- [PRIVACY.md](PRIVACY.md): what stays on your PC, what the web search sends, when your text is deleted.
- [SECURITY.md](SECURITY.md): how the local pages are protected, the web-fetch rules, and how to report
  a vulnerability.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md): installation, first run, migration, the optional Ollama engine
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): logs and common problems
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): every `config.ini` key
- [docs/guide-it.md](docs/guide-it.md): guida per l'utente in italiano
- [CONTRIBUTING.md](CONTRIBUTING.md): development, tests, build and CI
- [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md): code map

## Licenses

AI-Hotkeys' own code is under the MIT license ([LICENSE](LICENSE)). The installer also ships the AI model
(LFM Open License v1.0, modified), llama.cpp (MIT), Python, AutoHotkey (GPL-2.0), SearXNG (AGPL-3.0) and
other libraries, each under its own license: see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the [`licenses/`](licenses) folder. The source archives
for AutoHotkey 2.0.19, SearXNG, and lxml with the GNU libiconv it bundles are attached to every GitHub
Release as `third-party-sources.*` files, next to the installer. Ollama and its models are not included;
their own licenses apply.
