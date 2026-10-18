; =========================================================
;  AI-Hotkeys — pure helpers (no top-level code, no globals)
; =========================================================
;  Included by main.ahk and by tests\ahk\run.ahk:
;      #Include %A_ScriptDir%\lib\Util.ahk
;  Everything here is a function of its arguments (plus the config file
;  it reads), so it can be unit-tested without registering hotkeys.


; Reads "key = value" from config.ini (UTF-8, with or without BOM;
; CRLF, LF or CR line endings).
;   section = ""  → first "key =" line anywhere in the file (legacy behaviour)
;   section = "x" → only lines inside [x] (case-insensitive)
;   path    = ""  → A_ScriptDir "\config.ini" (the same file as main.ahk's CONFIG)
; The key is compared literally (case-insensitive), never spliced into a regex.
; An inline comment (";" preceded by a space or tab) is removed.
; The first matching line wins; an empty value returns the default.
ReadConfig(key, default := "", section := "", path := "")
{
    if (path = "")
        path := A_ScriptDir "\config.ini"
    if !FileExist(path)
        return default
    text := FileRead(path, "UTF-8")
    text := StrReplace(StrReplace(text, "`r`n", "`n"), "`r", "`n")

    inSection := (section = "")
    Loop Parse, text, "`n"
    {
        line := A_LoopField
        if RegExMatch(line, "^[ \t]*\[[ \t]*(.*?)[ \t]*\][ \t]*$", &h)
        {
            if (section != "")
                inSection := (h[1] = section)
            continue
        }
        if !inSection
            continue
        eq := InStr(line, "=")
        if !eq || (Trim(SubStr(line, 1, eq - 1), " `t") != key)
            continue
        value := RegExReplace(SubStr(line, eq + 1), "[ \t];.*$")
        value := Trim(value, " `t`r")
        return (value = "") ? default : value
    }
    return default
}

; True for "no", "false", "0", "off" (any case, surrounding spaces ignored)
IsNo(value)
{
    return RegExMatch(Trim(value), "i)^(no|false|0|off)$")
}

; Same rules as settings.py valid_hotkey (tests\fixtures\hotkey_vectors.json):
;   modifiers ^ ! + # (each at most once) followed by one key name;
;   a single letter or digit needs a modifier (they are for typing);
;   longer names must be in NAMED (case-sensitive), and without a modifier
;   only the SPECIAL ones are allowed.
ValidHotkey(hk)
{
    static SPECIAL := 0, NAMED := 0
    if !SPECIAL
    {
        SPECIAL := Map()
        for k in ["PgUp", "PgDn", "End", "Home", "Ins", "Del", "Pause", "ScrollLock", "AppsKey"]
            SPECIAL[k] := true
        Loop 24
            SPECIAL["F" A_Index] := true
        NAMED := SPECIAL.Clone()
        for k in ["Space", "Tab", "Enter", "Backspace", "Up", "Down", "Left", "Right",
                  "NumpadAdd", "NumpadSub", "NumpadMult", "NumpadDiv", "NumpadDot", "NumpadEnter"]
            NAMED[k] := true
        Loop 10
            NAMED["Numpad" (A_Index - 1)] := true
    }

    if !RegExMatch(hk, "D)^([\^!+#]*)([A-Za-z0-9]+)$", &m)
        return false
    mods := m[1], key := m[2]
    for c in ["^", "!", "+", "#"]
    {
        StrReplace(mods, c, , , &n)
        if (n > 1)
            return false
    }
    if (StrLen(key) = 1)
        return mods != ""
    if !NAMED.Has(key)
        return false
    return mods != "" || SPECIAL.Has(key)
}

; "^!r" → "Ctrl+Alt+R", "PgUp" → "PgUp"
KeyLabel(hk)
{
    names := Map("^", "Ctrl", "!", "Alt", "+", "Shift", "#", "Win")
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

HexToColorRef(hex)
{
    ; "RRGGBB" → 0x00BBGGRR
    return Integer("0x" SubStr(hex, 5, 2) SubStr(hex, 3, 2) SubStr(hex, 1, 2))
}

; Map with case-insensitive keys
CIMap(pairs*)
{
    m := Map()
    m.CaseSense := "Off"
    if pairs.Length
        m.Set(pairs*)
    return m
}


; =========================================================
;  Capture and routing (S8b1)
; =========================================================

; True for the window titles of AI-Hotkeys' own pages, where the hotkeys
; must keep their native function (scrolling, hotkey recording):
;   results page  "<Fix|Summary|Explanation> - AI-Hotkeys - <Browser>"
;                 (static\viewer.html: <title>__TITLE__ - AI-Hotkeys</title>
;                  and document.title = ui.title + " - AI-Hotkeys")
;   settings page "AI-Hotkeys Settings"  (static\settings.html <title>)
; The browser appends its own name, so " - AI-Hotkeys" must be followed by
; " - " or the end of the title. S10 must keep both titles.
IsAppPageTitle(title)
{
    static RESULTS_TITLE_RE := "D)\s-\sAI-Hotkeys(?:\s-\s|$)"
    static SETTINGS_TITLE   := "AI-Hotkeys Settings"
    return RegExMatch(title, RESULTS_TITLE_RE) > 0 || InStr(title, SETTINGS_TITLE) > 0
}

; True for console/terminal window classes: "^c" would interrupt the
; running program there (SIGINT), so the hotkeys stay native.
;   ConsoleWindowClass             conhost (cmd, PowerShell)
;   CASCADIA_HOSTING_WINDOW_CLASS  Windows Terminal
;   mintty                         Git Bash, Cygwin, MSYS2
IsConsoleClass(cls)
{
    static CLASSES := CIMap("ConsoleWindowClass", true, "CASCADIA_HOSTING_WINDOW_CLASS", true, "mintty", true)
    return CLASSES.Has(cls)
}

; [comportamento] clip_wait_ms → milliseconds to wait for "^c" (decision D12).
; Whole numbers from 100 to 10000 are accepted; anything else gives the default.
ParseClipWaitMs(value, default := 2000)
{
    value := Trim(value, " `t`r`n")
    if !RegExMatch(value, "D)^\d{1,5}$")
        return default
    n := Integer(value)
    return (n >= 100 && n <= 10000) ? n : default
}

; True if a re-copy of the selection still matches the text sent to Qwen
; (direct replace, C05). Line endings are ignored; everything else must match.
SelectionMatches(original, recopied)
{
    if (original = "")
        return false
    norm(s) => StrReplace(StrReplace(s, "`r`n", "`n"), "`r", "`n")
    return norm(original) == norm(recopied)
}


; =========================================================
;  Process lifecycle (S8b2)
; =========================================================

; Parses work\searxng.pid (contract K5): "<pid> <creation FILETIME>", or the
; legacy "<pid>". Returns {pid, ctime} (ctime = 0 for the legacy form), or ""
; for anything else. Same rules as avvia_searxng.parse_pid_record.
ParsePidRecord(text)
{
    text := Trim(text, " `t`r`n")
    if !RegExMatch(text, "D)^(\d{1,10})(?:[ \t]+(\d{1,19}))?$", &m)
        return ""
    pid := Integer(m[1])
    if (pid <= 0 || pid > 0xFFFFFFFF)
        return ""
    ctime := 0
    if (m[2] != "")
    {
        ; FILETIME fits in a signed 64-bit integer until the year 30828
        if (StrLen(m[2]) = 19 && StrCompare(m[2], "9223372036854775807") > 0)
            return ""
        ctime := Integer(m[2])
    }
    return {pid: pid, ctime: ctime}
}

; True if exePath is the configured interpreter (pythonExe, unquoted) or its
; python.exe / pythonw.exe sibling (websearch.py starts SearXNG with the
; pythonw.exe next to sys.executable). When pythonExe has no folder (system
; "pythonw"), only the file name can be compared.
IsConfiguredPython(exePath, pythonExe)
{
    if (exePath = "" || pythonExe = "")
        return false
    SplitPath(exePath, &name, &dir)
    if !(name = "python.exe" || name = "pythonw.exe")
        return false
    if !InStr(pythonExe, "\")
        return true
    SplitPath(pythonExe, , &wantDir)
    return (dir = wantDir)
}

; C20: may StopSearxng kill the process named by the pid file?
;   record     ParsePidRecord result ("" = unreadable → never)
;   exePath    ProcessGetPath of record.pid ("" = gone or not accessible → never)
;   ctime      creation FILETIME of record.pid (0 = unknown)
;   pythonExe  the configured interpreter, unquoted
; K5 record: the interpreter must match and the creation time must be equal.
; Legacy record (no creation time): never (SEC1). A reused pid that happens to
; be another python.exe of the same interpreter cannot be told apart, so the
; caller leaves that process running and logs it.
SearxngPidIsOurs(record, exePath, ctime, pythonExe)
{
    if !IsObject(record) || exePath = ""
        return false
    if !IsConfiguredPython(exePath, pythonExe)
        return false
    if !record.ctime
        return false
    return (ctime != 0 && ctime = record.ctime)
}


; =========================================================
;  Error surfacing and UX (S8b3)
; =========================================================

; Line 1 of work\error.txt (contract K1): the user-facing message.
; BOM, surrounding spaces and the detail lines are dropped; at most 200
; characters. "" when there is nothing to show.
ErrorFileLine1(text)
{
    text := LTrim(text, Chr(0xFEFF))
    text := StrReplace(text, "`r", "`n")
    nl := InStr(text, "`n")
    line := Trim(nl ? SubStr(text, 1, nl - 1) : text, " `t")
    return SubStr(line, 1, 200)
}

; work\config_warning.txt (contract K6, one warning per line) → toast text:
; the first maxLines non-empty lines, plus "(+N more)". "" if none.
WarningSummary(text, maxLines := 3)
{
    text := StrReplace(StrReplace(LTrim(text, Chr(0xFEFF)), "`r`n", "`n"), "`r", "`n")
    lines := []
    Loop Parse, text, "`n"
    {
        line := Trim(A_LoopField, " `t")
        if (line != "")
            lines.Push(SubStr(line, 1, 200))
    }
    out := ""
    for i, line in lines
    {
        if (i > maxLines)
        {
            out .= "`n(+" (lines.Length - maxLines) " more)"
            break
        }
        out .= (out = "" ? "" : "`n") line
    }
    return out
}

; Identity of a hotkey for duplicate detection: "!^r" and "^!R" are the
; same key. Modifiers in a fixed order, key name lower-cased.
HotkeyId(hk)
{
    i := 1
    while (i <= StrLen(hk) && InStr("^!+#", SubStr(hk, i, 1)))
        i++
    mods := SubStr(hk, 1, i - 1), out := ""
    for c in ["^", "!", "+", "#"]
        if InStr(mods, c)
            out .= c
    return out StrLower(SubStr(hk, i))
}

; C26: decides which key each slot gets, before anything is registered.
;   wanted   Map slot → the [tasti] value ("" = not set)
;   defaults Map slot → default key (I1)
;   names    Map slot → name for the messages ("Fix", ...)
; Valid keys the user set win over defaults; a key set for two slots goes
; to the first slot (in the order of defaults) and the other one falls back
; to its default. A slot whose default is taken too gets no key ("").
; Returns {keys: Map slot → key or "", warnings: [text, ...]}.
ResolveKeys(wanted, defaults, names)
{
    keys := Map(), owner := Map(), problem := Map(), warnings := []
    ; 1) keys set by the user
    for slot, def in defaults
    {
        raw := wanted.Has(slot) ? Trim(wanted[slot], " `t") : ""
        if (raw = "")
            continue
        if !ValidHotkey(raw)
        {
            problem[slot] := '"' raw '" is not a valid key'
            continue
        }
        id := HotkeyId(raw)
        if owner.Has(id)
        {
            problem[slot] := KeyLabel(raw) " is already used by " names[owner[id]]
            continue
        }
        keys[slot] := raw, owner[id] := slot
    }
    ; 2) defaults for the rest
    for slot, def in defaults
    {
        if keys.Has(slot)
            continue
        id := HotkeyId(def)
        if !owner.Has(id)
        {
            keys[slot] := def, owner[id] := slot
            if problem.Has(slot)
                warnings.Push(names[slot] ": " problem[slot] ", using " KeyLabel(def))
            continue
        }
        keys[slot] := ""
        warnings.Push(names[slot] ": " (problem.Has(slot) ? problem[slot] ", and " : "")
            . KeyLabel(def) " is used by " names[owner[id]] ": no key")
    }
    return {keys: keys, warnings: warnings}
}

; Text for a new prompts_user.py (decision D4): a header, then prompts.py
; with every line commented out. Uncommented names override prompts.py;
; anything left commented keeps coming from prompts.py (prompt_loader).
PromptsUserTemplate(promptsText)
{
    header := "
    (
# AI-Hotkeys — your own prompts (prompts_user.py).
#
# This file is never shipped or overwritten by an update. prompt_loader.py
# uses every name defined here instead of the one in prompts.py; anything
# you do not define keeps coming from prompts.py, so new prompts added by
# an update keep working.
#
# Below is a commented-out copy of prompts.py. To change a prompt, remove
# the '# ' in front of ALL the lines of that assignment (the name, every
# line of the text and the closing quotes), then edit it.
# Note: REWRITE_SYSTEM and the others are built from BASE_RULES inside
# prompts.py. If you change BASE_RULES here, also uncomment the names that
# use it, so they are rebuilt from your version.
#
# If this file has an error, prompts.py is used and a warning is shown
# after the next reload. Delete this file to go back to the standard prompts.
# =========================================================================

    )"
    text := StrReplace(StrReplace(LTrim(promptsText, Chr(0xFEFF)), "`r`n", "`n"), "`r", "`n")
    out := header
    Loop Parse, text, "`n"
        out .= (A_LoopField = "" ? "#" : "# " A_LoopField) "`n"
    return out
}


; ---------------------------------------------------------
; S9: per-run directories work\runs\<id>\ (C32, H04, C18)
; ---------------------------------------------------------
; Same rules as qwen_client.RUN_ID_RE / sweep_stale_runs.

; A new run id: local time (yyyyMMddHHmmss) + 16 random hex digits.
; now = A_Now unless given (tests).
NewRunId(now := "")
{
    if (now = "")
        now := A_Now
    return SubStr(now, 1, 14) "-" Format("{:08x}{:08x}", Random(0, 0xFFFFFFFF), Random(0, 0xFFFFFFFF))
}

; True for a name made by NewRunId: only such folders are ever swept away
IsRunId(name)
{
    return RegExMatch(name, "^\d{14}-[0-9a-f]{16}$") ? true : false
}

; work\runs\<id> (no trailing backslash: it is passed inside quotes to Python)
RunDirOf(workDir, id)
{
    return RTrim(workDir, "\") "\runs\" id
}

; Is a run folder last modified at stamp (yyyyMMddHHmmss) old enough to sweep?
; An unreadable stamp is never stale (nothing is deleted on doubt).
RunIsStale(stamp, now := "", maxAgeS := 3600)
{
    if (now = "")
        now := A_Now
    if !RegExMatch(stamp, "^\d{14}$") || !RegExMatch(now, "^\d{14}$")
        return false
    try
        return DateDiff(now, stamp, "Seconds") >= maxAgeS
    catch
        return false
}

; icacls arguments that give the folder to the current user (plus SYSTEM and
; Administrators, so backups and an elevated uninstaller still work), and the
; arguments that then drop the inherited entries. sid = the user's SID
; ("S-1-5-21-…", see SidFromWhoamiCsv): a SID, unlike DOMAIN\name, cannot be
; broken by localized names, spaces or quotes (SEC1). "" if sid is not one.
WorkAclArgs(dir, sid)
{
    if !IsSid(sid)
        return ""
    perm := ":(OI)(CI)F"
    grant := '"' dir '" /grant:r "*' sid perm '" "*S-1-5-18' perm '" "*S-1-5-32-544' perm '"'
    return {grant: grant, inherit: '"' dir '" /inheritance:r'}
}

; True for a string SID such as S-1-5-21-1004336348-1177238915-682003330-1001
IsSid(sid)
{
    return RegExMatch(sid, "D)^S-1-\d{1,14}(-\d{1,10}){1,15}$") ? true : false
}

; The SID in the output of  whoami /user /fo csv /nh  ("DOMAIN\user","S-1-5-21-…"),
; or "" when there is none. Same parsing as the installer's AihSecureDir.
SidFromWhoamiCsv(text)
{
    if RegExMatch(text, '"(S-1-[0-9-]+)"', &m) && IsSid(m[1])
        return m[1]
    return ""
}


; ---------------------------------------------------------
; SEC1: command-line and deletion guards
; ---------------------------------------------------------

; A label that is safe inside "…" on a command line: double quotes are removed
; (they would end the argument) and so are trailing backslashes (\" escapes the
; closing quote for the Microsoft C runtime that parses Python's argv).
CmdArgSafe(s)
{
    return RTrim(StrReplace(s, '"'), "\")
}

; May a folder with these attributes (FileExist / DirExist / FileGetAttrib
; string) be deleted recursively? Only a real directory: never a reparse point
; ("L": junction or symbolic link), whose target lies somewhere else.
TreeDeletable(attr)
{
    return (InStr(attr, "D") && !InStr(attr, "L")) ? true : false
}

; SearXNG is always on this PC: http(s) to 127.0.0.1 or localhost, any port.
; Anything else in searxng_url is never opened (SEC1).
IsLocalSearxUrl(url)
{
    return RegExMatch(url, "iD)^https?://(127\.0\.0\.1|localhost)(:\d{1,5})?(/[^\s\\]*)?$") ? true : false
}
