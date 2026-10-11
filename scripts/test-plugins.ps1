<#
.SYNOPSIS
  Run each plugin's pytest suite in its own process (plugins share the top-level package name `backend`).
.DESCRIPTION
  With -Container (or POTIONUI_CONTAINER in .env.local), tests run inside the PotionUI Docker container
  from /app with its venv, against content/plugins/local/<id>/tests: the plugin must be present there
  (bind mount, or copied with scripts/potionui-docker.ps1 copy).
  Without a container, tests run natively from the PotionUI checkout (POTIONUI_SRC), which needs
  PotionUI's own Python environment to be active.
  pytest.ini at the PotionUI root applies in both cases: network_guard blocks every network call.
.PARAMETER Plugin
  Only this plugin id. Default: every plugin of the repo that has a tests/ folder.
.EXAMPLE
  .\scripts\test-plugins.ps1 -Plugin model-browser -- -x -k health
#>
[CmdletBinding()]
param(
    [string]$Plugin,
    [string]$Container,
    [string]$PotionUISrc,
    [Parameter(ValueFromRemainingArguments)][string[]]$PytestArgs
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $Container) { $Container = Get-DotEnvValue 'POTIONUI_CONTAINER' }
if (-not $PotionUISrc) { $PotionUISrc = Get-DotEnvValue 'POTIONUI_SRC' }
$PytestArgs = @($PytestArgs | Where-Object { $_ -ne '--' })

$plugins = @(Get-PluginDirs | Where-Object { -not $Plugin -or $_.Name -eq $Plugin })
if (-not $plugins) { throw "no plugin found$(if ($Plugin) { " named $Plugin" })" }

$failed = @()
foreach ($p in $plugins) {
    if (-not (Test-Path (Join-Path $p.FullName 'tests'))) { Write-Host "skip    $($p.Name): no tests/"; continue }
    Write-Host "=== $($p.Name) ==="
    $testPath = "content/plugins/local/$($p.Name)/tests"
    if ($Container) {
        docker exec -w /app $Container venv/bin/python -m pytest $testPath -q @PytestArgs
    } else {
        if (-not $PotionUISrc) { throw 'Set -PotionUISrc / POTIONUI_SRC, or use -Container' }
        Push-Location $PotionUISrc
        try { python -m pytest $testPath -q @PytestArgs } finally { Pop-Location }
    }
    if ($LASTEXITCODE -ne 0) { $failed += $p.Name }
}

if ($failed) { Write-Host "FAILED: $($failed -join ', ')"; exit 1 }
Write-Host "All plugin suites passed."
