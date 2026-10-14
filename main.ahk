#Requires AutoHotkey v2.0
#SingleInstance Force

; =========================================================
;  AI-Hotkeys — AutoHotkey → Python → Ollama → Qwen 3.5 9B
; =========================================================
;  Impostazioni: icona nella barra delle applicazioni → Impostazioni
;  (oppure config.ini). Quando config.ini cambia, lo script si ricarica da solo.


; =========================================================
; PERCORSI
; =========================================================

global BASE       := A_ScriptDir
global PYTHON     := FindPython()
global CONFIG     := BASE "\config.ini"
global inputFile  := BASE "\work\input.txt"
global outputFile := BASE "\work\output.txt"
global viewer     := BASE "\viewer.py"
global statusFile := BASE "\work\status.txt"
global busy       := false
; Annullamento con Esc tenuto premuto: il lavoro in corso può essere
; interrotto tenendo premuto Esc per 2 secondi (vedi EscDown/CheckEscHold).
; cancelRequested = true chiede al ciclo di attesa di uccidere Python e pulire.
global cancelRequested := false
global currentPid      := 0
global escTracking     := false
; Riquadro di avanzamento: definito subito, prima di qualsiasi tasto o timer
global toastGui   := 0
global toastPos   := ""


; =========================================================
; AZIONI
; =========================================================
; mode    = come si comporta la pagina dei risultati
;           (rewrite = nuove versioni, summarize / explain = domande)
; replace = nelle app di EDITABLE_APPS il risultato prende il posto del testo
;           selezionato (solo la correzione, e solo se attivo nelle impostazioni)
; doing   = cosa mostra il riquadro di avanzamento

global ACTIONS := CIMap(
    "rewrite",   {script: BASE "\actions\rewrite.py",   name: "Correzione",  mode: "rewrite",   replace: true, doing: "Qwen corregge il testo"},
    "summarize", {script: BASE "\actions\summarize.py", name: "Riassunto",   mode: "summarize", doing: "Qwen scrive il riassunto"},
    "explain",   {script: BASE "\actions\explain.py",   name: "Spiegazione", mode: "explain",   doing: "Qwen prepara la spiegazione"},

    ; Azione speciale: riorganizza TUTTO il file To-Do List.md
    "obsidian_todo", {special: "obsidian_todo", name: "Riorganizza To-Do List"}
)


; =========================================================
; TASTI (da config.ini, sezione [tasti])
; =========================================================
; Le tre "posizioni" hanno un tasto ciascuna; il dispatcher lavora sulle
; posizioni, così cambiare tasto non richiede di toccare le regole sotto.

global DEFAULT_KEYS := Map("correggi", "PgUp", "riassumi", "PgDn", "spiega", "End")
global KEYS := Map()


; =========================================================
; DISPATCHER CENTRALE:  "contesto|posizione"  →  azione
; =========================================================
; Contesti, dal più specifico al più generale:
;   "Obsidian:To-Do"  = Obsidian con aperto To-Do List.md
;   "Chrome.exe"      = nome del processo (maiuscole indifferenti)
;   "*"               = qualsiasi programma
;
; Azione "native" = il tasto fa la sua funzione normale.

global ROUTES := CIMap(
    "Obsidian:To-Do|correggi", "obsidian_todo",

    "*|correggi", "rewrite",
    "*|riassumi", "summarize",
    "*|spiega",   "explain"

    ; Esempi (togli il ";" e aggiungi una virgola alla riga sopra):
    ; "Code.exe|spiega",     "native",
    ; "Discord.exe|correggi", "native"
)


; =========================================================
; APP IN CUI LA CORREZIONE SOSTITUISCE DIRETTAMENTE IL TESTO
; =========================================================
; Solo con [comportamento] sostituisci_testo = si.
; Riassunto e spiegazione si aprono sempre nella pagina dei risultati.

global EDITABLE_APPS := CIMap(
    "Notepad.exe",   true,
    "Obsidian.exe",  true,
    "Code.exe",      true,
    "WINWORD.EXE",   true,
    "notepad++.exe", true
)

global REPLACE_ENABLED := !IsNo(ReadConfig("sostituisci_testo", "si"))
global SHOW_PROGRESS   := !IsNo(ReadConfig("avanzamento", "si"))


; =========================================================
; OBSIDIAN: riconoscimento di To-Do List.md
; =========================================================
; Il titolo della finestra di Obsidian è "<nota> - <vault> - Obsidian v1.x.x".
; Si cambia in config.ini (window_title = ...)

global TODO_TITLE_PREFIX := ReadConfig("window_title", "To-Do List -")


; =========================================================
; AVVIO
; =========================================================

global THEME := LoadTheme()

DirCreate BASE "\work"
RegisterKeys()
SetupTrayMenu()

; Esc tenuto premuto 2 s = annulla il lavoro in corso e pulisce work\.
; "~" così Esc fa sempre anche la sua funzione normale (pressione breve).
Hotkey("~Esc", EscDown)
Hotkey("~Esc Up", EscUp)

; SearXNG (ricerca web per End) parte insieme ad AI-Hotkeys
StartSearxng()
OnExit(StopSearxng)

; Ricarica automatica quando config.ini cambia (es. dalle Impostazioni)
global CONFIG_STAMP := ConfigStamp()
SetTimer WatchConfig, 1500

if FileExist(BASE "\work\reloaded.flag")
{
    try FileDelete(BASE "\work\reloaded.flag")
    ToastShow("Impostazioni applicate", "", 1800)
}


; =========================================================
; DISPATCH
; =========================================================

RegisterKeys()
{
    global KEYS
    for slot, def in DEFAULT_KEYS
    {
        hk := Trim(ReadConfig(slot, def))
        if !ValidHotkey(hk)
            hk := def
        try
            Hotkey("$" hk, Dispatch.Bind(slot), "On")
        catch
        {
            ; AutoHotkey non conosce quel tasto: si usa il predefinito
            hk := def
            try Hotkey("$" hk, Dispatch.Bind(slot), "On")
        }
        KEYS[slot] := hk
    }
}

Dispatch(slot, *)
{
    global busy, ROUTES, ACTIONS, KEYS

    ; Nella pagina delle impostazioni i tasti servono per essere registrati
    try
    {
        if InStr(WinGetTitle("A"), "Impostazioni di AI-Hotkeys")
        {
            SendNative(KEYS[slot])
            return
        }
    }

    if busy
    {
        Flash("Qwen sta ancora lavorando", KeyLabel(KEYS[slot]))
        return
    }

    actionId := ""
    for ctx in GetContexts()
    {
        if ROUTES.Has(ctx "|" slot)
        {
            actionId := ROUTES[ctx "|" slot]
            break
        }
    }

    if (actionId = "" || actionId = "native")
    {
        SendNative(KEYS[slot])
        return
    }

    if !ACTIONS.Has(actionId)
    {
        MsgBox "Azione sconosciuta nel dispatcher: " actionId, "AI-Hotkeys", "Icon!"
        return
    }

    action := ACTIONS[actionId]
    busy := true

    try
    {
        if action.HasOwnProp("special") && action.special = "obsidian_todo"
            RunObsidianTodo(KeyLabel(KEYS[slot]))
        else
            RunSelectionAction(action, KEYS[slot])
    }
    finally
    {
        busy := false
    }
}


GetContexts()
{
    global TODO_TITLE_PREFIX

    contexts := []

    try
    {
        proc  := WinGetProcessName("A")
        title := WinGetTitle("A")
    }
    catch
    {
        proc  := ""
        title := ""
    }

    if (proc = "Obsidian.exe" && InStr(title, TODO_TITLE_PREFIX) = 1)
        contexts.Push("Obsidian:To-Do")

    if (proc != "")
        contexts.Push(proc)

    contexts.Push("*")
    return contexts
}


; =========================================================
; AZIONI SUL TESTO SELEZIONATO
; =========================================================

RunSelectionAction(action, hk)
{
    global inputFile, outputFile, viewer, PYTHON, BASE, EDITABLE_APPS, REPLACE_ENABLED, SHOW_PROGRESS
    global cancelRequested, currentPid, statusFile

    cancelRequested := false
    currentPid := 0

    keyLbl := KeyLabel(hk)

    ; Ricordiamo la finestra di partenza: Qwen può metterci un po'
    ; e nel frattempo potresti cambiare finestra.
    try
    {
        hwnd := WinExist("A")
        proc := WinGetProcessName(hwnd)
    }
    catch
    {
        hwnd := 0
        proc := ""
    }

    savedClipboard := ClipboardAll()

    A_Clipboard := ""
    Send "^c"

    if !ClipWait(2)
    {
        ; Niente selezionato: il tasto fa la sua funzione normale
        ; (PgUp scorre, Home va a inizio riga...)
        A_Clipboard := savedClipboard
        SendNative(hk)
        return
    }

    testo := A_Clipboard
    A_Clipboard := savedClipboard

    ; Salva il testo selezionato in UTF-8
    file := FileOpen(inputFile, "w", "UTF-8-RAW")
    file.Write(testo)
    file.Close()

    if FileExist(outputFile)
        FileDelete(outputFile)

    if SHOW_PROGRESS
        ToastShow(action.doing . "  ·  Esc 2 s = annulla", keyLbl)

    comando := PYTHON ' "' action.script '" "' inputFile '" "' outputFile '"'

    ; Python scrive in work\status.txt a che punto è (ricerca web,
    ; lettura delle pagine, scrittura): lo mostra il riquadro di avanzamento.
    try FileDelete(statusFile)
    ShowStatus("", true)
    statusTimer := ShowStatus.Bind(keyLbl)
    if SHOW_PROGRESS
        SetTimer statusTimer, 250

    ; Avvio cancellabile: tenendo premuto Esc 2 s, CheckEscHold mette
    ; cancelRequested := true e uccide il processo. Così una pressione
    ; per sbaglio non lascia file a metà: si pulisce tutto.
    ; (cancelRequested è già stato azzerato a inizio funzione, così
    ;  Esc tenuto premuto anche durante la copia negli appunti funziona.)
    try
    {
        Run(comando, BASE, "Hide", &currentPid)
    }
    catch as e
    {
        SetTimer statusTimer, 0
        ToastHide()
        currentPid := 0
        MsgBox "Impossibile avviare Python:`n" e.Message, "AI-Hotkeys", "Iconx"
        return
    }

    cancelled := WaitPid(currentPid)
    currentPid := 0

    SetTimer statusTimer, 0
    try FileDelete(statusFile)
    ToastHide()

    if cancelled
    {
        CleanupWorkFiles()
        ToastShow("Annullato", keyLbl, 2000)
        return
    }

    ; Il processo è finito da solo: se Python è uscito in errore
    ; non ha scritto output.txt (stesso controllo di prima, senza exitCode
    ; che con Run non è disponibile).
    if !FileExist(outputFile)
    {
        ; Annullato all'ultimo istante mentre il processo moriva
        if cancelRequested
        {
            CleanupWorkFiles()
            ToastShow("Annullato", keyLbl, 2000)
            return
        }
        MsgBox "Qwen non ha risposto.`nControlla che Ollama sia acceso e che il modello sia scaricato.", "AI-Hotkeys", "Iconx"
        return
    }

    risposta := FileRead(outputFile, "UTF-8")

    if Trim(risposta) = ""
    {
        MsgBox "Qwen ha restituito una risposta vuota.", "AI-Hotkeys", "Icon!"
        return
    }

    ; -----------------------------------------------------
    ; CORREZIONE IN UN'APP DI SCRITTURA → sostituzione diretta
    ; -----------------------------------------------------

    if (REPLACE_ENABLED && action.HasOwnProp("replace") && action.replace
        && EDITABLE_APPS.Has(proc) && hwnd && WinExist("ahk_id " hwnd))
    {
        WinActivate "ahk_id " hwnd
        WinWaitActive "ahk_id " hwnd, , 2

        A_Clipboard := risposta
        ClipWait 1
        Send "^v"
        Sleep 300

        ; Il risultato resta negli appunti
        return
    }

    ; -----------------------------------------------------
    ; TUTTO IL RESTO → pagina dei risultati
    ; -----------------------------------------------------

    Run PYTHON ' "' viewer '" "' inputFile '" "' outputFile '" "' action.name '" ' action.mode ' "--key=' keyLbl '"', BASE, "Hide"
}


; =========================================================
; OBSIDIAN: RIORGANIZZAZIONE DI To-Do List.md
; =========================================================

RunObsidianTodo(keyLbl)
{
    global PYTHON, BASE, cancelRequested, currentPid

    cancelRequested := false
    currentPid := 0

    statusFile := BASE "\work\obsidian_status.txt"

    ; Salva la nota prima di leggerla da disco
    Send "^s"
    Sleep 500

    if FileExist(statusFile)
        FileDelete(statusFile)

    ToastShow("Qwen riorganizza la To-Do List, può volerci qualche minuto  ·  Esc 2 s = annulla", keyLbl)

    comando := PYTHON ' "' BASE '\actions\obsidian_todo.py"'

    try
    {
        Run(comando, BASE, "Hide", &currentPid)
    }
    catch as e
    {
        ToastHide()
        currentPid := 0
        MsgBox "Impossibile avviare Python:`n" e.Message, "AI-Hotkeys", "Iconx"
        return
    }

    cancelled := WaitPid(currentPid)
    currentPid := 0

    ToastHide()

    if cancelled
    {
        ; Il file originale non è stato toccato (la scrittura è atomica
        ; alla fine): basta togliere gli esiti parziali.
        try FileDelete(statusFile)
        try FileDelete(BASE "\work\obsidian_output.txt")
        ToastShow("Annullato", keyLbl, 2000)
        return
    }

    if FileExist(statusFile)
        rawEsito := FileRead(statusFile, "UTF-8")
    else
        rawEsito := ""

    esito := RegExReplace(rawEsito, "^(OK|ERRORE)\R", "")

    if rawEsito = ""
        MsgBox "Nessun esito.", "AI-Hotkeys - To-Do List", "Icon!"
    else if RegExMatch(rawEsito, "^OK\R")
        ToastShow(Trim(esito), keyLbl, 4000)
    else
        MsgBox esito, "AI-Hotkeys - To-Do List", "Icon!"
}


; =========================================================
; ANNULLAMENTO: Esc tenuto premuto 2 s
; =========================================================
; Se premi un tasto per sbaglio, tieni premuto Esc per 2 secondi:
; il processo Python in corso viene ucciso e i file a metà in work\
; vengono cancellati, così la pressione dopo parte pulita.
; La pressione breve di Esc resta normale ("~" non la blocca).

EscDown(*)
{
    global escTracking
    if escTracking
        return              ; auto-ripetizione mentre è tenuto premuto
    escTracking := true
    SetTimer CheckEscHold, -2000
}

EscUp(*)
{
    global escTracking
    escTracking := false
    SetTimer CheckEscHold, 0
}

CheckEscHold()
{
    global escTracking, busy, cancelRequested, currentPid
    escTracking := false
    ; Esc già mollato prima dei 2 secondi: niente da fare
    if !GetKeyState("Esc", "P")
        return
    ; Niente in corso: Esc fa solo la sua funzione normale
    if !busy
        return
    if cancelRequested
        return
    cancelRequested := true
    try
    {
        if currentPid
            ProcessClose(currentPid)
    }
    ; La pulizia vera (file + riquadro) la fa il ciclo in WaitPid
}

; Attende la fine del processo pid. Restituisce true se l'utente ha
; annullato con Esc, false se il processo è finito da solo.
WaitPid(pid)
{
    global cancelRequested
    Loop
    {
        Sleep 80
        if cancelRequested
        {
            try ProcessClose(pid)
            Sleep 250
            try
            {
                if ProcessExist(pid)
                    ProcessClose(pid)
            }
            return true
        }
        try
        {
            if !ProcessExist(pid)
                return false
        }
        catch
        {
            return false
        }
    }
}

; Toglie i file a metà di un'azione annullata, così tutto è pulito.
CleanupWorkFiles()
{
    global BASE
    for f in ["input.txt", "output.txt", "status.txt", "meta.json", "sources.json"]
    {
        try FileDelete(BASE "\work\" f)
    }
}


; =========================================================
; RIQUADRO DI AVANZAMENTO (al posto del ToolTip di Windows)
; =========================================================
; Piccola finestra senza bordi, vicino al mouse, con i colori del tema:
; a sinistra il tasto premuto, a destra cosa sta succedendo.
; Non prende il focus e i clic la attraversano.


ToastShow(text, key := "", ms := 0, anchor := true)
{
    global toastGui, toastPos, THEME

    ToastHide()

    g := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20 +E0x08000000")
    g.BackColor := THEME.bg
    g.MarginX := 12
    g.MarginY := 9

    if (key != "")
    {
        g.SetFont("s10 w400 c" THEME.accent, "Bahnschrift SemiBold")
        g.AddText("x10 y8 h28 +0x200 Center Background" THEME.cap, "  " key "  ")
        g.SetFont("s10 w400 c" THEME.text, "Segoe UI")
        g.AddText("x+10 y8 h28 +0x200", text)
    }
    else
    {
        g.SetFont("s10 w400 c" THEME.text, "Segoe UI")
        g.AddText("x14 y8 h28 +0x200", text)
    }

    ; Angoli arrotondati e bordo sottile (Windows 11; altrove viene ignorato)
    try DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", g.Hwnd, "Int", 33, "Int*", 2, "Int", 4)
    try DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", g.Hwnd, "Int", 34, "UInt*", HexToColorRef(THEME.line), "Int", 4)

    if (anchor || toastPos = "")
    {
        CoordMode "Mouse", "Screen"
        MouseGetPos &mx, &my
        toastPos := [mx + 18, my + 22]
    }

    g.Show("NoActivate AutoSize Hide")
    g.GetPos(, , &w, &h)
    x := toastPos[1], y := toastPos[2]

    ; Dentro lo schermo su cui si trova il mouse
    Loop MonitorGetCount()
    {
        MonitorGetWorkArea(A_Index, &l, &t, &r, &b)
        if (x >= l - 18 && x < r && y >= t - 22 && y < b)
        {
            x := Min(Max(x, l + 8), r - w - 8)
            y := Min(Max(y, t + 8), b - h - 8)
            break
        }
    }

    g.Show("NoActivate x" x " y" y)
    ; Leggermente trasparente: così diventa "layered" e i clic lo attraversano
    try WinSetTransparent(246, g)
    toastGui := g

    if ms
        SetTimer ToastHide, -ms
}

ToastHide()
{
    global toastGui
    SetTimer ToastHide, 0
    if IsSet(toastGui) && toastGui
    {
        try toastGui.Destroy()
        toastGui := 0
    }
}

; Mostra la fase scritta da Python in work\status.txt
ShowStatus(keyLbl, reset := false)
{
    global statusFile
    static last := ""

    if reset
    {
        last := ""
        return
    }

    try
    {
        s := FileExist(statusFile) ? Trim(FileRead(statusFile, "UTF-8")) : ""
    }
    catch
        return

    if (s = "" || s = last)
        return

    last := s
    ToastShow(RTrim(s, ".…") . "  ·  Esc 2 s = annulla", keyLbl, 0, false)
}

; Messaggio breve
Flash(text, key := "", ms := 1800)
{
    ToastShow(text, key, ms)
}

; Colori del riquadro, dal tema scelto nelle impostazioni
LoadTheme()
{
    tema := StrLower(ReadConfig("tema", "scuro"))
    dark := (tema != "chiaro")
    if (tema = "sistema")
    {
        try dark := !RegRead("HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme")
    }

    accents := Map(
        "ambra",    ["F5A623", "A35A00"],
        "ghiaccio", ["62C9F2", "086B96"],
        "menta",    ["52D3A3", "0B7552"],
        "corallo",  ["FF8473", "B23A27"],
        "viola",    ["AC9EFF", "5843C4"],
        "neutro",   ["DCE1E8", "2C3542"]
    )
    c := StrLower(ReadConfig("colore", "ambra"))
    acc := accents.Has(c) ? accents[c] : accents["ambra"]

    if (tema = "nero")
        return {bg: "08090B", text: "E6E8EB", cap: "17191D", line: "262A31", accent: acc[1]}
    if dark
        return {bg: "19202A", text: "E4E8EE", cap: "2A3341", line: "3A4555", accent: acc[1]}
    return {bg: "F8F9FB", text: "141920", cap: "E3E7ED", line: "B8C1CD", accent: acc[2]}
}

HexToColorRef(hex)
{
    ; "RRGGBB" → 0x00BBGGRR
    return Integer("0x" SubStr(hex, 5, 2) SubStr(hex, 3, 2) SubStr(hex, 1, 2))
}


; =========================================================
; TASTI: controllo, nomi leggibili, tasto originale
; =========================================================

ValidHotkey(hk)
{
    if !RegExMatch(hk, "^([\^!+#]*)([A-Za-z0-9]+)$", &m)
        return false
    ; Lettere e numeri da soli servono per scrivere
    if (StrLen(m[2]) = 1 && m[1] = "")
        return false
    return true
}

; "^!r" → "Ctrl+Alt+R", "PgUp" → "PgUp"
KeyLabel(hk)
{
    names := Map("^", "Ctrl", "!", "Alt", "+", "Maiusc", "#", "Win")
    label := ""
    i := 1
    while (i <= StrLen(hk) && InStr("^!+#", SubStr(hk, i, 1)))
    {
        label .= names[SubStr(hk, i, 1)] "+"
        i++
    }
    k := SubStr(hk, i)
    return label (StrLen(k) = 1 ? StrUpper(k) : k)
}

; Invia il tasto come se AI-Hotkeys non ci fosse
SendNative(hk)
{
    i := 1
    while (i <= StrLen(hk) && InStr("^!+#", SubStr(hk, i, 1)))
        i++
    Send SubStr(hk, 1, i - 1) "{" SubStr(hk, i) "}"
}


; =========================================================
; IMPOSTAZIONI E RICARICA AUTOMATICA
; =========================================================

OpenSettings()
{
    global PYTHON, BASE
    try Run(PYTHON ' "' BASE '\settings.py"', BASE, "Hide")
    catch as e
        MsgBox "Impossibile aprire le impostazioni:`n" e.Message, "AI-Hotkeys", "Iconx"
}

ConfigStamp()
{
    global CONFIG
    try return FileGetTime(CONFIG, "M") "|" FileGetSize(CONFIG)
    return ""
}

WatchConfig()
{
    global CONFIG_STAMP, busy
    stamp := ConfigStamp()
    if (stamp = "" || stamp = CONFIG_STAMP)
        return
    if busy
        return          ; si ricarica a lavoro finito
    CONFIG_STAMP := stamp
    try FileAppend("", BASE "\work\reloaded.flag")
    Reload()
}


; =========================================================
; UTILITÀ
; =========================================================

; Python incluso nell'installazione, altrimenti quello di sistema
FindPython()
{
    if FileExist(A_ScriptDir "\python\pythonw.exe")
        return '"' A_ScriptDir '\python\pythonw.exe"'
    return "pythonw"
}

; Legge "chiave = valore" da config.ini (UTF-8)
ReadConfig(key, default := "")
{
    path := A_ScriptDir "\config.ini"
    if !FileExist(path)
        return default
    text := FileRead(path, "UTF-8")
    if RegExMatch(text, "im)^[ \t]*" key "[ \t]*=[ \t]*(.*?)[ \t]*$", &m) && m[1] != ""
        return m[1]
    return default
}

IsNo(value)
{
    return RegExMatch(Trim(value), "i)^(no|false|0|off)$")
}

SetupTrayMenu()
{
    global KEYS
    if FileExist(A_ScriptDir "\icon.ico")
        TraySetIcon A_ScriptDir "\icon.ico"
    A_IconTip := "AI-Hotkeys`n" KeyLabel(KEYS["correggi"]) " corregge, " KeyLabel(KEYS["riassumi"]) " riassume, " KeyLabel(KEYS["spiega"]) " spiega"
    tray := A_TrayMenu
    tray.Delete()
    tray.Add("Impostazioni", (*) => OpenSettings())
    tray.Default := "Impostazioni"
    tray.Add()
    tray.Add("Libera la VRAM", (*) => UnloadModel())
    tray.Add("Apri SearXNG nel browser", (*) => OpenSearxng())
    tray.Add()
    tray.Add("Modifica i prompt", (*) => Run('notepad.exe "' A_ScriptDir '\prompts.py"'))
    tray.Add("Apri config.ini", (*) => Run('notepad.exe "' A_ScriptDir '\config.ini"'))
    tray.Add("Apri la cartella", (*) => Run('explorer.exe "' A_ScriptDir '"'))
    tray.Add()
    tray.Add("Ricarica", (*) => Reload())
    tray.Add("Esci", (*) => ExitApp())
}

; Scarica il modello da Ollama: libera la VRAM senza chiudere AI-Hotkeys.
; Alla pressione successiva di un tasto il modello si ricarica da solo.
UnloadModel()
{
    global PYTHON, BASE

    ToastShow("Libero la VRAM")

    try
        exitCode := RunWait(PYTHON ' "' BASE '\actions\unload.py"', BASE, "Hide")
    catch as e
    {
        ToastHide()
        MsgBox "Impossibile avviare Python:`n" e.Message, "AI-Hotkeys", "Iconx"
        return
    }

    if exitCode = 0
        ToastShow("VRAM libera: il modello si ricarica al prossimo tasto", "", 2600)
    else
        ToastShow("Ollama non risponde: forse non è acceso", "", 2600)
}


; =========================================================
; SearXNG (ricerca web per End)
; =========================================================

SearxngUrl()
{
    return RTrim(ReadConfig("searxng_url", "http://127.0.0.1:8888"), "/")
}

SearxngEnabled()
{
    return !RegExMatch(ReadConfig("web_search", "auto"), "i)^(false|0|no|off)$")
}

; Avvia SearXNG in background (se è già acceso, il lanciatore esce subito)
StartSearxng()
{
    global PYTHON, BASE

    if !SearxngEnabled()
        return
    if !FileExist(BASE "\searxng\avvia_searxng.py") || !DirExist(BASE "\searxng\app\searx")
        return

    try Run(PYTHON ' "' BASE '\searxng\avvia_searxng.py"', BASE, "Hide")
}

; Chiude SearXNG quando si esce da AI-Hotkeys (non con "Ricarica")
StopSearxng(reason, *)
{
    if (reason = "Reload" || reason = "Single")
        return

    pidFile := A_ScriptDir "\work\searxng.pid"
    if !FileExist(pidFile)
        return

    try
    {
        pid := Integer(Trim(FileRead(pidFile)))
        ; Solo se quel numero è ancora un processo Python (il PID può essere stato riusato)
        if InStr(ProcessGetName(pid), "python")
            ProcessClose pid
    }
    try FileDelete(pidFile)
}

OpenSearxng()
{
    StartSearxng()
    Run SearxngUrl()
}

; Map che ignora maiuscole/minuscole nelle chiavi
CIMap(pairs*)
{
    m := Map()
    m.CaseSense := "Off"
    if pairs.Length
        m.Set(pairs*)
    return m
}
