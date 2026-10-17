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
