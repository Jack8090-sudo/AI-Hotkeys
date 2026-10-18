# Installing AI-Hotkeys

This guide covers a fresh Windows 10 or 11 (x64) PC. Requirements are listed in the
[README](../README.md#requirements). For a source checkout, see [Run from source](../README.md#run-from-source).

## 1. Download and run the installer

1. Download `AI-Hotkeys-Setup-<version>.exe` from the project's GitHub Releases page. Each release also
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
   - *AI-Hotkeys* (required): the app, a private Python and AutoHotkey, and the local SearXNG.
   - *Start with Windows* (on by default): a shortcut in your Startup folder.
   - *Desktop shortcut* (off by default).
   - *Check Ollama* (on by default): see the next section.
6. On the last page, leave "Launch AI-Hotkeys now" ticked. The ✦ icon appears in the notification area
   (you may need to open the hidden-icons arrow).

The Start menu gets an **AI-Hotkeys** folder with *AI-Hotkeys*, *Configuration* (opens `config.ini`),
*Edit prompts* and *Uninstall*.

### Silent install

`AI-Hotkeys-Setup-<version>.exe /S` installs with the defaults. Useful switches:

- `/D=<folder>`: install folder. It must be the last argument and must not be quoted, even with spaces.
- `/NOOLLAMA`: skip the Ollama check.

A silent install never opens a browser and never runs winget.

## 2. Install Ollama and the model

AI-Hotkeys needs [Ollama](https://ollama.com/download) **0.9.0 or newer** and the `qwen3.5:9b` model.

- **Through the installer.** If Ollama is missing, the installer asks how to get it:
  - **Yes**: install it with winget. This accepts the Ollama and winget source terms. Offered only when
    winget is present.
  - **No**: open the Ollama download page.
  - **Cancel**: skip.
- **By hand.** Download it from <https://ollama.com/download> and install it. Ollama starts in the
  background and listens on `http://localhost:11434`.

Then download the model once, in a Command Prompt or PowerShell window:

```
ollama pull qwen3.5:9b
```

It is about 6.6 GB. The installer tells you at the end if the model is missing, or if Ollama is
installed but not running. Check with `ollama list`.

The model needs about 8 GB of free video memory (12 GB card recommended). With less, Ollama moves part of
it to system RAM and the CPU, and answers become much slower. Tray → **Free VRAM** unloads the model when
you need the graphics card for something else, for example a game.

## 3. First run

1. Open Notepad, type a sentence with a typo, select it and press **PgUp**. The sentence is corrected in
   place. The first press of the day can take much longer (up to about a minute), because Ollama loads the
   model into video memory. After that, short texts take a few seconds.
2. Select a paragraph and press **PgDn** (summary) or **End** (explanation). A results page opens in
   your default browser.
3. Right-click the ✦ icon → **Settings** to change keys, theme, answer length, web search and the model.

At startup AI-Hotkeys checks Ollama once. If something is wrong you see a toast such as "Ollama is not
running" or "Model 'qwen3.5:9b' not found". See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Web search

End can search the web through the bundled SearXNG before explaining. Search words taken from your
selection are sent to public search engines. Read [PRIVACY.md](../PRIVACY.md), then choose on the Settings
page:

- **When to search**: when needed (`auto`, the default), always, or never.
- **Search words**: "Qwen or from the text" (default), or "Only Qwen's", which never sends your text
  verbatim.

### Obsidian To-Do note

PgUp in Obsidian reorganizes your To-Do note when that note is open. These settings are not on the
Settings page: open tray → **Open config.ini** and edit the `[obsidian]` section.

```
[obsidian]
todo_file = %USERPROFILE%\Documents\To-Do List.md
window_title = To-Do List -
```

- `todo_file` is the full path of the note. Quotes around the path are allowed.
- `window_title` is how the Obsidian window title starts while the note is open. Obsidian titles look
  like `To-Do List - MyVault - Obsidian`.
- **Documents on OneDrive.** If OneDrive backs up your Documents folder, your notes are probably in
  `%USERPROFILE%\OneDrive\Documents` and the default path is wrong. Open the note's folder in Explorer,
  copy the path from the address bar, and use it in `todo_file`, for example
  `todo_file = %USERPROFILE%\OneDrive\Documents\To-Do List.md`.
- Save the file. AI-Hotkeys reloads by itself.

Each run saves a backup in the hidden folder `.ai-hotkeys-backups` next to the note (the newest 20 are
kept). If a safety check fails, the note is not changed and a dialog lists the problems.

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
- `Uninstall.exe /S` keeps `config.ini` and `work\`. `Uninstall.exe /S /PURGE` deletes them too.
- Ollama and the model are separate programs. Remove them from Windows Settings → Apps, and the model with
  `ollama rm qwen3.5:9b`.
- Obsidian backups in `.ai-hotkeys-backups` are your data and are never deleted.
