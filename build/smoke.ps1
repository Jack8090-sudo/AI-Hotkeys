<#
.SYNOPSIS
    H16 smoke test of a built payload, using the payload's own interpreter.

.DESCRIPTION
    Copies build\out\payload into a throw-away install folder under %TEMP%, then:
      1. runs build\h16_probe.py with the shipped python313._pth (D2: zip, '.', '..') and
         again with a minimal one (zip, '.') to show what '..' is needed for;
         PYTHONPATH points at a poison folder that must be ignored (C28);
      2. starts searxng\avvia_searxng.py in the copy (its own work\ and a config.ini with
         a free port, never 8888), waits up to -TimeoutSec for /healthz, then stops
         only the process it started.
    Writes build\out\smoke\h16-<variant>.json and build\out\smoke\summary.txt.
    Never touches C:\AI-Hotkeys\work or the live SearXNG.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File build\smoke.ps1 -Payload build\out\payload
#>
param(
    [Parameter(Mandatory = $true)][string]$Payload,
    [int]$TimeoutSec = 60,
    [switch]$Keep
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Payload = (Resolve-Path $Payload).Path
$OutDir = Join-Path $PSScriptRoot 'out\smoke'
if (Test-Path -LiteralPath $OutDir) { Remove-Item -LiteralPath $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutDir | Out-Null
$Utf8 = New-Object Text.UTF8Encoding $false

$tag = [guid]::NewGuid().ToString('N').Substring(0, 8)
$T = Join-Path ([IO.Path]::GetTempPath()) "aih-smoke-$tag"
$P = Join-Path ([IO.Path]::GetTempPath()) "aih-probe-$tag"
$summary = New-Object Collections.Generic.List[string]
$failed = $false
$proc = $null

function Get-FreePort {
    $l = New-Object Net.Sockets.TcpListener ([Net.IPAddress]::Loopback), 0
    $l.Start()
    try { return $l.LocalEndpoint.Port } finally { $l.Stop() }
}

try {
    Write-Host "    install copy: $T"
    New-Item -ItemType Directory -Path $T | Out-Null
    Copy-Item -Path (Join-Path $Payload 'app\*') -Destination $T -Recurse
    Copy-Item -LiteralPath (Join-Path $Payload 'python') -Destination $T -Recurse
    Copy-Item -LiteralPath (Join-Path $Payload 'ahk') -Destination $T -Recurse
    Copy-Item -LiteralPath (Join-Path $Payload 'config.ini') -Destination $T

    $port = Get-FreePort
    if ($port -eq 8888) { $port = Get-FreePort }
    $cfgPath = Join-Path $T 'config.ini'
    $cfg = [IO.File]::ReadAllText($cfgPath)
    $cfg = [regex]::Replace($cfg, '(?m)^searxng_url\s*=.*$', "searxng_url = http://127.0.0.1:$port")
    [IO.File]::WriteAllText($cfgPath, $cfg, $Utf8)

    New-Item -ItemType Directory -Path (Join-Path $P 'poison') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'h16_probe.py') -Destination $P
    [IO.File]::WriteAllText((Join-Path $P 'poison\qwen_client.py'), "raise SystemExit('poison imported')`n", $Utf8)

    $py = Join-Path $T 'python\python.exe'
    $pth = Join-Path $T 'python\python313._pth'
    $shipped = [IO.File]::ReadAllText($pth)
    $oldPyPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $P 'poison'
    try {
        foreach ($variant in @('d2', 'minimal')) {
            if ($variant -eq 'minimal') { [IO.File]::WriteAllText($pth, "python313.zip`r`n.`r`n", $Utf8) }
            else { [IO.File]::WriteAllText($pth, $shipped, $Utf8) }
            $report = Join-Path $OutDir "h16-$variant.json"
            & $py -B (Join-Path $P 'h16_probe.py') --root $T --variant $variant --report $report --poison (Join-Path $P 'poison')
            $rc = $LASTEXITCODE
            $summary.Add("h16 $variant ._pth : exit $rc (report $report)")
            if ($variant -eq 'd2' -and $rc -ne 0) { $failed = $true }
        }
    }
    finally {
        [IO.File]::WriteAllText($pth, $shipped, $Utf8)
        $env:PYTHONPATH = $oldPyPath
    }

    Write-Host "    starting SearXNG on 127.0.0.1:$port"
    $proc = Start-Process -FilePath $py -ArgumentList @('-B', "`"$T\searxng\avvia_searxng.py`"") `
        -WorkingDirectory $T -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $healthy = $false
    $started = Get-Date
    while ((Get-Date) -lt $deadline -and -not $proc.HasExited) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $healthy = $true; break }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    $secs = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    if ($healthy) { $summary.Add("searxng /healthz : 200 after $secs s (pid $($proc.Id), port $port)") }
    else {
        $failed = $true
        $summary.Add("searxng /healthz : FAILED after $secs s (exited: $($proc.HasExited))")
        $log = Join-Path $T 'work\searxng.log'
        if (Test-Path -LiteralPath $log) { $summary.Add('searxng.log tail:'); Get-Content -LiteralPath $log -Tail 30 | ForEach-Object { $summary.Add("  $_") } }
    }
}
finally {
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force; $proc.WaitForExit(10000) | Out-Null }
    if (-not $Keep) {
        foreach ($d in @($T, $P)) {
            $tmp = [IO.Path]::GetTempPath()
            if ($d.StartsWith($tmp, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $d)) {
                Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

[IO.File]::WriteAllText((Join-Path $OutDir 'summary.txt'), (($summary -join "`n") + "`n"), $Utf8)
$summary | ForEach-Object { Write-Host "    $_" }
if ($failed) { throw 'Smoke test failed (see build\out\smoke).' }
