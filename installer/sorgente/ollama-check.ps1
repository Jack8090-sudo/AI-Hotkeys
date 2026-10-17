# AI-Hotkeys installer helper: is the Ollama model available? (C44)
#   1. the model's manifest file on disk (%OLLAMA_MODELS% or %USERPROFILE%\.ollama\models), which
#      works even when the Ollama server is not running
#   2. otherwise GET http://127.0.0.1:11434/api/tags (no proxy, 3 s timeout)
# Exit code: 0 = model present, 10 = server running but model missing,
#            11 = server not reachable and no manifest file found, 2 = bad -Model.
param([Parameter(Mandatory = $true)][string]$Model)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# name[:tag], name may be "namespace/name"; no host part, no path tricks
if ($Model -notmatch '^(?:([a-z0-9][a-z0-9._-]*)/)?([a-z0-9][a-z0-9._-]*)(?::([A-Za-z0-9][A-Za-z0-9._-]*))?$') {
    Write-Host "ollama-check.ps1: unsupported model name: $Model"
    exit 2
}
$ns = 'library'
if ($Matches[1]) { $ns = $Matches[1] }
$name = $Matches[2]
$tag = 'latest'
if ($Matches[3]) { $tag = $Matches[3] }

$roots = @()
if ($env:OLLAMA_MODELS) { $roots += $env:OLLAMA_MODELS }
$roots += (Join-Path $env:USERPROFILE '.ollama\models')
foreach ($r in $roots) {
    $m = Join-Path $r "manifests\registry.ollama.ai\$ns\$name\$tag"
    if (Test-Path -LiteralPath $m -PathType Leaf) { Write-Host "Model $Model found: $m"; exit 0 }
}

try {
    $req = [Net.WebRequest]::Create('http://127.0.0.1:11434/api/tags')
    $req.Proxy = $null
    $req.Timeout = 3000
    $resp = $req.GetResponse()
    try {
        $reader = New-Object IO.StreamReader($resp.GetResponseStream())
        $body = $reader.ReadToEnd()
    }
    finally { $resp.Close() }
}
catch {
    Write-Host "Ollama server not reachable on 127.0.0.1:11434 and no manifest for $Model on disk."
    exit 11
}

$wanted = @("$name`:$tag")
if ($ns -ne 'library') { $wanted = @("$ns/$name`:$tag") }
try { $tags = $body | ConvertFrom-Json } catch { $tags = $null }
if ($tags -and $tags.PSObject.Properties['models']) {
    foreach ($mo in @($tags.models)) {
        foreach ($field in @('name', 'model')) {
            if ($mo.PSObject.Properties[$field] -and ($wanted -contains [string]$mo.$field)) {
                Write-Host "Model $Model found (Ollama server)."
                exit 0
            }
        }
    }
}
Write-Host "Ollama server is running, but model $Model is not downloaded."
exit 10
