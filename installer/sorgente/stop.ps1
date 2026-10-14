# Chiude AI-Hotkeys (AutoHotkey con main.ahk e Python del programma) prima di aggiornare/disinstallare
param([string]$Dir)
$main = (Join-Path $Dir 'main.ahk').ToLower()
$py   = (Join-Path $Dir 'python').ToLower()
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -like 'AutoHotkey*' -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($main)) -or
    ($_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($py))
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
