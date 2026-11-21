# AI-Hotkeys: guida per l'utente

AI-Hotkeys usa un piccolo modello di intelligenza artificiale che gira sul tuo PC (LFM, incluso nel
programma e allenato apposta per i suoi tre tasti) sul testo che selezioni in qualsiasi programma di Windows. L'interfaccia del programma è in inglese; questa guida
spiega tutto in italiano.

## Cosa serve

- Windows 10 o 11 a 64 bit.
- Nient'altro: il modello (circa 190 MB) e il programma che lo fa girare sono inclusi nell'installer.
- Scheda video non obbligatoria. Se c'è (NVIDIA, AMD o Intel) le risposte sono circa due volte più veloci e
  il modello occupa circa 0,5 GB della sua memoria; senza, usa il processore.
- Circa 400 MB liberi su disco.

## Installazione

1. Fai doppio clic su `AI-Hotkeys-Setup-<versione>.exe`.
   Se Windows mostra "Windows ha protetto il PC", clicca **Ulteriori informazioni** e poi
   **Esegui comunque**: l'installer non è firmato digitalmente.
2. Segui i passaggi. La cartella proposta è `%LOCALAPPDATA%\Programs\AI-Hotkeys`, accessibile solo al tuo
   account di Windows. Python e AutoHotkey sono inclusi: non devi installarli.
3. Non serve scaricare niente: il modello è già incluso.
4. AI-Hotkeys parte insieme a Windows (si può disattivare durante l'installazione). La sua icona ✦ è vicino
   all'orologio, a volte sotto la freccia delle icone nascoste.

Guida completa (in inglese): [INSTALL.md](INSTALL.md).

### Se avevi la versione 1.0.0

La versione 1.0.0 si installava in `C:\AI-Hotkeys`. La nuova versione usa una cartella privata del tuo
account. Avvia il nuovo Setup lasciando la cartella proposta: quando trova la vecchia installazione ti
chiede se spostarla. Rispondendo **Sì**:

- chiude la vecchia copia, se è in esecuzione;
- copia il tuo `config.ini` (le tue impostazioni) nella nuova cartella;
- salva un `prompts.py` modificato come `prompts.py.bak-1.0.0`;
- rinomina il vecchio disinstallatore in `Uninstall.exe.disabled-by-1.1.0`;
- toglie i vecchi collegamenti in italiano (Configurazione, Modifica i prompt, Disinstalla) e quelli in
  Esecuzione automatica e sul desktop.

La vecchia cartella resta dov'è: quando la nuova versione funziona, puoi cancellare `C:\AI-Hotkeys` a mano.

### Se avevi la versione 1.1.0 (con Ollama e Gemma)

Dopo l'aggiornamento AI-Hotkeys usa il modello incluso, perché il `config.ini` della 1.1.0 non dice quale
motore usare. Se preferisci restare con Gemma: icona ✦ → **Settings** → **Model** → **Engine** = **Ollama**
(oppure scrivi `backend = ollama` nella sezione `[qwen]` di `config.ini`). Il modello di Ollama che avevi
scelto resta salvato.

### Scegliere il motore

In **Settings → Model**:

- **Engine → Built-in (LFM)** (predefinito): il modello incluso, non serve installare altro. Con
  **Graphics card** scegli se usare la scheda video quando c'è oppure solo il processore (utile mentre giochi).
- **Engine → Ollama**: un modello che fai girare tu in [Ollama](https://ollama.com/download) (0.9.0 o
  successivo), per esempio `gemma4:e4b-it-qat` (circa 6 GB, 3-4 GB di memoria video). Scrive spiegazioni più
  ricche, ma è molto più pesante e più lento. Dopo averlo installato e scaricato il modello
  (`ollama pull gemma4:e4b-it-qat`) lo scegli dall'elenco. I modelli cloud di Ollama (`:cloud` / `-cloud`)
  non sono mai permessi: il testo uscirebbe dal tuo PC.

## Uso

Seleziona del testo in qualsiasi programma e premi:

| Tasto | Azione |
|---|---|
| **PgUp** | correggi il testo |
| **PgDn** | riassumi |
| **End** | spiega (con ricerca sul web, se serve) |

- In Blocco note, Notepad++, Obsidian, Word e VS Code, **PgUp** sostituisce direttamente il testo
  selezionato. Negli altri programmi, e sempre per PgDn ed End, il risultato si apre in una pagina del
  browser.
- Prima di incollare, PgUp controlla che la finestra sia la stessa e che la selezione non sia cambiata.
  Altrimenti non incolla nulla, ti dice perché e apre il risultato nella pagina. Dopo una sostituzione
  riuscita, il testo corretto resta negli appunti.
- **Se non hai selezionato niente**, il tasto fa il suo lavoro normale (pagina su, pagina giù, fine riga)
  e i tuoi appunti restano intatti. Nelle console (Prompt dei comandi, PowerShell, Windows Terminal,
  Git Bash) e nelle pagine di AI-Hotkeys i tasti funzionano sempre normalmente.
- **Annullare**: tieni premuto **Esc** per 2 secondi mentre l'IA lavora. Una pressione breve di Esc arriva
  al programma come sempre.
- **Domande successive**: nella pagina dei risultati c'è un riquadro "Ask AI". Dopo una correzione ogni
  risposta è una nuova versione del testo; negli altri casi è una conversazione che ricorda le ultime
  6 domande e risposte e riusa le fonti trovate sul web.
- La pagina dei risultati non si può ricaricare con F5: per rivederla, premi di nuovo il tasto. Si chiude
  da sola dopo circa 4 minuti di inattività.
- La prima pressione dopo un po' di tempo aspetta che il modello si carichi: circa un secondo con il
  modello incluso (con Ollama può volerci fino a un minuto dopo l'accensione del PC).

### Menu dell'icona

Tasto destro sull'icona ✦:

| Voce | Cosa fa |
|---|---|
| Settings | impostazioni: tasti, tema, lunghezza delle risposte, ricerca web, modello |
| Free VRAM | libera subito la memoria usata dal modello (utile prima di giocare); al tasto dopo si ricarica |
| Open SearXNG in browser | apre il motore di ricerca locale nel browser |
| Edit prompts | apre i tuoi prompt personali (`prompts_user.py`) |
| Open config.ini | apre il file delle impostazioni |
| Open folder | apre la cartella di installazione |
| Reload / Exit | riavvia / chiude AI-Hotkeys (se l'IA sta lavorando chiede conferma) |

### Messaggi di errore

Gli errori compaiono in un riquadro vicino al mouse; nel frattempo i tasti continuano a funzionare.
I più comuni:

| Messaggio | Cosa fare |
|---|---|
| The AI engine is not responding / could not start | riprova; se continua guarda le ultime righe di `work\llama-server.log`; con problemi della scheda video metti **Graphics card → Processor only** |
| Port 8095 is used by another program | cambia `llama_port` in `config.ini` (per esempio `8096`) |
| The AI engine / model is missing: reinstall | un file è stato cancellato o messo in quarantena dall'antivirus: rilancia il Setup |
| Ollama is not running (solo con il motore Ollama) | avvia Ollama dal menu Start |
| Model '…' not found: run  ollama pull … (solo con Ollama) | scarica il modello con il comando indicato |
| The selected text is too long | seleziona una parte più corta |
| The answer was cut off | la risposta era troppo lunga: non è stato incollato nulla; seleziona meno testo |
| un avviso su config.ini (per esempio "'model' appears twice in [qwen]") | correggi la riga indicata nel file; nel frattempo valgono le impostazioni predefinite |
| un tasto "is not a valid key" o "is already used" | correggi il tasto nelle impostazioni; intanto vale quello predefinito |

Altri problemi (in inglese): [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Impostazioni

Quasi tutto si cambia da tasto destro sull'icona → **Settings**. Le modifiche valgono subito: compare il
messaggio "Settings applied".

Il file `config.ini` (tasto destro → Open config.ini) contiene tutte le impostazioni, anche quelle che non
sono nella pagina. I nomi delle sezioni e delle chiavi sono in italiano. Dopo il salvataggio AI-Hotkeys si
ricarica da solo. Elenco completo (in inglese): [CONFIGURATION.md](CONFIGURATION.md).

Le più utili:

- `[tasti]` `correggi`, `riassumi`, `spiega`: i tre tasti, in sintassi AutoHotkey
  (`^` = Ctrl, `!` = Alt, `+` = Maiusc, `#` = Win; per esempio `^!r` = Ctrl+Alt+R). Lettere e numeri da
  soli non sono ammessi, perché servono per scrivere.
- `[comportamento] sostituisci_testo = si | no`: PgUp sostituisce il testo o apre la pagina.
- `[comportamento] lunghezza = breve | normale | dettagliata`: lunghezza di riassunti e spiegazioni.
- `[qwen] backend = llama | ollama`: il modello incluso (predefinito) oppure Ollama. La sezione si chiama
  `[qwen]` per motivi storici.
- `[qwen] gpu = auto | off`: con il modello incluso, usare la scheda video se c'è oppure solo il processore.
- `[qwen] model`: con Ollama, il modello da usare (predefinito `gemma4:e4b-it-qat`). Deve girare in locale: i
  modelli cloud non sono ammessi.
- `[qwen] keep_alive`: per quanto tempo il modello resta pronto in memoria (predefinito `30m`).
- `[comportamento] clip_wait_ms` (facoltativa): quanti millisecondi un tasto aspetta la copia della
  selezione (predefinito 2000). Abbassala, per esempio a `500`, se senza selezione i tasti ti sembrano
  lenti; alzala se Excel o il desktop remoto copiano lentamente.

### I tuoi prompt

Tasto destro → **Edit prompts** apre `prompts_user.py`. La prima volta il file viene creato con una copia
commentata dei prompt standard: togli il commento solo a ciò che vuoi cambiare. Gli aggiornamenti non
toccano mai questo file. Se contiene un errore, AI-Hotkeys usa i prompt standard e mostra un avviso.
Per tornare ai prompt standard basta cancellarlo. Attenzione: il modello incluso è stato allenato sui prompt
corti di `prompts_lfm.py`; con prompt diversi di solito risponde peggio.

## Ricerca sul web e privacy

Il testo selezionato e le risposte restano sul tuo PC: il modello gira in locale (anche con Ollama).

L'unica eccezione è la ricerca sul web del tasto **End**. Passa da SearXNG, un motore di ricerca che gira
sul tuo PC, ma che inoltra le **parole di ricerca** a motori pubblici (Startpage, Yahoo); poi le pagine
trovate vengono scaricate dai rispettivi siti. Il testo completo e la risposta non escono dal PC.

Nella pagina Settings puoi scegliere:

- **When to search**: quando serve (predefinito), sempre, oppure mai (`web_search = false`: niente esce dal
  PC).
- **Search words**: "AI or from the text" (predefinito: se l'IA non scrive parole di ricerca, possono
  essere usate le prime 10 parole del testo o i termini tecnici trovati) oppure "Only the AI's" (il testo
  non viene mai inviato così com'è).

I file temporanei con il testo selezionato vengono cancellati appena possibile (cartella `work\runs`).
Dettagli (in inglese): [PRIVACY.md](../PRIVACY.md).

## Disinstallazione

Impostazioni di Windows → App → AI-Hotkeys → Disinstalla (oppure menu Start → AI-Hotkeys → Uninstall).
Ti viene chiesto se cancellare anche le impostazioni (`config.ini`) e la cartella `work`. I tuoi prompt
(`prompts_user.py`) restano comunque. Il modello incluso viene tolto con il programma; Ollama, se lo hai
installato, si toglie a parte (App di Windows, e `ollama rm <modello>`).
