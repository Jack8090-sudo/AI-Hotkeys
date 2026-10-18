; =========================================================
;  S3 ClipWait probe (benchmark tool, not shipped) - for D12 / H02 / H03 / H07
; =========================================================
;  Measures how long the copy takes in each app, exactly like main.ahk
;  RunSelectionAction does it: clear the clipboard, Send ^c, ClipWait.
;
;  Run:   ahk\AutoHotkey64.exe tools\bench\clipwait_probe.ahk
;         (quit AI-Hotkeys first, or its hotkeys keep working alongside)
;  Use:   select something in any app, press Ctrl+Alt+F11.
;         Ctrl+Alt+F12 quits the probe.
;  Out:   tools\bench\out\clipwait.csv  (process name, ms, characters, ok, kind)
;         Nothing of the copied text is written: only its length.
;         The clipboard is restored after each probe.
; =========================================================
#Requires AutoHotkey v2.0
#SingleInstance Force

global OUT_DIR := A_ScriptDir "\out"
global OUT := OUT_DIR "\clipwait.csv"
DirCreate OUT_DIR
if !FileExist(OUT)
    FileAppend "when,process,ms,chars,ok,kind`n", OUT, "UTF-8"

^!F11::Probe()
^!F12::ExitApp()

Probe()
{
    global OUT
    proc := ""
    try proc := WinGetProcessName("A")
    saved := ClipboardAll()
    A_Clipboard := ""

    freq := 0, t0 := 0, t1 := 0
    DllCall("QueryPerformanceFrequency", "Int64*", &freq)
    DllCall("QueryPerformanceCounter", "Int64*", &t0)
    Send "^c"
    ok := ClipWait(5, 1)            ; 1 = any format (Excel, files, images)
    DllCall("QueryPerformanceCounter", "Int64*", &t1)
    ms := Round((t1 - t0) * 1000 / freq, 1)

    kind := "none"
    chars := 0
    if ok
    {
        if DllCall("IsClipboardFormatAvailable", "UInt", 15)        ; CF_HDROP = file selection
            kind := "files"
        else if DllCall("IsClipboardFormatAvailable", "UInt", 13)   ; CF_UNICODETEXT
            kind := "text"
        else
            kind := "other"
        chars := StrLen(A_Clipboard)
    }
    A_Clipboard := saved

    FileAppend FormatTime(, "yyyy-MM-dd HH:mm:ss") "," proc "," ms "," chars "," (ok ? 1 : 0) "," kind "`n", OUT, "UTF-8"
    ToolTip proc ": " (ok ? ms " ms, " chars " chars (" kind ")" : "nothing copied within 5 s")
    SetTimer () => ToolTip(), -2500
}
