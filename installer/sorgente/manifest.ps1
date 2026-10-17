# AI-Hotkeys installer helper: applies payload manifests during an upgrade or a migration.
# Run by installer.nsi through nsExec from $PLUGINSDIR (Windows PowerShell 5.1, 32- or 64-bit).
#
# Manifest format (build\out\manifest.txt, $INSTDIR\.manifest, legacy-1.0.0.manifest):
#   "# ..."                       comment
#   "<sha256>  <relative path>"   a payload file, forward slashes, relative to the install folder
#   "shortcut  {programs|startup|desktop}/<path>"   a shortcut created by that release (legacy only)
#
# Actions
#   Upgrade        -Dir <install> -Old <manifest> -New <manifest> [-OldVersion v]
#                  1. backs up a customized prompts.py as prompts.py.bak-<oldver> (D4)
#                  2. deletes files listed in Old but not in New (C30), then the folders this empties
#                  3. purges every __pycache__ folder
#   BackupPrompts  -Dir <folder holding prompts.py> -Old <manifest> [-New <manifest>] [-OldVersion v] [-Dest <folder>]
#   Shortcuts      -Dir <old install> -Old <manifest with shortcut lines>
#                  deletes the listed shortcuts whose target or arguments point into -Dir
#
# Never deleted: config.ini, work\, prompts_user.py, prompts.local.py, prompts.py.bak-*, *.backup*,
# .manifest, Uninstall.exe*. Nothing outside -Dir is ever touched; reparse points are not followed.
# Exit code: 0 = done, 1 = some items failed (details in the log), 2 = bad arguments or unreadable manifest.
param(
    [Parameter(Mandatory = $true)][ValidateSet('Upgrade', 'BackupPrompts', 'Shortcuts')][string]$Action,
    [Parameter(Mandatory = $true)][string]$Dir,
    [string]$Old = '',
    [string]$New = '',
    [string]$OldVersion = '',
    [string]$Dest = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Failures = 0

function Fail([string]$msg) { Write-Host "manifest.ps1: $msg"; exit 2 }
function Warn([string]$msg) { Write-Host "  ! $msg"; $script:Failures++ }

function Get-Root([string]$Path) {
    try { $full = [IO.Path]::GetFullPath($Path) } catch { Fail "invalid folder: $Path" }
    $full = $full.TrimEnd('\')
    if ($full.Length -lt 4 -or -not (Test-Path -LiteralPath $full -PathType Container)) { Fail "not an existing folder (or a drive root): $Path" }
    return $full
}

function Read-Manifest([string]$Path) {
    # Returns @{ Files = ordered list of @{Path; Hash}; Shortcuts = list; Version = string or '' }
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { Fail "manifest not found: $Path" }
    $files = New-Object Collections.Generic.List[object]
    $shortcuts = New-Object Collections.Generic.List[string]
    $version = ''
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match '^#\s*AI-Hotkeys\s+(\S+)\s+payload manifest') { if (-not $version) { $version = $Matches[1] }; continue }
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -match '^([0-9a-fA-F]{64})  (.+)$') {
            $rel = $Matches[2]
            if (-not (Test-RelPath $rel)) { Warn "unsafe path ignored: $rel"; continue }
            $files.Add(@{ Path = $rel; Hash = $Matches[1].ToLowerInvariant() })
        }
        elseif ($line -match '^shortcut  (\{(programs|startup|desktop)\}/.+)$') { $shortcuts.Add($Matches[1]) }
        else { Warn "unrecognized manifest line ignored: $line" }
    }
    return @{ Files = $files; Shortcuts = $shortcuts; Version = $version }
}

function Test-RelPath([string]$Rel) {
    if ($Rel.Contains('\') -or $Rel.Contains(':') -or $Rel.StartsWith('/')) { return $false }
    foreach ($seg in $Rel.Split('/')) { if ($seg -eq '' -or $seg -eq '.' -or $seg -eq '..') { return $false } }
    return $true
}

function Test-Protected([string]$Rel) {
    $r = $Rel.ToLowerInvariant()
    $name = $r.Substring($r.LastIndexOf('/') + 1)
    if ($r -eq 'config.ini' -or $r -eq '.manifest' -or $r -eq 'prompts_user.py' -or $r -eq 'prompts.local.py') { return $true }
    if ($r.StartsWith('work/')) { return $true }
    if ($name -like 'prompts.py.bak-*' -or $name -like '*.backup*' -or $name -like 'uninstall.exe*') { return $true }
    return $false
}

function Test-InsideNoReparse([string]$Root, [string]$Full) {
    # True when $Full is inside $Root and no folder between them is a reparse point.
    if (-not $Full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $p = [IO.Path]::GetDirectoryName($Full)
    while ($p.Length -gt $Root.Length) {
        if (Test-Path -LiteralPath $p) {
            if (([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
        }
        $p = [IO.Path]::GetDirectoryName($p)
    }
    return $true
}

function Get-SafeVersion([string]$v, [object]$m) {
    if (-not $v -and $m) { $v = $m.Version }
    if ($v -match '^[0-9A-Za-z][0-9A-Za-z.\-]{0,31}$') { return $v }
    return 'unknown'
}

function Backup-Prompts([string]$Root, [object]$OldM, [object]$NewM, [string]$Ver, [string]$DestRoot) {
    $src = Join-Path $Root 'prompts.py'
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { return }
    $cur = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToLowerInvariant()
    $oldHash = $null; $newHash = $null
    foreach ($f in $OldM.Files) { if ($f.Path -ceq 'prompts.py') { $oldHash = $f.Hash } }
    if ($NewM) { foreach ($f in $NewM.Files) { if ($f.Path -ceq 'prompts.py') { $newHash = $f.Hash } } }
    if ($cur -eq $oldHash -or $cur -eq $newHash) { Write-Host '  prompts.py is the shipped version: no backup needed'; return }
    $base = Join-Path $DestRoot "prompts.py.bak-$Ver"
    $target = $base
    $n = 2
    while (Test-Path -LiteralPath $target) {
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant() -eq $cur) {
            Write-Host "  customized prompts.py already saved as $([IO.Path]::GetFileName($target))"; return
        }
        $target = "$base-$n"; $n++
    }
    try {
        Copy-Item -LiteralPath $src -Destination $target
        Write-Host "  customized prompts.py saved as $target"
    }
    catch { Warn "could not save the customized prompts.py as ${target}: $($_.Exception.Message)" }
}

function Remove-Stale([string]$Root, [object]$OldM, [object]$NewM) {
    $keep = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($f in $NewM.Files) { [void]$keep.Add($f.Path) }
    $dirs = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $removed = 0
    foreach ($f in $OldM.Files) {
        $rel = $f.Path
        if ($keep.Contains($rel) -or (Test-Protected $rel)) { continue }
        $full = Join-Path $Root ($rel.Replace('/', '\'))
        $parent = $rel
        while ($parent.Contains('/')) { $parent = $parent.Substring(0, $parent.LastIndexOf('/')); [void]$dirs.Add($parent) }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
        if (-not (Test-InsideNoReparse $Root $full)) { Warn "skipped (outside the folder or behind a link): $rel"; continue }
        try { Remove-Item -LiteralPath $full -Force; $removed++ }
        catch { Warn "could not delete ${rel}: $($_.Exception.Message)" }
    }
    Write-Host "  removed $removed obsolete file(s)"
    # Deepest first; only folders that are now empty (and never work\).
    $list = @($dirs) | Sort-Object -Property @{ Expression = { $_.Split('/').Count } } -Descending
    foreach ($d in $list) {
        if ($d -ieq 'work' -or $d.ToLowerInvariant().StartsWith('work/')) { continue }
        $full = Join-Path $Root ($d.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $full -PathType Container)) { continue }
        if (-not (Test-InsideNoReparse $Root (Join-Path $full 'x'))) { continue }
        if (@(Get-ChildItem -LiteralPath $full -Force).Count -eq 0) {
            try { Remove-Item -LiteralPath $full -Force } catch { Warn "could not remove folder ${d}: $($_.Exception.Message)" }
        }
    }
}

function Remove-Pycache([string]$Root) {
    # Walks the tree without following reparse points; skips work\.
    $stack = New-Object Collections.Generic.Stack[string]
    $stack.Push($Root)
    $count = 0
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        foreach ($sub in [IO.Directory]::GetDirectories($d)) {
            if (([IO.File]::GetAttributes($sub) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            $name = [IO.Path]::GetFileName($sub)
            if ($d -eq $Root -and $name -ieq 'work') { continue }
            if ($name -ieq '__pycache__') {
                try { Remove-Item -LiteralPath $sub -Recurse -Force; $count++ }
                catch { Warn "could not remove $sub : $($_.Exception.Message)" }
            }
            else { $stack.Push($sub) }
        }
    }
    Write-Host "  purged $count __pycache__ folder(s)"
}

function Remove-Shortcuts([string]$Root, [object]$OldM) {
    $shell = New-Object -ComObject WScript.Shell
    $bases = @{
        '{programs}' = [Environment]::GetFolderPath('Programs')
        '{startup}'  = [Environment]::GetFolderPath('Startup')
        '{desktop}'  = [Environment]::GetFolderPath('DesktopDirectory')
    }
    $needle = ($Root + '\').ToLowerInvariant()
    $folders = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($s in $OldM.Shortcuts) {
        $token = $s.Substring(0, $s.IndexOf('}') + 1)
        $rest = $s.Substring($token.Length + 1)
        if (-not (Test-RelPath $rest) -or -not $bases[$token]) { Warn "unsafe shortcut entry ignored: $s"; continue }
        $lnk = Join-Path $bases[$token] ($rest.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $lnk -PathType Leaf)) { continue }
        try {
            $sc = $shell.CreateShortcut($lnk)
            $refs = ([string]$sc.TargetPath + ' ' + [string]$sc.Arguments).ToLowerInvariant()
            if ($refs.Contains($needle)) {
                Remove-Item -LiteralPath $lnk -Force
                Write-Host "  removed shortcut $lnk"
                if ($rest.Contains('/')) { [void]$folders.Add(([IO.Path]::GetDirectoryName($lnk))) }
            }
            else { Write-Host "  kept shortcut $lnk (it does not point into $Root)" }
        }
        catch { Warn "could not process shortcut ${lnk}: $($_.Exception.Message)" }
    }
    foreach ($f in $folders) {
        if ((Test-Path -LiteralPath $f) -and @(Get-ChildItem -LiteralPath $f -Force).Count -eq 0) {
            try { Remove-Item -LiteralPath $f -Force } catch { Warn "could not remove empty folder $f" }
        }
    }
}

try {
    $root = Get-Root $Dir
    switch ($Action) {
        'Upgrade' {
            $oldM = Read-Manifest $Old
            $newM = Read-Manifest $New
            $ver = Get-SafeVersion $OldVersion $oldM
            Write-Host "Upgrading $root (previous version $ver)"
            Backup-Prompts $root $oldM $newM $ver $root
            Remove-Stale $root $oldM $newM
            Remove-Pycache $root
        }
        'BackupPrompts' {
            $oldM = Read-Manifest $Old
            $newM = $null
            if ($New) { $newM = Read-Manifest $New }
            $destRoot = $root
            if ($Dest) { $destRoot = Get-Root $Dest }
            Backup-Prompts $root $oldM $newM (Get-SafeVersion $OldVersion $oldM) $destRoot
        }
        'Shortcuts' {
            Remove-Shortcuts $root (Read-Manifest $Old)
        }
    }
}
catch {
    Write-Host "manifest.ps1: $($_.Exception.Message)"
    exit 2
}
if ($script:Failures -gt 0) { Write-Host "manifest.ps1: $($script:Failures) item(s) failed"; exit 1 }
exit 0
