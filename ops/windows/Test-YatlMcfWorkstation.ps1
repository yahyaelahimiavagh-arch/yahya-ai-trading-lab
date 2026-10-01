param(
    [ValidateSet("NODE-LAPTOP", "NODE-WORKPC")]
    [string]$NodeId = "NODE-WORKPC",
    [string]$VpsHost = "",
    [ValidateRange(1, 65535)]
    [int]$SshPort = 22,
    [string]$RuntimeRoot = "$HOME\yatl-mcf-runtime"
)

# Read-only: no downloads, package installation, keys or candidate execution.
$ErrorActionPreference = "Stop"
$tools = [ordered]@{}
foreach ($name in @("git", "ssh", "ssh-keygen", "uv")) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $tools[$name] = [ordered]@{ available = ($null -ne $command) }
}

$hardwareError = $null
$memoryBytes = $null
$cpuCount = [Environment]::ProcessorCount
$osCaption = [Environment]::OSVersion.VersionString
try {
    $computer = Get-CimInstance Win32_ComputerSystem
    $memoryBytes = [Int64]$computer.TotalPhysicalMemory
    $cpuCount = [int]$computer.NumberOfLogicalProcessors
    $osCaption = (Get-CimInstance Win32_OperatingSystem).Caption
} catch {
    $hardwareError = "CIM_HARDWARE_QUERY_UNAVAILABLE"
}

$diskFreeBytes = $null
$diskError = $null
try {
    $driveRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($RuntimeRoot))
    $drive = New-Object IO.DriveInfo($driveRoot)
    $diskFreeBytes = [Int64]$drive.AvailableFreeSpace
} catch {
    $diskError = "RUNTIME_DRIVE_QUERY_UNAVAILABLE"
}

$sshConnectivity = "NOT_CHECKED_NO_HOST"
if ($VpsHost) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $pending = $client.ConnectAsync($VpsHost, $SshPort)
        if ($pending.Wait(5000) -and $client.Connected) {
            $sshConnectivity = "TCP_REACHABLE_AUTH_NOT_TESTED"
        } else {
            $sshConnectivity = "TCP_TIMEOUT"
        }
    } catch {
        $sshConnectivity = "TCP_UNREACHABLE"
    } finally {
        $client.Dispose()
    }
}

$missing = @($tools.Keys | Where-Object { -not $tools[$_].available })
[ordered]@{
    status = "WORKSTATION_PREFLIGHT_COMPLETE_NO_PERFORMANCE"
    node_id = $NodeId
    os = $osCaption
    os_is_64_bit = [Environment]::Is64BitOperatingSystem
    powershell_version = $PSVersionTable.PSVersion.ToString()
    cpu_logical_count = $cpuCount
    physical_memory_bytes = $memoryBytes
    runtime_disk_free_bytes = $diskFreeBytes
    hardware_query_error = $hardwareError
    disk_query_error = $diskError
    required_tools = $tools
    missing_tools = $missing
    ssh_connectivity = $sshConnectivity
    capacity_status = "UNPROVEN_REQUIRES_ACCEPTED_BENCHMARK"
    performance_execution_authorized = $false
    max_concurrent_microshards_per_node = 1
} | ConvertTo-Json -Depth 5
