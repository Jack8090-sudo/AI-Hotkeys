<#
.SYNOPSIS
  Desktop E2E smoke test of an installed AI-Hotkeys (plan step S14, hypothesis H14). CI only.

.DESCRIPTION
  1. Points the installed config.ini at 127.0.0.1:11434 and turns web search off (no SearXNG).
  2. Starts scripts\ci\fake_ollama.py on 127.0.0.1:11434 with the host Python (tests\support.py
     FakeOllama, never a real model).
  3. Starts the installed main.ahk with the bundled AutoHotkey, then Notepad.
  4. Types a sentence, selects all (Ctrl+A) and sends PgUp (the default "fix" hotkey).
  5. Passes when the fake received /api/chat and Notepad's text became the fake's answer.
  Kills only what it started. Meant for a GitHub-hosted runner: it edits the installed config.ini
  and needs port 11434 free, so never run it on a machine with a real Ollama or a real install.
  Windows PowerShell 5.1 compatible.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci\e2e-notepad.ps1 -Dir "$env:LOCALAPPDATA\Programs\AI-Hotkeys" -LogDir $env:RUNNER_TEMP\e2e
#>
param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [Parameter(Mandatory = $true)][string]$LogDir,
    [string]$Python = 'python',
    [int]$TimeoutSec = 90
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'InstallerTest.psm1') -Force

$Dir = [IO.Path]::GetFullPath($Dir).TrimEnd('\')
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$original = 'this sentense has a typo and should be rewriten'
$answer = 'AIHK E2E rewritten by the fake Ollama.'
$fakeLog = Join-Path $LogDir 'fake-ollama.jsonl'
$ready = Join-Path $LogDir 'fake-ollama.ready'
$started = @()

function Set-IniValue([string]$Text, [string]$Key, [string]$Value) {
    $re = '(?m)^' + [regex]::Escape($Key) + '\s*=.*$'
    if (-not [regex]::IsMatch($Text, $re)) { throw "config.ini has no '$Key' line" }
    return [regex]::Replace($Text, $re, "$Key = $Value")
}

function Get-ChatCount {
    if (-not (Test-Path -LiteralPath $fakeLog)) { return 0 }
    return @(Get-Content -LiteralPath $fakeLog | Where-Object { $_ -match '"/api/chat' }).Count
}

try {
    $cfgPath = Join-Path $Dir 'config.ini'
    $cfg = [IO.File]::ReadAllText($cfgPath)
    $cfg = Set-IniValue $cfg 'ollama_url' 'http://127.0.0.1:11434'
    $cfg = Set-IniValue $cfg 'web_search' 'false'
    [IO.File]::WriteAllText($cfgPath, $cfg, (New-Object Text.UTF8Encoding $false))
    Write-Host 'config.ini: ollama_url = http://127.0.0.1:11434, web_search = false'

    $fake = Start-Process -FilePath $Python -PassThru -WindowStyle Hidden `
        -ArgumentList ('-I "' + (Join-Path $PSScriptRoot 'fake_ollama.py') + '" --port 11434 --text "' + $answer + '" --log "' + $fakeLog + '" --ready-file "' + $ready + '"') `
        -RedirectStandardOutput (Join-Path $LogDir 'fake.out.txt') -RedirectStandardError (Join-Path $LogDir 'fake.err.txt')
    $started += $fake
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-Path -LiteralPath $ready)) {
        if ($fake.HasExited -or (Get-Date) -gt $deadline) { Get-Content (Join-Path $LogDir 'fake.err.txt') | Write-Host; throw 'The fake Ollama did not start' }
        Start-Sleep -Milliseconds 200
    }
    if ((Get-HttpStatus 'http://127.0.0.1:11434/api/version') -ne 200) { throw 'The fake Ollama does not answer /api/version' }
    Write-Host 'fake Ollama ready on 127.0.0.1:11434'

    $ahk = Start-Process -FilePath (Join-Path $Dir 'ahk\AutoHotkey64.exe') -ArgumentList ('"' + (Join-Path $Dir 'main.ahk') + '"') `
        -WorkingDirectory $Dir -PassThru
    $started += $ahk
    Start-Sleep -Seconds 5
    if ($ahk.HasExited) { throw "main.ahk exited at startup (code $($ahk.ExitCode))" }
    Write-Host "main.ahk running (pid $($ahk.Id))"

    $before = @(Get-Process -Name notepad -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    $np = Start-Process -FilePath (Join-Path $env:WINDIR 'notepad.exe') -PassThru
    $started += $np
    # The Store Notepad may hand over to another process: take the newest notepad with a window.
    $win = $null
    $deadline = (Get-Date).AddSeconds(20)
    while (-not $win -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $win = Get-Process -Name notepad -ErrorAction SilentlyContinue |
            Where-Object { $before -notcontains $_.Id -and $_.MainWindowHandle -ne 0 } |
            Sort-Object StartTime -Descending | Select-Object -First 1
    }
    if (-not $win) { throw 'Notepad opened no window' }
    if ($win.Id -ne $np.Id) { $started += $win }
    Write-Host "Notepad window: pid $($win.Id), '$($win.MainWindowTitle)'"

    $ws = New-Object -ComObject WScript.Shell
    if (-not $ws.AppActivate($win.Id)) { Start-Sleep -Seconds 1; [void]$ws.AppActivate($win.Id) }
    Start-Sleep -Milliseconds 800
    $ws.SendKeys($original)
    Start-Sleep -Milliseconds 500
    $ws.SendKeys('^a')
    Start-Sleep -Milliseconds 500
    $ws.SendKeys('{PGUP}')
    Write-Host 'typed the sentence, Ctrl+A, PgUp'

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-ChatCount) -eq 0 -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if ((Get-ChatCount) -eq 0) {
        if (Test-Path -LiteralPath $fakeLog) { Get-Content -LiteralPath $fakeLog | Write-Host }
        throw "The fake Ollama received no /api/chat within $TimeoutSec s (the hotkey did not fire, or the copy failed)"
    }
    Write-Host 'the fake Ollama received /api/chat'

    $text = ''
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 2
        [void]$ws.AppActivate($win.Id)
        Start-Sleep -Milliseconds 300
        $ws.SendKeys('^a')
        Start-Sleep -Milliseconds 300
        $ws.SendKeys('^c')
        Start-Sleep -Milliseconds 500
        $text = (Get-Clipboard -Raw)
        if ($null -eq $text) { $text = '' }
        $text = $text.Trim()
    } while ($text -ne $answer -and (Get-Date) -lt $deadline)
    Write-Host "Notepad text now: '$text'"
    if ($text -eq $original) { throw 'The text did not change' }
    if ($text -ne $answer) { throw "The text changed, but not to the fake's answer" }
    Write-Host 'ok  PgUp replaced the selection with the model answer (H14 holds on this runner)'
}
finally {
    foreach ($p in $started) { if ($p -and -not $p.HasExited) { Stop-Tree $p.Id } }
    Start-Sleep -Seconds 1
    # main.ahk may have started helpers from the install folder: let the shipped stop.ps1-style
    # rule apply (only processes whose path or command line is inside $Dir).
    Get-CimInstance -ClassName Win32_Process | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith("$Dir\", [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine.IndexOf("$Dir\", [StringComparison]::OrdinalIgnoreCase) -ge 0)
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
