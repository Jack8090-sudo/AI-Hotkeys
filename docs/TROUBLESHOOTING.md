# Troubleshooting

Most problems show up as a toast near the mouse that says what went wrong. This page explains the
messages, where AI-Hotkeys keeps its logs, and fixes for common problems.

The install folder is `%LOCALAPPDATA%\Programs\AI-Hotkeys` unless you chose another one (tray →
**Open folder** opens it). Paths below are relative to it.

## Where to look

| File | What it holds |
|---|---|
| `work\error.txt` | The last error of the startup health check or of tray → Free VRAM. Line 1 is the message you saw; the next lines are technical detail. Errors of a PgUp/PgDn/End job are written inside that job's own folder (`work\runs\<id>\error.txt`), shown as a toast, and deleted together with the folder. |
| `work\server.log` | Errors of the local results and Settings pages. Restarted when it passes 1 MB. |
| `work\searxng.log` | The SearXNG search engine's log. Rotated to `searxng.log.1` at 5 MB. |
| `work\config_warning.txt` | Problems found in `config.ini` or `prompts_user.py`. Shown as a toast once, then deleted. |
| `work\obsidian_status.txt` | Result of the last Obsidian To-Do run. |
| `work\obsidian_output.txt` | The AI's version of the To-Do note, kept only when a safety check rejected it, so you can compare. |

The `work\` folder is private to your account and may contain parts of the text you selected. Do not
attach it to a bug report without reading it first. See [PRIVACY.md](../PRIVACY.md).

## Messages

**"Ollama is not running: start Ollama, then try again."**
Start Ollama from the Start menu (it then runs in the notification area), or run `ollama serve`. If
`ollama_url` in the settings points to another address, check it.

**"Model 'gemma4:e4b-it-qat' not found: run  ollama pull gemma4:e4b-it-qat"**
The model in `[qwen] model` is not downloaded. Run the command shown. If you changed `model`, check the
spelling against `ollama list`. After an upgrade, `config.ini` keeps the model it named before
(`qwen3.5:9b` before 1.1.0): pull that one, or switch to `gemma4:e4b-it-qat` in Settings → **Model**.

**"Ollama 0.x is too old: update it to 0.9.0 or newer."**
Install the current version from <https://ollama.com/download>. Your models are kept.

**"Ollama answered 404: check  ollama_url  in the settings"**
Something answers at `ollama_url`, but it is not Ollama. The default is `http://localhost:11434`.

**"Ollama did not answer in time" / "Ollama stopped while answering" / "The answer was interrupted
before the end."**
Ollama was busy, crashed or was restarted. Try again. If it keeps happening, look at Ollama's own log
(Ollama tray icon → View logs).

**"The selected text is too long (N characters, about M at most): select a shorter part."**
The text does not fit in the model's context. Fixing allows less text than summarizing, because the
answer is as long as the input. Select a part and run the key again.

**"The answer was cut off (too long for the model): select a shorter part."**
The model reached its answer limit. Nothing was pasted, so your text is unchanged.

**"Nothing selected: select some text first."**
The copy produced empty text. Some programs copy nothing for an empty selection.

**"The AI did not respond. Check that Ollama is running and that the model is downloaded."**
The job ended without a result and without a specific reason, for example because Python crashed. Try
again; if it repeats, check the points above and the [antivirus](#antivirus-or-quarantine) section.

**"Could not write / delete / read …"**
A file in `work\` is locked, usually by an antivirus scan or a backup tool. Try again, or restart
AI-Hotkeys (tray → Reload).

**"The window did not come back to the front" / "The selection changed" / "The window lost focus"**
PgUp did not paste because the target window or selection changed while the AI was working. The result is
in the results page; copy it from there. Your clipboard holds what it held before.

**Key warnings at startup**, for example *Fix: "pgup" is not a valid key, using PgUp* or
*Summarize: PgUp is already used by Fix, using PgDn*.
Fix the key in `[tasti]` or record it again on the Settings page. The rules are in
[CONFIGURATION.md](CONFIGURATION.md#tasti-hotkeys).

**A config.ini warning, for example "line 3: 'model' appears twice in [qwen]".**
Python could not read `config.ini`, so the actions use the default settings. Open it (tray → Open
config.ini), fix the line named in the message, and save it as UTF-8.

**"prompts_user.py has an error … using the standard prompts."**
Fix the file (tray → Edit prompts) or delete it.

## Common problems

### Port 8888 is busy

SearXNG listens on `127.0.0.1:8888`. If another program already uses that port, End explains without the
web and `work\searxng.log` says:

`ERROR: port 8888 on 127.0.0.1 is used by another program, not AI-Hotkeys' SearXNG.`

Either stop that program, or pick a free port in `config.ini`:

```
[searxng]
searxng_url = http://127.0.0.1:8899
```

Find the program with `Get-NetTCPConnection -LocalPort 8888 -State Listen` (the `OwningProcess` column is
its process id).

### Web search finds nothing

- `web_search` may be `false`, or with `auto` the AI decided the text needs no search (personal notes,
  opinions).
- With `query_mode = model`, there is no search when the AI writes no search words.
- Open tray → **Open SearXNG in browser** and search by hand. If that fails, read `work\searxng.log`.
- Some search engines block or rate-limit for a while; try again later.
- If your PC reaches the internet only through a proxy, pages cannot be read: page downloads deliberately
  ignore proxy settings (see [SECURITY.md](../SECURITY.md)). Search snippets may still work.

### Antivirus or quarantine

Unsigned AutoHotkey programs and new installers are sometimes flagged by antivirus heuristics. Symptoms:
the Setup is blocked, the ✦ icon never appears, or "The AI did not respond" on every key.

1. Open your antivirus quarantine and check whether it removed `ahk\AutoHotkey64.exe`, a file under
   `python\`, or the Setup itself.
2. Check the file against the release: every installed file is listed with its SHA-256 in `.manifest` in
   the install folder, and the Setup in the release's `SHA256SUMS.txt`.
3. If it matches, restore it and add an exclusion for the install folder, or reinstall.

### The keys do nothing

- Is the ✦ icon in the notification area? If not, start AI-Hotkeys from the Start menu.
- Another program may use the same key. Choose another one on the Settings page.
- In programs running as administrator, AI-Hotkeys (running as you) may not be able to copy or paste.
- Compact laptop keyboards may produce PgUp/PgDn/End only with Fn. Choose keys you can press directly,
  such as `^!r`.
- In consoles and on AI-Hotkeys' own pages the keys always act normally. That is intentional.

### The first key press is slow

- **With nothing selected**, a key waits up to 2 s for a copy before acting normally. Lower it with
  `[comportamento] clip_wait_ms`, for example `500`.
- **The first job after a while** waits for Ollama to load the model into video memory (seconds, up to
  about a minute after a reboot). Raise `[qwen] keep_alive` to keep it loaded longer.
- **Everything is slow**: the model probably does not fit in video memory. Close games or other GPU
  programs, check `ollama ps` (the PROCESSOR column should say 100% GPU), or choose a smaller model.

### The results page says "Disconnected" or shows a 403 page

Results pages close themselves after about 4 minutes without use (the Settings page after 5), and
reloading with F5 is not possible. Run the key again, or reopen Settings from the tray.

### Copying from Excel or a remote desktop fails

Large ranges or remote sessions can take longer than 2 s to copy. Set `[comportamento] clip_wait_ms`
to `4000` or more.

## Reporting a problem

Open an issue on the project's GitHub page with your Windows version, the AI-Hotkeys version
([`VERSION`](../VERSION) or Windows Settings → Apps), the Ollama version (`ollama -v`), and the exact message.
Remove personal text from any log you attach. Security problems: see [SECURITY.md](../SECURITY.md).
