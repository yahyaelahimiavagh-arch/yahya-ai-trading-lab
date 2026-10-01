# MCF-PROD-001 work-PC setup — 1 October 2026

Status: PREPARATION ONLY. No Development performance authority is granted by
this runbook. PR #174 acceptance and the blind capacity benchmark are separate
gates. Use the SSH path; Cloudflare/Hostinger purchase or deployment is not
needed. Each machine runs at most one micro-shard process at a time.

## First check at the office (Windows)

Download `ops/windows/Test-YatlMcfWorkstation.ps1` from the reviewed PR branch.
It works without Git, uv or Python. Run in Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Test-YatlMcfWorkstation.ps1 -NodeId NODE-WORKPC
```

The execution-policy option applies only to that new PowerShell process.
The script reads CPU, RAM, free disk space and tool availability. It does not
install tools, create keys, download datasets or start candidate execution.
Optionally add `-VpsHost ACTUAL_VPS_HOST` to check TCP port 22 with a five-second
limit. A reachable port does not prove SSH authentication or pinned host trust.
Share the JSON report to select the next concrete installation step. Missing
tools must be installed only if absent; there is no paid tooling requirement.

## VPS check from the existing SSH session

Run the reviewed `ops/ssh/yatl-mcf-vps-preflight.sh` with bash. It reports app
and distributed Git refs, memory/swap, disk space, the accepted index path,
binding-root presence and OS prerequisites without reading P10 or credentials.
The check does not modify Git refs or research artifacts. Root may run it with
sudo so Git executes under the existing `yatl` service account.

Do not change `/opt/yatl/app` checkout or the P10 collector for this setup.
Preparation uses a dedicated `/opt/yatl/mcf-distributed` worktree.

## After explicit PR acceptance

1. Pin the exact accepted merged Git SHA; a previously observed PR HEAD must
   not be substituted for the accepted merge SHA.
2. Run `yatl-mcf-vps-refreeze.sh` with that SHA. Independently verify the
   emitted runner-input SHA and path against the same accepted 525 Development
   datasets; this performs no candidate economics.
3. Run `yatl-mcf-vps-prepare.sh` with the exact Git and runner-input values and
   the real VPS host label. Retain its archive bytes, raw SHA, bundle-manifest
   SHA, SSH fingerprint and pinned `known_hosts` line. Preparation installs but
   does not enable/start the autonomous worker service.
4. Install only missing workstation tools (Git, OpenSSH client, uv). The setup
   script builds the locked Python 3.12 environment.
5. Run `Setup-YatlMcfWorker.ps1` with NODE-WORKPC and the VPS archive metadata.
   Its first run generates a dedicated ed25519 key and prints only the public
   key. Never send the private-key file. The key is for the restricted worker
   account and does not replace an existing administrator SSH key.
6. Enroll that public key with `yatl-mcf-vps-enroll-node.sh`. Save the pinned
   VPS host-key line from step 3 in the workstation's
   `$HOME\.ssh\yatl_mcf_known_hosts`. For a nondefault SSH port use the OpenSSH
   `[host]:port` host label.
7. Repeat the setup command to download and validate the frozen runtime bundle
   and check SSH coordinator status. Required final state:
   `WORKER_SETUP_STATUS=READY_NO_PERFORMANCE`.
8. Complete the fixed blind 24-candidate capacity benchmark on the refrozen
   VPS input. Inspect current/peak RSS, timing and success evidence before
   authorizing any full execution. Workstation RAM and disk reports alone are
   not proof that its runtime fits.
9. After separate Director full-Development authorization and a controlled
   workstation smoke test, use `Start-YatlMcfWorker.ps1` with the exact
   authorization metadata. The worker claims batches and transfers verified
   complete batches to the VPS automatically.

## Current operational limits

- Windows setup and SSH permissions require physical-device verification.
- The worker must stay powered on and awake while its current batch runs.
- Local checkpoints support restart on the same machine. An unfinished batch
  does not yet transfer its partial checkpoints automatically to another
  machine; do not claim cross-machine recovery without recomputation.
- Pause/stop and lease-expiry behavior must be checked before unattended
  operation. A single planned run per NODE-WORKPC avoids overlapping workers.
- No final economic selection, Fresh OOS, recent reserve, P10/P11 or Live
  action is authorized by setup or benchmark evidence.
