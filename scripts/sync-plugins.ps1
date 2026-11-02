<#
.SYNOPSIS
  Mirror every plugin of this repo into a PotionUI checkout as a real folder content/plugins/local/<id>.
.DESCRIPTION
  A real copy, not a junction: esbuild resolves a junction to its target path, and from there the
  plugin can no longer reach content/plugins/sdk nor content/plugins/node_modules, so the official
  frontend build (scripts/build-plugins.mjs) breaks. A mirror copy keeps the plugin sources
  identical to what the marketplace expects (relative '../../../../sdk/HostUi.svelte' import).
  Excluded from the copy: node_modules, __pycache__, .pytest_cache, .git, *.pyc, junctions.
  Run it again after editing the plugin (build-plugins.ps1 does it for you).
  robocopy mirrors on Windows; elsewhere (the Linux runners of the CI) rsync does the same mirror.
.PARAMETER PotionUISrc
  Path of the PotionUI checkout. Defaults to POTIONUI_SRC from the environment or .env.local.
.PARAMETER Plugin
  Only this plugin id. Default: every plugin of the repo.
#>
[CmdletBinding()]
param([string]$PotionUISrc, [string]$Plugin)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $PotionUISrc) { $PotionUISrc = Get-DotEnvValue 'POTIONUI_SRC' }
if (-not $PotionUISrc) { throw 'Give -PotionUISrc or set POTIONUI_SRC in .env.local' }
$PotionUISrc = (Resolve-Path $PotionUISrc).Path
if (-not (Test-Path ([IO.Path]::Combine($PotionUISrc, 'content', 'plugins')))) { throw "Not a PotionUI checkout: $PotionUISrc" }

$localDir = [IO.Path]::Combine($PotionUISrc, 'content', 'plugins', 'local')
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

$plugins = @(Get-PluginDirs | Where-Object { -not $Plugin -or $_.Name -eq $Plugin })
if (-not $plugins) { throw "no plugin found$(if ($Plugin) { " named $Plugin" })" }

foreach ($p in $plugins) {
    $dest = Join-Path $localDir $p.Name
    $existing = Get-Item -LiteralPath $dest -ErrorAction SilentlyContinue
    if ($existing -and ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        # A junction left by an older setup: drop the link itself, never its target.
        [IO.Directory]::Delete($dest)
        Write-Host "unlinked $dest (was a junction)"
    }
    if ($IsWindows -or $PSVersionTable.PSEdition -eq 'Desktop') {
        # robocopy exit codes 0-7 mean success (bits: 1 copied, 2 extras, 4 mismatches); 8+ is an error.
        robocopy $p.FullName $dest /MIR /XJ /XD node_modules __pycache__ .pytest_cache .git /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $($p.Name) (exit $LASTEXITCODE)" }
    } else {
        rsync -a --delete --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude .git --exclude '*.pyc' "$($p.FullName)/" "$dest/"
        if ($LASTEXITCODE -ne 0) { throw "rsync failed for $($p.Name) (exit $LASTEXITCODE)" }
    }
    Write-Host "synced  $($p.Name) -> $dest"
}
# robocopy's "files copied" exit code (1) would otherwise leak out as the script's exit code.
exit 0
