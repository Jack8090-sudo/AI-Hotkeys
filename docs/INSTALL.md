# Installing AI-Hotkeys

This guide covers a fresh Windows 10 or 11 (x64) PC. Requirements are listed in the
[README](../README.md#requirements). For a source checkout, see [Run from source](../README.md#run-from-source).

## 1. Download and run the installer

1. Download `AI-Hotkeys-Setup-<version>.exe` from the [latest release](https://github.com/Jack8090-sudo/AI-Hotkeys/releases/latest). Each release also
   lists `SHA256SUMS.txt`. To check the file in PowerShell:
   `Get-FileHash .\AI-Hotkeys-Setup-1.1.0.exe -Algorithm SHA256` and compare the hash with that list.
2. Double-click the installer. It is not code-signed, so **SmartScreen** may show "Windows protected your
   PC". Choose **More info**, then **Run anyway**. Some antivirus programs are wary of new unsigned
   installers; see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#antivirus-or-quarantine).
3. The license page shows AI-Hotkeys' MIT license. The bundled components keep their own licenses
   (`THIRD_PARTY_NOTICES.md` and `licenses\` in the install folder).
4. **Folder.** The default is `%LOCALAPPDATA%\Programs\AI-Hotkeys`, which only your Windows account,
   SYSTEM and Administrators can access. You can choose another folder, with these rules:
   - it must be writable, must not be the root of a drive, and must not be inside a git repository;
   - a folder outside your user profile is restricted to your account, SYSTEM and Administrators.
5. **Components.**
   - *AI-Hotkeys* (required): the app, the AI model (`models\`, about 190 MB) and its engine (`llama\`),
     a private Python and AutoHotkey, and the local SearXNG.
   - *Start with Windows* (on by default): a shortcut in your Startup folder.
   - *Desktop shortcut* (off by default).
6. On the last page, leave "Launch AI-Hotkeys now" ticked. The ✦ icon appears in the notification area
   (you may need to open the hidden-icons arrow).

The Start menu gets an **AI-Hotkeys** folder with *AI-Hotkeys*, *Configuration* (opens `config.ini`),
*Edit prompts* and *Uninstall*.

### Silent install

`AI-Hotkeys-Setup-<version>.exe /S` installs with the defaults. Useful switches:

- `/D=<folder>`: install folder. It must be the last argument and must not be quoted, even with spaces.
- `/NOOLLAMA`: accepted for compatibility with 1.1.0 scripts; it does nothing, because the installer no
  longer checks for Ollama.

A silent install never opens a browser and never downloads anything.

## 2. The AI model

The installer includes everything: the model (LFM2.5-230M fine-tuned for AI-Hotkeys, `models\`) and the
engine that runs it (llama.cpp's `llama-server.exe`, `llama\`). There is nothing to download.

- **Graphics card.** Not needed. With one (NVIDIA, AMD or Intel, through Vulkan) answers are about twice as
  fast and the model takes about 0.5 GB of video memory. Settings → **Model → Graphics card → Processor
  only** keeps it off the graphics card, for example while gaming.
- **Memory.** The model loads in about a second at the first key and unloads after 30 minutes without use
  (Settings → **Keep in memory**). Tray → **Free VRAM** unloads it at once.
- **Privacy.** `llama-server` listens only on `127.0.0.1:8095` (this PC) and has no web page.

### Using Ollama instead (optional)

If you prefer a bigger model, for example Gemma 4, install [Ollama](https://ollama.com/download) **0.9.0 or
newer**, download a model once (`ollama pull gemma4:e4b-it-qat`, about 6 GB, 3-4 GB of video memory), then
set Settings → **Model → Engine → Ollama** and choose the model. `gemma4:e2b-it-qat` is lighter,
`gemma4:12b-it-qat` gives the richest explanations. Comparison with the built-in model:
[audit/model-choice-2026-11.md](audit/model-choice-2026-11.md).

**Upgrading from 1.1.0?** Your `config.ini` is never overwritten, but it does not name an engine, so the
built-in model is used. To stay with Gemma, set the engine to Ollama (or `backend = ollama` under `[qwen]`).

## 3. First run

1. Open Notepad, type a sentence with a typo, select it and press **PgUp**. The sentence is corrected in
   place, usually in less than a second.
2. Select a paragraph and press **PgDn** (summary) or **End** (explanation). A results page opens in
   your default browser.
3. Right-click the ✦ icon → **Settings** to change keys, theme, answer length, web search and the model.

At startup AI-Hotkeys starts the AI engine once, so the first key is fast. If something is wrong you see a
toast, for example "The AI engine is not responding". See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Web search

End can search the web through the bundled SearXNG before explaining. Search words taken from your
selection are sent to public search engines. Read [PRIVACY.md](../PRIVACY.md), then choose on the Settings
page:

- **When to search**: when needed (`auto`, the default), always, or never.
- **Search words**: "AI or from the text" (default), or "Only the AI's", which never sends your text
  verbatim.

## 4. Updating

Run the new Setup over the old one. It stops AI-Hotkeys, replaces the program files and removes files the
new version no longer uses. It always keeps `config.ini`, `work\` and `prompts_user.py`. If you edited
`prompts.py`, your copy is saved as `prompts.py.bak-<old version>`: move your changes to
`prompts_user.py` (tray → Edit prompts).

## Migration from v1.0.0

v1.0.0 was an Italian-language build, not published on GitHub, that installed into `C:\AI-Hotkeys` by
default. That folder could be modified by any user of the PC, so version 1.1.0 installs into your private
`%LOCALAPPDATA%\Programs\AI-Hotkeys` instead.

**Recommended: move to the new folder.** Run the new Setup and keep the default folder. When it finds the
old installation, it asks whether to migrate. With **Yes** it:

- stops the running v1.0.0;
- copies your `config.ini` into the new folder (only if the new folder has none);
- copies a customized `prompts.py` as `prompts.py.bak-1.0.0`;
- renames the old `Uninstall.exe` to `Uninstall.exe.disabled-by-1.1.0`, so it cannot be run by mistake;
- removes the old Italian shortcuts (`Configurazione`, `Modifica i prompt`, `Disinstalla`, and the
  Startup and Desktop shortcuts that point into the old folder).

The old folder itself is left in place. Check that the new version works, then delete `C:\AI-Hotkeys`
yourself. With **No**, nothing in the old folder is touched. A silent install only copies `config.ini`.

**Alternative: upgrade in place.** Run the Setup with the old folder, for example
`AI-Hotkeys-Setup-1.1.0.exe /D=C:\AI-Hotkeys` or by choosing it on the folder page. It keeps
`config.ini`, saves a customized `prompts.py` as `prompts.py.bak-1.0.0`, removes the v1.0.0 files that are
no longer used (such as `config.esempio.ini` and the old Python library folder) and replaces the Italian
shortcuts. Because `C:\AI-Hotkeys` is outside your user profile, the installer restricts it to your
account, SYSTEM and Administrators.

The installer refuses any folder that is inside a git repository, so it never installs over a source
checkout.

## 5. Uninstalling

Windows Settings → Apps → AI-Hotkeys → Uninstall, or Start menu → AI-Hotkeys → Uninstall.

- It asks whether to delete your settings (`config.ini`) and `work\`. `prompts_user.py` and
  `prompts.py.bak-*` are kept either way.
- `Uninstall.exe /S` keeps `config.ini` and `work\`. `Uninstall.exe /S /PURGE` deletes them too, together with `prompts_user.py` and `prompts.py.bak-*`: nothing is left.
- The built-in model and engine are removed with the app. Ollama, if you installed it, is a separate program:
  remove it from Windows Settings → Apps, and its models with `ollama rm <model>`.
- Obsidian backups in `.ai-hotkeys-backups` are your data and are never deleted.
