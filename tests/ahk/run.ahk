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
             TestParsePidRecord, TestIsConfiguredPython, TestSearxngPidIsOurs, TestProcHelpers,
             TestErrorFileLine1, TestWarningSummary, TestHotkeyId, TestResolveKeys,
             TestPromptsUserTemplate, TestProcExitCode,
             TestNewRunId, TestIsRunId, TestRunDirOf, TestRunIsStale, TestWorkAclArgs,
             TestSid, TestCmdArgSafe, TestTreeDeletable, TestIsLocalSearxUrl]
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
    Assert("SearxngPidIsOurs legacy, path matches: still never (SEC1)", !!SearxngPidIsOurs(legacy, exe, 133700000000000000, exe), false)
    Assert("SearxngPidIsOurs legacy, path matches, ctime unknown", !!SearxngPidIsOurs(legacy, exe, 0, exe), false)
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


; ---------------------------------------------------------
; S8b3: error file (K1), config warnings (K6), keys (C26), prompts (D4)
; ---------------------------------------------------------

TestErrorFileLine1()
{
    Assert("ErrorFileLine1 LF", ErrorFileLine1("Ollama is not running: start Ollama.`ndetail`n"), "Ollama is not running: start Ollama.")
    Assert("ErrorFileLine1 CRLF", ErrorFileLine1("msg`r`ndetail"), "msg")
    Assert("ErrorFileLine1 BOM + spaces", ErrorFileLine1(Chr(0xFEFF) "  msg  `n"), "msg")
    Assert("ErrorFileLine1 keeps inner double space", ErrorFileLine1("run  ollama pull x`n"), "run  ollama pull x")
    Assert("ErrorFileLine1 no newline", ErrorFileLine1("only"), "only")
    Assert("ErrorFileLine1 empty", ErrorFileLine1(""), "")
    Assert("ErrorFileLine1 empty first line", ErrorFileLine1("`nsecond"), "")
    long := ""
    Loop 300
        long .= "x"
    Assert("ErrorFileLine1 capped at 200", StrLen(ErrorFileLine1(long "`nd")), 200)
}

TestWarningSummary()
{
    Assert("WarningSummary empty", WarningSummary(""), "")
    Assert("WarningSummary blank lines only", WarningSummary("`r`n  `n"), "")
    Assert("WarningSummary one", WarningSummary("line 3: 'model' appears twice in [qwen]`n"), "line 3: 'model' appears twice in [qwen]")
    Assert("WarningSummary CRLF, BOM, blanks", WarningSummary(Chr(0xFEFF) "a`r`n`r`nb`r`n"), "a`nb")
    Assert("WarningSummary 3 lines kept", WarningSummary("a`nb`nc"), "a`nb`nc")
    Assert("WarningSummary more than 3", WarningSummary("a`nb`nc`nd`ne"), "a`nb`nc`n(+2 more)")
    Assert("WarningSummary custom max", WarningSummary("a`nb`nc", 1), "a`n(+2 more)")
}

TestHotkeyId()
{
    Assert("HotkeyId modifier order", HotkeyId("!^r"), HotkeyId("^!r"))
    Assert("HotkeyId letter case", HotkeyId("^!R"), HotkeyId("^!r"))
    Assert("HotkeyId named key", HotkeyId("PgUp"), "pgup")
    Assert("HotkeyId all modifiers", HotkeyId("#+!^F5"), "^!+#f5")
    Assert("HotkeyId differs by modifier", HotkeyId("^PgUp") = HotkeyId("PgUp"), false)
}

TestResolveKeys()
{
    defs := Map("correggi", "PgUp", "riassumi", "PgDn", "spiega", "End")
    names := Map("correggi", "Fix", "riassumi", "Summarize", "spiega", "Explain")
    keysOf(r) => r.keys["correggi"] "|" r.keys["riassumi"] "|" r.keys["spiega"]

    r := ResolveKeys(Map(), defs, names)
    Assert("ResolveKeys nothing set -> defaults", keysOf(r), "PgUp|PgDn|End")
    Assert("ResolveKeys nothing set -> no warning", r.warnings.Length, 0)

    r := ResolveKeys(Map("correggi", "^!r", "riassumi", "", "spiega", "F8"), defs, names)
    Assert("ResolveKeys custom keys", keysOf(r), "^!r|PgDn|F8")
    Assert("ResolveKeys custom keys -> no warning", r.warnings.Length, 0)

    r := ResolveKeys(Map("correggi", "pgup"), defs, names)
    Assert("ResolveKeys invalid -> default", keysOf(r), "PgUp|PgDn|End")
    Assert("ResolveKeys invalid -> one warning", r.warnings.Length, 1)
    Assert("ResolveKeys invalid warning text", r.warnings[1], 'Fix: "pgup" is not a valid key, using PgUp')

    r := ResolveKeys(Map("correggi", "^!r", "riassumi", "!^R"), defs, names)
    Assert("ResolveKeys duplicate -> second falls back", keysOf(r), "^!r|PgDn|End")
    Assert("ResolveKeys duplicate warning", r.warnings[1], "Summarize: Alt+Ctrl+R is already used by Fix, using PgDn")

    ; A key set by the user wins over another slot's default
    r := ResolveKeys(Map("correggi", "PgDn"), defs, names)
    Assert("ResolveKeys user key takes a default -> that slot has no key", keysOf(r), "PgDn||End")
    Assert("ResolveKeys no-key warning", r.warnings[1], "Summarize: PgDn is used by Fix: no key")

    ; Swapped defaults: both explicit, no conflict
    r := ResolveKeys(Map("correggi", "PgDn", "riassumi", "PgUp"), defs, names)
    Assert("ResolveKeys swapped keys", keysOf(r), "PgDn|PgUp|End")
    Assert("ResolveKeys swapped keys -> no warning", r.warnings.Length, 0)

    ; Duplicate whose default is also taken
    r := ResolveKeys(Map("correggi", "End", "spiega", "End"), defs, names)
    Assert("ResolveKeys duplicate and default taken", keysOf(r), "End|PgDn|")
    Assert("ResolveKeys duplicate and default taken warning", r.warnings[1],
        "Explain: End is already used by Fix, and End is used by Fix: no key")
    Assert("ResolveKeys value is trimmed", ResolveKeys(Map("spiega", "  F8 "), defs, names).keys["spiega"], "F8")
}

TestPromptsUserTemplate()
{
    src := Chr(0xFEFF) 'x = """a`r`n`r`nb"""`r`nY = 1`r`n'
    out := PromptsUserTemplate(src)
    Assert("PromptsUserTemplate header", InStr(out, "# AI-Hotkeys — your own prompts (prompts_user.py).") = 1, true)
    Assert("PromptsUserTemplate commented copy", InStr(out, '# x = """a`n#`n# b"""`n# Y = 1`n') > 0, true)
    bad := 0
    Loop Parse, out, "`n"
        if (A_LoopField != "" && SubStr(A_LoopField, 1, 1) != "#")
            bad++
    Assert("PromptsUserTemplate every non-empty line is a comment", bad, 0)
    Assert("PromptsUserTemplate no BOM inside", InStr(out, Chr(0xFEFF)), 0)
    Assert("PromptsUserTemplate no CR", InStr(out, "`r"), 0)
}

TestProcExitCode()
{
    Run(A_ComSpec " /c exit 3", , "Hide", &pid)
    h := ProcOpen(pid)
    Assert("ProcOpen(child) handle", h != 0, true)
    Loop 100
    {
        if (ProcExitCode(h) != 259)
            break
        Sleep 50
    }
    Assert("ProcExitCode(child) = 3", ProcExitCode(h), 3)
    ProcClose(h)
    Assert("ProcExitCode(0) = -1", ProcExitCode(0), -1)
    Assert("ProcOpen(0) = 0", ProcOpen(0), 0)
}


; ---------------------------------------------------------
; S9: run folders work\runs\<id> (C32, H04, C18)
; ---------------------------------------------------------

TestNewRunId()
{
    id := NewRunId("20261018123456")
    Assert("NewRunId format", RegExMatch(id, "^20261018123456-[0-9a-f]{16}$") > 0, true)
    Assert("NewRunId default time is A_Now", SubStr(NewRunId(), 1, 8), SubStr(A_Now, 1, 8))
    Assert("NewRunId is a run id", IsRunId(NewRunId()), true)
    ; Same Python rule (qwen_client.RUN_ID_RE): 14 digits, "-", 16 lowercase hex
    seen := Map(), dup := 0
    Loop 2000
    {
        id := NewRunId("20261018123456")
        if seen.Has(id)
            dup++
        seen[id] := true
    }
    Assert("NewRunId 2000 ids in the same second are unique", dup, 0)
}

TestIsRunId()
{
    Assert("IsRunId valid", IsRunId("20261018123456-0123456789abcdef"), true)
    for bad in ["", "runs", "20261018123456", "20261018123456-0123456789ABCDEF",
                "2026101812345-0123456789abcdef", "20261018123456-0123456789abcde",
                "20261018123456-0123456789abcdef0", "20261018123456_0123456789abcdef",
                "..\20261018123456-0123456789abcdef", "20261018123456-0123456789abcdef\x",
                " 20261018123456-0123456789abcdef", "20261018123456-0123456789abcdeg"]
        Assert("IsRunId(" Show(bad) ") false", IsRunId(bad), false)
}

TestRunDirOf()
{
    Assert("RunDirOf", RunDirOf("C:\AI-Hotkeys\work", "X"), "C:\AI-Hotkeys\work\runs\X")
    Assert("RunDirOf trailing backslash", RunDirOf("C:\AI Hotkeys\work\", "X"), "C:\AI Hotkeys\work\runs\X")
    Assert("RunDirOf never ends in a backslash (argv quoting)", SubStr(RunDirOf("C:\w", NewRunId()), -1) != "\", true)
}

TestRunIsStale()
{
    now := "20261018120000"
    Assert("RunIsStale 1 h ago", RunIsStale("20261018110000", now), true)
    Assert("RunIsStale 2 h ago", RunIsStale("20261018100000", now), true)
    Assert("RunIsStale yesterday", RunIsStale("20261017120000", now), true)
    Assert("RunIsStale 59 min 59 s ago", RunIsStale("20261018110001", now), false)
    Assert("RunIsStale just now", RunIsStale(now, now), false)
    Assert("RunIsStale in the future", RunIsStale("20261018130000", now), false)
    Assert("RunIsStale custom age", RunIsStale("20261018115900", now, 30), true)
    Assert("RunIsStale empty stamp", RunIsStale("", now), false)
    Assert("RunIsStale garbage stamp", RunIsStale("yesterday", now), false)
    Assert("RunIsStale invalid date", RunIsStale("20261399000000", now), false)
    Assert("RunIsStale default now: an old stamp", RunIsStale("20000101000000"), true)
    Assert("RunIsStale default now: A_Now", RunIsStale(A_Now), false)
}

TestWorkAclArgs()
{
    sid := "S-1-5-21-1004336348-1177238915-682003330-1001"
    a := WorkAclArgs("C:\AI Hotkeys\work", sid)
    Assert("WorkAclArgs grant", a.grant,
        '"C:\AI Hotkeys\work" /grant:r "*' sid ':(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"')
    Assert("WorkAclArgs inheritance", a.inherit, '"C:\AI Hotkeys\work" /inheritance:r')
    Assert("WorkAclArgs refuses a user name", WorkAclArgs("C:\w", "PC\jack"), "")
    Assert("WorkAclArgs refuses an empty SID", WorkAclArgs("C:\w", ""), "")
    Assert("WorkAclArgs refuses a quoted SID", WorkAclArgs("C:\w", 'S-1-5-21-1" /grant "Everyone'), "")
}

TestSid()
{
    Assert("IsSid user", IsSid("S-1-5-21-1004336348-1177238915-682003330-1001"), true)
    Assert("IsSid SYSTEM", IsSid("S-1-5-18"), true)
    Assert("IsSid name", IsSid("PC\jack"), false)
    Assert("IsSid trailing dash", IsSid("S-1-5-"), false)
    Assert("IsSid trailing newline", IsSid("S-1-5-18`n"), false)
    Assert("IsSid injection", IsSid("S-1-5-18 /grant x"), false)
    Assert("SidFromWhoamiCsv",
        SidFromWhoamiCsv('"desktop-abc\jack","S-1-5-21-1004336348-1177238915-682003330-1001"`r`n'),
        "S-1-5-21-1004336348-1177238915-682003330-1001")
    Assert("SidFromWhoamiCsv name with spaces and quotes",
        SidFromWhoamiCsv('"PC\Jack ""J"" R","S-1-5-21-1-2-3-1001"'), "S-1-5-21-1-2-3-1001")
    Assert("SidFromWhoamiCsv nothing", SidFromWhoamiCsv("ERROR: access denied"), "")
    Assert("SidFromWhoamiCsv empty", SidFromWhoamiCsv(""), "")
    ; the real thing, as SecureWorkDir runs it
    out := TMP "\whoami.txt"
    RunWait(A_ComSpec ' /d /c ""' A_WinDir '\System32\whoami.exe" /user /fo csv /nh > "' out '""', , "Hide")
    Assert("SidFromWhoamiCsv real whoami output is a SID", IsSid(SidFromWhoamiCsv(FileRead(out))), true)
}

TestCmdArgSafe()
{
    Assert("CmdArgSafe plain", CmdArgSafe("End"), "End")
    Assert("CmdArgSafe modifiers", CmdArgSafe("Ctrl+Shift+F1"), "Ctrl+Shift+F1")
    Assert("CmdArgSafe quote", CmdArgSafe('"'), "")
    Assert("CmdArgSafe quote inside", CmdArgSafe('Ctrl+" --no-browser "x'), "Ctrl+ --no-browser x")
    Assert("CmdArgSafe trailing backslash", CmdArgSafe("Ctrl+\"), "Ctrl+")
    Assert("CmdArgSafe inner backslash kept", CmdArgSafe("a\b"), "a\b")
    Assert("CmdArgSafe KeyLabel of a quote key", InStr(CmdArgSafe(KeyLabel('^"')), '"'), 0)
}

TestTreeDeletable()
{
    Assert("TreeDeletable directory", TreeDeletable("D"), true)
    Assert("TreeDeletable hidden archive directory", TreeDeletable("HAD"), true)
    Assert("TreeDeletable junction", TreeDeletable("DL"), false)
    Assert("TreeDeletable symlink with other bits", TreeDeletable("RHDL"), false)
    Assert("TreeDeletable file", TreeDeletable("A"), false)
    Assert("TreeDeletable missing", TreeDeletable(""), false)
    ; real junction (no admin rights needed): DirExist reports "L" for it
    target := TMP "\junction-target"
    link := TMP "\junction-link"
    DirCreate(target)
    FileAppend("keep", target "\keep.txt")
    RunWait(A_ComSpec ' /d /c mklink /J "' link '" "' target '"', , "Hide")
    Assert("TreeDeletable real folder", TreeDeletable(DirExist(target)), true)
    Assert("TreeDeletable real junction", TreeDeletable(DirExist(link)), false)
    try DirDelete(link)          ; removes the link only
    Assert("junction target untouched", FileExist(target "\keep.txt") != "", true)
}

TestIsLocalSearxUrl()
{
    for u in ["http://127.0.0.1:8888", "http://127.0.0.1", "https://localhost:8443/", "http://LOCALHOST:8888/search"]
        Assert("IsLocalSearxUrl " u, IsLocalSearxUrl(u), true)
    for u in ["", "http://192.168.1.2:8888", "https://evil.example", "file:///C:/Windows/System32/calc.exe",
              "C:\Windows\System32\calc.exe", "calc.exe", "http://127.0.0.1.evil.example/",
              "http://127.0.0.1:8888@evil.example", "http://127.0.0.1\@evil.example", "http://localhost/a b",
              "http://127.0.0.1:8888`n", "ftp://127.0.0.1/", "mailto:x@127.0.0.1"]
        Assert("IsLocalSearxUrl rejects " Show(u), IsLocalSearxUrl(u), false)
}
