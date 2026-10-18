<#
.SYNOPSIS
  Download the third-party source archives attached to a Release and verify their SHA-256 (S14, LIC1).

.DESCRIPTION
  Reads scripts\ci\third-party-sources.json and writes every archive it lists into -Dest (normally
  build\out\third-party-sources), under the entry's 'asset' name. Currently:
    - AutoHotkey 2.0.19 source (GPL-2.0-only); its version must equal build\pins.json autohotkey.version;
    - SearXNG at the pinned commit (AGPL-3.0-or-later); url and sha256 come from build\pins.json, the
      same tarball the build unpacks;
    - lxml sdist; its version must equal the lxml pin in build\requirements-searxng.txt and in
      tools\licenses\components.json;
    - GNU libiconv (LGPL-2.1-or-later, statically linked into lxml's Windows wheel), its MSVC build tree
      and the libxml2-win-binaries build scripts; the libiconv version must match components.json.
  Any hash mismatch fails and deletes the file. A file already in -CacheDir (build\cache\downloads)
  with the right hash is reused instead of downloaded. -Dest must not contain other files: release.yml
  attaches everything in it. Windows PowerShell 5.1 compatible.

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
$components = Get-Content -Raw -LiteralPath (Join-Path $repo 'tools\licenses\components.json') | ConvertFrom-Json
$lockText = Get-Content -Raw -LiteralPath (Join-Path $repo 'build\requirements-searxng.txt')
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

# --- Consistency with what the build actually ships -------------------------------------------
$entries = @($src.archives)
if ($entries.Count -eq 0) { throw 'third-party-sources.json lists no archives' }
$byId = @{}
$assets = @{}
foreach ($e in $entries) {
    if (-not $e.id -or -not $e.asset -or -not $e.license -or -not $e.version) { throw "Incomplete entry in third-party-sources.json: $($e | ConvertTo-Json -Compress)" }
    if ($e.asset -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $e.asset.Contains('..')) { throw "Asset name is not a plain file name: $($e.asset)" }
    if ($byId.ContainsKey($e.id)) { throw "Duplicate id $($e.id)" }
    if ($assets.ContainsKey($e.asset.ToLowerInvariant())) { throw "Duplicate asset $($e.asset)" }
    $byId[$e.id] = $e
    $assets[$e.asset.ToLowerInvariant()] = $true
}
foreach ($id in @('autohotkey', 'searxng', 'lxml', 'libiconv')) {
    if (-not $byId.ContainsKey($id)) { throw "third-party-sources.json has no '$id' entry" }
}

if ($byId['autohotkey'].version -ne $pins.autohotkey.version) {
    throw "third-party-sources.json has AutoHotkey $($byId['autohotkey'].version), but the build ships $($pins.autohotkey.version)"
}
if ($byId['searxng'].version -ne $pins.searxng.commit -or $byId['searxng'].asset -notlike "*$($pins.searxng.commit)*") {
    throw "third-party-sources.json names SearXNG $($byId['searxng'].version), but the build pins $($pins.searxng.commit)"
}
$m = [regex]::Match($lockText, '(?m)^lxml==([^\s\\]+)')
if (-not $m.Success) { throw 'No lxml pin in build\requirements-searxng.txt' }
$lxmlLock = $m.Groups[1].Value
$lxmlNotice = $components.python_packages.extra_notices.lxml
if ($byId['lxml'].version -ne $lxmlLock) {
    throw "third-party-sources.json has lxml $($byId['lxml'].version), but build\requirements-searxng.txt pins $lxmlLock"
}
if ($lxmlNotice.version -ne $lxmlLock) {
    throw "components.json verified lxml $($lxmlNotice.version), but build\requirements-searxng.txt pins $lxmlLock"
}
$iconvTag = "libiconv $($byId['libiconv'].version) "
if (-not $lxmlNotice.bundles.Contains($iconvTag)) {
    throw "components.json says lxml bundles '$($lxmlNotice.bundles)', which does not name '$($iconvTag.Trim())'"
}

# --- Download and verify -------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$Dest = (Resolve-Path -LiteralPath $Dest).Path
foreach ($e in $entries) {
    Write-Host "$($e.name) $($e.version) ($($e.license))"
    $target = Join-Path $Dest $e.asset
    $hasPins = $null -ne $e.PSObject.Properties['from_pins']
    if ($hasPins) {
        $p = $pins.($e.from_pins)
        if (-not $p) { throw "build\pins.json has no '$($e.from_pins)' entry" }
        Get-Verified $p.url $p.sha256 $target $p.file
    }
    else {
        Get-Verified $e.url $e.sha256 $target $e.asset
    }
}
$extra = @(Get-ChildItem -LiteralPath $Dest -File | Where-Object { -not $assets.ContainsKey($_.Name.ToLowerInvariant()) })
if ($extra.Count -gt 0) { throw "Unexpected files in ${Dest}: $(($extra | ForEach-Object Name) -join ', ')" }
Write-Host "All $($entries.Count) source archives verified in $Dest"
