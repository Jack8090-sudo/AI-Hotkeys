# AI-Hotkeys: guida per l'utente

AI-Hotkeys usa un modello di intelligenza artificiale locale (Qwen, tramite Ollama) sul testo che
selezioni in qualsiasi programma di Windows. L'interfaccia del programma è in inglese; questa guida
spiega tutto in italiano.

## Cosa serve

- Windows 10 o 11 a 64 bit.
- [Ollama](https://ollama.com/download), versione **0.9.0 o successiva** (meglio la più recente).
- Il modello `qwen3.5:9b`: circa 6,6 GB da scaricare.
- Una scheda video con circa **8 GB di memoria (VRAM)** libera; consigliata una scheda da **12 GB**.
  Con meno memoria Ollama sposta una parte del modello nella RAM e sul processore: funziona, ma le
  risposte diventano molto più lente.
- Circa 7 GB liberi su disco (quasi tutti per il modello; AI-Hotkeys occupa circa 110 MB).

## Installazione

1. Fai doppio clic su `AI-Hotkeys-Setup-<versione>.exe`.
   Se Windows mostra "Windows ha protetto il PC", clicca **Ulteriori informazioni** e poi
   **Esegui comunque**: l'installer non è firmato digitalmente.
2. Segui i passaggi. La cartella proposta è `%LOCALAPPDATA%\Programs\AI-Hotkeys`, accessibile solo al tuo
   account di Windows. Python e AutoHotkey sono inclusi: non devi installarli.
3. Se Ollama non è installato, l'installer te lo propone:
   - **Sì**: lo installa con winget (accettando le condizioni di Ollama e di winget);
   - **No**: apre la pagina di download di Ollama;
   - **Annulla**: salta questo passaggio.
4. Alla fine apri il Prompt dei comandi e scarica il modello (una volta sola):

   ```
   ollama pull qwen3.5:9b
   ```

5. AI-Hotkeys parte insieme a Windows (si può disattivare durante l'installazione). La sua icona ✦ è vicino
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
- **Annullare**: tieni premuto **Esc** per 2 secondi mentre Qwen lavora. Una pressione breve di Esc arriva
  al programma come sempre.
- **Domande successive**: nella pagina dei risultati c'è un riquadro "Ask Qwen". Dopo una correzione ogni
  risposta è una nuova versione del testo; negli altri casi è una conversazione che ricorda le ultime
  6 domande e risposte e riusa le fonti trovate sul web.
- La pagina dei risultati non si può ricaricare con F5: per rivederla, premi di nuovo il tasto. Si chiude
  da sola dopo circa 4 minuti di inattività.
- La prima pressione dopo un po' di tempo può essere lenta: Ollama deve caricare il modello nella
  memoria della scheda video (fino a circa un minuto dopo l'accensione del PC).

### Menu dell'icona

Tasto destro sull'icona ✦:

| Voce | Cosa fa |
|---|---|
| Settings | impostazioni: tasti, tema, lunghezza delle risposte, ricerca web, modello |
| Free VRAM | libera subito la memoria della scheda video (utile prima di giocare) |
| Open SearXNG in browser | apre il motore di ricerca locale nel browser |
| Edit prompts | apre i tuoi prompt personali (`prompts_user.py`) |
| Open config.ini | apre il file delle impostazioni |
| Open folder | apre la cartella di installazione |
| Reload / Exit | riavvia / chiude AI-Hotkeys (se Qwen sta lavorando chiede conferma) |

### Messaggi di errore

Gli errori compaiono in un riquadro vicino al mouse; nel frattempo i tasti continuano a funzionare.
I più comuni:

| Messaggio | Cosa fare |
|---|---|
| Ollama is not running | avvia Ollama dal menu Start |
| Model 'qwen3.5:9b' not found: run  ollama pull qwen3.5:9b | scarica il modello con il comando indicato |
| Ollama … is too old: update it to 0.9.0 or newer | aggiorna Ollama |
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
- `[qwen] keep_alive`: per quanto tempo il modello resta pronto in memoria (predefinito `30m`).
- `[comportamento] clip_wait_ms` (facoltativa): quanti millisecondi un tasto aspetta la copia della
  selezione (predefinito 2000). Abbassala, per esempio a `500`, se senza selezione i tasti ti sembrano
  lenti; alzala se Excel o il desktop remoto copiano lentamente.

### La nota To-Do di Obsidian

Con la nota To-Do aperta in Obsidian, **PgUp** riorganizza l'intera nota invece di correggere la
selezione. Imposta in `config.ini`:

```
[obsidian]
todo_file = %USERPROFILE%\Documents\To-Do List.md
window_title = To-Do List -
```

- `todo_file` è il percorso completo della nota.
- `window_title` è l'inizio del titolo della finestra di Obsidian quando la nota è aperta
  (i titoli sono del tipo `To-Do List - IlMioVault - Obsidian`).
- Se la cartella Documenti è salvata su **OneDrive**, la nota si trova di solito in
  `%USERPROFILE%\OneDrive\Documents`: copia il percorso dalla barra degli indirizzi di Esplora file e
  usalo in `todo_file`.

Prima di ogni modifica viene salvata una copia nella cartella nascosta `.ai-hotkeys-backups`, accanto alla
nota (restano le 20 più recenti). Se un controllo di sicurezza fallisce (attività, link, tag o paragrafi
persi), la nota non viene toccata e una finestra elenca i problemi.

### I tuoi prompt

Tasto destro → **Edit prompts** apre `prompts_user.py`. La prima volta il file viene creato con una copia
commentata dei prompt standard: togli il commento solo a ciò che vuoi cambiare. Gli aggiornamenti non
toccano mai questo file. Se contiene un errore, AI-Hotkeys usa i prompt standard e mostra un avviso.
Per tornare ai prompt standard basta cancellarlo.

## Ricerca sul web e privacy

Il testo selezionato e le risposte restano sul tuo PC: Qwen gira in locale, tramite Ollama.

L'unica eccezione è la ricerca sul web del tasto **End**. Passa da SearXNG, un motore di ricerca che gira
sul tuo PC, ma che inoltra le **parole di ricerca** a motori pubblici (Startpage, Yahoo); poi le pagine
trovate vengono scaricate dai rispettivi siti. Il testo completo e la risposta non escono dal PC.

Nella pagina Settings puoi scegliere:

- **When to search**: quando serve (predefinito), sempre, oppure mai (`web_search = false`: niente esce dal
  PC).
- **Search words**: "Qwen or from the text" (predefinito: se Qwen non scrive parole di ricerca, possono
  essere usate le prime 10 parole del testo o i termini tecnici trovati) oppure "Only Qwen's" (il testo
  non viene mai inviato così com'è).

I file temporanei con il testo selezionato vengono cancellati appena possibile (cartella `work\runs`).
Dettagli (in inglese): [PRIVACY.md](../PRIVACY.md).

## Disinstallazione

Impostazioni di Windows → App → AI-Hotkeys → Disinstalla (oppure menu Start → AI-Hotkeys → Uninstall).
Ti viene chiesto se cancellare anche le impostazioni (`config.ini`) e la cartella `work`. I tuoi prompt
(`prompts_user.py`) e le copie della nota To-Do restano comunque. Ollama e il modello si tolgono a parte
(App di Windows, e `ollama rm qwen3.5:9b`).
