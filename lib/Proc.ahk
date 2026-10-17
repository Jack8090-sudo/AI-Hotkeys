; =========================================================
;  AI-Hotkeys — process helpers (Win32 calls, no globals, no top-level code)
; =========================================================
;  Included by main.ahk and by tests\ahk\run.ahk:
;      #Include %A_ScriptDir%\lib\Proc.ahk

PROCESS_QUERY_LIMITED_INFORMATION() => 0x1000

; Creation time of a running process as a Windows FILETIME (100 ns units
; since 1601, UTC), the value searxng\avvia_searxng.py writes into
; work\searxng.pid (contract K5). 0 if the process is gone or not accessible.
ProcessCreationTime(pid)
{
    if !(pid > 0)
        return 0
    h := DllCall("OpenProcess", "UInt", PROCESS_QUERY_LIMITED_INFORMATION(), "Int", 0, "UInt", pid, "Ptr")
    if !h
        return 0
    ; A process that has ended stays openable while someone holds a handle
    ; to it: only a running one counts (exit code STILL_ACTIVE = 259)
    code := 0
    running := DllCall("GetExitCodeProcess", "Ptr", h, "UInt*", &code) && code = 259
    created := 0, exited := 0, kernel := 0, user := 0
    ok := running && DllCall("GetProcessTimes", "Ptr", h, "Int64*", &created, "Int64*", &exited,
                             "Int64*", &kernel, "Int64*", &user)
    DllCall("CloseHandle", "Ptr", h)
    return ok ? created : 0
}

; Full path of a running process's executable, "" if gone or not accessible
ProcessPathOf(pid)
{
    if !(pid > 0)
        return ""
    try return ProcessGetPath(pid)
    return ""
}

; Handle that keeps a process's exit code readable after it ends.
; Open it right after Run(); 0 if the process is already gone.
ProcOpen(pid)
{
    if !(pid > 0)
        return 0
    return DllCall("OpenProcess", "UInt", PROCESS_QUERY_LIMITED_INFORMATION(), "Int", 0, "UInt", pid, "Ptr")
}

; Exit code of the process behind handle h: 259 (STILL_ACTIVE) while it
; runs, -1 if it cannot be read.
ProcExitCode(h)
{
    code := 0
    if !h || !DllCall("GetExitCodeProcess", "Ptr", h, "UInt*", &code)
        return -1
    return code
}

ProcClose(h)
{
    if h
        DllCall("CloseHandle", "Ptr", h)
}
