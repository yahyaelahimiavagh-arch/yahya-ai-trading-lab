# MCF-PROD-001 Distributed Execution Foundation — v1.0

Status: **IMPLEMENTATION FOUNDATION / NO PERFORMANCE AUTHORITY**

Work unit:
`MCF-PROD-001-DISTRIBUTED-EXECUTION-FOUNDATION`

Stacked baseline:
- main before OOM remediation: `21aa64e774f54b0399c561dab3f33e47d17630ff`;
- bounded-memory remediation PR #172 HEAD:
  `4dc1cdbf4862dd398c408438b5bdc8dcd68ed3d2`.

This work unit may be rebased/retargeted after PR #172 is accepted. It must not
change the frozen 6,852 candidate identities or any strategy outcome gate.

## Objective

Turn the one-machine MCF-PROD-001 run into a portable, resumable,
multi-node research compute pool while preserving one exact scientific
experiment.

Supported intended nodes:
- `NODE-VPS`;
- `NODE-LAPTOP`;
- `NODE-WORKPC`;
- future additional nodes with explicit enrollment.

The system must support all three nodes running simultaneously.

## Frozen work partition

The exact 6,852 executable candidates are partitioned deterministically by
canonical candidate ID:

- 14 logical batches;
- B001-B013: 500 candidates each;
- B014: 352 candidates;
- each logical batch contains micro-shards of at most 25 candidates;
- batch and micro-shard identities are SHA-256 bound;
- every candidate appears exactly once in the plan.

Logical batch codes are human-facing handles. A user may intentionally request
a specific code such as `B003`, while auto mode may lease the next available
batch.

Micro-shards are the operational failure boundary. They are not a new
statistical trial definition and do not alter candidate identity, cost,
evidence, or adjudication.

## Pause / resume / crash recovery

Candidate result artifacts are immutable and content-addressed.

Resume state is reconstructed from verified result artifacts rather than from a
mutable "current index" alone.

Required behavior:
- completed candidates are never recomputed for convenience;
- safe pause prevents a new candidate from starting;
- if a process dies during a candidate, only the incomplete candidate may be
  retried;
- if a node is offline, completed local artifacts remain durable;
- transfer of a batch between nodes is allowed only after all transferred
  artifacts reconcile to the same frozen plan, Git SHA and runner-input SHA;
- conflicting deterministic results are a hard failure, never silently chosen.

## Three-node simultaneous execution

The central coordinator leases batches to nodes.

Example:
- NODE-VPS -> B001;
- NODE-LAPTOP -> B002;
- NODE-WORKPC -> B003.

A live lease prevents another node from claiming the same batch. Expired leases
become eligible for recovery. Heartbeats extend the lease.

Manual mode:
`claim B003`

Auto mode:
`claim next available`

A logical batch may eventually be completed by multiple nodes across separate
safe resume/transfer episodes, but every accepted result in one batch manifest
must share the same Git SHA and runner-input SHA.

## Coordinator

Two coordinator implementations are defined:

1. Local SQLite coordinator
   - authoritative for unit tests and VPS fallback;
   - supports deterministic plan binding, claim, heartbeat, lease expiry,
     ingest state and status.

2. Cloudflare control plane
   - Worker HTTP API;
   - D1 state store;
   - node-scoped bearer tokens stored only as SHA-256 hashes in D1;
   - admin token stored only as a Cloudflare secret/hashed environment value;
   - no exchange credential, market dataset, P10 state or strategy outcome is
     stored in D1.

Cloudflare endpoints:
- `POST /v1/claim`;
- `POST /v1/heartbeat`;
- `POST /v1/release`;
- `POST /v1/ready`;
- `POST /v1/ingested` (VPS/admin only);
- `GET /v1/status`;
- `GET /health`.

The Cloudflare layer coordinates work. It does not perform backtests.

## Worker credentials

A worker receives only:
- node ID;
- node-scoped coordinator token;
- frozen plan;
- required Development runtime datasets;
- exact repository Git SHA;
- exact runner-input manifest;
- assigned batch/micro-shard.

A worker must not receive:
- exchange API keys;
- withdrawal/trade credentials;
- P10 database/state;
- Fresh OOS;
- recent reserve;
- Live secrets.

The portable Python client reads `YATL_NODE_TOKEN` only from the environment.
It never writes the plaintext token to disk.

## Result artifacts

Each candidate result envelope binds:
- distributed plan SHA;
- batch code;
- candidate ID;
- candidate spec SHA;
- node ID;
- Git SHA;
- runner-input SHA;
- exact candidate result;
- result artifact SHA.

One candidate directory may contain only one unique deterministic result.
A second conflicting result is a hard nondeterminism error.

A complete batch manifest binds:
- plan SHA;
- batch SHA;
- exact candidate count;
- one Git SHA;
- one runner-input SHA;
- all participating node IDs;
- ordered candidate result SHA list.

A batch is ready for central ingest only after all expected candidate identities
are present and reconciled.

## Auto-ingest target

The final architecture will require no manual copying by the user.

Preferred flow:
1. worker completes a micro-shard/batch;
2. worker produces result manifest;
3. result objects are uploaded or exposed through an authenticated transfer
   channel;
4. VPS automatically retrieves them;
5. VPS verifies artifact SHA, plan SHA, Git SHA, runner-input SHA and candidate
   coverage;
6. VPS writes immutable accepted copies;
7. VPS marks the coordinator batch `INGESTED`;
8. worker may archive/delete its local copy only after explicit
   `INGESTED_ACCEPTED`.

Cloudflare R2 is the preferred optional relay because it separates worker
availability from VPS ingest. Direct authenticated pull remains a fallback.

R2 integration is not activated by this foundation PR and requires explicit
account configuration.

## Hostinger role

Hostinger shared/cloud hosting is not a production backtest worker.

Potential later roles:
- human dashboard;
- secondary status mirror;
- secondary encrypted backup of non-sensitive coordinator metadata.

The compute path remains VPS / laptop / work PC (and future explicitly enrolled
compute nodes).

## Bounded-memory requirement

The confirmed 2026-09-30 OOM incident prohibits one unbounded long-lived Python
process for the 6,852-candidate batch.

Even after per-candidate derived-cache purge is accepted, the final execution
runner must include:
- bounded micro-shards;
- periodic process exit/restart;
- progress;
- checkpoint/reconciliation;
- deterministic resume;
- resource telemetry.

## Runner-input refreeze dependency

PR #172 modifies files that are part of the frozen runner code identity.
Therefore the previously accepted runner input
`3d089036d8a2e3b91f2efe3190c0775bbcb957a76ff352b647cfb177e9587cd3`
cannot be assumed valid after PR #172 merges.

Before any future performance execution:
1. accept/merge bounded-memory code;
2. re-freeze the runner input against the accepted code identity using the same
   accepted 525 Development datasets;
3. independently verify the new runner-input SHA;
4. rerun the fixed 24-candidate capacity benchmark;
5. choose bounded worker concurrency from observed CPU/RAM evidence;
6. freeze the distributed execution plan/bundle identities;
7. separately authorize full performance execution.

## Scientific invariants

Distributed execution changes compute placement only.

It must not change:
- 6,852 candidate identities;
- candidate parameters;
- family definitions;
- dynamic universe membership;
- 525 Development dataset content;
- cost policy;
- F0-F7 criteria;
- neighbor graph;
- multiple-testing accounting;
- Fresh OOS boundary;
- recent reserve boundary;
- P10 state.

CPU location is not a research degree of freedom.

## Current authorization

Allowed by this work unit:
- plan generation;
- plan/hash verification;
- local/Cloudflare coordinator implementation;
- claim/lease/heartbeat logic;
- pause/resume metadata;
- result envelope and batch reconciliation implementation;
- portable worker control client;
- tests;
- deployment preparation.

Not allowed by this work unit:
- calling `ProductionRuntime.run()` for the 6,852-candidate experiment;
- exposing new Development strategy outcomes;
- F0-F7 selection;
- Fresh OOS;
- recent reserve;
- P10 read/write;
- P11;
- Live trading.

Full performance execution remains separately Director-locked.

## Post-PR-175 process lifetime correction — 1 October 2026

The accepted PR #175 isolates each capacity candidate in a fresh process after
the second confirmed VPS OOM. The distributed runner must use the same
one-candidate process lifetime; a 25-candidate child would retain the unproven
long-lived execution model.

New execution plans therefore use exactly one candidate per micro-shard:
6,852 micro-shards across the same 14 logical batches (13 x 500 + 352).
Plan validation and the guarded shard runner reject multi-candidate shards.
The orchestrator already creates a fresh child for each micro-shard.

This changes the operational plan SHA and requires fresh plan/bundle freeze
before deployment. Older 25-candidate plans are rejected. Candidate identities,
specifications, batch membership, data, costs and selection gates are unchanged.
It does not authorize performance or establish runtime capacity. Real VPS and
laptop evidence and explicit full-run authorization remain required.


## Compact result transport

The raw MCF-03 simulator result contains three large structures that are not
consumed by MCF-04 adjudication:

- `per_symbol_base`;
- `per_symbol_stress`;
- `per_symbol_daily_return_series`.

Before durable worker storage, the full result must:
1. pass its original `result_sha256` integrity check;
2. retain every field used by MCF-04 plus the F0-F3 audit summaries;
3. record the source full-result SHA;
4. drop only the three declared heavy fields;
5. receive a new canonical `result_sha256`.

The projection therefore reduces disk/network load without changing candidate
performance, gates, daily return evidence, trial accounting, neighbor
stability, DSR, PBO, reality-check or clustering inputs.

The full unprojected result is ephemeral and must not be used as a reason to
increase worker storage or network privileges.

## Director recovery audit — 30 September 2026

The interrupted chat was recovered against GitHub, not cached refs:
- accepted main: `4a205efe6a20bc01ad7a71403dd320d0acff7a06` (PR #172);
- PR #174 observed HEAD: `56c87444fe989695aadcf86e2d177c5c97d3ed67`;
- PR #174 remained open, draft and unmerged;
- no deployment or full performance authority was inferred from continuation.

The SSH transport, Windows setup/start scripts and VPS-local worker loop are
already implemented. Cloudflare is optional; no account purchase is required.

Recovery fixes:
- create the dedicated `yatl-mcf` group and `yatl-node` SSH account before use;
- use the existing `yatl` account for Git worktrees, avoiding root-owned Git
  ownership checks and avoiding global `safe.directory=*` exceptions;
- set shared coordinator/results directory permissions and narrowly scoped
  ACLs for ancestor traversal, isolated code and the Python environment;
- install the forced command under root-owned `/usr/local/libexec` rather than
  changing the pinned Git worktree's executable bit;
- retain enrolled node keys when preparation is repeated;
- require a successful gateway status preflight under the actual `yatl-node`
  account before reporting VPS preparation ready;
- reject an uploaded batch/manifest that differs from the declared owned
  batch BEFORE writing candidate artifacts or marking it ingested;
- accept the existing capacity CLI's ordinary JSON output and bind its exact
  raw bytes in the authorization, preserving the benchmark evidence unchanged.

Free OS prerequisites on Ubuntu: OpenSSH, `runuser`, and `setfacl` (package
`acl`). If `setfacl` is absent, prepare stops before account setup. Install it
with `sudo apt-get install acl` before retrying. This is an OS utility, not a
new paid service or Python package. Existing `yatl` and the accepted Python
environment remain prerequisites.

After explicit PR acceptance, the preparation order is:
1. pin the accepted merged Git SHA;
2. run `ops/ssh/yatl-mcf-vps-refreeze.sh` with sudo and that SHA;
3. record the emitted runner-input relative path and SHA;
4. run `ops/ssh/yatl-mcf-vps-prepare.sh` with sudo, the exact SHA, runner-input
   values and VPS host label (no performance execution);
5. enroll the separate laptop/work-PC public keys and pin the VPS host key;
6. rerun the blind 24-candidate capacity benchmark on the refrozen input;
7. verify archive import and SSH control on each physical device;
8. separately authorize the 6,852 Development run only after these gates pass.

Acceptance limits: local tests do not prove VPS memory capacity, Windows
PowerShell installation, real SSH transfer, or simultaneous physical-device
execution. Batch-complete auto-ingest is implemented. Partial candidate results
remain local until completion; automatic cross-node recovery of an unfinished
batch still needs a transfer gate before claiming that a different node can
resume it without recomputing completed candidates. These are runtime gates,
not strategy-selection evidence. P10, Fresh OOS, recent reserve, P11 and Live
remain outside this work unit.

## Process-isolation incident and current runtime hold

On 2026-10-01 the isolated fixed benchmark still stopped after 8/24, with global
OOM killing the ninth worker. See the capacity gate's third incident record.
Process lifetime bounds cross-candidate accumulation but does not guarantee a
single candidate fits. No distributed/full run or benchmark retry is authorized
by the new diagnostic work. Its evidence cannot serve as a completed capacity
benchmark or full-performance authorization. The new implementation-only path
is documented in `MCF-PROD-001-SINGLE-CANDIDATE-MEMORY-DIAGNOSTIC-v1.0.md`.
