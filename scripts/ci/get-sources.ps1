<#
.SYNOPSIS
  Download the third-party source archives attached to a Release and verify their SHA-256 (S14).

.DESCRIPTION
  Writes into -Dest (normally build\out\third-party-sources):
    - the AutoHotkey source zip pinned in scripts\ci\third-party-sources.json, whose version must
      equal build\pins.json autohotkey.version (the binary that is shipped);
    - the SearXNG tarball pinned in build\pins.json (the same file the build unpacks).
  Any hash mismatch fails and deletes the file. A file already in -CacheDir (build\cache\downloads)
  with the right hash is reused instead of downloaded. Windows PowerShell 5.1 compatible.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci\get-sources.ps1 -Dest build\out\third-party-sources
#>
param(
    [Parameter(Mandatory = $true)][string]$Dest,
    [string]$CacheDir = ''
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pins = Get-Content -Raw -LiteralPath (Join-Path $repo 'build\pins.json') | ConvertFrom-Json
$src = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'third-party-sources.json') | ConvertFrom-Json
if (-not $CacheDir) { $CacheDir = Join-Path $repo 'build\cache\downloads' }

function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Get-Verified([string]$Url, [string]$Sha256, [string]$Target, [string]$CacheName) {
    if ($Sha256 -notmatch '^[0-9a-f]{64}$') { throw "Bad SHA-256 pin for $Url" }
    if (-not $Url.StartsWith('https://')) { throw "Not an https URL: $Url" }
    $cached = $null
    if ($CacheName) { $cached = Join-Path $CacheDir $CacheName }
    if ($cached -and (Test-Path -LiteralPath $cached) -and (Get-Sha256 $cached) -eq $Sha256) {
        Copy-Item -LiteralPath $cached -Destination $Target -Force
        Write-Host "    reused $cached"
    }
    else {
        Write-Host "    downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $Target -UseBasicParsing
    }
    $actual = Get-Sha256 $Target
    if ($actual -ne $Sha256) {
        Remove-Item -LiteralPath $Target -Force
        throw "SHA-256 mismatch for ${Url}: expected $Sha256, got $actual"
    }
    Write-Host "    ok  $actual  $(Split-Path $Target -Leaf)"
}

if ($src.autohotkey.version -ne $pins.autohotkey.version) {
    throw "third-party-sources.json has AutoHotkey $($src.autohotkey.version), but the build ships $($pins.autohotkey.version)"
}
if ($src.searxng.asset -notlike "*$($pins.searxng.commit)*") {
    throw "third-party-sources.json names $($src.searxng.asset), but the build pins SearXNG $($pins.searxng.commit)"
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$Dest = (Resolve-Path -LiteralPath $Dest).Path
Write-Host "AutoHotkey $($src.autohotkey.version) source ($($src.autohotkey.license))"
Get-Verified $src.autohotkey.url $src.autohotkey.sha256 (Join-Path $Dest $src.autohotkey.asset) ''
Write-Host "SearXNG $($pins.searxng.commit) source ($($src.searxng.license))"
Get-Verified $pins.searxng.url $pins.searxng.sha256 (Join-Path $Dest $src.searxng.asset) $pins.searxng.file
