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
global WORK_DIR   := BASE "\work"
global viewer     := BASE "\viewer.py"
; Each selection job has its own folder work\runs\<random id>\ (S9): input.txt,
; output.txt, meta.json, sources.json, status.txt and error.txt live there, so a
; late writer (an orphaned job) can never touch a newer job's files. The
; folder is deleted after a replace, an error or a cancel; the results page
; (viewer.py) deletes it once it has loaded it. currentRunDir = the running
; job's folder, "" when none (OnExit removes it).
global currentRunDir := ""
; The running job's status.txt, "" between jobs
global statusFile := ""
; Contract K1: line 1 = the user-facing reason a Python job failed. Jobs write
; it in their run folder; work\error.txt stays for the health check.
global errorFile  := BASE "\work\error.txt"
; Contract K6: config.ini / prompts_user.py warnings, one per line
global configWarningFile := BASE "\work\config_warning.txt"
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
; The job's progress toast, so a short Flash can put it back (C27)
global progressText := ""
global progressKey  := ""
global flashHwnd    := 0
; Startup notices toast, so the health check result can join it
global noticeText  := ""
global noticeUntil := 0
; Incremented by every job: the health check stays quiet once one started
global jobSerial := 0


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
global SLOT_NAMES   := Map("correggi", "Fix", "riassumi", "Summarize", "spiega", "Explain")
; slot → registered key, "" when the slot has no working key (C26)
global KEYS := Map()
global KEY_WARNINGS := []


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
; work\ holds the selected text while a job runs: only this user may read it
SecureWorkDir()
; Leftovers of a crash (run folders older than 1 h) and of older versions
SweepRuns()
LegacyWorkCleanup()
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

; One toast for everything worth saying at startup: "Settings applied",
; keys that could not be used (C26) and config warnings (K6)
StartupNotices()

; Is Ollama running, recent enough, with the model? (H24, in the background)
StartHealthCheck()


; =========================================================
; DISPATCH
; =========================================================

; Invalid and duplicate keys fall back to the default (I2) with a warning;
; KEYS holds what is really registered, "" for a slot without a key (C26)
RegisterKeys()
{
    global KEYS, KEY_WARNINGS
    wanted := Map()
    for slot in DEFAULT_KEYS
        wanted[slot] := ReadConfig(slot, "")
    r := ResolveKeys(wanted, DEFAULT_KEYS, SLOT_NAMES)
    KEY_WARNINGS := r.warnings
    used := Map()
    for slot, hk in r.keys
        if (hk != "")
            used[HotkeyId(hk)] := slot
    for slot, hk in r.keys
    {
        KEYS[slot] := ""
        if (hk = "")
            continue
        try
        {
            Hotkey("$" hk, Dispatch.Bind(slot), "On")
            KEYS[slot] := hk
            continue
        }
        ; AutoHotkey refused the key: try the default if no other slot has it
        def := DEFAULT_KEYS[slot]
        note := SLOT_NAMES[slot] ": AutoHotkey cannot use " KeyLabel(hk)
        if (hk != def && (!used.Has(HotkeyId(def)) || used[HotkeyId(def)] = slot))
        {
            try
            {
                Hotkey("$" def, Dispatch.Bind(slot), "On")
                KEYS[slot] := def
                used[HotkeyId(def)] := slot
                KEY_WARNINGS.Push(note ", using " KeyLabel(def))
                continue
            }
        }
        KEY_WARNINGS.Push(note ": no key")
    }
}

; "PgUp", or "(no key)" for a slot that has none
SlotKeyLabel(slot)
{
    global KEYS
    return (KEYS.Has(slot) && KEYS[slot] != "") ? KeyLabel(KEYS[slot]) : "(no key)"
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
        Flash("Qwen is still working", SlotKeyLabel(slot))
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
    global cancelRequested, currentPid, statusFile, busy, capturing, CLIP_WAIT_S
    global WORK_DIR, currentRunDir

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

    ; A fresh folder for this job (S9): nothing left by an earlier or orphaned
    ; job can be mistaken for this job's input, result or error
    SweepRuns()
    runDir := ""
    Loop 5
    {
        dir := RunDirOf(WORK_DIR, NewRunId())
        if DirExist(dir)
            continue
        try
        {
            DirCreate(dir)
            runDir := dir
        }
        break
    }
    if (runDir = "")
    {
        ShowError("Could not create a work folder in " WORK_DIR "\runs", keyLbl)
        return
    }
    currentRunDir := runDir
    handedOff := false
    try
        handedOff := RunCapturedJob(action, keyLbl, testo, hwnd, proc, runDir)
    finally
    {
        ; The results page owns the folder from now on (it deletes it once
        ; loaded); otherwise no copy of the selection stays on disk (C32)
        statusFile := ""
        currentRunDir := ""
        if !handedOff
            DeleteRunDir(runDir)
    }
}

; Runs Python on the captured text in runDir and shows the outcome.
; Returns true when the results page was started (it then owns runDir).
RunCapturedJob(action, keyLbl, testo, hwnd, proc, runDir)
{
    global PYTHON, BASE, EDITABLE_APPS, REPLACE_ENABLED, SHOW_PROGRESS
    global cancelRequested, currentPid, statusFile, jobSerial

    inputFile  := runDir "\input.txt"
    outputFile := runDir "\output.txt"

    ; Save the selected text as UTF-8
    try
    {
        file := FileOpen(inputFile, "w", "UTF-8-RAW")
        file.Write(testo)
        file.Close()
    }
    catch as e
    {
        ShowError("Could not write " inputFile ": " e.Message, keyLbl)
        return false
    }

    jobSerial++

    if SHOW_PROGRESS
        ProgressShow(action.doing . "  ·  Esc 2 s = cancel", keyLbl)

    ; Python reads input.txt from the run folder and writes output.txt,
    ; meta.json, sources.json, status.txt and error.txt there (S9)
    comando := PYTHON ' "' action.script '" "--run-dir=' runDir '"'

    ; Python writes its progress to status.txt (web search,
    ; reading pages, writing): the progress popup shows it.
    statusFile := runDir "\status.txt"
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
        ProgressEnd()
        currentPid := 0
        ShowError("Could not start Python: " e.Message, keyLbl)
        return false
    }

    cancelled := WaitPid(currentPid)
    currentPid := 0

    SetTimer statusTimer, 0
    ProgressEnd()

    ; Cancelled: the caller deletes the run folder (I5)
    if cancelled
    {
        ToastShow("Cancelled", keyLbl, 2000)
        return false
    }

    ; The process ended on its own: if Python exited with an error
    ; it did not write output.txt, and error.txt in the run folder says why (K1).
    if !FileExist(outputFile)
    {
        ; Cancelled at the last moment while the process was dying
        if cancelRequested
        {
            ToastShow("Cancelled", keyLbl, 2000)
            return false
        }
        msg := ReadErrorLine(runDir "\error.txt")
        if (msg = "")
            msg := "Qwen did not respond. Check that Ollama is running and that the model is downloaded."
        ShowError(msg, keyLbl)
        return false
    }

    try
        risposta := FileRead(outputFile, "UTF-8")
    catch as e
    {
        ShowError("Could not read the result " outputFile ": " e.Message, keyLbl)
        return false
    }

    if Trim(risposta) = ""
    {
        ShowError("Qwen returned an empty response.", keyLbl)
        return false
    }

    ; -----------------------------------------------------
    ; FIX IN A WRITING APP → direct replacement
    ; -----------------------------------------------------

    if (REPLACE_ENABLED && action.HasOwnProp("replace") && action.replace
        && EDITABLE_APPS.Has(proc) && hwnd && WinExist("ahk_id " hwnd))
    {
        why := ReplaceSelection(hwnd, testo, risposta)
        if (why = "")
            return false    ; pasted: the result stays in the clipboard (I15, D10); folder deleted
        ; Not pasted: nothing was overwritten, the result opens in the results page
        ToastShow(why " — opened in the results page", keyLbl, 4000)
    }

    ; -----------------------------------------------------
    ; EVERYTHING ELSE → results page
    ; -----------------------------------------------------

    return OpenResultsPage(action, keyLbl, runDir)
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

; Opens the result in the results page (viewer.py, new --run-dir form of K3).
; The viewer deletes runDir once it has loaded it. Returns true if started.
OpenResultsPage(action, keyLbl, runDir)
{
    global PYTHON, viewer, BASE
    try
    {
        Run(PYTHON ' "' viewer '" "--run-dir=' runDir '" "' action.name '" ' action.mode ' "--key=' CmdArgSafe(keyLbl) '"', BASE, "Hide")
        return true
    }
    catch as e
    {
        ShowError("Could not open the results page: " e.Message, keyLbl)
        return false
    }
}


; =========================================================
; OBSIDIAN: REORGANIZING To-Do List.md
; =========================================================

RunObsidianTodo(keyLbl)
{
    global PYTHON, BASE, cancelRequested, currentPid, busy, jobSerial

    cancelRequested := false
    currentPid := 0
    jobSerial++

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
        ShowError("Could not delete " statusFile " (is another program using it?): " e.Message, keyLbl)
        return
    }

    ProgressShow("Qwen is reorganizing the To-Do List, it may take a few minutes  ·  Esc 2 s = cancel", keyLbl)

    comando := PYTHON ' "' BASE '\actions\obsidian_todo.py"'

    try
    {
        Run(comando, BASE, "Hide", &currentPid)
    }
    catch as e
    {
        ProgressEnd()
        currentPid := 0
        ShowError("Could not start Python: " e.Message, keyLbl)
        return
    }

    cancelled := WaitPid(currentPid)
    currentPid := 0

    ProgressEnd()

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
        ShowError("To-Do List: no result.", keyLbl)
    else if RegExMatch(rawEsito, "^OK\R")
        ToastShow(Trim(esito), keyLbl, 4000)
    else
    {
        ; The checks can list several problems: a dialog, but with the
        ; hotkeys free while it is open (C27)
        busy := false
        MsgBox esito, "AI-Hotkeys - To-Do List", "Icon!"
    }
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

; Deletes a job's run folder (input, result, error...). Only folders inside
; work\runs named like a run id; retried once if a file is briefly locked.
DeleteRunDir(dir)
{
    global WORK_DIR
    SplitPath(dir, &name, &parent)
    if (dir = "" || !IsRunId(name) || parent != WORK_DIR "\runs")
        return
    Loop 2
    {
        try
        {
            if DirExist(dir)
                DeleteRunTree(dir)
            return
        }
        Sleep 200
    }
}

; DirDelete(dir, true), but never through a junction or symbolic link (SEC1):
; neither the run folder nor work\runs may be a reparse point, or the recursive
; delete would empty the folder it points to. Such a link is left alone.
DeleteRunTree(dir)
{
    SplitPath(dir, , &parent)
    if !TreeDeletable(DirExist(dir)) || !TreeDeletable(DirExist(parent))
        return false
    DirDelete(dir, true)
    return true
}

; Deletes run folders not modified for an hour: left by a crash, or by a
; results page that never started. Never the running job's folder.
SweepRuns()
{
    global WORK_DIR, currentRunDir
    Loop Files, WORK_DIR "\runs\*", "D"
    {
        if !IsRunId(A_LoopFileName) || (A_LoopFileFullPath = currentRunDir)
            continue
        try stamp := FileGetTime(A_LoopFileFullPath, "M")
        catch
            continue
        if RunIsStale(stamp)
            try DeleteRunTree(A_LoopFileFullPath)
    }
}

; Versions before S9 kept the selection and the result in work\ itself
LegacyWorkCleanup()
{
    global WORK_DIR
    for f in ["input.txt", "output.txt", "status.txt", "meta.json", "sources.json"]
        try FileDelete(WORK_DIR "\" f)
}

; Best effort: work\ (which holds the selection while a job runs) is
; restricted to the current user (by SID, from whoami as in the installer),
; SYSTEM and Administrators. The inherited entries are removed only after the
; grant succeeded, so a failure never locks the user out. work\acl.done is
; written only once both steps succeeded: a failure is retried at the next
; start (SEC1).
SecureWorkDir()
{
    global WORK_DIR
    marker := WORK_DIR "\acl.done"
    if FileExist(marker)
        return
    a := WorkAclArgs(WORK_DIR, CurrentUserSid())
    if !IsObject(a)
        return
    icacls := A_WinDir "\System32\icacls.exe"
    try
    {
        if RunWait('"' icacls '" ' a.grant, , "Hide") != 0
            return
        if RunWait('"' icacls '" ' a.inherit, , "Hide") != 0
            return
        FileAppend("ok " A_Now "`n", marker, "UTF-8-RAW")
    }
}

; The current user's SID, from  whoami /user /fo csv /nh  ("" if unknown)
CurrentUserSid()
{
    out := A_Temp "\aihk-whoami-" ProcessExist() ".txt"
    whoami := A_WinDir "\System32\whoami.exe"
    sid := ""
    try
    {
        RunWait(A_ComSpec ' /d /c ""' whoami '" /user /fo csv /nh > "' out '""', , "Hide")
        sid := SidFromWhoamiCsv(FileRead(out))
    }
    try FileDelete(out)
    return sid
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

    ; Long or multi-line text (errors, warnings) wraps at a fixed width
    textOpt := (StrLen(text) > 110 || InStr(text, "`n")) ? "w460" : "h28 +0x200"

    if (key != "")
    {
        g.SetFont("s10 w400 c" THEME.accent, "Bahnschrift SemiBold")
        g.AddText("x10 y8 h28 +0x200 Center Background" THEME.cap, "  " key "  ")
        g.SetFont("s10 w400 c" THEME.text, "Segoe UI")
        g.AddText("x+10 y8 " textOpt, text)
    }
    else
    {
        g.SetFont("s10 w400 c" THEME.text, "Segoe UI")
        g.AddText("x14 y8 " textOpt, text)
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

    if (statusFile = "")
        return
    try
    {
        s := FileExist(statusFile) ? Trim(FileRead(statusFile, "UTF-8")) : ""
    }
    catch
        return

    if (s = "" || s = last)
        return

    last := s
    ProgressShow(RTrim(s, ".…") . "  ·  Esc 2 s = cancel", keyLbl, false)
}

; The job's progress toast: remembered, so Flash can put it back
ProgressShow(text, key, anchor := true)
{
    global progressText, progressKey
    progressText := text, progressKey := key
    ToastShow(text, key, 0, anchor)
}

ProgressEnd()
{
    global progressText, progressKey
    progressText := "", progressKey := ""
    ToastHide()
}

; Short message. If a job's progress toast was showing, it comes back
; afterwards (C27)
Flash(text, key := "", ms := 1800)
{
    global toastGui, flashHwnd
    ToastShow(text, key, 0)
    flashHwnd := toastGui ? toastGui.Hwnd : 0
    SetTimer FlashEnd, -ms
}

FlashEnd()
{
    global toastGui, flashHwnd, progressText, progressKey
    ; Something else replaced the flash meanwhile: leave it alone
    if !(toastGui && flashHwnd && toastGui.Hwnd = flashHwnd)
        return
    flashHwnd := 0
    if (progressText != "")
        ToastShow(progressText, progressKey, 0, false)
    else
        ToastHide()
}

; A job failed: non-modal, so the hotkeys keep working while it shows (C27)
ShowError(msg, key := "")
{
    ToastShow(msg, key, Max(8000, 6000 + 40 * StrLen(msg)))
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
    global currentPid, currentRunDir
    if (reason != "Single" && currentPid)
    {
        pid := currentPid
        currentPid := 0
        try ProcessClose(pid)
    }
    ; No copy of the selection stays behind (I5, C32). Also on "Single": a job
    ; that keeps running finds its folder gone and writes nothing (S9).
    if (currentRunDir != "")
    {
        dir := currentRunDir
        currentRunDir := ""
        DeleteRunDir(dir)
    }
    StopSearxng(reason)
}

SetupTrayMenu()
{
    global KEYS
    if FileExist(A_ScriptDir "\icon.ico")
        TraySetIcon A_ScriptDir "\icon.ico"
    A_IconTip := "AI-Hotkeys`n" SlotKeyLabel("correggi") " fixes, " SlotKeyLabel("riassumi") " summarizes, " SlotKeyLabel("spiega") " explains"
    tray := A_TrayMenu
    tray.Delete()
    tray.Add("Settings", (*) => OpenSettings())
    tray.Default := "Settings"
    tray.Add()
    tray.Add("Free VRAM", (*) => UnloadModel())
    tray.Add("Open SearXNG in browser", (*) => OpenSearxng())
    tray.Add()
    tray.Add("Edit prompts", (*) => EditPrompts())
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


; "Edit prompts" (decision D4): your own prompts_user.py, never prompts.py
; (replaced on every update). Created on first use from a commented-out
; copy of prompts.py, so it changes nothing until you uncomment a prompt.
EditPrompts()
{
    global BASE
    userFile := BASE "\prompts_user.py"
    if !FileExist(userFile)
    {
        try
        {
            tpl := PromptsUserTemplate(FileRead(BASE "\prompts.py", "UTF-8"))
            f := FileOpen(userFile, "w", "UTF-8-RAW")
            f.Write(tpl)
            f.Close()
        }
        catch as e
        {
            MsgBox "Could not create " userFile ":`n" e.Message, "AI-Hotkeys", "Iconx"
            return
        }
    }
    try Run('notepad.exe "' userFile '"')
    catch as e
        MsgBox "Could not open " userFile ":`n" e.Message, "AI-Hotkeys", "Iconx"
}

; Line 1 of an error.txt (contract K1), "" if there is none.
; file = "" means work\error.txt (health check); jobs pass their run folder's.
ReadErrorLine(file := "")
{
    global errorFile
    if (file = "")
        file := errorFile
    try
    {
        if FileExist(file)
            return ErrorFileLine1(FileRead(file, "UTF-8"))
    }
    return ""
}

; work\config_warning.txt (contract K6) as toast text, then deleted, so
; each warning is shown once per reload. "" if there is none.
TakeConfigWarnings()
{
    global configWarningFile
    text := ""
    try
    {
        if FileExist(configWarningFile)
            text := WarningSummary(FileRead(configWarningFile, "UTF-8"))
    }
    try FileDelete(configWarningFile)
    return text
}

; Startup toast: "Settings applied", key problems (C26), config warnings (K6)
StartupNotices()
{
    global BASE, KEY_WARNINGS, noticeText, noticeUntil
    lines := []
    reloaded := FileExist(BASE "\work\reloaded.flag")
    if reloaded
    {
        try FileDelete(BASE "\work\reloaded.flag")
        lines.Push("Settings applied")
    }
    for w in KEY_WARNINGS
        lines.Push(w)
    cw := TakeConfigWarnings()
    if (cw != "")
        lines.Push("config.ini: " cw)
    if !lines.Length
        return
    text := ""
    for l in lines
        text .= (text = "" ? "" : "`n") l
    ms := (lines.Length = 1 && reloaded) ? 1800 : 10000
    ShowNotice(text, ms)
}

; A notice toast; one that arrives while the previous is still up joins it
ShowNotice(text, ms)
{
    global noticeText, noticeUntil, busy, capturing
    if (busy || capturing)
        return          ; a job's own toasts have priority
    if (noticeText != "" && A_TickCount < noticeUntil)
    {
        ; The health check rewrites the same config warning: show it once
        joined := noticeText
        Loop Parse, text, "`n"
        {
            if !InStr("`n" noticeText "`n", "`n" A_LoopField "`n", true)
                joined .= "`n" A_LoopField
        }
        if (joined = noticeText)
            return
        text := joined, ms := Max(ms, noticeUntil - A_TickCount)
    }
    noticeText := text, noticeUntil := A_TickCount + ms
    ToastShow(text, "", ms)
}

; Health check (H24): actions\health.py once at startup, in the background.
; Exit code 0 = ready; otherwise work\error.txt line 1 says what to do (K1).
StartHealthCheck()
{
    global PYTHON, BASE, jobSerial
    if !FileExist(BASE "\actions\health.py")
        return
    try
        Run(PYTHON ' "' BASE '\actions\health.py"', BASE, "Hide", &pid)
    catch as e
    {
        ShowNotice("Python could not be started: " e.Message, 10000)
        return
    }
    h := ProcOpen(pid)
    if !h
        return
    poll := HealthPoll.Bind(h, A_TickCount, jobSerial)
    SetTimer poll, 300
}

HealthPoll(h, started, serial)
{
    global jobSerial
    code := ProcExitCode(h)
    timedOut := (A_TickCount - started > 30000)
    if (code = 259 && !timedOut)
        return
    SetTimer , 0            ; stop this timer
    ProcClose(h)
    if (code = 259 || code = -1)
        return              ; still running after 30 s, or unreadable: say nothing
    ; A job started meanwhile: error.txt may be its own, and it reports itself
    if (jobSerial != serial)
        return
    lines := []
    if (code != 0)
    {
        msg := ReadErrorLine()
        lines.Push(msg != "" ? msg : "Ollama check failed: AI-Hotkeys may not work until Ollama runs.")
    }
    cw := TakeConfigWarnings()
    if (cw != "")
        lines.Push("config.ini: " cw)
    if !lines.Length
        return
    text := ""
    for l in lines
        text .= (text = "" ? "" : "`n") l
    ShowNotice(text, 10000)
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
    if !record.ctime
    {
        ; Old pid-file format, without a creation time: the pid may have been
        ; reused, so the process is never closed on its say-so (SEC1).
        LogSearxng("searxng.pid has no creation time (old format): PID " record.pid " (" exePath ") was left running")
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

; One line in work\searxng.log (the launcher's log) and in the debugger output
LogSearxng(msg)
{
    line := FormatTime(, "yyyy-MM-dd HH:mm:ss") " main.ahk: " msg
    OutputDebug(line)
    try FileAppend(line "`n", A_ScriptDir "\work\searxng.log", "UTF-8-RAW")
}

OpenSearxng()
{
    url := SearxngUrl()
    ; Only the local engine is ever opened (SEC1): config.ini cannot turn this
    ; menu item into a launcher for another URL, file or program.
    if !IsLocalSearxUrl(url)
    {
        ShowError("searxng_url in config.ini must be http://127.0.0.1:<port> or http://localhost:<port>: " url, "SearXNG")
        return
    }
    StartSearxng()
    Run url
}
