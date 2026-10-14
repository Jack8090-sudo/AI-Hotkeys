# AI-Hotkeys

Tasti globali per usare un LLM in locale su qualsiasi testo selezionato:

- **PgUp** → correggi il testo selezionato
- **PgDn** → riassumi
- **End** → spiega (con ricerca web opzionale)

Stack: AutoHotkey v2 (hotkey + UI) → Python → Ollama → Qwen. La ricerca web
usa SearXNG in locale su `127.0.0.1:8888`.

## Requisiti

- Windows 10/11 a 64 bit
- [Ollama](https://ollama.com/download) + modello `qwen3.5:9b` (~6.6 GB, Q4_K_M):
  `ollama pull qwen3.5:9b` (scheda da ~12 GB consigliata)
- AutoHotkey v2 (incluso nel setup, oppure installato a parte per l'uso da sorgente)
- SearXNG solo per la ricerca web di End (codice wrapper in `searxng/`, opzionale)

## Uso

1. Scarica una release oppure clona i sorgenti.
2. Copia `config.esempio.ini` in `config.ini` e imposta il file Obsidian:
   `todo_file = %USERPROFILE%\Documents\To-Do List.md`
   e il prefisso titolo corrispondente (`window_title = To-Do List -`).
3. Avvia `main.ahk`, seleziona del testo e premi PgUp / PgDn / End.
4. Impostazioni: icona nella tray → Impostazioni (oppure `config.ini` + "Ricarica").

Da sorgente è richiesto un Python 3.x con i soli moduli standard
(`configparser`, `urllib`, `http.server` — nessuna dipendenza esterna).

## Comportamento

- **Annulla con Esc:** tieni premuto Esc per 2 secondi mentre Qwen lavora
  per uccidere il processo Python e pulire i file a metà in `work\`.
  La pressione breve di Esc resta normale.
- **PgUp in Obsidian con To-Do List.md aperto** non corregge il testo
  selezionato: riorganizza l'intero file (`actions/obsidian_todo.py`,
  scrittura atomica + backup `To-Do List.backup_*.md`, controlli di
  sicurezza che bloccano la scrittura se mancano attività, link o tag).
- **Sostituzione diretta:** con `[comportamento] sostituisci_testo = si`,
  la correzione PgUp sostituisce il testo selezionato in Blocco note,
  Obsidian, Word, VS Code e Notepad++; PgDn ed End aprono sempre la pagina.
- **Ricerca web (End):** `[searxng] web_search = auto` cerca solo quando
  serve (il modello decide dalle query, i termini tecnici riconosciuti
  forzano comunque la ricerca), `always` cerca sempre, `false` mai.
  Le fonti diventano citazioni `[1] [2]…` cliccabili + elenco in fondo.
- **Chiedi a Qwen:** la pagina dei risultati ha un popup per domande
  successive (riscrittura iterativa in modalità correzione, Q&A con le
  ultime 6 coppie domanda/risposta nelle altre modalità, fonti riusate).
- **Lunghezza:** `[comportamento] lunghezza = breve | normale | dettagliata`
  (vale per riassunti e spiegazioni).
- **VRAM:** il modello resta in memoria per `[qwen] keep_alive` (default
  `30m`); tasto destro sull'icona → "Libera la VRAM" lo scarica subito
  (`actions/unload.py`).
- **Tasti personalizzabili** in `[tasti]` (sintassi AutoHotkey; lettere e
  numeri da soli non ammessi perché servono per scrivere). Nella pagina
  delle Impostazioni i tasti si registrano premendoli.
- **Pagine locali sicure:** risultati e impostazioni sono server su
  `127.0.0.1` con porta casuale e token effimero (`?t=…` + header
  `X-Token`); si chiudono da soli dopo minuti di inattività
  (240 s risultati, 300 s impostazioni). Richieste non da
  `127.0.0.1`/`localhost` → 403.
- **Chiavi mancanti:** se `config.ini` non ha una chiave presente in
  `config.esempio.ini` (es. `[tasti]`, `aspetto.larghezza`), vale il
  predefinito del codice — nessun errore.

## Struttura

- `main.ahk` — hotkey, dispatcher (`contesto|posizione` → azione), tray, integrazione SearXNG
- `qwen_client.py`, `prompts.py`, `websearch.py` — client Ollama, prompt, ricerca
- `viewer.py`, `settings.py`, `pages.py` — pagina risultati / impostazioni (server locali su 127.0.0.1 con token effimero)
- `config_edit.py`, `test_config_edit.py` — modifica config preservando commenti + test (`python test_config_edit.py`)
- `actions/` — `rewrite.py`, `summarize.py`, `explain.py`, `obsidian_todo.py`, `unload.py`
- `ahk/` — `license.txt` versionato + `AutoHotkey64.exe` locale (il binario viaggia col setup, non via git)
- `static/` — `viewer.html`, `settings.html`, `theme.css`, `marked.min.js`, `fonts/`
- `searxng/` — solo `avvia_searxng.py`, `settings.yml`, `LICENSE-searxng.txt`
- `installer/sorgente/` — `installer.nsi`, `stop.ps1` (il setup compila il payload da `config.esempio.ini`, mai da `config.ini`)

## Cosa NON è nel repo (e perché)

- `config.ini` — percorsi personali, ignorato via `.gitignore`
- `work/` — file runtime (`input.txt`, `output.txt`, log, pid). Attenzione: contiene
  in chiaro gli ultimi testi selezionati — non committarlo mai, non includerlo nei backup
- `python/` (~31 MB), `searxng/app|lib/` (~82 MB), `*.exe`, `*.rar` — distribuiti via GitHub Releases, non via git
- `graphify-out/`, `__pycache__/` — derivati locali

## Documentazione

- Mappa del codice generata dai sorgenti: [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)
- Log delle rimozioni: [docs/DELETION_LOG.md](docs/DELETION_LOG.md)
- Istruzioni per l'utente finale installato: `installer/AI-Hotkeys/LEGGIMI.txt`

## Licenze terze

- AutoHotkey: `ahk/license.txt` (GPLv2) — il binario non è versionato
- SearXNG: `searxng/LICENSE-searxng.txt` (AGPLv3) — solo wrapper + settings versionati
- `static/marked.min.js` (MIT), font Barlow / IBM Plex (`static/fonts/OFL-*.txt`, SIL OFL)
- Il codice proprio è MIT (`LICENSE`).
