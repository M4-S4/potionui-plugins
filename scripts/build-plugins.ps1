<#
.SYNOPSIS
  Build a plugin's frontend with PotionUI's own toolchain and copy the release dist back into the repo.
.DESCRIPTION
  1. Mirrors the plugin into <checkout>/.wt/marketplace/content/plugins/marketplace/<id> (the
     marketplace worktree, see marketplace-check.ps1), or with -Local into
     <checkout>/content/plugins/local/<id> (see sync-plugins.ps1).
  2. Runs the official build from that content/plugins folder:
       node ..\..\scripts\build-plugins.mjs <id>        (add -DebugBuild for source maps: never commit those)
     First run: `npm install` in <checkout>/content/plugins (done here when node_modules is missing).
  3. Copies <copy>/frontend/dist back to <repo>/<id>/frontend/dist (committed, release build).
.PARAMETER Plugin
  Plugin id (folder name). Default: every plugin of the repo that has frontend/src.
.PARAMETER PotionUISrc
  PotionUI checkout; defaults to POTIONUI_SRC from the environment or .env.local.
#>
[CmdletBinding()]
param([string]$Plugin, [string]$PotionUISrc, [switch]$DebugBuild, [switch]$Local)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $PotionUISrc) { $PotionUISrc = Get-DotEnvValue 'POTIONUI_SRC' }
if (-not $PotionUISrc) { throw 'Give -PotionUISrc or set POTIONUI_SRC in .env.local' }
$pluginsRoot = Join-Path $PotionUISrc 'content\plugins'
if (-not (Test-Path (Join-Path $pluginsRoot 'package.json'))) { throw "Not a PotionUI checkout: $PotionUISrc" }

$plugins = @(Get-PluginDirs | Where-Object { (-not $Plugin -or $_.Name -eq $Plugin) -and (Test-Path (Join-Path $_.FullName 'frontend\src')) })
if (-not $plugins) { throw "no plugin with frontend/src found$(if ($Plugin) { " named $Plugin" })" }

if (-not (Test-Path (Join-Path $pluginsRoot 'node_modules'))) {
    Write-Host 'installing the plugin toolchain (npm install in content/plugins)...'
    Push-Location $pluginsRoot
    try { npm install --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'npm install failed' } } finally { Pop-Location }
}

# Svelte 5 hashes each component's file path into its CSS class names, so the committed dist
# only matches PotionUI's CI drift check when it is built from content/plugins/marketplace/<id>.
# That build runs in the worktree <checkout>\.wt\marketplace (see marketplace-check.ps1), never
# in the checkout itself, whose marketplace folder is tracked.
$worktreePlugins = Join-Path $PotionUISrc '.wt\marketplace\content\plugins'
$useMarketplace = -not $Local -and (Test-Path (Join-Path $worktreePlugins 'node_modules'))
if (-not $Local -and -not $useMarketplace) { Write-Warning "no marketplace worktree at ${worktreePlugins}: building from local/, the dist will drift from CI" }

foreach ($p in $plugins) {
    if ($useMarketplace) {
        $buildRoot = $worktreePlugins
        $copy = Join-Path $buildRoot "marketplace\$($p.Name)"
        robocopy $p.FullName $copy /MIR /XD __pycache__ node_modules .pytest_cache /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "mirroring $($p.Name) failed (robocopy $LASTEXITCODE)" }
        Write-Host "mirrored $($p.Name) -> $copy"
    } else {
        & (Join-Path $PSScriptRoot 'sync-plugins.ps1') -PotionUISrc $PotionUISrc -Plugin $p.Name
        $buildRoot = $pluginsRoot
        $copy = Join-Path $buildRoot "local\$($p.Name)"
    }
    Push-Location $buildRoot
    try {
        $args = @('..\..\scripts\build-plugins.mjs'); if ($DebugBuild) { $args += '--debug' }; $args += $p.Name
        node @args
        if ($LASTEXITCODE -ne 0) { throw "build failed for $($p.Name)" }
    } finally { Pop-Location }

    $builtDist = Join-Path $copy 'frontend\dist'
    $repoDist = Join-Path $p.FullName 'frontend\dist'
    robocopy $builtDist $repoDist /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying dist back failed for $($p.Name) (exit $LASTEXITCODE)" }
    Get-ChildItem $repoDist | ForEach-Object { Write-Host ("built   {0}\frontend\dist\{1} ({2:N0} bytes)" -f $p.Name, $_.Name, $_.Length) }
}
# robocopy's "files copied" exit code (1) would otherwise leak out as the script's exit code.
exit 0
