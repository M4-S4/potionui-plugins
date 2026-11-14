param(
    [Parameter(Mandatory = $true)] [string] $EnvFile,
    [Parameter(Mandatory = $true)] [string] $UserKey,
    [Parameter(Mandatory = $true)] [string] $PasswordKey,
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)] [string[]] $Command
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Env file not found: $EnvFile"
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    $text = $line.Trim()
    if ($text -eq '' -or $text.StartsWith([string][char]35)) { continue }
    $parts = $text -split '=', 2
    if ($parts.Count -ne 2) { continue }
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
}

foreach ($key in @($UserKey, $PasswordKey)) {
    if (-not $values.ContainsKey($key) -or $values[$key] -eq '') {
        throw "Key $key is missing or empty in the env file"
    }
}

if ($Command.Count -gt 0 -and $Command[0] -eq '--') {
    $Command = $Command[1..($Command.Count - 1)]
}
if ($Command.Count -eq 0) {
    throw 'No command to run'
}

$env:POTION_AUDIT_USER = $values[$UserKey]
$env:POTION_AUDIT_PASSWORD = $values[$PasswordKey]
$values.Clear()
try {
    $arguments = @()
    if ($Command.Count -gt 1) { $arguments = $Command[1..($Command.Count - 1)] }
    & $Command[0] @arguments
    $code = $LASTEXITCODE
}
finally {
    Remove-Item Env:POTION_AUDIT_USER -ErrorAction SilentlyContinue
    Remove-Item Env:POTION_AUDIT_PASSWORD -ErrorAction SilentlyContinue
}
exit $code
