param(
    [Parameter(Mandatory=$true)]
    [string]$AuthorizationFile,
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
if (-not (Test-Path $AuthorizationFile)) { throw "Director authorization artifact is missing." }

. $envFile

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
