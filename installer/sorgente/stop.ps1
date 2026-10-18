# Closes AI-Hotkeys running from -Dir before an update, a migration or an uninstall.
# Stops only what AI-Hotkeys itself starts (SEC1: nothing else that merely mentions <Dir>\):
#   - the bundled interpreter: python*.exe directly in <Dir>\python\
#   - the bundled AutoHotkey: AutoHotkey*.exe directly in <Dir>\ahk\
#   - AutoHotkey running <Dir>\main.ahk (also a system-wide AutoHotkey)
#   - any python*.exe whose command line runs one of our scripts: <Dir>\<name>.py (viewer,
#     settings, ...), or something under <Dir>\actions\ or <Dir>\searxng\ (SearXNG)
# Paths are compared with a trailing separator, so C:\AI-Hotkeys never matches C:\AI-Hotkeys2.
# Exit code: 0 = nothing left running, 1 = some processes are still running, 2 = bad -Dir,
# 3 = the process list could not be read.
param([Parameter(Mandatory = $true)][string]$Dir, [switch]$SelfTest)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try { $root = [IO.Path]::GetFullPath($Dir).TrimEnd('\') }
catch { Write-Host "stop.ps1: invalid folder: $Dir"; exit 2 }
if ($root.Length -lt 4) { Write-Host "stop.ps1: refusing a drive root: $Dir"; exit 2 }

$rootL = ($root + '\').ToLowerInvariant()
$pyDir = ($root + '\python\').ToLowerInvariant()
$ahkDir = ($root + '\ahk\').ToLowerInvariant()
$mainAhk = ($root + '\main.ahk').ToLowerInvariant()
# <Dir>\name.py[w] (top-level script), <Dir>\actions\..., <Dir>\searxng\...
$ourScript = [regex]::Escape($rootL) + '([^\\/:*?"<>|]+\.pyw?(["\s]|$)|actions\\|searxng\\)'
$pyName = '^pythonw?(\d+(\.\d+)?)?\.exe$'
$self = $PID

# True when the process (lower-case exe path, name and command line) is one of ours.
function Test-Ours([string]$exe, [string]$name, [string]$cmd) {
    if ($name -match $pyName -and $exe.StartsWith($pyDir) -and -not $exe.Substring($pyDir.Length).Contains('\')) { return $true }
    if ($name -like 'autohotkey*.exe' -and $exe.StartsWith($ahkDir) -and -not $exe.Substring($ahkDir.Length).Contains('\')) { return $true }
    if ($name -like 'autohotkey*' -and $cmd.Contains($mainAhk)) { return $true }
    if ($name -match $pyName -and $cmd -match $ourScript) { return $true }
    return $false
}

function Get-Targets {
    $procs = Get-CimInstance -ClassName Win32_Process
    $parent = ($procs | Where-Object { $_.ProcessId -eq $self } | Select-Object -First 1)
    $skip = @($self)
    if ($parent) { $skip += $parent.ParentProcessId }
    foreach ($p in $procs) {
        if ($skip -contains $p.ProcessId) { continue }
        $exe = ''
        if ($p.ExecutablePath) { $exe = ([string]$p.ExecutablePath).ToLowerInvariant() }
        $cmd = ''
        if ($p.CommandLine) { $cmd = ([string]$p.CommandLine).ToLowerInvariant() }
        $name = ([string]$p.Name).ToLowerInvariant()
        if (Test-Ours $exe $name $cmd) { $p }
    }
}

if ($SelfTest) {
    # Matching rules only (no process is listed or stopped): used by the developers' checks.
    $cases = @(
        @(($pyDir + 'pythonw.exe'), 'pythonw.exe', '', $true),
        @(($pyDir + 'lib\tool.exe'), 'tool.exe', '', $false),
        @(($pyDir + 'scripts\python.exe'), 'python.exe', '', $false),
        @(($ahkDir + 'autohotkey64.exe'), 'autohotkey64.exe', '', $true),
        @('c:\tools\autohotkey64.exe', 'autohotkey64.exe', ('"x" "' + $mainAhk + '"'), $true),
        @('c:\py\python.exe', 'python.exe', ('python "' + $rootL + 'viewer.py" --run-dir=x'), $true),
        @('c:\py\pythonw.exe', 'pythonw.exe', ('pythonw ' + $rootL + 'searxng\avvia_searxng.py'), $true),
        @('c:\py\python.exe', 'python.exe', ('python "' + $rootL + 'actions\explain.py"'), $true),
        @('c:\py\python.exe', 'python.exe', ('python c:\other\x.py "' + $rootL + 'notes.txt"'), $false),
        @('c:\py\python.exe', 'python.exe', ('python -m http.server -d "' + $rootL + 'work"'), $false),
        @('c:\py\python.exe', 'python.exe', ('python "' + $rootL + 'sub\x.py"'), $false),
        @('c:\windows\notepad.exe', 'notepad.exe', ('notepad "' + $rootL + 'config.ini"'), $false),
        @('c:\py\python.exe', 'python.exe', ('python "' + $rootL.TrimEnd('\') + '2\viewer.py"'), $false)
    )
    $bad = 0
    foreach ($c in $cases) {
        $got = Test-Ours $c[0] $c[1] $c[2]
        if ($got -ne $c[3]) { $bad++; Write-Host "FAIL: $($c[0]) | $($c[2]) -> $got" }
    }
    Write-Host "stop.ps1 self-test: $($cases.Count - $bad)/$($cases.Count) ok"
    exit $bad
}

try { $targets = @(Get-Targets) }
catch { Write-Host "stop.ps1: cannot list processes: $($_.Exception.Message)"; exit 3 }

if ($targets.Count -eq 0) { Write-Host 'No AI-Hotkeys process is running.'; exit 0 }

foreach ($t in $targets) {
    Write-Host "Stopping $($t.Name) (PID $($t.ProcessId))"
    try { Stop-Process -Id $t.ProcessId -Force -ErrorAction Stop }
    catch {
        # Already exited is fine; anything else is reported by the final check.
        if (Get-Process -Id $t.ProcessId -ErrorAction SilentlyContinue) {
            Write-Host "  could not stop PID $($t.ProcessId): $($_.Exception.Message)"
        }
    }
}

# Wait up to 5 s for the processes to go away (file handles are released on exit).
$deadline = (Get-Date).AddSeconds(5)
do {
    Start-Sleep -Milliseconds 250
    $left = @($targets | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
} while ($left.Count -gt 0 -and (Get-Date) -lt $deadline)

if ($left.Count -gt 0) {
    foreach ($l in $left) { Write-Host "Still running: $($l.Name) (PID $($l.ProcessId))" }
    exit 1
}
Write-Host "Stopped $($targets.Count) process(es)."
exit 0
