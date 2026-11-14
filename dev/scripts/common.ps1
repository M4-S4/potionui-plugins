# Shared helpers for the scripts in this folder.
# Dot-source it from a script:  . (Join-Path $PSScriptRoot 'common.ps1')

function Get-RepoRoot {
    Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Get-DotEnvValue {
    <#
    .SYNOPSIS
      Value of a key from the environment, else from .env.local, else from .env at the repo root.
    #>
    param([Parameter(Mandatory)][string]$Key)
    $value = [Environment]::GetEnvironmentVariable($Key)
    if ($value) { return $value }
    $repoRoot = Get-RepoRoot
    foreach ($file in @('.env.local', '.env')) {
        $path = Join-Path $repoRoot $file
        if (-not (Test-Path $path)) { continue }
        foreach ($line in Get-Content $path) {
            if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
            $k, $v = $line -split '=', 2
            if ($k.Trim() -eq $Key) { return $v.Trim().Trim('"') }
        }
    }
    return $null
}

function Get-PluginDirs {
    <#
    .SYNOPSIS
      Every top-level folder of the repo that holds a manifest.yml, i.e. every plugin.
    #>
    Get-ChildItem -Path (Get-RepoRoot) -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'manifest.yml') }
}
