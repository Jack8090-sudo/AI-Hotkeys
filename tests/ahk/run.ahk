#Requires AutoHotkey v2.0
#NoTrayIcon
; =========================================================
;  AI-Hotkeys — AHK unit tests for lib\Util.ahk
; =========================================================
;  Run (GUI-subsystem exe: capture stdout/stderr, see the plan §0.6):
;    ahk\AutoHotkey64.exe /ErrorStdOut tests\ahk\run.ahk
;  Prints one line per assertion and exits with the number of failures.
;  Fixture config files are written to a private folder in A_Temp, never the repo.
;  No hotkeys are registered.

#Include %A_ScriptDir%\..\..\lib\Util.ahk

global failures := 0, passes := 0
global TMP := A_Temp "\aihk-ahk-tests-" ProcessExist() "-" A_TickCount
global REPO := RegExReplace(A_ScriptDir, "\\tests\\ahk$")

DirCreate(TMP)
; Each group runs on its own: an exception fails that group, the others still run
for test in [TestReadConfig, TestIsNo, TestValidHotkey, TestKeyLabel, TestHexToColorRef, TestCIMap]
{
    try
        test()
    catch as e
    {
        failures++
        Out("ERROR  " test.Name ": " e.Message " (" e.What ", line " e.Line ")")
    }
}
try DirDelete(TMP, true)
Out((failures ? "FAILED" : "OK") ": " passes " passed, " failures " failed")
ExitApp(failures)


; ---------------------------------------------------------
; Harness
; ---------------------------------------------------------

Out(text)
{
    FileAppend(text "`n", "*", "UTF-8")
}

Assert(name, actual, expected)
{
    global failures, passes
    if (Type(actual) = Type(expected) || IsNumber(actual) && IsNumber(expected)) && (actual == expected)
    {
        passes++
        Out("ok     " name)
        return true
    }
    failures++
    Out("FAIL   " name ": expected " Show(expected) ", got " Show(actual))
    return false
}

Show(v)
{
    if IsObject(v)
        return "<" Type(v) ">"
    if IsNumber(v) && Type(v) != "String"
        return String(v)
    return '"' StrReplace(StrReplace(StrReplace(v, "`r", "\r"), "`n", "\n"), "`t", "\t") '"'
}

; Writes a fixture file byte-exact: UTF-8 without BOM unless bom = true.
Fixture(name, text, bom := false)
{
    global TMP
    path := TMP "\" name
    f := FileOpen(path, "w", "UTF-8-RAW")
    if bom
    {
        b := Buffer(3)
        NumPut("UChar", 0xEF, "UChar", 0xBB, "UChar", 0xBF, b)
        f.RawWrite(b)
    }
    f.Write(text)
    f.Close()
    return path
}

; Minimal reader for a JSON array of strings: "name": ["a", "b\n", ...]
; Decodes \n \t \" \\ and \uXXXX (the fixture is limited to these escapes).
JsonStringArray(text, name)
{
    out := []
    if !RegExMatch(text, '"' name '"\s*:\s*\[', &m)
        throw Error("JSON array not found: " name)
    pos := m.Pos + m.Len
    Loop
    {
        if RegExMatch(text, '\G\s*\]', , pos)
            return out
        if !RegExMatch(text, '\G\s*,?\s*"((?:[^"\\]|\\.)*)"', &s, pos)
            throw Error("unexpected JSON at offset " pos " in " name)
        out.Push(JsonUnescape(s[1]))
        pos := s.Pos + s.Len
    }
}

JsonUnescape(s)
{
    out := "", i := 1
    while (i <= StrLen(s))
    {
        c := SubStr(s, i, 1)
        if (c != "\")
        {
            out .= c, i++
            continue
        }
        n := SubStr(s, i + 1, 1)
        switch n, true
        {
            case "n": out .= "`n"
            case "t": out .= "`t"
            case '"': out .= '"'
            case "\": out .= "\"
            case "u":
                out .= Chr(Integer("0x" SubStr(s, i + 2, 4)))
                i += 4
            default: throw Error("unsupported JSON escape \" n)
        }
        i += 2
    }
    return out
}


; ---------------------------------------------------------
; ReadConfig (C37, H01)
; ---------------------------------------------------------

TestReadConfig()
{
    global TMP
    missing := TMP "\does-not-exist.ini"
    Assert("ReadConfig missing file -> default", ReadConfig("correggi", "PgUp", "", missing), "PgUp")
    Assert("ReadConfig missing file, no default -> empty", ReadConfig("correggi", , , missing), "")
    Assert("ReadConfig missing file with section -> default", ReadConfig("correggi", "D", "tasti", missing), "D")
    ; Default path is A_ScriptDir\config.ini (here tests\ahk, which has none)
    Assert("ReadConfig default path (no config.ini next to the script) -> default",
        ReadConfig("aihk_no_such_key", "dflt"), "dflt")

    body := "[tasti]|correggi = PgUp|riassumi = ^!r  |spiega=End|vuoto =|tab`t=`tF8`t|"
    for nl, label in Map("`n", "LF", "`r`n", "CRLF", "`r", "CR")
    {
        for bom in [false, true]
        {
            tag := label (bom ? "+BOM" : "")
            p := Fixture("nl-" label "-" bom ".ini", StrReplace(body, "|", nl), bom)
            v := ReadConfig("correggi", "X", "", p)
            Assert("ReadConfig " tag " value", v, "PgUp")
            Assert("ReadConfig " tag " StrLen (H01: no trailing CR)", StrLen(v), 4)
            Assert("ReadConfig " tag " trailing spaces trimmed", ReadConfig("riassumi", "X", "", p), "^!r")
            Assert("ReadConfig " tag " no spaces around =", ReadConfig("spiega", "X", "", p), "End")
            Assert("ReadConfig " tag " empty value -> default", ReadConfig("vuoto", "X", "", p), "X")
            Assert("ReadConfig " tag " tabs around = trimmed", ReadConfig("tab", "X", "", p), "F8")
            Assert("ReadConfig " tag " section-aware", ReadConfig("spiega", "X", "tasti", p), "End")
            Assert("ReadConfig " tag " missing key -> default", ReadConfig("nope", "X", "", p), "X")
        }
    }

    ; BOM with the key on the very first line (no section header before it)
    p := Fixture("bom-first.ini", "correggi = Home`r`n", true)
    Assert("ReadConfig BOM, key on first line", ReadConfig("correggi", "X", "", p), "Home")

    ; Inline comments: ";" preceded by whitespace starts a comment
    p := Fixture("inline.ini", "[tasti]`r`n"
        . "correggi = ^!r `; my key`r`n"
        . "riassumi = PgDn`t;tab comment`r`n"
        . "spiega = `; only a comment`r`n"
        . "[obsidian]`r`n"
        . "window_title = To-Do;List -`r`n"
        . "todo_file = C:\Notes\To-Do List.md `; path`r`n")
    Assert("ReadConfig inline comment after space stripped", ReadConfig("correggi", "X", "tasti", p), "^!r")
    Assert("ReadConfig inline comment after tab stripped", ReadConfig("riassumi", "X", "tasti", p), "PgDn")
    Assert("ReadConfig value that is only a comment -> default", ReadConfig("spiega", "End", "tasti", p), "End")
    Assert("ReadConfig ';' without whitespace before it is kept", ReadConfig("window_title", "X", "obsidian", p), "To-Do;List -")
    Assert("ReadConfig path value with inline comment", ReadConfig("todo_file", "X", "obsidian", p), "C:\Notes\To-Do List.md")

    ; Same key in two sections
    p := Fixture("dup.ini", "; header comment`n"
        . "correggi = BeforeAnySection`n"
        . "[altro]`n"
        . "correggi = F1`n"
        . "[ Tasti ]`n"
        . "; correggi = Commented`n"
        . "correggi = F2`n"
        . "[vuota]`n"
        . "[ultima]`n"
        . "correggi = F3`n")
    Assert("ReadConfig no section -> first match in file (legacy)", ReadConfig("correggi", "X", "", p), "BeforeAnySection")
    Assert("ReadConfig section [altro]", ReadConfig("correggi", "X", "altro", p), "F1")
    Assert("ReadConfig section header with spaces, case-insensitive", ReadConfig("correggi", "X", "tasti", p), "F2")
    Assert("ReadConfig section name case-insensitive", ReadConfig("correggi", "X", "ULTIMA", p), "F3")
    Assert("ReadConfig empty section -> default", ReadConfig("correggi", "X", "vuota", p), "X")
    Assert("ReadConfig missing section -> default", ReadConfig("correggi", "X", "nessuna", p), "X")
    Assert("ReadConfig commented-out line ignored", InStr(ReadConfig("correggi", "X", "tasti", p), "Commented"), 0)

    ; Key matching: literal, case-insensitive, whole name only
    p := Fixture("keys.ini", "[k]`n"
        . "axb = regex-dot-trap`n"
        . "a.b = dotted`n"
        . "c(d = paren`n"
        . "correggi_extra = longer`n"
        . "CORREGGI = Upper`n"
        . "url = http://h/?x=1&y=2`n"
        . "first = `n"
        . "first = second-ignored`n")
    Assert("ReadConfig key with '.' is literal", ReadConfig("a.b", "X", "k", p), "dotted")
    Assert("ReadConfig key with '(' does not break the regex", ReadConfig("c(d", "X", "k", p), "paren")
    Assert("ReadConfig '.*' is not a wildcard", ReadConfig(".*", "X", "k", p), "X")
    Assert("ReadConfig key is case-insensitive, prefix not matched", ReadConfig("correggi", "X", "k", p), "Upper")
    Assert("ReadConfig '=' inside the value kept", ReadConfig("url", "X", "k", p), "http://h/?x=1&y=2")
    Assert("ReadConfig first match wins even if empty (legacy)", ReadConfig("first", "X", "k", p), "X")

    ; Lines before any [section] are outside every section
    p := Fixture("nosection.ini", "correggi = Home`n")
    Assert("ReadConfig key before any section, section given -> default", ReadConfig("correggi", "X", "tasti", p), "X")
}


; ---------------------------------------------------------
; IsNo
; ---------------------------------------------------------

TestIsNo()
{
    for v in ["no", "NO", "No", "false", "FALSE", "0", "off", "Off", " no ", "`tfalse"]
        Assert("IsNo(" Show(v) ") true", !!IsNo(v), true)
    for v in ["si", "sì", "yes", "true", "1", "", "nope", "no no", "o", "offf"]
        Assert("IsNo(" Show(v) ") false", !!IsNo(v), false)
}


; ---------------------------------------------------------
; ValidHotkey: parity with settings.valid_hotkey
; ---------------------------------------------------------

TestValidHotkey()
{
    global REPO
    text := FileRead(REPO "\tests\fixtures\hotkey_vectors.json", "UTF-8")
    valid := JsonStringArray(text, "valid")
    invalid := JsonStringArray(text, "invalid")
    Assert("hotkey vectors: valid list loaded", valid.Length > 10, true)
    Assert("hotkey vectors: invalid list loaded", invalid.Length > 10, true)
    for hk in valid
        Assert("ValidHotkey(" Show(hk) ") true", !!ValidHotkey(hk), true)
    for hk in invalid
        Assert("ValidHotkey(" Show(hk) ") false", !!ValidHotkey(hk), false)
    ; Defaults (I1) must be valid
    for hk in ["PgUp", "PgDn", "End"]
        Assert("ValidHotkey default " hk, !!ValidHotkey(hk), true)
}


; ---------------------------------------------------------
; KeyLabel, HexToColorRef, CIMap
; ---------------------------------------------------------

TestKeyLabel()
{
    cases := [["^!r", "Ctrl+Alt+R"], ["PgUp", "PgUp"], ["+#a", "Shift+Win+A"], ["F8", "F8"],
              ["^Numpad1", "Ctrl+Numpad1"], ["!Tab", "Alt+Tab"], ["^1", "Ctrl+1"], ["", ""]]
    for c in cases
        Assert("KeyLabel(" Show(c[1]) ")", KeyLabel(c[1]), c[2])
}

TestHexToColorRef()
{
    cases := [["3A4555", 0x55453A], ["FFFFFF", 0xFFFFFF], ["000000", 0], ["123456", 0x563412], ["F5A623", 0x23A6F5]]
    for c in cases
        Assert("HexToColorRef(" Show(c[1]) ")", HexToColorRef(c[1]), c[2])
}

TestCIMap()
{
    m := CIMap("Notepad.exe", true, "*|correggi", "rewrite")
    Assert("CIMap is a Map", Type(m), "Map")
    Assert("CIMap CaseSense Off", m.CaseSense, "Off")
    Assert("CIMap count", m.Count, 2)
    Assert("CIMap Has, different case", m.Has("NOTEPAD.EXE"), true)
    Assert("CIMap get, different case", m["*|CORREGGI"], "rewrite")
    Assert("CIMap missing key", m.Has("Code.exe"), false)
    Assert("CIMap() empty", CIMap().Count, 0)
}
