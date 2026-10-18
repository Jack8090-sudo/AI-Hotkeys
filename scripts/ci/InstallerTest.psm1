<#
.SYNOPSIS
  Helpers for the installer CI jobs (.github/workflows/installer.yml, plan step S14).

.DESCRIPTION
  Windows PowerShell 5.1 compatible (the workflow runs them with `shell: powershell`).
  NEVER run Invoke-Setup / Invoke-Uninstall on a developer machine: the installer registers itself
  in HKCU and would overwrite the user's own installation. The workflows run them on GitHub-hosted
  runners only. The assertion and smoke functions are read-only (apart from the processes they start
  and kill themselves) and can be run against any folder.

  Usage in a workflow step:
      Import-Module .\scripts\ci\InstallerTest.psm1 -Force
      Invoke-Setup -Setup $exe -Arguments '/S /NOOLLAMA /D=C:\Temp Dir\AI Hotkeys Test'
      Assert-Installed -Dir 'C:\Temp Dir\AI Hotkeys Test' -Version 1.1.0 -Manifest build\out\manifest.txt -ProtectedAcl
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:AppName = 'AI-Hotkeys'
$script:AppKey = 'HKCU:\Software\AI-Hotkeys'
$script:UninstKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AI-Hotkeys'
$script:Publisher = 'AI-Hotkeys contributors'
$script:Url = 'https://github.com/Jack8090-sudo/AI-Hotkeys'

# Well-known SIDs that must never get write access to the install folder.
$script:BroadSids = @{
    'S-1-1-0'      = 'Everyone'
    'S-1-5-11'     = 'Authenticated Users'
    'S-1-5-32-545' = 'Users'
}

function Write-Ok([string]$Message) { Write-Host "    ok  $Message" }

function Get-DefaultInstallDir {
    return (Join-Path $env:LOCALAPPDATA "Programs\$script:AppName")
}

function Get-NormalDir([string]$Dir) {
    return [IO.Path]::GetFullPath($Dir).TrimEnd('\')
}

# ---------------------------------------------------------------------------
# Running the installer and the uninstaller
# ---------------------------------------------------------------------------

function Invoke-Process {
    # Start an exe with a raw argument string, wait for it and return its exit code.
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string]$Arguments = '',
        [int]$TimeoutSec = 900
    )
    Write-Host "> `"$FilePath`" $Arguments"
    if ($Arguments) { $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru }
    else { $p = Start-Process -FilePath $FilePath -PassThru }
    # Windows PowerShell 5.1: unless the handle is opened while the process is alive, ExitCode can
    # come back empty (same quirk as scripts\ci\ahk-run.ps1).
    $null = $p.Handle
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw "$FilePath did not exit within $TimeoutSec s"
    }
    $p.WaitForExit()
    $code = $p.ExitCode
    if ($null -eq $code -or "$code" -eq '') { throw "Could not read the exit code of $FilePath" }
    Write-Host "    exit code: $code"
    return [int]$code
}

function Invoke-Setup {
    # Silent install. NSIS takes /D= unquoted and last, so pass the arguments as one raw string,
    # e.g. '/S /NOOLLAMA /D=C:\Temp Dir\AI Hotkeys Test'.
    param(
        [Parameter(Mandatory = $true)][string]$Setup,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [int]$ExpectedExitCode = 0,
        [int]$TimeoutSec = 900
    )
    $code = Invoke-Process -FilePath (Resolve-Path -LiteralPath $Setup).Path -Arguments $Arguments -TimeoutSec $TimeoutSec
    if ($code -ne $ExpectedExitCode) { throw "Setup exited with $code, expected $ExpectedExitCode ($Arguments)" }
    Write-Ok "Setup $Arguments -> exit $code"
}

function Invoke-Uninstall {
    # Silent uninstall that waits for the real work and returns its exit code.
    # An NSIS uninstaller normally copies itself to %TEMP% and returns at once. Running our own copy
    # with _?=<dir> makes it run synchronously, and since the copy is outside <dir>, the uninstaller
    # can still delete <dir>\Uninstall.exe and the folder itself.
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [switch]$Purge,
        [int]$ExpectedExitCode = 0,
        [int]$TimeoutSec = 600
    )
    $Dir = Get-NormalDir $Dir
    $un = Join-Path $Dir 'Uninstall.exe'
    if (-not (Test-Path -LiteralPath $un)) { throw "No uninstaller at $un" }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('aih-un-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $copy = Join-Path $tmp 'Uninstall.exe'
        Copy-Item -LiteralPath $un -Destination $copy
        $argList = '/S'
        if ($Purge) { $argList += ' /PURGE' }
        $argList += " _?=$Dir"
        $code = Invoke-Process -FilePath $copy -Arguments $argList -TimeoutSec $TimeoutSec
    }
    finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($code -ne $ExpectedExitCode) { throw "Uninstall exited with $code, expected $ExpectedExitCode" }
    Write-Ok "Uninstall.exe $argList -> exit $code"
}

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

function Read-Manifest([string]$Path) {
    # "<sha256>  <install-relative path>" lines (build\out\manifest.txt); skips comments and the
    # "shortcut" lines of legacy manifests.
    $entries = New-Object 'Collections.Generic.List[object]'
    foreach ($line in [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $Path).Path)) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $m = [regex]::Match($line, '^([0-9a-f]{64})  (.+)$')
        if (-not $m.Success) { continue }
        $entries.Add([pscustomobject]@{ Sha256 = $m.Groups[1].Value; Path = $m.Groups[2].Value })
    }
    if ($entries.Count -lt 100) { throw "Manifest $Path has only $($entries.Count) entries" }
    return $entries
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-Shortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    try {
        $lnk = $shell.CreateShortcut($Path)
        return [pscustomobject]@{ Target = $lnk.TargetPath; Arguments = $lnk.Arguments; WorkingDirectory = $lnk.WorkingDirectory }
    }
    finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }
}

function Get-ShortcutPaths {
    $programs = Join-Path ([Environment]::GetFolderPath('Programs')) $script:AppName
    return [pscustomobject]@{
        ProgramsDir = $programs
        App         = Join-Path $programs 'AI-Hotkeys.lnk'
        Config      = Join-Path $programs 'Configuration.lnk'
        Prompts     = Join-Path $programs 'Edit prompts.lnk'
        Uninstall   = Join-Path $programs 'Uninstall.lnk'
        Startup     = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI-Hotkeys.lnk'
        Desktop     = Join-Path ([Environment]::GetFolderPath('Desktop')) 'AI-Hotkeys.lnk'
    }
}

function Assert-Shortcut([string]$Lnk, [string]$Target, [string]$Arguments) {
    if (-not (Test-Path -LiteralPath $Lnk)) { throw "Missing shortcut $Lnk" }
    $s = Get-Shortcut $Lnk
    if ($s.Target -ne $Target) { throw "$Lnk points to '$($s.Target)', expected '$Target'" }
    if ($s.Arguments -ne $Arguments) { throw "$Lnk has arguments '$($s.Arguments)', expected '$Arguments'" }
    if (-not (Test-Path -LiteralPath $s.Target)) { throw "$Lnk target does not exist: $($s.Target)" }
    $m = [regex]::Match($s.Arguments, '^"([^"]+)"$')
    if ($m.Success -and -not (Test-Path -LiteralPath $m.Groups[1].Value)) {
        throw "$Lnk argument does not exist: $($m.Groups[1].Value)"
    }
    Write-Ok "$(Split-Path $Lnk -Leaf) -> $Target $Arguments"
}

function Test-WriteRight([Security.AccessControl.FileSystemRights]$Rights) {
    $write = [Security.AccessControl.FileSystemRights]'WriteData, AppendData, WriteExtendedAttributes, WriteAttributes, Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership'
    if (($Rights -band $write) -ne 0) { return $true }
    # Generic rights as stored in inherit-only ACEs: GENERIC_ALL (0x10000000), GENERIC_WRITE (0x40000000)
    $raw = [int64]$Rights
    if (($raw -band 0x10000000) -ne 0 -or ($raw -band 0x40000000) -ne 0) { return $true }
    return $false
}

function Assert-NoBroadWriteAccess {
    # Fails if Everyone, Authenticated Users or Users have any write-type right on the folder or on
    # anything inside it. With -Protected, the folder must also have inheritance disabled (an explicit
    # ACL, as the installer sets for a folder outside the user profile).
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [switch]$Protected
    )
    $Dir = Get-NormalDir $Dir
    $acl = Get-Acl -LiteralPath $Dir
    if ($Protected -and -not $acl.AreAccessRulesProtected) { throw "$Dir still inherits its parent's ACL" }
    $items = @(Get-Item -LiteralPath $Dir -Force) + @(Get-ChildItem -LiteralPath $Dir -Recurse -Force)
    $bad = New-Object 'Collections.Generic.List[string]'
    foreach ($item in $items) {
        $rules = (Get-Acl -LiteralPath $item.FullName).GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
        foreach ($r in $rules) {
            $sid = $r.IdentityReference.Value
            if ($r.AccessControlType -ne 'Allow' -or -not $script:BroadSids.ContainsKey($sid)) { continue }
            if (Test-WriteRight $r.FileSystemRights) {
                $bad.Add("$($item.FullName): $($script:BroadSids[$sid]) has $($r.FileSystemRights)")
            }
        }
    }
    if ($bad.Count) {
        $bad | Select-Object -First 20 | ForEach-Object { Write-Host "::error::$_" }
        throw "$($bad.Count) ACE(s) give Everyone, Authenticated Users or Users write access under $Dir"
    }
    $what = 'inherited (profile) ACL'
    if ($acl.AreAccessRulesProtected) { $what = 'explicit ACL, inheritance disabled' }
    Write-Ok "no write access for Everyone, Authenticated Users or Users on $($items.Count) items ($what)"
}

function Assert-Installed {
    # Checks a fresh (or upgraded) installation: every manifest file with its hash, the extra files,
    # the HKCU registry values, the shortcut targets and the folder ACL.
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Manifest,
        [switch]$ProtectedAcl,
        # Upgrade tests: the user's config.ini is expected to differ from the example.
        [switch]$CustomConfig
    )
    $Dir = Get-NormalDir $Dir
    Write-Host "Checking the installation in $Dir"
    if (-not (Test-Path -LiteralPath $Dir -PathType Container)) { throw "$Dir does not exist" }

    # Files: everything in the build manifest, byte for byte (config.ini is user data).
    $entries = Read-Manifest $Manifest
    $missing = 0; $changed = 0
    foreach ($e in $entries) {
        if ($e.Path -eq 'config.ini') { continue }
        $p = Join-Path $Dir ($e.Path.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
            if ($missing -lt 20) { Write-Host "::error::missing $($e.Path)" }
            $missing++
            continue
        }
        if ((Get-Sha256 $p) -ne $e.Sha256) {
            if ($changed -lt 20) { Write-Host "::error::hash differs: $($e.Path)" }
            $changed++
        }
    }
    if ($missing -or $changed) { throw "$missing manifest file(s) missing and $changed changed in $Dir" }
    Write-Ok "$($entries.Count) manifest files present with the expected SHA-256"

    foreach ($rel in @('Uninstall.exe', 'config.ini', '.manifest', 'main.ahk', 'python\python.exe', 'ahk\AutoHotkey64.exe',
            'LICENSE', 'THIRD_PARTY_NOTICES.md', 'searxng\avvia_searxng.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Dir $rel) -PathType Leaf)) { throw "Missing $rel" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Dir 'work') -PathType Container)) { throw 'Missing work\' }
    if ([IO.File]::ReadAllText((Join-Path $Dir '.manifest')) -ne [IO.File]::ReadAllText((Resolve-Path -LiteralPath $Manifest).Path)) {
        throw '.manifest differs from the build manifest'
    }
    Write-Ok 'Uninstall.exe, .manifest (= build manifest), config.ini and work\ present'

    $cfg = Get-Sha256 (Join-Path $Dir 'config.ini')
    $example = Get-Sha256 (Join-Path $Dir 'config.example.ini')
    if (-not $CustomConfig) {
        if ($cfg -ne $example) { throw 'config.ini differs from config.example.ini on a fresh install' }
        Write-Ok 'config.ini is identical to config.example.ini'
    }

    # No developer files may have slipped into the install folder.
    foreach ($rel in @('tests', 'plans', 'scripts', 'tools', 'docs', 'installer', 'build', 'pyproject.toml', '.git')) {
        if (Test-Path -LiteralPath (Join-Path $Dir $rel)) { throw "Developer file in the install folder: $rel" }
    }

    # Registry (HKCU).
    $app = Get-ItemProperty -LiteralPath $script:AppKey
    if ((Get-NormalDir $app.InstallDir) -ne $Dir) { throw "InstallDir is '$($app.InstallDir)', expected '$Dir'" }
    $u = Get-ItemProperty -LiteralPath $script:UninstKey
    $expected = [ordered]@{
        DisplayName          = $script:AppName
        DisplayVersion       = $Version
        Publisher            = $script:Publisher
        DisplayIcon          = "$Dir\icon.ico"
        InstallLocation      = $Dir
        UninstallString      = "`"$Dir\Uninstall.exe`""
        QuietUninstallString = "`"$Dir\Uninstall.exe`" /S"
        URLInfoAbout         = $script:Url
        HelpLink             = $script:Url
        NoModify             = 1
        NoRepair             = 1
    }
    foreach ($k in $expected.Keys) {
        $actual = $null
        if ($u.PSObject.Properties[$k]) { $actual = $u.$k }
        if ("$actual" -ne "$($expected[$k])") { throw "Uninstall key value $k is '$actual', expected '$($expected[$k])'" }
    }
    if (-not $u.PSObject.Properties['EstimatedSize']) { throw 'EstimatedSize is missing' }
    $sizeKb = [int64]$u.EstimatedSize
    $realKb = [int64](((Get-ChildItem -LiteralPath $Dir -Recurse -Force -File | Measure-Object Length -Sum).Sum) / 1KB)
    if ($sizeKb -lt 10000 -or $sizeKb -gt ($realKb * 2 + 1024)) { throw "EstimatedSize $sizeKb KB is implausible (folder: $realKb KB)" }
    Write-Ok "HKCU uninstall key: $($expected.Count) values as expected, EstimatedSize $sizeKb KB (folder $realKb KB)"

    # Shortcuts (resolved through WScript.Shell).
    $s = Get-ShortcutPaths
    $ahk = "$Dir\ahk\AutoHotkey64.exe"
    $notepad = Join-Path $env:WINDIR 'notepad.exe'
    Assert-Shortcut $s.App $ahk "`"$Dir\main.ahk`""
    Assert-Shortcut $s.Config $notepad "`"$Dir\config.ini`""
    Assert-Shortcut $s.Prompts $notepad "`"$Dir\prompts.py`""
    Assert-Shortcut $s.Uninstall "$Dir\Uninstall.exe" ''
    Assert-Shortcut $s.Startup $ahk "`"$Dir\main.ahk`""
    if (Test-Path -LiteralPath $s.Desktop) { throw 'The desktop shortcut is optional and off by default, but it was created' }
    Write-Ok 'no desktop shortcut (optional section, off by default)'

    Assert-NoBroadWriteAccess -Dir $Dir -Protected:$ProtectedAcl
}

function Assert-Uninstalled {
    # -Kept: a default uninstall must leave exactly config.ini and work\. Otherwise (/PURGE) the
    # folder must be gone. Either way the registry keys and the shortcuts must be gone.
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [switch]$Kept
    )
    $Dir = Get-NormalDir $Dir
    if ($Kept) {
        if (-not (Test-Path -LiteralPath $Dir)) { throw "$Dir was removed, but config.ini and work\ should be kept" }
        $left = @(Get-ChildItem -LiteralPath $Dir -Force | ForEach-Object { $_.Name } | Sort-Object)
        if (($left -join '|') -ne 'config.ini|work') { throw "Left in ${Dir}: $($left -join ', ') (expected only config.ini and work)" }
        Write-Ok 'only config.ini and work\ remain'
    }
    else {
        if (Test-Path -LiteralPath $Dir) {
            $left = @(Get-ChildItem -LiteralPath $Dir -Force -Recurse | Select-Object -First 20 | ForEach-Object { $_.FullName })
            throw "$Dir still exists after /PURGE: $($left -join ', ')"
        }
        Write-Ok "$Dir is gone"
    }
    foreach ($k in @($script:AppKey, $script:UninstKey)) {
        if (Test-Path -LiteralPath $k) { throw "Registry key still present: $k" }
    }
    $s = Get-ShortcutPaths
    foreach ($p in @($s.App, $s.Config, $s.Prompts, $s.Uninstall, $s.Startup, $s.Desktop, $s.ProgramsDir)) {
        if (Test-Path -LiteralPath $p) { throw "Still present after uninstall: $p" }
    }
    Write-Ok 'registry keys and shortcuts removed'
}

function Assert-NoAppProcesses {
    # After an uninstall (or at the end of a job) no AutoHotkey or Python process may be left running.
    param([int]$WaitSec = 10)
    $deadline = (Get-Date).AddSeconds($WaitSec)
    do {
        $left = @(Get-CimInstance -ClassName Win32_Process | Where-Object { $_.Name -like 'AutoHotkey*' -or $_.Name -like 'python*' })
        if (-not $left.Count) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if ($left.Count) {
        $left | ForEach-Object { Write-Host "::error::left running: pid $($_.ProcessId) $($_.ExecutablePath) $($_.CommandLine)" }
        throw "$($left.Count) AutoHotkey/Python process(es) left running"
    }
    Write-Ok 'no AutoHotkey or Python processes running'
}

# ---------------------------------------------------------------------------
# Smoke tests with the bundled Python
# ---------------------------------------------------------------------------

function Get-FreePort {
    for ($i = 0; $i -lt 10; $i++) {
        $l = New-Object Net.Sockets.TcpListener ([Net.IPAddress]::Loopback), 0
        $l.Start()
        try { $port = $l.LocalEndpoint.Port } finally { $l.Stop() }
        if ($port -ne 8888 -and $port -ne 11434) { return $port }
    }
    throw 'No free port'
}

function Get-HttpStatus([string]$Url, [int]$TimeoutMs = 5000) {
    # Status code of a GET, or 0 if nothing answers. No proxy, no exception on 4xx/5xx.
    $req = [Net.HttpWebRequest]::Create($Url)
    $req.Proxy = $null
    $req.Timeout = $TimeoutMs
    $req.AllowAutoRedirect = $false
    try {
        $resp = $req.GetResponse()
        try { return [int]$resp.StatusCode } finally { $resp.Close() }
    }
    catch [Net.WebException] {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            $_.Exception.Response.Close()
            return $code
        }
        return 0
    }
}

function Stop-Tree([int]$ProcessId) {
    # Kill a process we started and its descendants (and nothing else).
    $all = @(Get-CimInstance -ClassName Win32_Process)
    $ids = New-Object 'Collections.Generic.List[int]'
    $ids.Add($ProcessId)
    for ($i = 0; $i -lt $ids.Count; $i++) {
        foreach ($p in $all) { if ($p.ParentProcessId -eq $ids[$i] -and -not $ids.Contains([int]$p.ProcessId)) { $ids.Add([int]$p.ProcessId) } }
    }
    for ($i = $ids.Count - 1; $i -ge 0; $i--) { Stop-Process -Id $ids[$i] -Force -ErrorAction SilentlyContinue }
}

function Start-Logged {
    # Start a process hidden with stdout/stderr redirected to files in $LogDir.
    param([string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory, [string]$LogDir, [string]$Name)
    $out = Join-Path $LogDir "$Name.out.txt"
    $err = Join-Path $LogDir "$Name.err.txt"
    $quoted = $ArgumentList | ForEach-Object { if ($_ -match '[\s"]') { '"' + $_.Replace('"', '\"') + '"' } else { $_ } }
    $p = Start-Process -FilePath $FilePath -ArgumentList ($quoted -join ' ') -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $p.Handle
    return [pscustomobject]@{ Process = $p; Out = $out; Err = $err; Name = $Name }
}

function Read-SharedText([string]$Path) {
    # The child process still has its redirected output open: read with FileShare.ReadWrite.
    $fs = New-Object IO.FileStream($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite, Delete')
    try { $sr = New-Object IO.StreamReader($fs); return $sr.ReadToEnd() } finally { $fs.Dispose() }
}

function Show-Logs($Started) {
    foreach ($f in @($Started.Out, $Started.Err)) {
        if (Test-Path -LiteralPath $f) {
            $t = Read-SharedText $f
            # The viewer and settings URLs carry their token: never print it.
            $t = [regex]::Replace($t, '\?t=[A-Za-z0-9_\-]+', '?t=<redacted>')
            if ($t.Trim()) { Write-Host "--- $($Started.Name) $(Split-Path $f -Leaf):"; Write-Host $t.TrimEnd() }
        }
    }
}

function Wait-TokenUrl($Started, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Started.Process.HasExited) { Show-Logs $Started; throw "$($Started.Name) exited early ($($Started.Process.ExitCode))" }
        if (Test-Path -LiteralPath $Started.Out) {
            $m = [regex]::Match((Read-SharedText $Started.Out), 'http://127\.0\.0\.1:(\d+)/\?t=([A-Za-z0-9_\-]+)')
            if ($m.Success) { return [pscustomobject]@{ Port = [int]$m.Groups[1].Value; Token = $m.Groups[2].Value } }
        }
        Start-Sleep -Milliseconds 250
    }
    Show-Logs $Started
    throw "$($Started.Name) printed no URL within $TimeoutSec s"
}

function Test-TokenServer($Started) {
    # The page must be 403 without the token and with a wrong one, and 200 with the right one.
    $u = Wait-TokenUrl $Started
    $base = "http://127.0.0.1:$($u.Port)"
    $none = Get-HttpStatus "$base/"
    $wrong = Get-HttpStatus "$base/?t=wrong-token"
    $right = Get-HttpStatus "$base/?t=$($u.Token)"
    if ($none -ne 403) { throw "$($Started.Name): GET / without the token returned $none, expected 403" }
    if ($wrong -ne 403) { throw "$($Started.Name): GET / with a wrong token returned $wrong, expected 403" }
    if ($right -ne 200) { throw "$($Started.Name): GET / with the token returned $right, expected 200" }
    Write-Ok "$($Started.Name) on port $($u.Port): 403 without token, 403 wrong token, 200 with token"
}

function Invoke-InstalledSmoke {
    # Smoke tests of an installed (or extracted) payload with its bundled Python:
    #   1. import every app module;
    #   2. viewer.py and settings.py with --no-browser: 403 without the token;
    #   3. searxng\avvia_searxng.py on a free port with a temp work dir: /healthz within 60 s.
    # Only the processes started here are killed. The install folder's work\ is not used by 2 and 3
    # except by the viewer/settings themselves (they read config.ini).
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [int]$SearxTimeoutSec = 60
    )
    $Dir = Get-NormalDir $Dir
    $py = Join-Path $Dir 'python\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { throw "No bundled Python at $py" }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('aih-smoke-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $started = New-Object 'Collections.Generic.List[object]'
    try {
        # 1. Imports. -B: no __pycache__ in the install folder. The cwd is neutral (the temp dir):
        #    python313._pth puts the install root on sys.path (D2).
        $code = 'import sys, qwen_client, prompt_loader, prompts, websearch, pages, config_edit, viewer, settings; ' +
        'assert sys.flags.isolated and sys.flags.ignore_environment, sys.flags; print("imports ok", sys.version.split()[0])'
        $p = Start-Logged -FilePath $py -ArgumentList @('-B', '-c', $code) -WorkingDirectory $tmp -LogDir $tmp -Name 'import'
        if (-not $p.Process.WaitForExit(60000)) { Stop-Tree $p.Process.Id; throw 'The import check did not finish in 60 s' }
        $p.Process.WaitForExit()
        Show-Logs $p
        if ($p.Process.ExitCode -ne 0) { throw "Importing the app with the bundled Python failed ($($p.Process.ExitCode))" }
        Write-Ok 'app modules import with the bundled Python (isolated mode)'

        # 2. viewer.py and settings.py.
        $in = Join-Path $tmp 'input.txt'
        $outFile = Join-Path $tmp 'output.txt'
        [IO.File]::WriteAllText($in, 'Smoke test input.', (New-Object Text.UTF8Encoding $false))
        [IO.File]::WriteAllText($outFile, 'Smoke test output.', (New-Object Text.UTF8Encoding $false))
        $v = Start-Logged -FilePath $py -ArgumentList @('-B', "$Dir\viewer.py", $in, $outFile, 'Smoke', '--no-browser') `
            -WorkingDirectory $Dir -LogDir $tmp -Name 'viewer'
        $started.Add($v)
        Test-TokenServer $v
        $s = Start-Logged -FilePath $py -ArgumentList @('-B', "$Dir\settings.py", '--no-browser') `
            -WorkingDirectory $Dir -LogDir $tmp -Name 'settings'
        $started.Add($s)
        Test-TokenServer $s

        # 3. SearXNG on a free port with its own work dir (never port 8888 or the install's work\).
        $port = Get-FreePort
        $work = Join-Path $tmp 'searx-work'
        New-Item -ItemType Directory -Path $work | Out-Null
        $sx = Start-Logged -FilePath $py -ArgumentList @('-B', "$Dir\searxng\avvia_searxng.py", '--port', "$port", '--work-dir', $work) `
            -WorkingDirectory $Dir -LogDir $tmp -Name 'searxng'
        $started.Add($sx)
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $status = 0
        while ($sw.Elapsed.TotalSeconds -lt $SearxTimeoutSec) {
            if ($sx.Process.HasExited) { break }
            $status = Get-HttpStatus "http://127.0.0.1:$port/healthz" 3000
            if ($status -eq 200) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($status -ne 200) {
            Show-Logs $sx
            $log = Join-Path $work 'searxng.log'
            if (Test-Path -LiteralPath $log) { Write-Host '--- searxng.log:'; Get-Content -LiteralPath $log -Tail 60 | Write-Host }
            throw "SearXNG did not answer /healthz with 200 within $SearxTimeoutSec s (last status $status)"
        }
        Write-Ok ("SearXNG /healthz 200 on port $port after {0:N1} s" -f $sw.Elapsed.TotalSeconds)
    }
    finally {
        foreach ($p in $started) { if (-not $p.Process.HasExited) { Stop-Tree $p.Process.Id } }
        foreach ($p in $started) { [void]$p.Process.WaitForExit(10000) }
        Start-Sleep -Milliseconds 500
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Upgrade test (current build over itself)
# ---------------------------------------------------------------------------

function Initialize-UpgradeFixture {
    # Turns a fresh install into "a previous version the user has customized":
    #   - config.ini modified (must be kept, I13), prompts_user.py added (must be kept),
    #   - prompts.py modified (must be saved as prompts.py.bak-<oldver>, D4),
    #   - an obsolete file listed in the old .manifest (must be removed, C30),
    #   - stale __pycache__ folders (must be purged; work\ is left alone).
    # Writes the expectations to $StateFile (JSON) for Assert-UpgradeResult.
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [Parameter(Mandatory = $true)][string]$StateFile
    )
    $Dir = Get-NormalDir $Dir
    $utf8 = New-Object Text.UTF8Encoding $false
    $cfgPath = Join-Path $Dir 'config.ini'
    $cfg = [IO.File]::ReadAllText($cfgPath)
    $cfg = [regex]::Replace($cfg, '(?m)^keep_alive\s*=.*$', 'keep_alive = 10m')
    $cfg += "`r`n; modified by the S14 upgrade test`r`n"
    [IO.File]::WriteAllText($cfgPath, $cfg, $utf8)

    [IO.File]::WriteAllText((Join-Path $Dir 'prompts_user.py'), "# user prompts (S14 upgrade test)`n", $utf8)
    $prompts = Join-Path $Dir 'prompts.py'
    [IO.File]::AppendAllText($prompts, "`n# customized by the S14 upgrade test`n", $utf8)

    $obsolete = 'actions/obsolete_s14.py'
    [IO.File]::WriteAllText((Join-Path $Dir ($obsolete.Replace('/', '\'))), "# shipped by the 'previous' version only`n", $utf8)
    $hash = Get-Sha256 (Join-Path $Dir ($obsolete.Replace('/', '\')))
    [IO.File]::AppendAllText((Join-Path $Dir '.manifest'), "$hash  $obsolete`n", $utf8)

    foreach ($d in @('__pycache__', 'actions\__pycache__', 'work\__pycache__')) {
        $p = Join-Path $Dir $d
        New-Item -ItemType Directory -Force -Path $p | Out-Null
        [IO.File]::WriteAllText((Join-Path $p 'stale.cpython-313.pyc'), 'stale', $utf8)
    }

    $state = [ordered]@{
        Config      = Get-Sha256 $cfgPath
        PromptsUser = Get-Sha256 (Join-Path $Dir 'prompts_user.py')
        Prompts     = Get-Sha256 $prompts
        Obsolete    = $obsolete
        OldVersion  = (Get-ItemProperty -LiteralPath $script:UninstKey).DisplayVersion
    }
    [IO.File]::WriteAllText($StateFile, ($state | ConvertTo-Json), $utf8)
    Write-Ok "upgrade fixture ready (old version $($state.OldVersion))"
}

function Assert-UpgradeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Dir,
        [Parameter(Mandatory = $true)][string]$StateFile
    )
    $Dir = Get-NormalDir $Dir
    $state = Get-Content -Raw -LiteralPath $StateFile | ConvertFrom-Json
    if ((Get-Sha256 (Join-Path $Dir 'config.ini')) -ne $state.Config) { throw 'The modified config.ini was not preserved' }
    Write-Ok 'modified config.ini preserved'
    $pu = Join-Path $Dir 'prompts_user.py'
    if (-not (Test-Path -LiteralPath $pu) -or (Get-Sha256 $pu) -ne $state.PromptsUser) { throw 'prompts_user.py was not preserved' }
    Write-Ok 'prompts_user.py preserved'
    $bak = Join-Path $Dir "prompts.py.bak-$($state.OldVersion)"
    if (-not (Test-Path -LiteralPath $bak)) { throw "No $bak for the customized prompts.py (D4)" }
    if ((Get-Sha256 $bak) -ne $state.Prompts) { throw "$bak does not hold the customized prompts.py" }
    Write-Ok "customized prompts.py saved as $(Split-Path $bak -Leaf)"
    if (Test-Path -LiteralPath (Join-Path $Dir ($state.Obsolete.Replace('/', '\')))) { throw "Obsolete file $($state.Obsolete) was not removed" }
    Write-Ok "obsolete $($state.Obsolete) removed"
    $caches = @(Get-ChildItem -LiteralPath $Dir -Recurse -Force -Directory -Filter '__pycache__' |
        Where-Object { -not $_.FullName.StartsWith("$Dir\work\", [StringComparison]::OrdinalIgnoreCase) })
    if ($caches.Count) { throw "__pycache__ not purged: $(($caches | Select-Object -First 5 | ForEach-Object { $_.FullName }) -join ', ')" }
    if (-not (Test-Path -LiteralPath (Join-Path $Dir 'work\__pycache__'))) { throw 'work\ was modified by the upgrade' }
    Write-Ok '__pycache__ purged outside work\, work\ untouched'
}

function Start-InstalledApp {
    # Starts main.ahk and settings.py from the install folder, as a user would have them running
    # during an upgrade or uninstall (C45: the installer must stop them).
    param([Parameter(Mandatory = $true)][string]$Dir)
    $Dir = Get-NormalDir $Dir
    $ahk = Start-Process -FilePath "$Dir\ahk\AutoHotkey64.exe" -ArgumentList "`"$Dir\main.ahk`"" -WorkingDirectory $Dir -PassThru
    $set = Start-Process -FilePath "$Dir\python\python.exe" -ArgumentList "-B `"$Dir\settings.py`" --no-browser" `
        -WorkingDirectory $Dir -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 5
    foreach ($p in @($ahk, $set)) {
        if ($p.HasExited) { throw "$($p.ProcessName) exited early ($($p.ExitCode))" }
    }
    Write-Ok "main.ahk (pid $($ahk.Id)) and settings.py (pid $($set.Id)) running from $Dir"
}

Export-ModuleMember -Function Invoke-Setup, Invoke-Uninstall, Invoke-Process, Assert-Installed, Assert-Uninstalled,
Assert-NoAppProcesses, Assert-NoBroadWriteAccess, Invoke-InstalledSmoke, Get-DefaultInstallDir, Get-FreePort,
Get-HttpStatus, Get-Shortcut, Stop-Tree, Read-Manifest, Initialize-UpgradeFixture, Assert-UpgradeResult,
Start-InstalledApp
