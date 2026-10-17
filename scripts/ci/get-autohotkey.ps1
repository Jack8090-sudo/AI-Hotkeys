<#
.SYNOPSIS
  Download the AutoHotkey build pinned in build/pins.json, verify its SHA-256 and extract it (CI, step S2).
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci\get-autohotkey.ps1 -Dest $env:RUNNER_TEMP\ahk
  Writes <Dest>\AutoHotkey64.exe and prints its path. Windows PowerShell 5.1 compatible.
#>
param(
    [Parameter(Mandatory = $true)][string]$Dest,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$pins = Join-Path $PSScriptRoot 'pins.py'
function Get-Pin([string]$Field) {
    $v = & $Python -I $pins autohotkey $Field
    if ($LASTEXITCODE -ne 0 -or -not $v) { throw "pins.py autohotkey $Field failed ($LASTEXITCODE)" }
    return ([string]$v).Trim()
}
$url = Get-Pin 'url'
$sha = Get-Pin 'sha256'
$file = Get-Pin 'file'
$version = Get-Pin 'version'

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$zip = Join-Path $Dest $file
Write-Host "Downloading AutoHotkey $version from $url"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $sha) {
    Remove-Item -LiteralPath $zip -Force
    throw "SHA-256 mismatch for ${file}: expected $sha, got $actual"
}
Write-Host "SHA-256 ok: $actual"

$extract = Join-Path $Dest 'dist'
if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
Expand-Archive -LiteralPath $zip -DestinationPath $extract
$exe = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'AutoHotkey64.exe' | Select-Object -First 1
if (-not $exe) { throw "AutoHotkey64.exe not found in $file" }
$target = Join-Path $Dest 'AutoHotkey64.exe'
Copy-Item -LiteralPath $exe.FullName -Destination $target -Force
$fv = (Get-Item -LiteralPath $target).VersionInfo.FileVersion
Write-Host "AutoHotkey64.exe file version: $fv"
if ($fv -notlike "$version*") { throw "AutoHotkey64.exe reports version '$fv', pin says $version" }
Write-Output $target
