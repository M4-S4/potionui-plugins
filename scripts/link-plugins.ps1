<#
.SYNOPSIS
  Link every plugin of this repo into a PotionUI checkout as content/plugins/local/<id> (NTFS junction).
.DESCRIPTION
  A junction (not a symlink) needs no admin rights and works across volumes. PotionUI's plugin
  frontend build and its Tailwind scan only look at content/plugins/marketplace and
  content/plugins/local, so the junction is required even when POTIONUI_EXTRA_PLUGIN_DIRS is set.
.PARAMETER PotionUISrc
  Path of the PotionUI checkout. Defaults to POTIONUI_SRC from the environment or .env.local.
.EXAMPLE
  .\scripts\link-plugins.ps1 -PotionUISrc D:\dev\PotionUI
#>
[CmdletBinding()]
param([string]$PotionUISrc)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $PotionUISrc) { $PotionUISrc = Get-DotEnvValue 'POTIONUI_SRC' }
if (-not $PotionUISrc) { throw 'Give -PotionUISrc or set POTIONUI_SRC in .env.local' }
if (-not (Test-Path (Join-Path $PotionUISrc 'content\plugins'))) { throw "Not a PotionUI checkout: $PotionUISrc" }

$localDir = Join-Path $PotionUISrc 'content\plugins\local'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

foreach ($plugin in Get-PluginDirs) {
    $link = Join-Path $localDir $plugin.Name
    if (Test-Path $link) {
        Write-Host "exists  $link"
    } else {
        New-Item -ItemType Junction -Path $link -Target $plugin.FullName | Out-Null
        Write-Host "linked  $link -> $($plugin.FullName)"
    }
}
