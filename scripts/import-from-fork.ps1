<#
.SYNOPSIS
  Mirror Video Producer from a checkout of the M4-S4/PotionUI fork into this repo, then show git status.
.DESCRIPTION
  The fork stays the working copy of Video Producer until the core loads the CSS of a plugin
  installed outside its tree. This script brings its current state here:
    <checkout>/content/plugins/marketplace/video-producer           ->  video-producer/
    <checkout>/tests/plugins/marketplace/test_video_producer_*.py   ->  core-tests/video-producer/
  A robocopy mirror: a file removed in the fork is removed here. Never copied and never purged:
  node_modules, __pycache__, .pytest_cache, *.pyc, frontend/dist (built by the CI, attached to
  the releases) and docs/screenshots (kept here as WebP). In README.md and docs/user-guide.md, a
  reference to docs/screenshots/<name>.png or .jpg is pointed at <name>.webp when that file
  exists here; the others are listed in a warning. A file whose only difference is the CRLF line
  endings of the fork's Windows checkout is restored from the index, so that git status lists
  only real changes. Review with git diff, then commit.
.PARAMETER PotionUISrc
  Path of the fork checkout. Defaults to POTIONUI_SRC from the environment or .env.local.
#>
[CmdletBinding()]
param([string]$PotionUISrc)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $PotionUISrc) { $PotionUISrc = Get-DotEnvValue 'POTIONUI_SRC' }
if (-not $PotionUISrc) { throw 'Give -PotionUISrc or set POTIONUI_SRC in .env.local' }
$PotionUISrc = (Resolve-Path $PotionUISrc).Path
$pluginSrc = Join-Path $PotionUISrc 'content\plugins\marketplace\video-producer'
$testsSrc = Join-Path $PotionUISrc 'tests\plugins\marketplace'
if (-not (Test-Path (Join-Path $pluginSrc 'manifest.yml'))) { throw "No Video Producer in $PotionUISrc" }

$repo = Get-RepoRoot
$pluginDest = Join-Path $repo 'video-producer'
$testsDest = Join-Path $repo 'core-tests\video-producer'

$kept = foreach ($sub in @('frontend\dist', 'docs\screenshots')) { Join-Path $pluginSrc $sub; Join-Path $pluginDest $sub }
robocopy $pluginSrc $pluginDest /MIR /XJ /XD node_modules __pycache__ .pytest_cache @kept /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed for video-producer (exit $LASTEXITCODE)" }
Write-Host "mirrored $pluginSrc -> $pluginDest"

New-Item -ItemType Directory -Force -Path $testsDest | Out-Null
robocopy $testsSrc $testsDest 'test_video_producer_*.py' /PURGE /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed for the core-side tests (exit $LASTEXITCODE)" }
Write-Host "mirrored $testsSrc\test_video_producer_*.py -> $testsDest"

$shots = Join-Path $pluginDest 'docs\screenshots'
$missing = New-Object System.Collections.Generic.List[string]
foreach ($doc in @('README.md', 'docs\user-guide.md')) {
    $path = Join-Path $pluginDest $doc
    if (-not (Test-Path $path)) { continue }
    $text = [IO.File]::ReadAllText($path)
    $evaluator = [Text.RegularExpressions.MatchEvaluator] {
        param($match)
        $name = $match.Groups[1].Value
        if (Test-Path (Join-Path $shots "$name.webp")) { return "$name.webp" }
        $missing.Add("$doc -> docs/screenshots/$($match.Value)")
        return $match.Value
    }
    $updated = [regex]::Replace($text, '(?<=screenshots/)([\w.-]+)\.(?:png|jpe?g)\b', $evaluator)
    if ($updated -cne $text) {
        [IO.File]::WriteAllText($path, $updated, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "pointed the screenshots of $doc at their .webp"
    }
}
if ($missing.Count) {
    Write-Warning ("screenshots cited but absent from video-producer/docs/screenshots, add them as WebP:`n  " + ($missing -join "`n  "))
}

$scope = @('video-producer', 'core-tests/video-producer')
$edited = @(git -C $repo -c core.safecrlf=false diff --name-only -- @scope)
$eolOnly = @(git -C $repo -c core.safecrlf=false ls-files -m -- @scope | Where-Object { $edited -notcontains $_ })
if ($eolOnly.Count) {
    git -C $repo -c core.safecrlf=false checkout -- @eolOnly
    Write-Host "restored the LF line endings of $($eolOnly.Count) unchanged files"
}

git -C $repo status -- @scope
exit 0
