<#
.SYNOPSIS
  Run AutoHotkey on a script and check its exit code (CI, step S2). Windows PowerShell 5.1 compatible.
.DESCRIPTION
  AutoHotkey64.exe is a GUI-subsystem exe, so a plain call does not wait or return an exit code.
  This uses Start-Process -Wait -PassThru with stdout/stderr redirected to temp files (plan §0.6).
  /ErrorStdOut sends load-time errors to stdout instead of a message box, so nothing can hang on a dialog.
.PARAMETER Validate
  Pass /validate: load and syntax-check the script, then exit without running it (hypothesis H13).
.PARAMETER ExpectFailure
  Succeed only if AutoHotkey exits non-zero (negative test on a deliberately broken fixture).
.EXAMPLE
  scripts\ci\ahk-run.ps1 -Ahk ahk\AutoHotkey64.exe -Script main.ahk -Validate
  scripts\ci\ahk-run.ps1 -Ahk ahk\AutoHotkey64.exe -Script scripts\ci\fixtures\broken.ahk -Validate -ExpectFailure
  scripts\ci\ahk-run.ps1 -Ahk ahk\AutoHotkey64.exe -Script tests\ahk\run.ahk
#>
param(
    [Parameter(Mandatory = $true)][string]$Ahk,
    [Parameter(Mandatory = $true)][string]$Script,
    [switch]$Validate,
    [switch]$ExpectFailure,
    [int]$TimeoutSeconds = 300
)
$ErrorActionPreference = 'Stop'

$ahkPath = (Resolve-Path -LiteralPath $Ahk).Path
$scriptPath = (Resolve-Path -LiteralPath $Script).Path
$out = [IO.Path]::GetTempFileName()
$err = [IO.Path]::GetTempFileName()
$argList = @('/ErrorStdOut')
if ($Validate) { $argList += '/validate' }
$argList += ('"' + $scriptPath + '"')

Write-Host "> $ahkPath $($argList -join ' ')"
$p = Start-Process -FilePath $ahkPath -ArgumentList $argList -PassThru -NoNewWindow `
    -RedirectStandardOutput $out -RedirectStandardError $err
# Windows PowerShell 5.1 quirk: unless the process handle is opened while the process is alive,
# ExitCode comes back empty after a redirected Start-Process. Touching .Handle caches it.
$null = $p.Handle
if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $p.Id -Force
    throw "AutoHotkey did not exit within $TimeoutSeconds s"
}
$p.WaitForExit()
$code = $p.ExitCode
$text = (Get-Content -LiteralPath $out -Raw -Encoding UTF8) + (Get-Content -LiteralPath $err -Raw -Encoding UTF8)
Remove-Item -LiteralPath $out, $err -Force
if ($text) { Write-Host $text.TrimEnd() }
Write-Host "exit code: $code"
if ($null -eq $code -or "$code" -eq '') { Write-Host "::error::could not read the AutoHotkey exit code"; exit 1 }

if ($ExpectFailure) {
    if ($code -eq 0) { Write-Host "::error::expected a non-zero exit code for $Script, got 0"; exit 1 }
    Write-Host "ok: $Script failed as expected"
    exit 0
}
if ($code -ne 0) { Write-Host "::error::AutoHotkey exited $code for $Script"; exit 1 }
exit 0
