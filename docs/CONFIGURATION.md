# Configuration reference

AI-Hotkeys reads `config.ini` in its install folder. A fresh install copies it from
[`config.example.ini`](../config.example.ini), which also explains each key in comments. An upgrade never
overwrites your `config.ini`.

- **Where to change settings.** Most keys are on the Settings page (tray ✦ → Settings). Every key can
  be edited in the file (tray → Open config.ini). AI-Hotkeys notices the saved file and reloads by itself;
  the "Settings applied" toast confirms it.
- **Italian names.** Section names, key names and values such as `si`/`no` or `scuro` are Italian.
  They are part of the file format and will not be renamed. The tables below give the English meaning.
- **Missing or invalid keys.** A missing key falls back to the default shown here, without an error. The
  Settings page only offers allowed values. Numbers typed into the file outside their range are clamped,
  and unknown choices are treated as the default. A file that cannot be read at all (for example a key that appears twice in
  a section, or a file not saved as UTF-8) gives a warning toast, and the defaults are used until it is
  fixed.
- **Yes/no values.** `si` means yes and `no` means no. `no`, `false`, `0` and `off` all count as no.
- **Inline comments.** A `;` preceded by a space ends the value: `correggi = ^!r ; my key` gives `^!r`.

## `[qwen]`: the model

The section keeps the name `[qwen]` for historical reasons (the first default model); it works with any
Ollama model.

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `model` | `gemma4:e4b-it-qat` | an Ollama model name (letters, digits, `.` `:` `-` `/` `_`) that runs locally; never a cloud model | The Ollama model used for every action. Download it with `ollama pull <name>`. Alternatives: `gemma4:e2b-it-qat` (light: about 1.7 GB VRAM, about twice as fast, shallower explanations; for GPUs with 4 GB or less or CPU-only PCs), `gemma4:12b-it-qat` (best quality, about 7.4 GB VRAM, slower) or any other model installed in Ollama, such as `qwen3.5:9b` (the default before 1.1.0). An upgrade never changes this value. See "Choosing the model" below. |
| `ollama_url` | `http://localhost:11434` | `http://` or `https://` URL | Where Ollama listens. Pointing it at another computer sends your selected text there; the Settings page warns about it. |
| `keep_alive` | `30m` | Settings page: `5m`, `10m`, `30m`, `1h`, `-1` (never unload), `0` (unload at once) | How long Ollama keeps the model in video memory after the last request. Tray → Free VRAM unloads it at once. |

### Choosing the model

Gemma 4 is the default and the recommended choice; other models are optional and must be installed locally.

- **Settings → Model** is a list, not a text box. The settings server asks Ollama (`GET /api/tags` at
  `ollama_url`, never through a proxy, 2 s timeout) which models are installed.
- At the top, **Recommended: Gemma 4**: `gemma4:e4b-it-qat` (default, recommended), `gemma4:e2b-it-qat`
  (light: GPUs with 4 GB or less) and `gemma4:12b-it-qat` (maximum quality, slower). Each says "Installed" or
  "Not installed: run `ollama pull <name>`".
- Below, **Other local models**: every other model installed in Ollama, with its size and quantization.
- **What can be saved.** An installed local model, or one of the three recommended names even before it is
  downloaded (the page then shows the `ollama pull` command). The server checks this again on save
  (`settings.validate`); a hand-written name that is neither installed nor recommended is refused.
- **Cloud models are never allowed.** Ollama models tagged `:cloud` or `-cloud` (or listed with
  `remote_host` / `remote_model`) run on Ollama's servers, so your selected text would leave this PC. They
  are hidden from the list and refused on save. If `config.ini` names one, AI-Hotkeys uses
  `gemma4:e4b-it-qat` instead and shows a configuration warning; the health check and every action refuse a
  cloud model with "Cloud models are not allowed: AI-Hotkeys keeps your text on this PC. Choose a local
  model in Settings."
- **Ollama not running.** The page shows the current model read-only, the recommended list and a note. Start
  Ollama, then press **Check installed models again** (the page itself cannot be reloaded).

## `[searxng]`: web search for End

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `web_search` | `auto` | `auto` (when needed), `always`, `false` (never) | Whether End searches the web before explaining. With `false`, SearXNG is never started. |
| `query_mode` | `allow_fallback` | `allow_fallback`, `model` | What may be sent to the search engines. `allow_fallback`: the AI's search words; if a search is forced but the AI writes none, the technical terms found in the text, or its first 10 words. `model`: only the AI's search words; nothing is ever taken verbatim from your text, and with no words there is no search. On the Settings page: "Search words". |
| `searxng_url` | `http://127.0.0.1:8888` | URL | Address of the local SearXNG. Change the port here if 8888 is taken. |
| `results` | `5` | Settings page: 3–8 (the code accepts 1–10) | How many search results are passed to the AI. |
| `pages_to_read` | `3` | 0–5 | For how many results the full page is downloaded and read (the others are used as short previews). |

## `[aspetto]`: look of the results and Settings pages

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `tema` | `scuro` | `scuro` (dark), `nero` (black), `chiaro` (light), `sistema` (follow Windows) | Colour theme. |
| `colore` | `ambra` | `ambra` (amber), `ghiaccio` (ice blue), `menta` (mint), `corallo` (coral), `viola` (violet), `neutro` (neutral) | Accent colour. |
| `testo` | `16` | 14–20 | Text size in pixels. |
| `larghezza` | `normale` | `stretta` (narrow), `normale` (normal), `ampia` (wide) | Width of the reading column. |
| `mostra_originale` | `si` | `si`, `no` | Show the selected text next to the result. |
| `avanzamento` | `si` | `si`, `no` | Show the progress bubble near the mouse while the AI works. |

## `[tasti]`: hotkeys

| Key | Default | Meaning |
|---|---|---|
| `correggi` | `PgUp` | Fix (correct) the selected text. |
| `riassumi` | `PgDn` | Summarize it. |
| `spiega` | `End` | Explain it. |

Keys use AutoHotkey syntax: `^` = Ctrl, `!` = Alt, `+` = Shift, `#` = Win, for example `^!r` for Ctrl+Alt+R.
The same rules apply in the file and on the Settings page, where you record a key by pressing it:

- A letter or digit needs at least one modifier, because you need it for typing.
- Without a modifier, only PgUp, PgDn, End, Home, Ins, Del, Pause, ScrollLock, AppsKey and F1–F24 are
  allowed.
- With a modifier, the Settings page also offers Space, Tab, Enter, Backspace, the arrow keys and the
  numeric keypad keys. Names are case-sensitive (`PgUp`, not `pgup`), and each modifier may appear once.
- An invalid key, or a key already used by another action, falls back to the default and is reported in a
  toast at startup.

## `[comportamento]`: behaviour

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `sostituisci_testo` | `si` | `si`, `no` | PgUp replaces the selected text directly in Notepad, Notepad++, Obsidian, Word and VS Code. With `no` the result opens in the results page. PgDn and End always open the page. |
| `lunghezza` | `normale` | `breve` (short), `normale` (normal), `dettagliata` (detailed) | Length of summaries and explanations. |
| `clip_wait_ms` | `2000` | whole milliseconds, 100–10000 | Optional, not on the Settings page. How long a key waits for the copied selection. With nothing selected, the key acts normally after this time. Lower it (for example `500`) for a snappier key; raise it if Excel or a remote desktop copies slowly. |

## `[obsidian]`: the To-Do note

| Key | Default | Meaning |
|---|---|---|
| `todo_file` | `%USERPROFILE%\Documents\To-Do List.md` | The note that PgUp reorganizes when it is open in Obsidian. Environment variables are expanded, and surrounding quotes are allowed. If your Documents folder is redirected to OneDrive, use the real path, for example `%USERPROFILE%\OneDrive\Documents\To-Do List.md`. |
| `window_title` | `To-Do List -` | How the Obsidian window title starts while that note is open. Obsidian titles look like `<note name> - <vault name> - Obsidian`. |

Backups of the note go to the hidden folder `.ai-hotkeys-backups` next to it; the newest 20 are kept.

## Files that are not settings

- `prompts_user.py`: your own prompts (tray → Edit prompts). See the README.
- `work\`: temporary and log files. See [PRIVACY.md](../PRIVACY.md) and
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
