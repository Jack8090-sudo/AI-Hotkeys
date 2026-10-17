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
#Include %A_ScriptDir%\..\..\lib\Proc.ahk

global failures := 0, passes := 0
global TMP := A_Temp "\aihk-ahk-tests-" ProcessExist() "-" A_TickCount
global REPO := RegExReplace(A_ScriptDir, "\\tests\\ahk$")

DirCreate(TMP)
; Each group runs on its own: an exception fails that group, the others still run
for test in [TestReadConfig, TestIsNo, TestValidHotkey, TestKeyLabel, TestHexToColorRef, TestCIMap,
             TestIsAppPageTitle, TestIsConsoleClass, TestParseClipWaitMs, TestSelectionMatches,
             TestParsePidRecord, TestIsConfiguredPython, TestSearxngPidIsOurs, TestProcHelpers]
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


; ---------------------------------------------------------
; S8b1: own-page titles (C04), consoles (C03), ClipWait (D12), re-copy (C05)
; ---------------------------------------------------------

TestIsAppPageTitle()
{
    yes := ["Fix - AI-Hotkeys - Google Chrome", "Summary - AI-Hotkeys - Personal - Microsoft Edge",
            "Explanation - AI-Hotkeys - Mozilla Firefox", "Fix - AI-Hotkeys", "Fix - AI-Hotkeys - ",
            "AI-Hotkeys Settings", "AI-Hotkeys Settings - Google Chrome", "ai-hotkeys settings - Brave",
            "Riassunto - AI-Hotkeys - Opera"]
    no := ["", "AI-Hotkeys", "AI-Hotkeys - Google Chrome", "Fix - AI-Hotkeys2 - Chrome",
           "Fix - AI-HotkeysX", "Fix -AI-Hotkeys - Chrome", "My AI-Hotkeys notes - Notepad",
           "Fix - ai-hotkeys - Chrome", "C:\AI-Hotkeys", "Fix - AI-Hotkeys-dev - Chrome"]
    for t in yes
        Assert("IsAppPageTitle(" Show(t) ") true", !!IsAppPageTitle(t), true)
    for t in no
        Assert("IsAppPageTitle(" Show(t) ") false", !!IsAppPageTitle(t), false)
}

TestIsConsoleClass()
{
    for c in ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "consolewindowclass"]
        Assert("IsConsoleClass(" Show(c) ") true", !!IsConsoleClass(c), true)
    for c in ["", "Notepad", "Chrome_WidgetWin_1", "MozillaWindowClass", "OpusApp", "Console", "minttyx"]
        Assert("IsConsoleClass(" Show(c) ") false", !!IsConsoleClass(c), false)
}

TestParseClipWaitMs()
{
    cases := [["", 2000], ["500", 500], [" 300 ", 300], ["300`r", 300], ["100", 100], ["10000", 10000],
              ["99", 2000], ["0", 2000], ["10001", 2000], ["-5", 2000], ["0.5", 2000], ["abc", 2000],
              ["500ms", 2000], ["123456", 2000], ["0300", 300]]
    for c in cases
        Assert("ParseClipWaitMs(" Show(c[1]) ")", ParseClipWaitMs(c[1]), c[2])
    Assert("ParseClipWaitMs custom default", ParseClipWaitMs("x", 750), 750)
}

TestSelectionMatches()
{
    Assert("SelectionMatches identical", !!SelectionMatches("ciao mondo", "ciao mondo"), true)
    Assert("SelectionMatches CRLF vs LF", !!SelectionMatches("a`r`nb", "a`nb"), true)
    Assert("SelectionMatches CR vs LF", !!SelectionMatches("a`rb", "a`nb"), true)
    Assert("SelectionMatches different text", !!SelectionMatches("ciao", "ciao!"), false)
    Assert("SelectionMatches case differs", !!SelectionMatches("Ciao", "ciao"), false)
    Assert("SelectionMatches recopy empty", !!SelectionMatches("ciao", ""), false)
    Assert("SelectionMatches original empty", !!SelectionMatches("", ""), false)
    Assert("SelectionMatches whole line copied instead", !!SelectionMatches("word", "a word here`r`n"), false)
}


; ---------------------------------------------------------
; S8b2: SearXNG pid file (K5, C20) and process helpers
; ---------------------------------------------------------

TestParsePidRecord()
{
    r := ParsePidRecord("1234 133700000000000000")
    Assert("ParsePidRecord K5 pid", r.pid, 1234)
    Assert("ParsePidRecord K5 ctime", r.ctime, 133700000000000000)
    r := ParsePidRecord("  42`t133700000000000001`r`n")
    Assert("ParsePidRecord tab and CRLF pid", r.pid, 42)
    Assert("ParsePidRecord tab and CRLF ctime", r.ctime, 133700000000000001)
    r := ParsePidRecord("5678`n")
    Assert("ParsePidRecord legacy pid", r.pid, 5678)
    Assert("ParsePidRecord legacy ctime = 0", r.ctime, 0)
    r := ParsePidRecord("7 9223372036854775807")
    Assert("ParsePidRecord max Int64 ctime", r.ctime, 9223372036854775807)
    for bad in ["", "   ", "0", "0 123", "-5", "12 -3", "abc", "12 abc", "12 34 56", "12,34", "1.5",
                "12345678901", "7 9223372036854775808", "7 99999999999999999999", "４２"]
        Assert("ParsePidRecord(" Show(bad) ") rejected", ParsePidRecord(bad), "")
}

TestIsConfiguredPython()
{
    exe := "C:\Program Files\AI-Hotkeys\python\pythonw.exe"
    Assert("IsConfiguredPython same path", !!IsConfiguredPython(exe, exe), true)
    Assert("IsConfiguredPython case-insensitive", !!IsConfiguredPython("c:\program files\ai-hotkeys\PYTHON\PythonW.EXE", exe), true)
    Assert("IsConfiguredPython python.exe sibling", !!IsConfiguredPython("C:\Program Files\AI-Hotkeys\python\python.exe", exe), true)
    Assert("IsConfiguredPython other folder", !!IsConfiguredPython("C:\Python313\pythonw.exe", exe), false)
    Assert("IsConfiguredPython subfolder", !!IsConfiguredPython("C:\Program Files\AI-Hotkeys\python\x\pythonw.exe", exe), false)
    Assert("IsConfiguredPython other exe same folder", !!IsConfiguredPython("C:\Program Files\AI-Hotkeys\python\notepad.exe", exe), false)
    Assert("IsConfiguredPython lookalike name", !!IsConfiguredPython("C:\Program Files\AI-Hotkeys\python\pythonw.exe.exe", exe), false)
    Assert("IsConfiguredPython empty path", !!IsConfiguredPython("", exe), false)
    Assert("IsConfiguredPython system pythonw: name only", !!IsConfiguredPython("C:\Python313\pythonw.exe", "pythonw"), true)
    Assert("IsConfiguredPython system pythonw: other exe", !!IsConfiguredPython("C:\Windows\notepad.exe", "pythonw"), false)
}

TestSearxngPidIsOurs()
{
    exe := "C:\AI-Hotkeys\python\pythonw.exe"
    k5 := {pid: 100, ctime: 133700000000000000}
    legacy := {pid: 100, ctime: 0}
    Assert("SearxngPidIsOurs K5 match", !!SearxngPidIsOurs(k5, exe, 133700000000000000, exe), true)
    Assert("SearxngPidIsOurs K5 ctime differs (pid reused)", !!SearxngPidIsOurs(k5, exe, 133700000000000001, exe), false)
    Assert("SearxngPidIsOurs K5 ctime unknown", !!SearxngPidIsOurs(k5, exe, 0, exe), false)
    Assert("SearxngPidIsOurs K5 other python", !!SearxngPidIsOurs(k5, "C:\Python313\python.exe", 133700000000000000, exe), false)
    Assert("SearxngPidIsOurs K5 unrelated exe", !!SearxngPidIsOurs(k5, "C:\Windows\explorer.exe", 133700000000000000, exe), false)
    Assert("SearxngPidIsOurs process gone", !!SearxngPidIsOurs(k5, "", 0, exe), false)
    Assert("SearxngPidIsOurs legacy, path matches", !!SearxngPidIsOurs(legacy, exe, 133700000000000000, exe), true)
    Assert("SearxngPidIsOurs legacy, unrelated python", !!SearxngPidIsOurs(legacy, "C:\Python313\python.exe", 1, exe), false)
    Assert("SearxngPidIsOurs legacy, system pythonw (no path to match)", !!SearxngPidIsOurs(legacy, "C:\Python313\pythonw.exe", 1, "pythonw"), false)
    Assert("SearxngPidIsOurs K5, system pythonw, ctime matches", !!SearxngPidIsOurs(k5, "C:\Python313\pythonw.exe", 133700000000000000, "pythonw"), true)
    Assert("SearxngPidIsOurs unreadable record", !!SearxngPidIsOurs("", exe, 1, exe), false)
}

TestProcHelpers()
{
    me := ProcessExist()
    Assert("ProcessCreationTime(self) > 0", ProcessCreationTime(me) > 0, true)
    Assert("ProcessCreationTime(self) stable", ProcessCreationTime(me) = ProcessCreationTime(me), true)
    ; FILETIME of a process started this century: after 2000-01-01 (125911584000000000)
    Assert("ProcessCreationTime(self) plausible FILETIME", ProcessCreationTime(me) > 125911584000000000, true)
    Assert("ProcessCreationTime(0) = 0", ProcessCreationTime(0), 0)
    Assert("ProcessPathOf(self) = A_AhkPath", ProcessPathOf(me) = A_AhkPath, true)
    Assert("ProcessPathOf(0) empty", ProcessPathOf(0), "")
    ; A short-lived child: once it has ended, both helpers report "gone"
    Run(A_ComSpec " /c exit 0", , "Hide", &pid)
    ProcessWaitClose(pid, 10)
    Assert("ProcessCreationTime(ended child) = 0", ProcessCreationTime(pid), 0)
    Assert("ProcessPathOf(ended child) empty", ProcessPathOf(pid), "")
    ; The pid-file check end to end on this very process
    rec := ParsePidRecord(me " " ProcessCreationTime(me))
    Assert("K5 record of self verifies against A_AhkPath",
        !!(rec.ctime = ProcessCreationTime(me) && ProcessPathOf(rec.pid) = A_AhkPath), true)
}
