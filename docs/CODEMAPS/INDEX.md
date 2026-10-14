# AI-Hotkeys Codemap — Index

**Last Updated:** 2026-10-14
**Entry Points:** `main.ahk`, `actions/*.py`, `viewer.py`, `settings.py`
**Source of truth:** generata dai sorgenti; se un percorso qui non esiste più, la mappa è da rigenerare.

## Architecture

```
                    +------------------ main.ahk ------------------+
                    | hotkey -> dispatcher (contesto|posizione)     |
                    | tray, toast avanzamento, Esc 2s, watch config |
                    +---+----------+-----------+----------+--------+
                        |          |           |          |
        testo selezionato  To-Do List    Impostazioni   SearXNG lifecycle
                        |          |           |          |
            +-----------v--+  +----v--------+-+ +-v--------+-+ +-v------------------+
            | rewrite.py    |  | obsidian_   | | | settings.py | | searxng/           |
            | summarize.py  |  | todo.py     | | | /api/save   | | avvia_searxng.py   |
            | explain.py    |  | atomica+    | | +-------------+ | settings.yml       |
            +------+--------+  | backup      | |                 +---------+----------+
                   |           +------+------+ |                           |
                   v                  |      |                   http://127.0.0.1:8888
            +------v----------------+-v------v-+                           |
            | qwen_client.py         |         |                           |
            | chat / open_stream     |         |                           |
            +---+----------+---------+         |                           |
                |          |                   |                           |
        +-------v----+ +---v-------------+ +---v---------------------------v---+
        | prompts.py | | Ollama          | | websearch.py (solo End)           |
        | system+user| | localhost:11434 | | query -> SearXNG -> pagine ->     |
        | OPTIONS    | | qwen3.5:9b      | | fonti [n] -> prompt -> add_sources|
        +------------+ +--------+--------+ +-----------------------------------+
                                |
                    +-----------v-----------+
                    | viewer.py (127.0.0.1) |
                    | pagina + /api/ask     |
                    | "Chiedi a Qwen"       |
                    +-----------------------+

Config: config.example.ini -> config.ini (personal, gitignored) <-> config_edit.py <-> watch in main.ahk
State: work/input.txt, work/output.txt, work/status.txt, work/meta.json, work/sources.json, work/obsidian_*.txt
```

## Key Modules

| Module | Purpose | Exports | Dependencies |
|--------|---------|---------|--------------|
| `main.ahk` | Hotkey, dispatcher `contesto\|posizione` → azione, tray, toast, Esc-2s, ricarica config, avvio/stop SearXNG | `Dispatch`, `RunSelectionAction`, `RunObsidianTodo`, `WaitPid`, `ToastShow`, `SearxngUrl/Enabled`, `ReadConfig` | `actions/*.py`, `viewer.py`, `settings.py`, `config.ini`, `work/*`, `searxng/avvia_searxng.py`, `ahk/AutoHotkey64.exe` |
| `actions/rewrite.py`, `actions/summarize.py`, `actions/explain.py` | Wrapper sottili delle 3 azioni su selezione | `qwen_client.run_action(mode, argv)` | `qwen_client.py` |
| `actions/obsidian_todo.py` | Riorganizza To-Do List.md con controlli di sicurezza, backup, scrittura atomica | `main`, `ask_qwen`, `normalize`, `validate`, `check_structure`, `task_states`, `write_status` | `qwen_client.py`, `work/obsidian_output.txt`, `work/obsidian_status.txt` |
| `actions/unload.py` | Libera la VRAM (voce tray) | `qwen_client.unload()` | `qwen_client.py` |
| `qwen_client.py` | Client Ollama condiviso, config, pulizia risposte, orchestrazione `run_action` | `CONFIG`, `MODEL`, `KEEP_ALIVE`, `load_config`, `chat`, `open_stream`, `stream_pieces`, `unload`, `clean_answer`, `run_action`, `todo_file` | `prompts.py`, `websearch.py` (lazy, solo `explain`), `config.ini`, `work/meta.json` |
| `prompts.py` | Tutti i prompt Qwen + parametri Ollama (modificabili dall'utente) | `first_messages`, `query_messages`, `followup_rewrite_messages`, `followup_qa_messages`, `OPTIONS`, `NUM_CTX=16384`, costanti `REWRITE/SUMMARIZE/EXPLAIN/QUERY/FOLLOWUP` | nessuna |
| `websearch.py` | Ricerca web End: decisione query, SearXNG, lettura pagine, citazioni `[n]` | `status`, `gather_sources`, `make_queries`, `decide_queries`, `technical_terms`, `parse_queries`, `searx_search`, `fetch_page_text`, `select_relevant`, `source_kind`, `sources_block`, `linkify`, `add_sources`, `save/load_sources`, `ensure_running` | `prompts.py`, `qwen_client.py`, `searxng/lib` (curl_cffi), SearXNG HTTP |
| `viewer.py` | Pagina risultati + popup "Chiedi a Qwen" (server `127.0.0.1`, token effimero) | `Session`, `detect_mode`, `build_page`, `make_handler`, `read_meta`, `main`; `GET /`, `/api/ping`, `/fonts/*`; `POST /api/ask` (NDJSON) | `pages.py`, `prompts.py`, `qwen_client.py`, `websearch.py`, `static/viewer.html` |
| `settings.py` | Pagina impostazioni (server `127.0.0.1`, token effimero) | `current_values`, `validate`, `build_page`, `make_handler`, `valid_hotkey`, `defaults`; `GET /`, `/api/ping`; `POST /api/save` | `config_edit.py`, `pages.py`, `static/settings.html`, `config.ini` |
| `pages.py` | Parti comuni alle pagine: aspetto, font, CSS, JSON sicura | `LOOK`, `TEXT_SIZE`, `look_settings`, `theme_css`, `script_json`, `html_escape`, `try_serve_font` | `static/theme.css`, `static/fonts/*.woff2` |
| `config_edit.py` | Scrittura `config.ini` preservando commenti/ordine/BOM/CRLF + CLI per installer | `set_values`, `read_values`; CLI `config_edit.py <ini> sezione.chiave=valore` | nessuna (stdlib) |
| `test_config_edit.py` | Test preservazione commenti/BOM/CRLF | 1 test `SetValuesTest` (`python test_config_edit.py`) | `config_edit.py` |
| `searxng/avvia_searxng.py`, `searxng/settings.yml` | Launcher SearXNG locale (pid `work/searxng.pid`, log `work/searxng.log`) | avvio idempotente + attesa `healthz` | `searxng/app/`, `searxng/lib/` (vendored, gitignored) |
| `installer/sorgente/installer.nsi`, `installer/sorgente/stop.ps1` | Setup (VERSION `1.0.0`, MODEL `qwen3.5:9b`): payload app+python+ahk, `config.ini` never overwritten, check Ollama via winget | app/startup/desktop/Ollama sections | `config.example.ini` as source of the initial `config.ini` |

## Data Flow

1. **Correzione/riassunto (PgUp/PgDn):** hotkey → `Dispatch(slot)` → route `*|slot` → copia selezione (`^c`) → `work/input.txt` → `actions/<modo>.py` → `qwen_client.run_action` → `prompts.first_messages` → Ollama `/api/chat` → `clean_answer` → `work/output.txt` (+ `work/meta.json`) → sostituzione diretta (solo rewrite in app editabili) oppure `viewer.py`.
2. **Spiegazione (End):** come sopra + prima `websearch.gather_sources`: `decide_queries` (termini tecnici → forza, altrimenti Qwen dice NO o scrive 1-2 query) → `ensure_running` (avvia SearXNG se serve) → `searx_search` parallela → `fetch_page_text` parallela (`PAGES_TO_READ+2` candidati) → `select_relevant` dentro il budget (`SOURCES_BUDGET=10000`, `TOTAL_INPUT_CHARS=36000`) → `sources_block` nel prompt → risposta con `[n]` → `add_sources` (link + `## Fonti`) → `save_sources` per il follow-up.
3. **Obsidian To-Do (PgUp con To-Do aperto):** route `Obsidian:To-Do|correggi` → `RunObsidianTodo` (`^s`, poi `obsidian_todo.py`) → Qwen riorganizza → `normalize` → `validate` (struttura 3 livelli × 3 categorie, checkbox, link/immagini/URL/tag, anti-troncamento) → se ok: backup + scrittura atomica; se ko: file intatto, esito in `work/obsidian_status.txt`.
4. **Follow-up ("Chiedi a Qwen"):** pagina → `POST /api/ask {question, base}` → `Session.build_messages` (rewrite: originale + versione base; qa: originale + primo risultato + ultime 6 coppie + fonti) → `open_stream` → NDJSON `{t}` → `clean_answer` → `linkify` → `Session.save` → `{done, index, text}`.
5. **Impostazioni:** tray → `settings.py` → `GET /?t=token` (`build_page` legge `config.ini` ogni volta) → `POST /api/save` → `validate` → `config_edit.set_values` → `WatchConfig` in `main.ahk` vede il cambio e fa `Reload`.

## External Dependencies

- Ollama on `http://localhost:11434` + model `qwen3.5:9b` (not vendored; `ollama pull qwen3.5:9b`) — version in `installer.nsi` (`MODEL`) and `config.example.ini` (`[qwen] model`)
- SearXNG su `http://127.0.0.1:8888` (wrapper versionato `avvia_searxng.py`+`settings.yml`, AGPLv3 `searxng/LICENSE-searxng.txt`; `app/|lib/` vendored ~82 MB via Releases)
- AutoHotkey v2 (`ahk/AutoHotkey64.exe` locale via setup, GPLv2 `ahk/license.txt`; sorgente `main.ahk` con `#Requires AutoHotkey v2.0`)
- Python 3.x soli moduli standard (`configparser`, `urllib`, `http.server`, `concurrent.futures`, `html.parser`, …); `python/` portatile ~31 MB via Releases; `curl_cffi` riusato da `searxng/lib` per pagine anti-403
- `static/marked.min.js` (MIT), font Barlow/IBM Plex (`static/fonts/OFL-*.txt`, SIL OFL)

## Recent Changes (2026-10-14)

- Rimossi `websearch._bool` e `websearch.clear_status` (zero chiamanti; ciclo status è write-only: `status()` → `work/status.txt` → `main.ahk` lo cancella). Nessuna doc utente li citava. Dettagli in `docs/DELETION_LOG.md`.
- Nota: `graphify-out/` è un derivato gitignored e contiene ancora i nodi rimossi nella cache — va rigenerato, non corretto a mano.

## Related Areas

- Utente finale: `installer/AI-Hotkeys/LEGGIMI.txt`, `README.md` (sezioni Uso/Comportamento)
- Configuration: `config.example.ini` (template) → `config.ini` (personal); validation in `settings.py` (`CHOICES`/`NUMBERS`/`TEXTS`/`KEYS`), look in `pages.py` (`LOOK`, `TEXT_SIZE`)
- Storia rimozioni: `docs/DELETION_LOG.md`
