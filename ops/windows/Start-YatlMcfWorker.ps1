param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$AuthorizationSha256,

    [Parameter(Mandatory=$true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$AuthorizationRawSha256,

    [Parameter(Mandatory=$true)]
    [Int64]$AuthorizationBytes,

    [string]$RepoDir = "$HOME\yatl-mcf-distributed",
    [string]$RuntimeRoot = "$HOME\yatl-mcf-runtime",
    [string]$WorkerStateRoot = "$HOME\yatl-mcf-worker-state",
    [int]$MaxBatches = 0
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoDir ".venv\Scripts\python.exe"
$envFile = Join-Path $RuntimeRoot "yatl-worker-env.ps1"

if (-not (Test-Path $python)) { throw "Worker Python is missing. Run Setup-YatlMcfWorker.ps1 first." }
if (-not (Test-Path $envFile)) { throw "Worker environment is missing. Run Setup-YatlMcfWorker.ps1 first." }

. $envFile

$AuthorizationFile = Join-Path $RuntimeRoot "authorization-$AuthorizationSha256-$AuthorizationRawSha256.json"

if (-not (Test-Path $AuthorizationFile)) {
    $downloadArgs = @(
        "-m",
        "research.mass_candidate_factory.production_ssh_gateway",
        "client-auth-download",
        "--host", $env:YATL_SSH_HOST,
        "--user", $env:YATL_SSH_USER,
        "--identity", $env:YATL_SSH_IDENTITY,
        "--known-hosts", $env:YATL_SSH_KNOWN_HOSTS,
        "--port", $env:YATL_SSH_PORT,
        "--authorization-sha256", $AuthorizationSha256,
        "--raw-sha256", $AuthorizationRawSha256,
        "--artifact-bytes", "$AuthorizationBytes",
        "--output", $AuthorizationFile
    )
    Push-Location $RepoDir
    try {
        & $python @downloadArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Director authorization download/verification failed"
        }
    }
    finally {
        Pop-Location
    }
}

$arguments = @(
    "-m",
    "research.mass_candidate_factory.production_worker_orchestrator",
    "--runtime-root", $RuntimeRoot,
    "--worker-root", $WorkerStateRoot,
    "--authorization", $AuthorizationFile,
    "--transport", "ssh",
    "--max-batches", "$MaxBatches"
)

Push-Location $RepoDir
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "YATL auto-worker exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
