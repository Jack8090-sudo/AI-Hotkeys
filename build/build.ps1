<#
.SYNOPSIS
    Reproducible build of the AI-Hotkeys payload and installer (step S11).

.DESCRIPTION
    1. Requires a clean git tree (unless -AllowDirty) and reads the version from VERSION.
    2. Downloads every upstream pin in build\pins.json into build\cache\downloads and
       verifies its SHA-256; any mismatch fails the build.
    3. Exports the committed sources with `git archive HEAD` (line endings pinned by
       .gitattributes, independent of core.autocrlf) and assembles build\out\payload
       from an explicit allowlist:
           payload\app\      app files + searxng\ (wrapper, upstream searx, locked wheels)
           payload\python\   official embeddable CPython + python313._pth (decision D2)
           payload\ahk\      AutoHotkey64.exe + license.txt
           payload\config.ini  copy of config.example.ini
    4. Audits the payload (no developer config.ini, work\, __pycache__, tests, plans, ...).
    5. Writes build\out\manifest.txt ("<sha256>  <install-relative path>") and
       build\out\uninstall.nsh (generated uninstall list, consumed by S13b).
    6. Unless -SkipInstaller: runs makensis /DVERSION=<VERSION>.
    7. Writes build\out\SHA256SUMS.txt and runs the H16 smoke test (build\smoke.ps1)
       unless -SkipSmoke.

    The payload always reflects HEAD, never uncommitted edits: -AllowDirty only skips
    the clean-tree check.

.PARAMETER AllowMissingNotices
    Build even if THIRD_PARTY_NOTICES.md / licenses\ (step S12) are missing, or
    tools\licenses\check_notices.py fails. Never use it for a release.

.PARAMETER SkipInstaller
    Stop after the payload, manifest and uninstall.nsh (no NSIS).

.PARAMETER NsisTarget
    Override installer.nsi's Target in the staged copy (e.g. x86-unicode). The pinned official
    NSIS has only x86 stubs, so "Target amd64-unicode" cannot compile with it.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstaller -AllowMissingNotices
#>
param(
    [switch]$SkipInstaller,
    [switch]$AllowMissingNotices,
    [switch]$AllowDirty,
    [switch]$SkipSmoke,
    [string]$NsisTarget = '',
    [string]$HostPython = 'python'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$BuildDir = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $BuildDir '..')).Path
$Cache = Join-Path $BuildDir 'cache'
$Downloads = Join-Path $Cache 'downloads'
$Out = Join-Path $BuildDir 'out'
$Payload = Join-Path $Out 'payload'
$Utf8 = New-Object Text.UTF8Encoding $false
$Tar = Join-Path $env:SystemRoot 'System32\tar.exe'

function Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Invoke-Native([string]$Exe, [string[]]$ArgList) {
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

function Write-TextFile([string]$Path, [string[]]$Lines, [string]$Eol = "`n") {
    [IO.File]::WriteAllText($Path, (($Lines -join $Eol) + $Eol), $Utf8)
}

function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Get-RelPath([string]$Root, [string]$Full) {
    $Full.Substring($Root.TrimEnd('\').Length + 1).Replace('\', '/')
}

function Sort-Ordinal([string[]]$Items) {
    $arr = [string[]]@($Items)
    [Array]::Sort($arr, [StringComparer]::Ordinal)
    return , $arr
}

function Reset-Dir([string]$Path) {
    # Only ever wipes folders inside build\ (out\, cache\ subfolders).
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($BuildDir + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to wipe a folder outside build\: $full"
    }
    # Empties the folder rather than deleting it, so a shell sitting in it does not break the build.
    if (Test-Path -LiteralPath $full) {
        Get-ChildItem -LiteralPath $full -Force | Remove-Item -Recurse -Force
    }
    else { New-Item -ItemType Directory -Path $full -Force | Out-Null }
}

function Get-Pin([object]$Pin) {
    # Download (if not cached) and verify one pinned artifact. Returns the local path.
    if (-not (Test-Path -LiteralPath $Downloads)) { New-Item -ItemType Directory -Path $Downloads | Out-Null }
    $dst = Join-Path $Downloads $Pin.file
    if (-not (Test-Path -LiteralPath $dst)) {
        Write-Host "    downloading $($Pin.url)"
        $tmp = "$dst.part"
        # SourceForge answers PowerShell's browser-like default user agent with an HTML mirror page
        # instead of the file: identify as a plain download tool. Retried for transient network errors.
        for ($try = 1; ; $try++) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $Pin.url -OutFile $tmp -UserAgent 'Wget/1.21.4'
                break
            }
            catch {
                if ($try -ge 3) { throw }
                Write-Host "    retry $try after: $($_.Exception.Message)"
                Start-Sleep -Seconds (5 * $try)
            }
        }
        Move-Item -LiteralPath $tmp -Destination $dst -Force
    }
    $actual = Get-Sha256 $dst
    if ($actual -ne $Pin.sha256.ToLowerInvariant()) {
        $bad = "$dst.bad"
        Move-Item -LiteralPath $dst -Destination $bad -Force
        throw "SHA-256 mismatch for $($Pin.file): expected $($Pin.sha256), got $actual (moved to $bad)"
    }
    Write-Host "    ok  $($Pin.file)  $actual"
    return $dst
}

function Expand-ZipSafe([string]$Zip, [string]$Dest, [scriptblock]$Map) {
    # Extracts entries with a zip-slip guard. $Map turns an entry name into a relative
    # target path, or $null to skip the entry.
    $root = [IO.Path]::GetFullPath($Dest).TrimEnd('\') + '\'
    $za = [IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        foreach ($e in $za.Entries) {
            if ($e.FullName.EndsWith('/')) { continue }
            $rel = & $Map $e.FullName
            if (-not $rel) { continue }
            $target = [IO.Path]::GetFullPath((Join-Path $root $rel))
            if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe path in $Zip : $($e.FullName)"
            }
            $dir = Split-Path $target -Parent
            if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $false)
        }
    }
    finally { $za.Dispose() }
}

function Read-Lock([string]$Path) {
    # Parses a pip --generate-hashes lock: normalized name -> @{ Version; Hashes }.
    $lock = @{}
    $cur = $null
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match '^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)') {
            $name = ($Matches[1].ToLowerInvariant() -replace '[-_.]+', '-')
            $cur = @{ Version = $Matches[2]; Hashes = @{} }
            $lock[$name] = $cur
        }
        elseif ($cur -and $line -match '--hash=sha256:([0-9a-f]{64})') {
            $cur.Hashes[$Matches[1]] = $true
        }
    }
    return $lock
}

# ---------------------------------------------------------------------------
Step 'Checking the source tree'
$version = ([IO.File]::ReadAllText((Join-Path $Repo 'VERSION'))).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "VERSION must be MAJOR.MINOR.PATCH, got '$version'" }
$commit = (& git -C $Repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'git rev-parse failed' }
$commitTime = [DateTimeOffset]::FromUnixTimeSeconds([long](& git -C $Repo log -1 --format=%ct HEAD)).UtcDateTime
$dirty = & git -C $Repo status --porcelain
if ($dirty) {
    if ($AllowDirty) { Write-Warning "Uncommitted changes are NOT part of the payload (it is built from HEAD $commit)." }
    else { throw "The git tree is not clean (commit or use -AllowDirty):`n$($dirty -join "`n")" }
}
Write-Host "    AI-Hotkeys $version  commit $commit"

$pins = Get-Content -Raw -LiteralPath (Join-Path $BuildDir 'pins.json') | ConvertFrom-Json

Step 'Downloading and verifying pins'
$pyZip = Get-Pin $pins.python
$ahkZip = Get-Pin $pins.autohotkey
$sxTgz = Get-Pin $pins.searxng
$nsisZip = $null
if (-not $SkipInstaller) { $nsisZip = Get-Pin $pins.nsis }

Step 'Downloading and verifying SearXNG wheels'
$lockPath = Join-Path $Repo $pins.pypi.requirements
$lock = Read-Lock $lockPath
$wheelDir = Join-Path $Cache ('wheels\' + (Get-Sha256 $lockPath).Substring(0, 16))
if (-not (Test-Path -LiteralPath $wheelDir)) { New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null }
Invoke-Native $HostPython @('-I', '-m', 'pip', 'download', '--isolated', '--disable-pip-version-check',
    '--no-cache-dir', '--index-url', $pins.pypi.index_url, '--only-binary=:all:', '--no-deps',
    '--platform', $pins.pypi.platform, '--python-version', $pins.pypi.python_version,
    '--implementation', 'cp', '--abi', $pins.pypi.abi, '--require-hashes', '-r', $lockPath, '-d', $wheelDir, '-q')
# Independent re-check of every wheel against the lock (pip already enforced the hashes).
$wheels = @{}
foreach ($w in Get-ChildItem -LiteralPath $wheelDir -Filter '*.whl') {
    $parts = $w.BaseName.Split('-')
    $name = ($parts[0].ToLowerInvariant() -replace '[-_.]+', '-')
    if (-not $lock.ContainsKey($name)) { throw "Wheel not in the lock: $($w.Name)" }
    if ($parts[1] -ne $lock[$name].Version) { throw "Wheel version differs from the lock: $($w.Name)" }
    if (-not $lock[$name].Hashes.ContainsKey((Get-Sha256 $w.FullName))) { throw "Wheel hash not in the lock: $($w.Name)" }
    if ($wheels.ContainsKey($name)) { throw "Two wheels for $name in $wheelDir" }
    $wheels[$name] = $w.FullName
}
foreach ($name in $lock.Keys) { if (-not $wheels.ContainsKey($name)) { throw "No wheel downloaded for $name" } }
Write-Host "    ok  $($wheels.Count) wheels match build\requirements-searxng.txt"

# ---------------------------------------------------------------------------
Step 'Exporting committed sources (git archive HEAD)'
Reset-Dir $Out
$src = Join-Path $Out 'src'
New-Item -ItemType Directory -Path $src | Out-Null
$srcTar = Join-Path $Out 'src.tar'
Invoke-Native git @('-C', $Repo, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive', '--format=tar', '-o', $srcTar, 'HEAD')
Invoke-Native $Tar @('-xf', $srcTar, '-C', $src)
Remove-Item -LiteralPath $srcTar

Step 'Assembling payload\app from the allowlist'
$app = Join-Path $Payload 'app'
New-Item -ItemType Directory -Path $app -Force | Out-Null
$missingNotices = New-Object Collections.Generic.List[string]

function Copy-SrcFile([string]$Rel) {
    $from = Join-Path $src $Rel
    $to = Join-Path $app $Rel
    $dir = Split-Path $to -Parent
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item -LiteralPath $from -Destination $to
}

# Explicit allowlist. Kind: File (required unless Optional), RootGlob, Dir (recursive).
# Notice = owned by S12; missing is fatal unless -AllowMissingNotices.
$allow = @(
    @{ Kind = 'File'; Path = 'main.ahk' }
    @{ Kind = 'File'; Path = 'icon.ico' }
    @{ Kind = 'File'; Path = 'config.example.ini' }
    @{ Kind = 'File'; Path = 'LICENSE' }
    @{ Kind = 'File'; Path = 'THIRD_PARTY_NOTICES.md'; Notice = $true }
    @{ Kind = 'RootGlob'; Path = '*.py'; Exclude = @('test_*.py', 'conftest.py') }
    @{ Kind = 'Dir'; Path = 'actions'; Include = @('*.py') }
    @{ Kind = 'Dir'; Path = 'static' }
    @{ Kind = 'Dir'; Path = 'lib'; Include = @('*.ahk'); Optional = $true }
    @{ Kind = 'Dir'; Path = 'licenses'; Notice = $true }
    @{ Kind = 'File'; Path = 'searxng/avvia_searxng.py' }
    @{ Kind = 'File'; Path = 'searxng/settings.yml' }
    @{ Kind = 'File'; Path = 'searxng/LICENSE-searxng.txt' }
)
foreach ($a in $allow) {
    $full = Join-Path $src $a.Path
    $isNotice = $a.ContainsKey('Notice')
    $isOptional = $a.ContainsKey('Optional')
    switch ($a.Kind) {
        'File' {
            if (Test-Path -LiteralPath $full -PathType Leaf) { Copy-SrcFile $a.Path }
            elseif ($isNotice) { $missingNotices.Add($a.Path) }
            elseif (-not $isOptional) { throw "Allowlisted file missing from HEAD: $($a.Path)" }
        }
        'RootGlob' {
            foreach ($f in Get-ChildItem -LiteralPath $src -File -Filter $a.Path) {
                $skip = $false
                foreach ($x in $a.Exclude) { if ($f.Name -like $x) { $skip = $true } }
                if (-not $skip) { Copy-SrcFile $f.Name }
            }
        }
        'Dir' {
            if (-not (Test-Path -LiteralPath $full -PathType Container)) {
                if ($isNotice) { $missingNotices.Add($a.Path + '/') }
                elseif (-not $isOptional) { throw "Allowlisted folder missing from HEAD: $($a.Path)" }
                continue
            }
            foreach ($f in Get-ChildItem -LiteralPath $full -File -Recurse) {
                $rel = Get-RelPath $src $f.FullName
                if ($rel -match '(^|/)__pycache__/' -or $f.Name -like '*.py[co]') { continue }
                if ($a.ContainsKey('Include')) {
                    $ok = $false
                    foreach ($p in $a.Include) { if ($f.Name -like $p) { $ok = $true } }
                    if (-not $ok) { continue }
                }
                Copy-SrcFile $rel
            }
        }
    }
}
if ($missingNotices.Count -gt 0) {
    $msg = "Missing license notices (step S12): $($missingNotices -join ', ')"
    if ($AllowMissingNotices) { Write-Warning "$msg -- continuing because of -AllowMissingNotices (never for a release)." }
    else { throw "$msg. Use -AllowMissingNotices only for non-release builds." }
}

Step "Adding SearXNG $($pins.searxng.version_string) (upstream searx + locked wheels)"
$sxApp = Join-Path $app 'searxng\app'
New-Item -ItemType Directory -Path $sxApp -Force | Out-Null
$prefix = 'searxng-' + $pins.searxng.commit
Invoke-Native $Tar @('-xzf', $sxTgz, '-C', $sxApp, '--strip-components=1', "$prefix/searx")
# H17: the vendored v1.0.0 tree equals upstream except this generated file (searx/version.py freeze).
Write-TextFile (Join-Path $sxApp 'searx\version_frozen.py') @(
    '# SPDX-License-Identifier: AGPL-3.0-or-later'
    '# pylint: disable=missing-module-docstring'
    '# this file is generated automatically by searx/version.py'
    ''
    "VERSION_STRING = `"$($pins.searxng.version_string)`""
    "VERSION_TAG = `"$($pins.searxng.version_string)`""
    "DOCKER_TAG = `"$($pins.searxng.docker_tag)`""
    "GIT_URL = `"$($pins.searxng.git_url)`""
    "GIT_BRANCH = `"$($pins.searxng.git_branch)`""
)
$sxLib = Join-Path $app 'searxng\lib'
New-Item -ItemType Directory -Path $sxLib -Force | Out-Null
foreach ($name in (Sort-Ordinal @($wheels.Keys))) {
    # A wheel is a zip: unpacking it is the install (no scripts, no bytecode, no code run).
    Expand-ZipSafe $wheels[$name] $sxLib {
        param($n)
        if ($n -match '^[^/]+\.data/(purelib|platlib)/(.+)$') { return $Matches[2] }
        if ($n -match '^[^/]+\.data/') { return $null }   # scripts, headers, data
        return $n
    }
}

Step "Adding Python $($pins.python.version) (embeddable) and AutoHotkey $($pins.autohotkey.version)"
$pyDir = Join-Path $Payload 'python'
New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
Expand-ZipSafe $pyZip $pyDir { param($n) return $n }
# D2: stdlib zip, the interpreter folder and the install root. Isolated mode: no PYTHONPATH,
# no registry, no user site-packages (fixes the runtime part of C28).
Write-TextFile (Join-Path $pyDir 'python313._pth') @('python313.zip', '.', '..') "`r`n"
$ahkDir = Join-Path $Payload 'ahk'
New-Item -ItemType Directory -Path $ahkDir -Force | Out-Null
Expand-ZipSafe $ahkZip $ahkDir {
    param($n)
    if ($n -ceq 'AutoHotkey64.exe' -or $n -ceq 'license.txt') { return $n }
    return $null
}
Copy-Item -LiteralPath (Join-Path $src 'config.example.ini') -Destination (Join-Path $Payload 'config.ini')

# ---------------------------------------------------------------------------
Step 'Auditing the payload'
$problems = New-Object Collections.Generic.List[string]
$anyDepthDirs = @('__pycache__', 'work', '.git')
$rootForbidden = @('tests', 'plans', 'pyproject.toml', 'requirements-dev.txt', 'scripts', 'tools', 'build',
    'docs', 'installer', 'graphify-out', 'config.ini', 'python', 'ahk', 'Uninstall.exe')
foreach ($d in Get-ChildItem -LiteralPath $Payload -Directory -Recurse) {
    if ($anyDepthDirs -contains $d.Name) { $problems.Add('folder ' + (Get-RelPath $Payload $d.FullName)) }
}
foreach ($f in Get-ChildItem -LiteralPath $Payload -File -Recurse -Force) {
    $rel = Get-RelPath $Payload $f.FullName
    if ($f.Name -like '*.py[co]' -or $f.Name -like '.git*' -or $f.Name -like '*.log' -or $f.Name -like '*.pid') {
        $problems.Add("file $rel")
    }
    if ($rel -like 'app/test_*.py') { $problems.Add("test file $rel") }
}
foreach ($n in $rootForbidden) {
    if (Test-Path -LiteralPath (Join-Path $app $n)) { $problems.Add("app/$n") }
}
if ((Get-Sha256 (Join-Path $Payload 'config.ini')) -ne (Get-Sha256 (Join-Path $app 'config.example.ini'))) {
    $problems.Add('config.ini is not a copy of config.example.ini')
}
if ($problems.Count -gt 0) { throw "Payload audit failed:`n  $($problems -join "`n  ")" }
Write-Host '    ok  no developer config, work\, __pycache__, tests, plans or VCS files'

# Fixed timestamps (commit time) so NSIS, which stores file times, can be reproducible.
foreach ($i in Get-ChildItem -LiteralPath $Payload -Recurse -Force) { $i.LastWriteTimeUtc = $commitTime }

# ---------------------------------------------------------------------------
Step 'Writing manifest.txt and uninstall.nsh'
# Install-relative path of every payload file (payload\app\X installs to $INSTDIR\X).
$entries = @{}
foreach ($f in Get-ChildItem -LiteralPath $Payload -File -Recurse -Force) {
    $rel = Get-RelPath $Payload $f.FullName
    if ($rel.StartsWith('app/')) { $inst = $rel.Substring(4) } else { $inst = $rel }
    if ($entries.ContainsKey($inst)) { throw "Two payload files install to $inst" }
    $entries[$inst] = $f.FullName
}
$paths = Sort-Ordinal @($entries.Keys)
$manifest = New-Object Collections.Generic.List[string]
$manifest.Add("# AI-Hotkeys $version payload manifest (commit $commit). Generated by build\build.ps1.")
$manifest.Add('# <sha256>  <path relative to the install folder>. config.ini is user data after install.')
foreach ($p in $paths) { $manifest.Add((Get-Sha256 $entries[$p]) + '  ' + $p) }
$manifestPath = Join-Path $Out 'manifest.txt'
Write-TextFile $manifestPath $manifest

$nsh = New-Object Collections.Generic.List[string]
$nsh.Add("; AI-Hotkeys $version (commit $commit): generated by build\build.ps1, do not edit.")
$nsh.Add('; Removes exactly the files of this payload. config.ini (user data) is never listed.')
$nsh.Add('!macro AIH_UNINSTALL_PAYLOAD')
$dirs = @{}
$pyDirs = @{ '' = $true }
foreach ($p in $paths) {
    if ($p -ceq 'config.ini') { continue }
    $win = $p.Replace('/', '\').Replace('$', '$$')
    $nsh.Add("    Delete `"`$INSTDIR\$win`"")
    $parent = $p
    while ($parent.Contains('/')) {
        $parent = $parent.Substring(0, $parent.LastIndexOf('/'))
        $dirs[$parent] = $true
    }
    if ($p.EndsWith('.py')) {
        if ($p.Contains('/')) { $pyDirs[$p.Substring(0, $p.LastIndexOf('/'))] = $true } else { $pyDirs[''] = $true }
    }
}
foreach ($d in (Sort-Ordinal @($pyDirs.Keys))) {
    if ($d) { $nsh.Add("    RMDir /r `"`$INSTDIR\$($d.Replace('/', '\').Replace('$', '$$'))\__pycache__`"") }
    else { $nsh.Add('    RMDir /r "$INSTDIR\__pycache__"') }
}
# Deepest folders first; plain RMDir only removes folders that are now empty.
$dirList = Sort-Ordinal @($dirs.Keys)
[Array]::Reverse($dirList)
foreach ($d in $dirList) { $nsh.Add("    RMDir `"`$INSTDIR\$($d.Replace('/', '\').Replace('$', '$$'))`"") }
$nsh.Add('!macroend')
$nshPath = Join-Path $Out 'uninstall.nsh'
Write-TextFile $nshPath $nsh "`r`n"
Write-Host "    ok  $($paths.Count) files, $($dirs.Count) folders"

$checker = Join-Path $src 'tools\licenses\check_notices.py'
if (Test-Path -LiteralPath $checker) {
    Step 'Checking license notices against the manifest (S12)'
    & $HostPython -I -B $checker $manifestPath
    if ($LASTEXITCODE -ne 0) {
        if ($AllowMissingNotices) { Write-Warning "check_notices.py failed ($LASTEXITCODE) -- continuing because of -AllowMissingNotices." }
        else { throw "check_notices.py failed ($LASTEXITCODE)" }
    }
}

# ---------------------------------------------------------------------------
$release = @($manifestPath, $nshPath)
if (-not $SkipInstaller) {
    Step "Building the installer with NSIS $($pins.nsis.version)"
    $nsisDir = Join-Path $Cache "tools\nsis-$($pins.nsis.version)"
    $makensis = Join-Path $nsisDir 'makensis.exe'
    if (-not (Test-Path -LiteralPath $makensis)) {
        Reset-Dir $nsisDir
        $top = "nsis-$($pins.nsis.version)/"
        Expand-ZipSafe $nsisZip $nsisDir {
            param($n)
            if ($n.StartsWith($top)) { return $n.Substring($top.Length) }
            return $null
        }
    }
    # The script compiles next to payload\ (installer.nsi uses payload\... relative paths).
    foreach ($f in Get-ChildItem -LiteralPath (Join-Path $src 'installer\sorgente') -File) {
        if ($f.Extension -in @('.nsi', '.nsh', '.ps1', '.manifest')) { Copy-Item -LiteralPath $f.FullName -Destination $Out }
    }
    $nsi = Join-Path $Out 'installer.nsi'
    $nsiText = [IO.File]::ReadAllText($nsi, $Utf8)
    $unguarded = '(?m)^(\s*)!define\s+VERSION\s+"[^"]*"\s*$'
    if ($nsiText -match $unguarded -and $nsiText -notmatch '(?m)^\s*!ifndef\s+VERSION\b') {
        # Transitional: until S13a/S13b guard the define, /DVERSION would clash with it.
        Write-Warning 'installer.nsi defines VERSION unconditionally; the staged copy wraps it in !ifndef (fix in S13a).'
        $nsiText = [regex]::Replace($nsiText, $unguarded, "`$1!ifndef VERSION`r`n`$1!define VERSION `"$version`"`r`n`$1!endif")
        [IO.File]::WriteAllText($nsi, $nsiText, $Utf8)
    }
    # The official NSIS distribution only ships x86 stubs; installer.nsi asks for amd64-unicode
    # (the v1.0.0 Setup.exe was built with a non-official amd64 NSIS). Fail clearly unless the
    # caller picks a target the pinned NSIS supports.
    $targetRe = '(?m)^(\s*)Target\s+(\S+)\s*$'
    $m = [regex]::Match($nsiText, $targetRe)
    $target = 'x86-unicode'
    if ($m.Success) { $target = $m.Groups[2].Value }
    if ($NsisTarget -and $NsisTarget -ne $target) {
        Write-Warning "Staged installer.nsi: Target $target -> $NsisTarget (-NsisTarget; the decision belongs to S13a)."
        if ($m.Success) { $nsiText = [regex]::Replace($nsiText, $targetRe, "`$1Target $NsisTarget") }
        else { $nsiText = "Target $NsisTarget`r`n" + $nsiText }
        [IO.File]::WriteAllText($nsi, $nsiText, $Utf8)
        $target = $NsisTarget
    }
    if (-not (Test-Path -LiteralPath (Join-Path $nsisDir "Stubs\lzma_solid-$target"))) {
        throw ("The pinned NSIS $($pins.nsis.version) has no '$target' stubs (official builds are x86 only). " +
            "Re-run with -NsisTarget x86-unicode, or change Target in installer.nsi (S13a).")
    }
    Invoke-Native $makensis @('/V2', '/INPUTCHARSET', 'UTF8', "/DVERSION=$version", $nsi)
    $built = Join-Path $Out 'AI-Hotkeys-Setup.exe'
    $setup = Join-Path $Out "AI-Hotkeys-Setup-$version.exe"
    Move-Item -LiteralPath $built -Destination $setup -Force
    $release = @($setup) + $release
}

Remove-Item -LiteralPath $src -Recurse -Force

Step 'Writing SHA256SUMS.txt'
$sums = foreach ($r in $release) { (Get-Sha256 $r) + '  ' + (Split-Path $r -Leaf) }
Write-TextFile (Join-Path $Out 'SHA256SUMS.txt') $sums
$sums | ForEach-Object { Write-Host "    $_" }

if (-not $SkipSmoke) {
    Step 'Smoke test (H16)'
    & (Join-Path $BuildDir 'smoke.ps1') -Payload $Payload
}

Step "Done: $Out"
