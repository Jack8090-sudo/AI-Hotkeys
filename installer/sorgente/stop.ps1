# Closes AI-Hotkeys running from -Dir before an update, a migration or an uninstall.
# Stops:
#   - any process whose executable lives in <Dir>\python\ or <Dir>\ahk\ (bundled Python, AutoHotkey)
#   - AutoHotkey running <Dir>\main.ahk (also a system-wide AutoHotkey)
#   - any python*.exe whose command line references <Dir>\ (SearXNG, viewer, settings or an action
#     started with a system Python)
# Paths are compared with a trailing separator, so C:\AI-Hotkeys never matches C:\AI-Hotkeys2.
# Exit code: 0 = nothing left running, 1 = some processes are still running, 2 = bad -Dir,
# 3 = the process list could not be read.
param([Parameter(Mandatory = $true)][string]$Dir)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try { $root = [IO.Path]::GetFullPath($Dir).TrimEnd('\') }
catch { Write-Host "stop.ps1: invalid folder: $Dir"; exit 2 }
if ($root.Length -lt 4) { Write-Host "stop.ps1: refusing a drive root: $Dir"; exit 2 }

$rootL = ($root + '\').ToLowerInvariant()
$exeDirs = @(($root + '\python\').ToLowerInvariant(), ($root + '\ahk\').ToLowerInvariant())
$mainAhk = ($root + '\main.ahk').ToLowerInvariant()
$self = $PID

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
        $hit = $false
        foreach ($d in $exeDirs) { if ($exe.StartsWith($d)) { $hit = $true } }
        if (-not $hit -and $name -like 'autohotkey*' -and $cmd.Contains($mainAhk)) { $hit = $true }
        if (-not $hit -and $name -match '^pythonw?(\d+(\.\d+)?)?\.exe$' -and $cmd.Contains($rootL)) { $hit = $true }
        if ($hit) { $p }
    }
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
