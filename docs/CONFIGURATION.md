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

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `model` | `qwen3.5:9b` | an Ollama model name (letters, digits, `.` `:` `-` `/` `_`) | The Ollama model used for every action. Download it with `ollama pull <name>`. |
| `ollama_url` | `http://localhost:11434` | `http://` or `https://` URL | Where Ollama listens. Pointing it at another computer sends your selected text there; the Settings page warns about it. |
| `keep_alive` | `30m` | Settings page: `5m`, `10m`, `30m`, `1h`, `-1` (never unload), `0` (unload at once) | How long Ollama keeps the model in video memory after the last request. Tray → Free VRAM unloads it at once. |

## `[searxng]`: web search for End

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `web_search` | `auto` | `auto` (when needed), `always`, `false` (never) | Whether End searches the web before explaining. With `false`, SearXNG is never started. |
| `query_mode` | `allow_fallback` | `allow_fallback`, `model` | What may be sent to the search engines. `allow_fallback`: Qwen's search words; if a search is forced but Qwen writes none, the technical terms found in the text, or its first 10 words. `model`: only Qwen's search words; nothing is ever taken verbatim from your text, and with no words there is no search. On the Settings page: "Search words". |
| `searxng_url` | `http://127.0.0.1:8888` | URL | Address of the local SearXNG. Change the port here if 8888 is taken. |
| `results` | `5` | Settings page: 3–8 (the code accepts 1–10) | How many search results are passed to Qwen. |
| `pages_to_read` | `3` | 0–5 | For how many results the full page is downloaded and read (the others are used as short previews). |

## `[aspetto]`: look of the results and Settings pages

| Key | Default | Allowed values | Meaning |
|---|---|---|---|
| `tema` | `scuro` | `scuro` (dark), `nero` (black), `chiaro` (light), `sistema` (follow Windows) | Colour theme. |
| `colore` | `ambra` | `ambra` (amber), `ghiaccio` (ice blue), `menta` (mint), `corallo` (coral), `viola` (violet), `neutro` (neutral) | Accent colour. |
| `testo` | `16` | 14–20 | Text size in pixels. |
| `larghezza` | `normale` | `stretta` (narrow), `normale` (normal), `ampia` (wide) | Width of the reading column. |
| `mostra_originale` | `si` | `si`, `no` | Show the selected text next to the result. |
| `avanzamento` | `si` | `si`, `no` | Show the progress bubble near the mouse while Qwen works. |

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
