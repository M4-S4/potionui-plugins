<#
.SYNOPSIS
  Day-to-day helper for a PotionUI instance running in Docker.
.DESCRIPTION
  Reads POTIONUI_URL, POTIONUI_USER, POTIONUI_PASSWORD, POTIONUI_CONTAINER and POTIONUI_APP_DIR (the
  directory the backend runs from inside the container: /app for the published image, /work for a
  container serving a PotionUI checkout mounted there) from the environment or .env.local (see
  .env.example). Actions:
    status            container state and health
    restart           docker restart, then wait until the health check passes
    logs [-Tail n]    container logs (default: last 80 lines)
    scan              log in, POST /api/plugins/scan, list the plugins the core sees
    enable -Plugin x  POST /api/plugins/x/enable   (disable: the same with -Disable)
    pytest [-Plugin x] [-- pytest args]
                      install pytest into the container venv if missing, then run the plugin's tests
                      from /app (pytest.ini applies: network blocked, asyncio auto)
    copy [-Plugin x]  docker cp the plugin folder(s) into /app/content/plugins/local/ (only needed
                      when the plugin folder is not bind-mounted into the container)
.EXAMPLE
  .\scripts\potionui-docker.ps1 pytest -Plugin model-browser -- -q -x
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet('status', 'restart', 'logs', 'scan', 'enable', 'pytest', 'copy')]
    [string]$Action,
    [string]$Plugin,
    [switch]$Disable,
    [int]$Tail = 80,
    [Parameter(ValueFromRemainingArguments)][string[]]$Rest
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$container = Get-DotEnvValue 'POTIONUI_CONTAINER'
if (-not $container) { throw 'Set POTIONUI_CONTAINER in .env.local (container name or id)' }
$baseUrl = (Get-DotEnvValue 'POTIONUI_URL')
if (-not $baseUrl) { $baseUrl = 'http://localhost:26730' }
$baseUrl = $baseUrl.TrimEnd('/')
$appDir = Get-DotEnvValue 'POTIONUI_APP_DIR'
if (-not $appDir) { $appDir = '/app' }
# The image's virtualenv, whatever directory the backend runs from.
$python = '/app/venv/bin/python'
# `$null | Where-Object` still emits one `$null`, which `@Rest` would splat as an empty argument
# (pytest then reads '' as "the current folder" and collects the whole of /app).
$Rest = @($Rest | Where-Object { $null -ne $_ -and $_ -ne '--' })

function Get-Token {
    $user = Get-DotEnvValue 'POTIONUI_USER'
    $password = Get-DotEnvValue 'POTIONUI_PASSWORD'
    if (-not $user -or -not $password) { throw 'Set POTIONUI_USER and POTIONUI_PASSWORD in .env.local' }
    # /api/auth/login takes an OAuth2 password form and answers {access_token, token_type}.
    $resp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/login" `
        -ContentType 'application/x-www-form-urlencoded' `
        -Body @{ username = $user; password = $password }
    return $resp.access_token
}

function Invoke-Api {
    param([string]$Method, [string]$Path, [string]$Token, $Body)
    $params = @{ Method = $Method; Uri = "$baseUrl$Path"; Headers = @{ Authorization = "Bearer $Token" } }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = 'application/json' }
    Invoke-RestMethod @params
}

function Wait-Healthy {
    param([int]$TimeoutSeconds = 240)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        $status = docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' $container
        Write-Host "  $(Get-Date -Format HH:mm:ss) $status"
    } while ($status -notmatch 'healthy|exited|dead' -and (Get-Date) -lt $deadline)
    if ($status -notmatch 'healthy') { throw "container did not become healthy: $status" }
}

function Select-Plugins {
    $plugins = @(Get-PluginDirs | Where-Object { -not $Plugin -or $_.Name -eq $Plugin })
    if (-not $plugins) { throw "no plugin found$(if ($Plugin) { " named $Plugin" })" }
    return $plugins
}

switch ($Action) {
    'status' {
        docker ps -a --filter "name=$container" --format '{{.ID}}  {{.Names}}  {{.Status}}  {{.Image}}  {{.Ports}}'
        docker inspect -f 'image revision: {{index .Config.Labels "org.opencontainers.image.revision"}} (v{{index .Config.Labels "org.opencontainers.image.version"}})' $container
        Write-Host "app dir: $appDir"
        if ($appDir -ne '/app') {
            $src = Get-DotEnvValue 'POTIONUI_SRC'
            if ($src) { Write-Host ("checkout served: {0} {1}" -f (git -C $src rev-parse --short HEAD), (git -C $src branch --show-current)) }
        }
    }
    'restart' {
        docker restart $container | Out-Null
        Wait-Healthy
    }
    'logs' {
        docker logs --tail $Tail $container 2>&1
    }
    'scan' {
        $token = Get-Token
        $null = Invoke-Api -Method Post -Path '/api/plugins/scan' -Token $token
        $list = Invoke-Api -Method Get -Path '/api/plugins' -Token $token
        $items = if ($list.data) { $list.data } else { $list }
        $items | ForEach-Object { '{0,-28} enabled={1,-5} v{2}  {3}' -f $_.id, $_.enabled, $_.version, $_.source }
    }
    'enable' {
        if (-not $Plugin) { throw 'enable needs -Plugin <id>' }
        $token = Get-Token
        $verb = if ($Disable) { 'disable' } else { 'enable' }
        $resp = Invoke-Api -Method Post -Path "/api/plugins/$Plugin/$verb" -Token $token
        Write-Host ("{0}: {1}" -f $verb, ($resp | ConvertTo-Json -Compress -Depth 3))
    }
    'pytest' {
        docker exec $container $python -c 'import pytest, pytest_asyncio, pytest_timeout' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'installing pytest into the container venv...'
            docker exec $container /app/venv/bin/pip install --quiet 'pytest>=7.4.0' 'pytest-asyncio>=0.23.0' 'pytest-timeout>=2.2.0' 'httpx>=0.27.0'
            if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
        }
        $failed = @()
        foreach ($p in Select-Plugins) {
            Write-Host "=== $($p.Name) ==="
            docker exec -w $appDir $container $python -m pytest "content/plugins/local/$($p.Name)/tests" -q @Rest
            if ($LASTEXITCODE -ne 0) { $failed += $p.Name }
        }
        if ($failed) { Write-Host "FAILED: $($failed -join ', ')"; exit 1 }
    }
    'copy' {
        docker exec $container mkdir -p "$appDir/content/plugins/local"
        foreach ($p in Select-Plugins) {
            docker cp "$($p.FullName)" "${container}:$appDir/content/plugins/local/"
            Write-Host "copied  $($p.Name) -> ${container}:$appDir/content/plugins/local/$($p.Name)"
        }
        Write-Host 'run `scan` to discover it, `restart` after backend code changes'
    }
}
