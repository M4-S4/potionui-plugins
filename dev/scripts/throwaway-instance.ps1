<#
.SYNOPSIS
  Start (or tear down) a throwaway PotionUI instance that serves a worktree of the clone, to check
  a PR branch live without touching the dev instance.
.DESCRIPTION
  Start:
    - container <Name> from the dev container's image, the worktree bind-mounted on /work, named
      volumes <Name>-storage and <Name>-models over /work/storage and /work/models (fresh data),
      uvicorn on 127.0.0.1:<Port> (api.py hard-codes 26730, so the port is passed to uvicorn);
    - first admin `<Name>admin` registered over loopback inside the container (no claim token is
      needed on a fresh storage), a plain user `<Name>user` created through POST /api/users;
    - their generated passwords are written to .env.local as POTIONUI_THROWAWAY_ADMIN_PASSWORD and
      POTIONUI_THROWAWAY_USER_PASSWORD (git-ignored, never printed), with POTIONUI_THROWAWAY_URL;
    - POST /api/plugins/scan, then POST /api/plugins/<Plugin>/enable.
  The worktree's frontend/build is served only if it exists (build it there with npm run build
  for a UI check; API checks do not need it).
  -Teardown removes the container, its volumes and the POTIONUI_THROWAWAY_* lines.
.EXAMPLE
  .\dev\scripts\throwaway-instance.ps1 -Worktree <checkout>\.wt\pr-mb-1
  .\dev\scripts\throwaway-instance.ps1 -Teardown
#>
[CmdletBinding()]
param(
    [string]$Worktree,
    [string]$Name = 'potionui-pr',
    [int]$Port = 26731,
    [string]$Plugin = 'model-browser',
    [switch]$Teardown
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$envFile = Join-Path (Get-RepoRoot) '.env.local'
$keys = 'POTIONUI_THROWAWAY_URL', 'POTIONUI_THROWAWAY_ADMIN_PASSWORD', 'POTIONUI_THROWAWAY_USER_PASSWORD'

function Remove-ThrowawayKeys {
    if (-not (Test-Path $envFile)) { return }
    $kept = Get-Content $envFile | Where-Object { $line = $_; -not ($keys | Where-Object { $line.StartsWith("$_=") }) }
    Set-Content -Path $envFile -Value $kept -Encoding utf8NoBOM
}

if ($Teardown) {
    docker rm -f $Name 2>$null | Out-Null
    docker volume rm "$Name-storage" "$Name-models" 2>$null | Out-Null
    Remove-ThrowawayKeys
    Write-Host "removed $Name, its volumes and the throwaway credentials"
    exit 0
}

if (-not $Worktree -or -not (Test-Path (Join-Path $Worktree 'api.py'))) { throw 'Give -Worktree <a PotionUI worktree>' }
$base = "http://127.0.0.1:$Port"
$image = docker inspect (Get-DotEnvValue 'POTIONUI_CONTAINER') -f '{{.Config.Image}}'
$mount = ($Worktree -replace '\\', '/')
docker rm -f $Name 2>$null | Out-Null
$env:MSYS_NO_PATHCONV = '1'
docker run -d --name $Name --no-healthcheck -p "127.0.0.1:${Port}:$Port" `
    -v "${mount}:/work" -v "$Name-storage:/work/storage" -v "$Name-models:/work/models" `
    -w /work -e PYTHONDONTWRITEBYTECODE=1 --entrypoint /app/venv/bin/python $image `
    -m uvicorn api:app --host 0.0.0.0 --port $Port | Out-Null

$deadline = (Get-Date).AddSeconds(240)
do {
    Start-Sleep 3
    try { $up = (Invoke-WebRequest "$base/health" -TimeoutSec 5 -SkipHttpErrorCheck).StatusCode -eq 200 } catch { $up = $false }
} while (-not $up -and (Get-Date) -lt $deadline)
if (-not $up) { docker logs --tail 40 $Name; throw "$Name did not come up" }

function New-Secret { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ }) }
$adminPassword = New-Secret
$userPassword = New-Secret
$register = @{ username = "${Name}admin"; email = "${Name}admin@example.com"; password = $adminPassword } | ConvertTo-Json -Compress
$status = $register | docker exec -i $Name sh -c "curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:$Port/api/auth/register"
if ($status -ne '200') { throw "registering the first admin answered $status" }
$token = (Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -Body @{ username = "${Name}admin"; password = $adminPassword } -ContentType 'application/x-www-form-urlencoded').access_token
$admin = @{ Authorization = "Bearer $token" }
$null = Invoke-RestMethod -Method Post -Uri "$base/api/users" -Headers $admin -ContentType 'application/json' `
    -Body (@{ username = "${Name}user"; email = "${Name}user@example.com"; password = $userPassword; account_type = 'USER' } | ConvertTo-Json)

Remove-ThrowawayKeys
Add-Content -Path $envFile -Encoding utf8NoBOM -Value @(
    "POTIONUI_THROWAWAY_URL=$base",
    "POTIONUI_THROWAWAY_ADMIN_PASSWORD=$adminPassword",
    "POTIONUI_THROWAWAY_USER_PASSWORD=$userPassword"
)

$null = Invoke-RestMethod -Method Post -Uri "$base/api/plugins/scan" -Headers $admin
$enabled = Invoke-RestMethod -Method Post -Uri "$base/api/plugins/$Plugin/enable" -Headers $admin
Write-Host "$Name up on $base serving $Worktree; users ${Name}admin and ${Name}user (passwords in .env.local); $($enabled.message)"
