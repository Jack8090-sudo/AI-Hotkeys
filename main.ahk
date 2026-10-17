#Requires AutoHotkey v2.0
#SingleInstance Force
; A second press of the same key may run while the first one is still
; copying the selection: it is sent natively instead of being dropped (C03).
#MaxThreadsPerHotkey 2

; Pure helpers: ReadConfig, IsNo, ValidHotkey, KeyLabel, HexToColorRef, CIMap, ...
#Include %A_ScriptDir%\lib\Util.ahk
; Process helpers: ProcessCreationTime, ProcessPathOf
#Include %A_ScriptDir%\lib\Proc.ahk

; =========================================================
;  AI-Hotkeys — AutoHotkey → Python → Ollama → Qwen 3.5 9B
; =========================================================
;  Settings: tray icon → Settings
;  (or config.ini). When config.ini changes, the script reloads itself.


; =========================================================
; PATHS
; =========================================================

global BASE       := A_ScriptDir
; PYTHON_EXE = the interpreter (unquoted), PYTHON = the command prefix used
; for every launch. -E ignores PYTHON* variables (PYTHONPATH, PYTHONHOME...),
; -s ignores the user site-packages: the bundled interpreter only loads the
; app's own modules (C28). Under the shipped python313._pth both are already
; implied (S11), so they are redundant there but harmless.
global PYTHON_EXE := FindPython()
global PYTHON     := '"' PYTHON_EXE '" -E -s'
global CONFIG     := BASE "\config.ini"
global inputFile  := BASE "\work\input.txt"
global outputFile := BASE "\work\output.txt"
global viewer     := BASE "\viewer.py"
global statusFile := BASE "\work\status.txt"
; capturing = a key was pressed and "^c" / ClipWait is running: nothing has
;             been captured yet, so further presses keep their native function.
; busy      = text was captured (or the To-Do route started) and a job runs.
global capturing  := false
global busy       := false
; Cancelling by holding Esc: the running job can be
; interrupted by holding Esc for 2 seconds (see EscDown/CheckEscHold).
; cancelRequested = true asks the wait loop to kill Python and clean up.
global cancelRequested := false
global currentPid      := 0
global escTracking     := false
; Progress popup: defined early, before any key or timer
global toastGui   := 0
global toastPos   := ""


; =========================================================
; ACTIONS
; =========================================================
; mode    = how the results page behaves
;           (rewrite = new versions, summarize / explain = questions)
; replace = in EDITABLE_APPS apps the result replaces the selected
;           text (only the fix, and only if enabled in Settings)
; doing   = what the progress popup shows

global ACTIONS := CIMap(
    "rewrite",   {script: BASE "\actions\rewrite.py",   name: "Fix",         mode: "rewrite",   replace: true, doing: "Qwen is fixing the text"},
    "summarize", {script: BASE "\actions\summarize.py", name: "Summary",     mode: "summarize", doing: "Qwen is writing the summary"},
    "explain",   {script: BASE "\actions\explain.py",   name: "Explanation", mode: "explain",   doing: "Qwen is preparing the explanation"},

    ; Special action: reorganizes the whole To-Do List.md file
    "obsidian_todo", {special: "obsidian_todo", name: "Reorganize To-Do List"}
)


; =========================================================
; KEYS (from config.ini, [tasti] section)
; =========================================================
; The three "slots" each have one key; the dispatcher works on
; slots, so changing a key does not require touching the rules below.

global DEFAULT_KEYS := Map("correggi", "PgUp", "riassumi", "PgDn", "spiega", "End")
global KEYS := Map()


; =========================================================
; CENTRAL DISPATCHER:  "context|slot"  →  action
; =========================================================
; Contexts, from most specific to most general:
;   "Obsidian:To-Do"  = Obsidian with To-Do List.md open
;   "Chrome.exe"      = process name (case insensitive)
;   "*"               = any program
;
;   "Console"         = terminal windows (IsConsoleClass): "^c" is never sent there
;
; "native" action = the key keeps its normal function.

global ROUTES := CIMap(
    "Console|correggi", "native",
    "Console|riassumi", "native",
    "Console|spiega",   "native",

    "Obsidian:To-Do|correggi", "obsidian_todo",

    "*|correggi", "rewrite",
    "*|riassumi", "summarize",
    "*|spiega",   "explain"

    ; Examples (remove the ";" and add a comma to the line above):
    ; "Code.exe|spiega",     "native",
    ; "Discord.exe|correggi", "native"
)


; =========================================================
; APPS WHERE THE FIX DIRECTLY REPLACES THE TEXT
; =========================================================
; Only with [comportamento] sostituisci_testo = si.
; Summary and explanation always open in the results page.

global EDITABLE_APPS := CIMap(
    "Notepad.exe",   true,
    "Obsidian.exe",  true,
    "Code.exe",      true,
    "WINWORD.EXE",   true,
    "notepad++.exe", true
)

global REPLACE_ENABLED := !IsNo(ReadConfig("sostituisci_testo", "si"))
global SHOW_PROGRESS   := !IsNo(ReadConfig("avanzamento", "si"))
; How long "^c" may take before "nothing selected" (decision D12).
; Optional [comportamento] clip_wait_ms; 2000 until S3 measures a safe floor.
global CLIP_WAIT_S     := ParseClipWaitMs(ReadConfig("clip_wait_ms", "", "comportamento")) / 1000


; =========================================================
; OBSIDIAN: recognizing To-Do List.md
; =========================================================
; The Obsidian window title is "<note> - <vault> - Obsidian v1.x.x".
; It can be changed in config.ini (window_title = ...)

global TODO_TITLE_PREFIX := ReadConfig("window_title", "To-Do List -")


; =========================================================
; STARTUP
; =========================================================

global THEME := LoadTheme()

DirCreate BASE "\work"
RegisterKeys()
SetupTrayMenu()

; Holding Esc for 2 s = cancels the running job and cleans work\.
; "~" so Esc always keeps its normal function too (short press).
Hotkey("~Esc", EscDown)
Hotkey("~Esc Up", EscUp)

; SearXNG (web search for End) starts together with AI-Hotkeys
StartSearxng()
OnExit(OnExitCleanup)

; Automatic reload when config.ini changes (e.g. from Settings)
global CONFIG_STAMP := ConfigStamp()
SetTimer WatchConfig, 1500

if FileExist(BASE "\work\reloaded.flag")
{
    try FileDelete(BASE "\work\reloaded.flag")
    ToastShow("Settings applied", "", 1800)
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
            ; AutoHotkey does not know that key: fall back to the default
            hk := def
            try Hotkey("$" hk, Dispatch.Bind(slot), "On")
        }
        KEYS[slot] := hk
    }
}

Dispatch(slot, *)
{
    global busy, capturing, ROUTES, ACTIONS, KEYS

    ; Until capturing/busy is set, a second press (#MaxThreadsPerHotkey 2)
    ; must not interrupt this thread and start a second capture
    Critical "On"

    ; AI-Hotkeys' own pages: the results page scrolls with these keys and the
    ; Settings page records them, so they stay native there (C04)
    if IsOwnPageActive()
    {
        SendNative(KEYS[slot])
        return
    }

    ; Another press while the first one is still copying the selection
    ; (e.g. holding PgDn with nothing selected): keep the native key (C03)
    if capturing
    {
        SendNative(KEYS[slot])
        return
    }

    if busy
    {
        Critical "Off"
        Flash("Qwen is still working", KeyLabel(KEYS[slot]))
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
        Critical "Off"
        MsgBox "Unknown action in dispatcher: " actionId, "AI-Hotkeys", "Icon!"
        return
    }

    action := ACTIONS[actionId]

    try
    {
        if action.HasOwnProp("special") && action.special = "obsidian_todo"
        {
            busy := true
            Critical "Off"
            RunObsidianTodo(KeyLabel(KEYS[slot]))
        }
        else
        {
            ; busy becomes true only once the text is captured
            capturing := true
            Critical "Off"
            RunSelectionAction(action, KEYS[slot])
        }
    }
    finally
    {
        capturing := false
        busy := false
    }
}

; True if the active window is the results page or the Settings page.
; Editors are never the browser that shows those pages: a VS Code window
; titled "main.ahk - AI-Hotkeys - Visual Studio Code" (a folder named
; AI-Hotkeys) must keep working.
IsOwnPageActive()
{
    global EDITABLE_APPS
    try
    {
        title := WinGetTitle("A")
        proc  := WinGetProcessName("A")
    }
    catch
        return false
    return IsAppPageTitle(title) && !EDITABLE_APPS.Has(proc)
}


GetContexts()
{
    global TODO_TITLE_PREFIX

    contexts := []

    try
    {
        proc  := WinGetProcessName("A")
        title := WinGetTitle("A")
        cls   := WinGetClass("A")
    }
    catch
    {
        proc  := ""
        title := ""
        cls   := ""
    }

    if IsConsoleClass(cls)
        contexts.Push("Console")

    if (proc = "Obsidian.exe" && InStr(title, TODO_TITLE_PREFIX) = 1)
        contexts.Push("Obsidian:To-Do")

    if (proc != "")
        contexts.Push(proc)

    contexts.Push("*")
    return contexts
}


; =========================================================
; ACTIONS ON THE SELECTED TEXT
; =========================================================

RunSelectionAction(action, hk)
{
    global inputFile, outputFile, viewer, PYTHON, BASE, EDITABLE_APPS, REPLACE_ENABLED, SHOW_PROGRESS
    global cancelRequested, currentPid, statusFile, busy, capturing, CLIP_WAIT_S

    cancelRequested := false
    currentPid := 0

    keyLbl := KeyLabel(hk)

    ; Remember the starting window: Qwen may take a while
    ; and you might switch windows in the meantime.
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

    if !ClipWait(CLIP_WAIT_S)
    {
        ; Nothing selected: the key keeps its normal function
        ; (PgUp scrolls, Home goes to start of line...)
        A_Clipboard := savedClipboard
        capturing := false
        SendNative(hk)
        return
    }

    testo := A_Clipboard
    A_Clipboard := savedClipboard

    ; Text captured: from now on further presses say "still working"
    busy := true
    capturing := false

    ; Save the selected text as UTF-8
    try
    {
        file := FileOpen(inputFile, "w", "UTF-8-RAW")
        file.Write(testo)
        file.Close()
    }
    catch as e
    {
        ShowError("Could not write " inputFile ":`n" e.Message)
        return
    }

    ; A leftover output.txt would be shown as this job's result
    try
    {
        if FileExist(outputFile)
            FileDelete(outputFile)
    }
    catch as e
    {
        ShowError("Could not delete the previous result " outputFile
            . " (is another program using it?):`n" e.Message)
        return
    }

    if SHOW_PROGRESS
        ToastShow(action.doing . "  ·  Esc 2 s = cancel", keyLbl)

    comando := PYTHON ' "' action.script '" "' inputFile '" "' outputFile '"'

    ; Python writes its progress to work\status.txt (web search,
    ; reading pages, writing): the progress popup shows it.
    try FileDelete(statusFile)
    ShowStatus("", true)
    statusTimer := ShowStatus.Bind(keyLbl)
    if SHOW_PROGRESS
        SetTimer statusTimer, 250

    ; Cancellable launch: holding Esc for 2 s makes CheckEscHold set
    ; cancelRequested := true and kill the process. So an accidental
    ; press leaves no half-written files: everything is cleaned up.
    ; (cancelRequested was already reset at the start of this function, so
    ;  holding Esc even while copying to the clipboard works.)
    try
    {
        Run(comando, BASE, "Hide", &currentPid)
    }
    catch as e
    {
        SetTimer statusTimer, 0
        ToastHide()
        currentPid := 0
        ShowError("Could not start Python:`n" e.Message)
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
        ToastShow("Cancelled", keyLbl, 2000)
        return
    }

    ; The process ended on its own: if Python exited with an error
    ; it did not write output.txt (same check as before, without exitCode
    ; which is not available with Run).
    if !FileExist(outputFile)
    {
        ; Cancelled at the last moment while the process was dying
        if cancelRequested
        {
            CleanupWorkFiles()
            ToastShow("Cancelled", keyLbl, 2000)
            return
        }
        MsgBox "Qwen did not respond.`nCheck that Ollama is running and that the model is downloaded.", "AI-Hotkeys", "Iconx"
        return
    }

    try
        risposta := FileRead(outputFile, "UTF-8")
    catch as e
    {
        ShowError("Could not read the result " outputFile ":`n" e.Message)
        return
    }

    if Trim(risposta) = ""
    {
        MsgBox "Qwen returned an empty response.", "AI-Hotkeys", "Icon!"
        return
    }

    ; -----------------------------------------------------
    ; FIX IN A WRITING APP → direct replacement
    ; -----------------------------------------------------

    if (REPLACE_ENABLED && action.HasOwnProp("replace") && action.replace
        && EDITABLE_APPS.Has(proc) && hwnd && WinExist("ahk_id " hwnd))
    {
        why := ReplaceSelection(hwnd, testo, risposta)
        if (why = "")
            return          ; pasted: the result stays in the clipboard (I15, D10)
        ; Not pasted: nothing was overwritten, the result opens in the results page
        ToastShow(why " — opened in the results page", keyLbl, 4000)
    }

    ; -----------------------------------------------------
    ; EVERYTHING ELSE → results page
    ; -----------------------------------------------------

    OpenResultsPage(action, keyLbl)
}

; Direct replace (C05). Pastes risposta over the selection only if the
; starting window is active again and its selection is still the text that
; was sent to Qwen. Returns "" when pasted, otherwise the reason it did not.
ReplaceSelection(hwnd, original, risposta)
{
    global CLIP_WAIT_S

    win := "ahk_id " hwnd
    try WinActivate(win)
    if !WinWaitActive(win, , 2)
        return "The window did not come back to the front"

    ; Re-copy the selection: the user may have changed it while Qwen worked
    savedClipboard := ClipboardAll()
    A_Clipboard := ""
    Send "^c"
    recopied := ClipWait(CLIP_WAIT_S) ? A_Clipboard : ""
    if !SelectionMatches(original, recopied)
    {
        A_Clipboard := savedClipboard
        return "The selection changed"
    }
    if !WinActive(win)
    {
        A_Clipboard := savedClipboard
        return "The window lost focus"
    }

    A_Clipboard := risposta
    ClipWait 1
    Send "^v"
    ; C41: fixed sleep kept until S3 measures a safe floor
    Sleep 300
    return ""
}

; Opens the result in the results page (viewer.py, contract K3)
OpenResultsPage(action, keyLbl)
{
    global PYTHON, viewer, inputFile, outputFile, BASE
    try Run(PYTHON ' "' viewer '" "' inputFile '" "' outputFile '" "' action.name '" ' action.mode ' "--key=' keyLbl '"', BASE, "Hide")
    catch as e
        ShowError("Could not open the results page:`n" e.Message)
}


; =========================================================
; OBSIDIAN: REORGANIZING To-Do List.md
; =========================================================

RunObsidianTodo(keyLbl)
{
    global PYTHON, BASE, cancelRequested, currentPid

    cancelRequested := false
    currentPid := 0

    statusFile := BASE "\work\obsidian_status.txt"

    ; Save the note before reading it from disk
    ; (C41: fixed sleep kept until S3 measures the save time)
    Send "^s"
    Sleep 500

    ; A leftover status file would be read as this run's result
    try
    {
        if FileExist(statusFile)
            FileDelete(statusFile)
    }
    catch as e
    {
        ShowError("Could not delete " statusFile " (is another program using it?):`n" e.Message)
        return
    }

    ToastShow("Qwen is reorganizing the To-Do List, it may take a few minutes  ·  Esc 2 s = cancel", keyLbl)

    comando := PYTHON ' "' BASE '\actions\obsidian_todo.py"'

    try
    {
        Run(comando, BASE, "Hide", &currentPid)
    }
    catch as e
    {
        ToastHide()
        currentPid := 0
        ShowError("Could not start Python:`n" e.Message)
        return
    }

    cancelled := WaitPid(currentPid)
    currentPid := 0

    ToastHide()

    if cancelled
    {
        ; The original file was not touched (writing is atomic
        ; at the end): just remove the partial results.
        try FileDelete(statusFile)
        try FileDelete(BASE "\work\obsidian_output.txt")
        ToastShow("Cancelled", keyLbl, 2000)
        return
    }

    rawEsito := ""
    try
    {
        if FileExist(statusFile)
            rawEsito := FileRead(statusFile, "UTF-8")
    }

    esito := RegExReplace(rawEsito, "^(OK|ERRORE)\R", "")

    if rawEsito = ""
        MsgBox "No result.", "AI-Hotkeys - To-Do List", "Icon!"
    else if RegExMatch(rawEsito, "^OK\R")
        ToastShow(Trim(esito), keyLbl, 4000)
    else
        MsgBox esito, "AI-Hotkeys - To-Do List", "Icon!"
}


; =========================================================
; CANCELLATION: holding Esc for 2 s
; =========================================================
; If you press a key by mistake, hold Esc for 2 seconds:
; the running Python process is killed and the half-written files in work\
; are deleted, so the next press starts clean.
; A short Esc press stays normal ("~" does not block it).

EscDown(*)
{
    global escTracking
    if escTracking
        return              ; auto-repeat while held down
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
    global escTracking, busy, capturing, cancelRequested, currentPid
    escTracking := false
    ; Esc already released before 2 seconds: nothing to do
    if !GetKeyState("Esc", "P")
        return
    ; Nothing running: Esc just keeps its normal function.
    ; While capturing, the request is kept and WaitPid acts on it at once.
    if !(busy || capturing)
        return
    if cancelRequested
        return
    cancelRequested := true
    try
    {
        if currentPid
            ProcessClose(currentPid)
    }
    ; The actual cleanup (files + popup) is done by the loop in WaitPid
}

; Waits for the pid process to end. Returns true if the user
; cancelled with Esc, false if the process ended on its own.
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

; Removes the half-written files of a cancelled action, so all is clean.
CleanupWorkFiles()
{
    global BASE
    for f in ["input.txt", "output.txt", "status.txt", "meta.json", "sources.json"]
    {
        try FileDelete(BASE "\work\" f)
    }
}


; =========================================================
; PROGRESS POPUP (instead of the Windows ToolTip)
; =========================================================
; Small borderless window, near the mouse, with the theme colors:
; the pressed key on the left, what is happening on the right.
; It never takes focus and clicks pass through it.


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

    ; Rounded corners and thin border (Windows 11; ignored elsewhere)
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

    ; Inside the screen where the mouse is
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
    ; Slightly transparent: this makes it "layered" so clicks pass through
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

; Shows the phase written by Python in work\status.txt
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
    ToastShow(RTrim(s, ".…") . "  ·  Esc 2 s = cancel", keyLbl, 0, false)
}

; Short message
Flash(text, key := "", ms := 1800)
{
    ToastShow(text, key, ms)
}

; Popup colors, from the theme chosen in Settings
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


; =========================================================
; KEYS: native key (validation and labels are in lib\Util.ahk)
; =========================================================

; Sends the key as if AI-Hotkeys was not there
SendNative(hk)
{
    i := 1
    while (i <= StrLen(hk) && InStr("^!+#", SubStr(hk, i, 1)))
        i++
    Send SubStr(hk, 1, i - 1) "{" SubStr(hk, i) "}"
}


; =========================================================
; SETTINGS AND AUTOMATIC RELOAD
; =========================================================

OpenSettings()
{
    global PYTHON, BASE
    try Run(PYTHON ' "' BASE '\settings.py"', BASE, "Hide")
    catch as e
        MsgBox "Could not open Settings:`n" e.Message, "AI-Hotkeys", "Iconx"
}

ConfigStamp()
{
    global CONFIG
    try return FileGetTime(CONFIG, "M") "|" FileGetSize(CONFIG)
    return ""
}

WatchConfig()
{
    global CONFIG_STAMP, busy, capturing
    stamp := ConfigStamp()
    if (stamp = "" || stamp = CONFIG_STAMP)
        return
    if (busy || capturing)
        return          ; reloads when the job is done
    CONFIG_STAMP := stamp
    try FileAppend("", BASE "\work\reloaded.flag")
    Reload()
}


; =========================================================
; UTILITIES
; =========================================================

; Bundled Python if present, otherwise the system one (unquoted)
FindPython()
{
    if FileExist(A_ScriptDir "\python\pythonw.exe")
        return A_ScriptDir "\python\pythonw.exe"
    return "pythonw"
}

; Error from a job. Modal for now; S8b3 turns it into a non-modal toast.
ShowError(msg)
{
    MsgBox msg, "AI-Hotkeys", "Iconx"
}

; Tray Reload / Exit while a job runs: ask first, the job will be cancelled
ConfirmIfBusy(what)
{
    global busy
    if !busy
        return true
    return MsgBox("Qwen is still working. " what " anyway? The running job will be cancelled.",
        "AI-Hotkeys", "YesNo Icon? Default2") = "Yes"
}

; OnExit: cancel the running job, then stop SearXNG (C18).
; Not on "Single" (#SingleInstance Force replaced this instance): the new
; instance owns the cleanup, as the plan decided for S8b2.
OnExitCleanup(reason, *)
{
    global currentPid
    if (reason != "Single" && currentPid)
    {
        pid := currentPid
        currentPid := 0
        try ProcessClose(pid)
        ; No half-written files for the next run
        CleanupWorkFiles()
    }
    StopSearxng(reason)
}

SetupTrayMenu()
{
    global KEYS
    if FileExist(A_ScriptDir "\icon.ico")
        TraySetIcon A_ScriptDir "\icon.ico"
    A_IconTip := "AI-Hotkeys`n" KeyLabel(KEYS["correggi"]) " fixes, " KeyLabel(KEYS["riassumi"]) " summarizes, " KeyLabel(KEYS["spiega"]) " explains"
    tray := A_TrayMenu
    tray.Delete()
    tray.Add("Settings", (*) => OpenSettings())
    tray.Default := "Settings"
    tray.Add()
    tray.Add("Free VRAM", (*) => UnloadModel())
    tray.Add("Open SearXNG in browser", (*) => OpenSearxng())
    tray.Add()
    tray.Add("Edit prompts", (*) => Run('notepad.exe "' A_ScriptDir '\prompts.py"'))
    tray.Add("Open config.ini", (*) => Run('notepad.exe "' A_ScriptDir '\config.ini"'))
    tray.Add("Open folder", (*) => Run('explorer.exe "' A_ScriptDir '"'))
    tray.Add()
    tray.Add("Reload", (*) => ConfirmIfBusy("Reload") && Reload())
    tray.Add("Exit", (*) => ConfirmIfBusy("Exit") && ExitApp())
}

; Unloads the model from Ollama: frees the VRAM without closing AI-Hotkeys.
; On the next key press the model reloads by itself.
UnloadModel()
{
    global PYTHON, BASE

    ToastShow("Freeing VRAM")

    try
        exitCode := RunWait(PYTHON ' "' BASE '\actions\unload.py"', BASE, "Hide")
    catch as e
    {
        ToastHide()
        MsgBox "Could not start Python:`n" e.Message, "AI-Hotkeys", "Iconx"
        return
    }

    if exitCode = 0
        ToastShow("VRAM freed: the model reloads on the next key", "", 2600)
    else
        ToastShow("Ollama is not responding: it may not be running", "", 2600)
}


; =========================================================
; SearXNG (web search for End)
; =========================================================

SearxngUrl()
{
    return RTrim(ReadConfig("searxng_url", "http://127.0.0.1:8888"), "/")
}

SearxngEnabled()
{
    return !RegExMatch(ReadConfig("web_search", "auto"), "i)^(false|0|no|off)$")
}

; Starts SearXNG in the background (if already running, the launcher exits at once)
StartSearxng()
{
    global PYTHON, BASE

    if !SearxngEnabled()
        return
    if !FileExist(BASE "\searxng\avvia_searxng.py") || !DirExist(BASE "\searxng\app\searx")
        return

    try Run(PYTHON ' "' BASE '\searxng\avvia_searxng.py"', BASE, "Hide")
}

; Closes SearXNG when exiting AI-Hotkeys (not on "Reload")
; The pid file (contract K5) is trusted only if the process is still our
; interpreter and, for the K5 form, was created at the recorded time: a pid
; reused by another program is never killed (C20).
StopSearxng(reason, *)
{
    global PYTHON_EXE
    if (reason = "Reload" || reason = "Single")
        return

    pidFile := A_ScriptDir "\work\searxng.pid"
    if !FileExist(pidFile)
        return

    try
        record := ParsePidRecord(FileRead(pidFile))
    catch
        return
    if !IsObject(record)
    {
        try FileDelete(pidFile)         ; unreadable: stale
        return
    }

    exePath := ProcessPathOf(record.pid)
    if (exePath = "")
    {
        if !ProcessExist(record.pid)
            try FileDelete(pidFile)     ; process gone: stale
        return
    }
    if SearxngPidIsOurs(record, exePath, ProcessCreationTime(record.pid), PYTHON_EXE)
    {
        try ProcessClose(record.pid)
        try FileDelete(pidFile)
    }
    ; Otherwise the pid now belongs to someone else (or cannot be verified):
    ; leave both alone. The launcher removes its own pid file on a clean exit.
}

OpenSearxng()
{
    StartSearxng()
    Run SearxngUrl()
}
