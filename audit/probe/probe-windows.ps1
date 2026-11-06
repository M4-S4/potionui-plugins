param(
    [string] $Out
)

$ErrorActionPreference = 'Stop'
$homeDir = $env:USERPROFILE
$notes = New-Object System.Collections.Generic.List[string]

function Hide-Home([string] $path) {
    if (-not $path) { return $path }
    if ($homeDir -and $path.StartsWith($homeDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        return '<home>' + $path.Substring($homeDir.Length)
    }
    return $path
}

function Try-Read([string] $label, [scriptblock] $block) {
    try {
        return & $block
    }
    catch {
        $notes.Add("${label}: $($_.Exception.Message)")
        return $null
    }
}

function File-Facts([string] $path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    $item = Get-Item -LiteralPath $path -Force
    $attributes = $item.Attributes.ToString()
    $volume = Try-Read "volume of $(Hide-Home $path)" { Get-Volume -FilePath $path }
    [ordered]@{
        path        = Hide-Home $item.FullName
        size_bytes  = $item.Length
        sparse      = $attributes -match 'SparseFile'
        compressed  = $attributes -match 'Compressed'
        encrypted   = $attributes -match 'Encrypted'
        drive       = if ($volume) { [string]$volume.DriveLetter } else { $item.PSDrive.Name }
        modified    = $item.LastWriteTimeUtc.ToString('o')
    }
}

$physical = Try-Read 'Get-PhysicalDisk' {
    Get-PhysicalDisk | Sort-Object DeviceId | ForEach-Object {
        [ordered]@{
            device_id         = $_.DeviceId
            model             = $_.FriendlyName
            media_type        = [string]$_.MediaType
            bus_type          = [string]$_.BusType
            size_bytes        = $_.Size
            health            = [string]$_.HealthStatus
            operational       = [string]$_.OperationalStatus
            firmware          = $_.FirmwareVersion
            spindle_speed     = $_.SpindleSpeed
        }
    }
}

$reliability = Try-Read 'Get-StorageReliabilityCounter' {
    Get-PhysicalDisk | Sort-Object DeviceId | ForEach-Object {
        $counter = $_ | Get-StorageReliabilityCounter
        [ordered]@{
            device_id      = $_.DeviceId
            wear_percent   = $counter.Wear
            temperature_c  = $counter.Temperature
            power_on_hours = $counter.PowerOnHours
            read_errors    = $counter.ReadErrorsTotal
        }
    }
}

$disks = Try-Read 'Get-Disk' {
    Get-Disk | Sort-Object Number | ForEach-Object {
        [ordered]@{
            number          = $_.Number
            model           = $_.FriendlyName
            bus_type        = [string]$_.BusType
            partition_style = [string]$_.PartitionStyle
            size_bytes      = $_.Size
            is_boot         = $_.IsBoot
            is_system       = $_.IsSystem
        }
    }
}

$partitions = Try-Read 'Get-Partition' {
    Get-Partition | Sort-Object DiskNumber, PartitionNumber | ForEach-Object {
        [ordered]@{
            disk      = $_.DiskNumber
            partition = $_.PartitionNumber
            drive     = [string]$_.DriveLetter
            size_bytes = $_.Size
            type      = [string]$_.Type
        }
    }
}

$volumes = Try-Read 'Get-Volume' {
    Get-Volume | Where-Object { $_.DriveLetter } | Sort-Object DriveLetter | ForEach-Object {
        $free = if ($_.Size) { [math]::Round(100.0 * $_.SizeRemaining / $_.Size, 1) } else { $null }
        [ordered]@{
            drive        = [string]$_.DriveLetter
            label        = $_.FileSystemLabel
            file_system  = $_.FileSystem
            drive_type   = [string]$_.DriveType
            size_bytes   = $_.Size
            free_bytes   = $_.SizeRemaining
            free_percent = $free
            health       = [string]$_.HealthStatus
        }
    }
}

$wslDistros = Try-Read 'WSL registry' {
    $root = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (-not (Test-Path $root)) { return @() }
    Get-ChildItem $root | ForEach-Object {
        $entry = Get-ItemProperty $_.PSPath
        $base = [string]$entry.BasePath
        if ($base.StartsWith('\\?\')) { $base = $base.Substring(4) }
        [ordered]@{
            name    = $entry.DistributionName
            version = $entry.Version
            vhdx    = File-Facts (Join-Path $base 'ext4.vhdx')
        }
    }
}

$dockerRoots = New-Object System.Collections.Generic.List[string]
$dockerRoots.Add((Join-Path $env:LOCALAPPDATA 'Docker\wsl'))
$dockerSettings = Try-Read 'Docker Desktop settings' {
    foreach ($name in @('settings-store.json', 'settings.json')) {
        $file = Join-Path $env:APPDATA "Docker\$name"
        if (Test-Path -LiteralPath $file) {
            $json = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
            $custom = $json.CustomWslDistroDir
            if (-not $custom) { $custom = $json.customWslDistroDir }
            if ($custom) { $dockerRoots.Add([string]$custom) }
            return [ordered]@{ file = Hide-Home $file; custom_wsl_distro_dir = Hide-Home $custom; disk_size_mib = $json.DiskSizeMiB }
        }
    }
    return $null
}
$dockerCandidates = foreach ($root in $dockerRoots) {
    foreach ($relative in @('disk\docker_data.vhdx', 'data\ext4.vhdx', 'main\ext4.vhdx', 'distro\ext4.vhdx', 'docker_data.vhdx')) {
        Join-Path $root $relative
    }
}
$dockerDisks = @($dockerCandidates | Select-Object -Unique | ForEach-Object { File-Facts $_ } | Where-Object { $_ })

$wslConfigPath = Join-Path $homeDir '.wslconfig'
$wslConfig = $null
if (Test-Path -LiteralPath $wslConfigPath) {
    $wslConfig = [ordered]@{}
    $section = ''
    foreach ($line in Get-Content -LiteralPath $wslConfigPath) {
        $text = $line.Trim()
        if ($text -eq '' -or $text.StartsWith([string][char]35) -or $text.StartsWith(';')) { continue }
        if ($text.StartsWith('[') -and $text.EndsWith(']')) { $section = $text.Trim('[', ']'); continue }
        $parts = $text -split '=', 2
        if ($parts.Count -eq 2) { $wslConfig["$section.$($parts[0].Trim())"] = Hide-Home $parts[1].Trim() }
    }
}

$gpu = Try-Read 'nvidia-smi' {
    $query = & nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,pstate --format=csv,noheader,nounits
    $apps = & nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
    $table = & nvidia-smi
    $compute = @($table | Where-Object { $_ -match '^\|\s+\d+\s+\S+\s+\S+\s+\d+\s+C\s' })
    $fields = ($query | Select-Object -First 1) -split ',\s*'
    [ordered]@{
        name                 = $fields[0]
        driver               = $fields[1]
        memory_total_mib     = [int]$fields[2]
        memory_used_mib      = [int]$fields[3]
        pstate               = $fields[4]
        listed_apps          = @($apps).Count
        compute_only_type_c  = $compute.Count
    }
}

$session = Try-Read 'session' {
    $explorer = @(Get-Process -Name explorer -ErrorAction SilentlyContinue).Count
    $logonui = @(Get-Process -Name LogonUI -ErrorAction SilentlyContinue).Count
    [ordered]@{
        interactive      = [Environment]::UserInteractive
        explorer_running = $explorer -gt 0
        lock_screen_up   = $logonui -gt 0
    }
}

$os = Try-Read 'Win32_OperatingSystem' {
    $info = Get-CimInstance Win32_OperatingSystem
    [ordered]@{ caption = $info.Caption; version = $info.Version; build = $info.BuildNumber }
}

$result = [ordered]@{
    schema         = 1
    probe          = 'windows'
    generated_at   = (Get-Date).ToUniversalTime().ToString('o')
    powershell     = $PSVersionTable.PSVersion.ToString()
    os             = $os
    physical_disks = @($physical)
    reliability    = @($reliability)
    disks          = @($disks)
    partitions     = @($partitions)
    volumes        = @($volumes)
    wsl            = [ordered]@{ distros = @($wslDistros); wslconfig = $wslConfig }
    docker_desktop = [ordered]@{ settings = $dockerSettings; disks = $dockerDisks }
    gpu            = $gpu
    session        = $session
    notes          = @($notes)
}

$json = $result | ConvertTo-Json -Depth 8
if ($Out) {
    [System.IO.File]::WriteAllText($Out, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}
else {
    $json
}
