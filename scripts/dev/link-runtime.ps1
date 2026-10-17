<#
.SYNOPSIS
    Link the gitignored AI-Hotkeys runtime (portable Python, AutoHotkey, vendored SearXNG)
    into a git worktree, so tests and the app can run there.

.DESCRIPTION
    Git worktrees only contain tracked files. This script creates directory junctions
    (no admin rights needed) from an existing install or checkout:
        python\              -> <From>\python
        searxng\app, \lib    -> <From>\searxng\app, \lib
    and copies ahk\AutoHotkey64.exe (a single file: junctions only work for folders).
    Nothing is written into <From>.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\link-runtime.ps1 -From C:\AI-Hotkeys
#>
param(
    [Parameter(Mandatory = $true)][string]$From,
    [string]$To = ''
)

$ErrorActionPreference = 'Stop'
# $PSScriptRoot is empty inside param() on Windows PowerShell 5.1: resolve the default here
if (-not $To) { $To = Join-Path $PSScriptRoot '..\..' }
$From = (Resolve-Path $From).Path.TrimEnd('\')
$To = (Resolve-Path $To).Path.TrimEnd('\')

if ($From -ieq $To) {
    throw "Source and target are the same folder ($To): run this inside a worktree, not in the main checkout."
}

function Link-Dir([string]$rel) {
    $src = Join-Path $From $rel
    $dst = Join-Path $To $rel
    if (-not (Test-Path $src -PathType Container)) {
        Write-Warning "Missing in source, skipped: $rel"
        return
    }
    if (Test-Path $dst) {
        Write-Host "Already present, left as is: $rel"
        return
    }
    $parent = Split-Path $dst -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    New-Item -ItemType Junction -Path $dst -Target $src | Out-Null
    Write-Host "Linked: $rel -> $src"
}

Link-Dir 'python'
Link-Dir 'searxng\app'
Link-Dir 'searxng\lib'

$ahkSrc = Join-Path $From 'ahk\AutoHotkey64.exe'
$ahkDst = Join-Path $To 'ahk\AutoHotkey64.exe'
if ((Test-Path $ahkSrc) -and -not (Test-Path $ahkDst)) {
    Copy-Item $ahkSrc $ahkDst
    Write-Host "Copied: ahk\AutoHotkey64.exe"
}
elseif (-not (Test-Path $ahkSrc)) {
    Write-Warning "Missing in source, skipped: ahk\AutoHotkey64.exe"
}
