<#
.SYNOPSIS
  Check a plugin the way PotionUI's CI checks a marketplace plugin, in a worktree of the clone.
.DESCRIPTION
  1. Mirrors <repo>/<id> into <worktree>/content/plugins/marketplace/<id> and copies
     <repo>/core-tests/<id>/*.py into <worktree>/tests/plugins/marketplace/ (core-side tests:
     the ones that need a core internal, which a plugin's own tests/ may not import).
  2. In the potionui-core-tests container (clone mounted on /work):
       python tests/plugins/run_suites.py -q --timeout=300 -m "<CI marker filter>"   (every marketplace suite, as backend-tests.yml)
       python -m pytest tests/plugins/marketplace/test_<id_with_underscores>_*.py tests/architecture -q
  3. On the host: release build of the plugin in the worktree and a byte comparison of the
     built frontend/dist with the committed one (windows.yml's drift check).
  The worktree is created once with:
    git -C <clone> worktree add --detach .wt/marketplace upstream/master
  plus a junction <worktree>/content/plugins/node_modules -> <clone>/content/plugins/node_modules.
.PARAMETER Plugin
  Plugin id (folder name). Default: model-browser.
.PARAMETER SkipSuites
  Skip run_suites.py (it runs every marketplace plugin's suite, about two minutes).
#>
[CmdletBinding()]
param([string]$Plugin = 'model-browser', [string]$Worktree, [switch]$SkipSuites)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$clone = Get-DotEnvValue 'POTIONUI_SRC'
if (-not $Worktree) { $Worktree = Join-Path $clone '.wt\marketplace' }
if (-not (Test-Path (Join-Path $Worktree 'tests\plugins\run_suites.py'))) { throw "No PotionUI worktree at $Worktree" }
$repo = Get-RepoRoot
$source = Join-Path $repo $Plugin
$target = Join-Path $Worktree "content\plugins\marketplace\$Plugin"
$relative = ($Worktree.Substring($clone.Length) -replace '\\', '/').TrimStart('/')
$workdir = "/work/$relative"
$container = 'potionui-core-tests'
$failures = @()

robocopy $source $target /MIR /XD __pycache__ node_modules .pytest_cache /XF PLAN.md /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "mirroring $Plugin failed (robocopy $LASTEXITCODE)" }
$coreTests = Join-Path $repo "core-tests\$Plugin"
$prefix = 'test_' + ($Plugin -replace '-', '_') + '_'
Get-ChildItem (Join-Path $Worktree 'tests\plugins\marketplace') -Filter "$prefix*.py" | Remove-Item
if (Test-Path $coreTests) { Copy-Item (Join-Path $coreTests '*.py') (Join-Path $Worktree 'tests\plugins\marketplace') }
Write-Host "mirrored $Plugin into $target"

if ((docker inspect -f '{{.State.Running}}' $container) -ne 'true') { docker start $container | Out-Null }
$env:MSYS_NO_PATHCONV = '1'
$python = '/app/venv/bin/python'
$markers = 'not requires_gpu and not requires_models and not gc_sensitive'

if (-not $SkipSuites) {
    Write-Host '--- run_suites.py (every marketplace plugin)'
    docker exec -w $workdir -e PYTHONDONTWRITEBYTECODE=1 $container $python tests/plugins/run_suites.py -q --timeout=300 -p no:cacheprovider -m $markers 2>&1 |
        Select-String -Pattern '^=== |passed|failed|error|FAILED|All \d+' | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { $failures += 'run_suites' }
}

Write-Host '--- core-side tests and tests/architecture'
$paths = @('tests/architecture')
if (Test-Path $coreTests) { $paths = @("tests/plugins/marketplace/$prefix*.py") + $paths }
$joined = $paths -join ' '
docker exec -w $workdir -e PYTHONDONTWRITEBYTECODE=1 $container sh -c "$python -m pytest $joined -q -p no:cacheprovider -m '$markers' --deselect tests/architecture/test_no_private_setup.py" 2>&1 |
    Select-Object -Last 15 | ForEach-Object { $_ }
if ($LASTEXITCODE -ne 0) { $failures += 'core-side/architecture' }

if (Test-Path (Join-Path $source 'frontend\src')) {
    Write-Host '--- release build and dist drift check'
    $committed = Join-Path $source 'frontend\dist'
    Push-Location (Join-Path $Worktree 'content\plugins')
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        node ../../scripts/build-plugins.mjs $Plugin 2>&1 | ForEach-Object { "$_" } | Select-String -Pattern 'built successfully|ERROR|FAILED' | ForEach-Object { $_.Line }
        if ($LASTEXITCODE -ne 0) { $failures += 'build' }
    } finally { $ErrorActionPreference = $previous; Pop-Location }
    $built = Join-Path $target 'frontend\dist'
    $a = Get-ChildItem $built -File | ForEach-Object { "$($_.Name) $((Get-FileHash $_.FullName).Hash)" }
    $b = Get-ChildItem $committed -File | ForEach-Object { "$($_.Name) $((Get-FileHash $_.FullName).Hash)" }
    if (Compare-Object $a $b) { Write-Host 'dist DRIFT:'; Compare-Object $a $b | Format-Table | Out-String | Write-Host; $failures += 'dist' }
    else { Write-Host "dist identical ($(@($a).Count) files)" }
}

if ($failures) { Write-Host "FAILED: $($failures -join ', ')"; exit 1 }
Write-Host 'marketplace check passed'
exit 0
