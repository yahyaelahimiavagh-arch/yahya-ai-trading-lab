param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("NODE-LAPTOP","NODE-WORKPC")]
    [string]$NodeId,

    [Parameter(Mandatory=$true)]
    [ValidatePattern("^[0-9a-f]{40}$")]
    [string]$GitSha,

    [Parameter(Mandatory=$true)]
    [string]$VpsHost,

    [string]$SshUser = "yatl-node",
    [int]$SshPort = 22,

    [Parameter(Mandatory=$true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$BundleManifestSha256,

    [Parameter(Mandatory=$true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$ArchiveSha256,

    [Parameter(Mandatory=$true)]
    [Int64]$ArchiveBytes,

    [string]$RepoUrl = "https://github.com/yahyaelahimiavagh-arch/yahya-ai-trading-lab.git",
    [string]$RepoDir = "$HOME\yatl-mcf-distributed",
    [string]$RuntimeRoot = "$HOME\yatl-mcf-runtime",
    [string]$WorkerStateRoot = "$HOME\yatl-mcf-worker-state",
    [string]$IdentityFile = "$HOME\.ssh\yatl_mcf_node_ed25519",
    [string]$KnownHostsFile = "$HOME\.ssh\yatl_mcf_known_hosts"
)

$ErrorActionPreference = "Stop"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $Name"
    }
}

Require-Command git
Require-Command ssh
Require-Command ssh-keygen
Require-Command uv

$sshDir = Split-Path -Parent $IdentityFile
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

if (-not (Test-Path $IdentityFile)) {
    # Windows PowerShell 5.1 drops empty native arguments with direct '&'
    # invocation. Start-Process preserves the quoted empty passphrase.
    $keygen = Start-Process -FilePath (Get-Command ssh-keygen).Source `
        -ArgumentList @("-q", "-t", "ed25519", "-N", '""', "-f", ('"{0}"' -f $IdentityFile)) `
        -NoNewWindow -Wait -PassThru
    if ($keygen.ExitCode -ne 0) { throw "ssh-keygen failed" }
    Write-Host ""
    Write-Host "NODE_KEY_ENROLLMENT_REQUIRED=YES"
    Write-Host "Copy this PUBLIC key to the VPS enrollment step:"
    Get-Content "$IdentityFile.pub"
    Write-Host ""
    Write-Host "After the VPS installs this public key, run this same script again."
    return
}

if (-not (Test-Path "$IdentityFile.pub")) {
    throw "Missing public key next to identity file: $IdentityFile.pub"
}
if (-not (Test-Path $KnownHostsFile)) {
    throw "Pinned known_hosts file is missing: $KnownHostsFile"
}

if (-not (Test-Path $RepoDir)) {
    & git clone $RepoUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
}

& git -C $RepoDir fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

& git -C $RepoDir cat-file -e "${GitSha}^{commit}"
if ($LASTEXITCODE -ne 0) { throw "Expected Git commit is unavailable" }

& git -C $RepoDir checkout --detach $GitSha
if ($LASTEXITCODE -ne 0) { throw "git checkout failed" }

$actualGitSha = (& git -C $RepoDir rev-parse HEAD).Trim()
if ($actualGitSha -ne $GitSha) {
    throw "Git HEAD mismatch: $actualGitSha"
}

Push-Location $RepoDir
try {
    & uv sync --frozen --python 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
}
finally {
    Pop-Location
}

$python = Join-Path $RepoDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Pinned Python environment not found: $python"
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorkerStateRoot | Out-Null
$downloadDir = Join-Path $RuntimeRoot "_download"
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
$archivePath = Join-Path $downloadDir "worker-runtime-$BundleManifestSha256-$ArchiveSha256.zip"

Push-Location $RepoDir
try {
    & $python -m research.mass_candidate_factory.production_ssh_gateway client-download `
        --host $VpsHost `
        --user $SshUser `
        --identity $IdentityFile `
        --known-hosts $KnownHostsFile `
        --port $SshPort `
        --bundle-manifest-sha256 $BundleManifestSha256 `
        --archive-sha256 $ArchiveSha256 `
        --archive-bytes $ArchiveBytes `
        --output $archivePath
    if ($LASTEXITCODE -ne 0) { throw "Runtime archive download failed" }

    & $python -m research.mass_candidate_factory.production_worker_bundle import-archive `
        --runtime-root $RuntimeRoot `
        --archive $archivePath
    if ($LASTEXITCODE -ne 0) { throw "Runtime archive import/verification failed" }
}
finally {
    Pop-Location
}

$manifestPath = Join-Path $RuntimeRoot "worker-bundle-manifest.json"
$planPath = Join-Path $RuntimeRoot "distributed-plan.json"
if (-not (Test-Path $manifestPath) -or -not (Test-Path $planPath)) {
    throw "Imported worker runtime is missing plan or bundle manifest"
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
if ($manifest.git_sha -ne $GitSha) {
    throw "Worker bundle Git identity differs from checked-out commit"
}

$envFile = Join-Path $RuntimeRoot "yatl-worker-env.ps1"
@"
`$env:YATL_NODE_ID="$NodeId"
`$env:YATL_COORDINATOR_TRANSPORT="ssh"
`$env:YATL_SSH_HOST="$VpsHost"
`$env:YATL_SSH_USER="$SshUser"
`$env:YATL_SSH_PORT="$SshPort"
`$env:YATL_SSH_IDENTITY="$IdentityFile"
`$env:YATL_SSH_KNOWN_HOSTS="$KnownHostsFile"
`$env:YATL_WORKER_ROOT="$WorkerStateRoot"
`$env:YATL_DISTRIBUTED_PLAN="$planPath"
"@ | Set-Content -Encoding UTF8 $envFile

. $envFile

Push-Location $RepoDir
try {
    & $python -m research.mass_candidate_factory.production_worker_agent `
        --transport ssh `
        --root $WorkerStateRoot `
        --plan $planPath `
        status
    if ($LASTEXITCODE -ne 0) { throw "SSH coordinator status check failed" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "WORKER_SETUP_STATUS=READY_NO_PERFORMANCE"
Write-Host "NODE_ID=$NodeId"
Write-Host "GIT_SHA=$GitSha"
Write-Host "PLAN=$planPath"
Write-Host "RUNNER_INPUT_SHA256=$($manifest.runner_input_sha256)"
Write-Host "RUNNER_INPUT_RELATIVE=$($manifest.runner_input_relative)"
Write-Host "ENV_SCRIPT=$envFile"
Write-Host "FULL_6852_EXECUTION_STARTED=NO"
