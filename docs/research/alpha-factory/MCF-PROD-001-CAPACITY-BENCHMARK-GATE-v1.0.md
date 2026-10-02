# MCF-PROD-001 Capacity Benchmark Gate — v1.0

Status: **IMPLEMENTATION CANDIDATE / NO FULL BATCH AUTHORITY**

Work unit: `MCF-PROD-001-CAPACITY-BENCHMARK-GATE`

Baseline main:
`ab3eea1436cc72c8e0a33631215bc649192c7c95` (PR #169 merged).

## Purpose

Measure the real VPS cost of the frozen Development runtime before authorizing
the complete 6,852-candidate production batch.

This is an engineering-capacity gate, not a selection run.

The benchmark is deliberately blind to candidate outcomes:
- exactly 24 candidates are selected deterministically before runtime outcome;
- selection is round-robin across frozen family/timeframe buckets;
- no PnL, return, drawdown, Sharpe, trade count, gate result, rank or survivor
  status is printed or written;
- no candidate result artifact is persisted;
- only elapsed time, CPU time, peak RSS and family/timeframe timing totals are
  exposed;
- candidate logic, thresholds, families, membership and evidence are immutable.

## Authoritative input

The benchmark may consume only the accepted frozen runner input:

`3d089036d8a2e3b91f2efe3190c0775bbcb957a76ff352b647cfb177e9587cd3`

from:

`/var/lib/yatl/research/mcf-prod-001-runtime-input`

The accepted materialized runtime index remains:

`55c8c476cd5043a652c09f060e2a58b6b1dd9cfd9bffef33e3d8ff7a3a6092c3`

The runner input already binds:
- 34 monthly memberships;
- selected union of 175 symbols;
- 525 materialized 15m/1h/4h datasets;
- exact 6,852 executable candidate identities;
- cost policy;
- Development evidence boundaries;
- safety locks.

## Fixed benchmark sample

Benchmark count: **24 candidates**.

The subset is derived only from static frozen candidate metadata:
1. group executable candidates by `(family, timeframe)`;
2. sort candidates in each bucket by canonical candidate ID;
3. sort bucket keys;
4. round-robin one candidate per bucket until 24 are selected.

No performance value participates in selection.

The benchmark-selection SHA-256 is emitted at runtime so repeated VPS runs can
prove they used the same static subset.

## Runtime authorization

The capacity command requires the exact Director token:

`MCF-PROD-001-CAPACITY-BENCHMARK-001`

This token authorizes only the fixed 24-candidate blind benchmark.

It does **not** authorize:
- the 6,852-candidate batch;
- candidate ranking or survivor selection;
- F0-F7 adjudication;
- Fresh OOS;
- recent reserve;
- P10 read/write;
- P11;
- Live execution.

## Output boundary

Allowed output:
- benchmark status;
- runner-input SHA;
- candidate count;
- static benchmark-selection SHA;
- family/timeframe bucket count;
- wall time;
- process user/system CPU time;
- peak RSS;
- aggregate timing by family/timeframe;
- fixed safety flags.

Forbidden output:
- per-candidate or aggregate economics;
- completed trade counts;
- signal counts;
- drawdown;
- Sharpe/DSR/PBO;
- pass/fail performance gates;
- ranking;
- survivor information.

Progress messages such as `7/24 (29.2%)` are allowed because they reveal no
candidate outcome.

## Scientific boundary

The benchmark may influence only engineering choices such as:
- VPS CPU/RAM size;
- shard sizing;
- safe worker count;
- timeout policy;
- checkpoint/restart design.

It may not influence:
- candidate parameters;
- family inclusion/exclusion;
- opportunity thresholds;
- cost thresholds;
- statistical gates;
- symbol membership;
- evidence partitions.

If capacity is inadequate, the remedy is engineering infrastructure, not
strategy retuning.

## Safety

Unchanged:
- PAPER / RESEARCH ONLY;
- LIVE_MASTER_LOCK=OFF;
- NO FUTURES;
- NO LEVERAGE;
- NO SHORT;
- NO LIVE EXECUTION;
- NO ORDER ENDPOINT;
- NO AI DIRECT EXECUTION;
- Fresh OOS unread;
- recent reserve unread;
- P10 read/write=false;
- P11 locked.

## Acceptance sequence

1. implementation and tests green on exact PR HEAD;
2. Director review and merge;
3. run the fixed benchmark once on VPS using the accepted runner input;
4. inspect capacity metrics only;
5. freeze the full-batch execution/sharding plan;
6. obtain a separate explicit Director authorization before exposing any
   6,852-candidate Development performance.

Zero candidate economics are authorized in this work unit's user-visible output.


## VPS OOM incident — 2026-09-30

The first real VPS benchmark on merged main `21aa64e774f54b0399c561dab3f33e47d17630ff`
was terminated after 8/24 candidates with exit code 137.

Kernel evidence:
- global OOM killer invoked by the Python benchmark process;
- killed PID: 48793;
- anonymous RSS at kill: 3,586,144 KiB;
- total VPS RAM: approximately 3.7 GiB;
- swap: 0 bytes.

Classification:
`CONFIRMED_OOM / ENGINEERING_CAPACITY_FAILURE / NO_SELECTION_OUTCOME`.

No candidate economics were printed or persisted by the benchmark.

Root mechanism:
the long-lived `ProductionRuntime` retained candidate-derived feature arrays
inside each `ProductionFeatureCache._cache` and retained liquidity matrices
across candidates. The cache key space grows as parameter combinations change.

Required remediation before any capacity rerun:
- clear candidate-derived feature arrays after every candidate;
- clear candidate-derived liquidity matrices after every candidate;
- force garbage collection at the benchmark boundary;
- expose current RSS with progress for operational diagnosis;
- retain immutable source bars and the frozen input binding;
- preserve the exact 24-candidate pre-outcome benchmark selection.

Full-batch requirement is stronger:
even after bounded in-process caches are accepted, the eventual 6,852-candidate
runner must use bounded shards plus periodic process termination/restart,
append-only checkpoints and deterministic resume. One unbounded Python process
is forbidden for the production batch.

This incident does not authorize strategy tuning, family changes, threshold
changes, selection, Fresh OOS, recent reserve or P10 access.


## Second VPS OOM incident — 2026-10-01

The cache-release remediation merged in PR #172 was rerun on main
\`4a205efe6a20bc01ad7a71403dd320d0acff7a06\` after deterministic reconstruction
of the accepted pre-performance evidence.

Reconstructed identities matched the previously accepted evidence:

- classification map SHA-256:
  \`e19cb8539c29e6a95c453b6a680b56b5b88bddad65df8a67ca32a14ceab41012\`;
- production-binding preflight SHA-256:
  \`f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc\`;
- monthly membership SHA-256:
  \`c75aa5c4347dff5daeed1ca2625fb86e2df3f4e105fde55aed0248df4ce868b7\`;
- runtime dataset count: 525;
- runtime index SHA-256:
  \`55c8c476cd5043a652c09f060e2a58b6b1dd9cfd9bffef33e3d8ff7a3a6092c3\`;
- refrozen runner-input SHA-256 on the PR #172 code identity:
  \`ac123936204b571a93982341dfaa79c2527370c3e2b4d5be3f1fbb3cddb3d561\`.

Independent no-performance verification passed before the benchmark.

The fixed 24-candidate benchmark again completed 8/24 candidates and then the
Python process was killed with exit code 137. Progress checkpoints after
completed candidates reported approximately 1.10-1.36 GiB current RSS, but the
kernel recorded a much larger transient allocation before the next progress
checkpoint:

- OOM timestamp: 2026-10-01 08:09:55 UTC;
- killed PID: 52959;
- total VM: 3,580,284 KiB;
- anonymous RSS: 3,531,456 KiB;
- file RSS: 2,176 KiB;
- total VPS RAM: approximately 3.7 GiB;
- swap: 0 bytes.

Classification:

\`CONFIRMED_OOM_AFTER_IN_PROCESS_CACHE_RELEASE / ENGINEERING_CAPACITY_FAILURE / NO_SELECTION_OUTCOME\`.

No candidate economics were printed or persisted.

This second incident disproves the assumption that clearing transient feature
caches and forcing garbage collection is sufficient for this VPS. Post-candidate
RSS is not a safe upper bound on within-candidate transient memory. A single
long-lived Python process may still approach the machine limit between progress
checkpoints.

Required remediation before another capacity rerun:

- preserve the exact deterministic 24-candidate pre-outcome selection;
- execute each selected candidate in a fresh Python subprocess;
- independently verify inside each worker that its candidate belongs to that
  fixed selection;
- discard all candidate economics inside the worker;
- permit only capacity-only worker fields to cross the process boundary;
- aggregate wall time, CPU time, peak worker RSS and family/timeframe timings in
  the parent;
- fail closed if a worker returns any unexpected field or exits abnormally;
- do not expose or authorize the 6,852-candidate Development batch.

This process-isolation remediation is an engineering change only. It does not
authorize parameter changes, family changes, selection, Fresh OOS, recent
reserve, P10, P11 or Live execution.

## Third VPS OOM incident — 2026-10-01, after process isolation

Director-provided runtime/kernel evidence (not independently read from VPS in
this implementation unit): accepted main `da0b34adf83f0e824b501d54e3597717c8dc4ea6`,
GitHub Actions #493 successful. The one fixed blind benchmark attempt completed
8/24 workers. Their peak RSS values in KiB were 2,458,312; 667,072; 2,502,676;
680,140; 2,637,232; 708,444; 2,610,468; 705,640. The next isolated worker exited 137.

Artifact: `CAPACITY_BENCHMARK_BLOCKED`, reason
`isolated capacity worker failed with exit code 137`; selection and full batch
remain unauthorized. Kernel approximately 20:40:46 UTC: global OOM killed python
PID 56813, UID 999; total-vm 3,591,404 kB, anon-rss 3,533,404 kB, file-rss 2,432 kB.
MemTotal 3,911,552 kB; SwapTotal 0 kB.

Classification: `CONFIRMED_SINGLE-CANDIDATE_OOM_AFTER_PROCESS_ISOLATION` /
`NO_SELECTION_OUTCOME`. This disproves the engineering assumption that fresh
processes alone fit each candidate on this VPS. The first and second incidents
above remain negative evidence; none is superseded or erased.

Current next unit is implementation-only instrumentation for the deterministic
ninth member. **No 24-candidate retry is authorized.** Historical acceptance and
refreeze instructions above are not a new runtime permission. See
`MCF-PROD-001-SINGLE-CANDIDATE-MEMORY-DIAGNOSTIC-v1.0.md`.

## Fourth OOM incident — one-time memory diagnostic

Director-provided diagnostic/kernel evidence on accepted main
`890c47ce2c75774ab5f5e4aebcc0cbfddfb7c866`: fixed ninth member
`MCF-PROD-001-004784` completed dataset loading at RSS 3,181,220 KiB
(approximately 3.034 GiB), peak 3,213,048 KiB, elapsed 343.646712 seconds.
It was globally OOM-killed during `feature_cache_initialization`, with no end
checkpoint for that stage. Diagnostic was `DIAGNOSTIC_INCOMPLETE`, child -9 /
137 / signal 9; kernel identified the same PID 59773, anon-rss 3,563,328 kB,
total-vm 3,628,592 kB, file-rss 2,432 kB. Host MemTotal about 3,911,552 kB,
SwapTotal 0. Classification: `CONFIRMED_OOM_DURING_FEATURE_CACHE_INITIALIZATION`.

No economics/performance artifact, selection, benchmark retry or full run.
All first/second/third incidents above remain preserved negative evidence.
Engineering remediation and synthetic-only equivalence/memory evidence are in
`MCF-PROD-001-FEATURE-CACHE-MEMORY-REMEDIATION-001.md`. That implementation
does not grant refreeze, real candidate runtime, benchmark retry or batch authority.

## Fifth OOM incident — post-cache-remediation diagnostic

Director-provided diagnostic/kernel evidence on accepted main
`37ed99d4c636646909cb23cf59b0f9ad554fedb0`, fixed ninth member
`MCF-PROD-001-004784`, candidate spec
`73395d80d49f24818b9aedf8dbbfac35df3ad585f7d510a11d90778e0861f6c9`.
Runner input `2b6f9d63fbf6224b178dbc3cf46762220777dfb2f4110e7042efb5b83434a5f8`;
authorization `a24140f8ca19d994af625570d6218644654fe9202543490cb5b346a53d588647`;
unchanged benchmark selection
`03f02f30f576b9e71c906d47ee15c200364f04cd187f229c00e54030c50a5248`.

Dataset loading ended at elapsed 360.224187 seconds, RSS 3,183,108 KiB,
peak 3,213,016 KiB. Feature-cache initialization began at 360.224468 and
completed at 490.108808 seconds with the same RSS/peak. Signal compilation
began at 490.109322 seconds; no END checkpoint. Diagnostic was
`DIAGNOSTIC_INCOMPLETE`, child -9 / exit 137 / signal 9. Kernel identified
the same PID 62418 as a global OOM victim: total-vm 3,633,116 kB,
anon-rss 3,572,800 kB, file-rss 2,432 kB, shmem-rss 0, swap 0.
Classification: `CONFIRMED_OOM_DURING_FEATURE_SIGNAL_COMPILATION`.

This is a new stage boundary. PR #177 completed its intended stage and is
preserved as effective engineering evidence. All five historical OOM incidents
remain separate records. No performance exposed/written, selection, benchmark
retry or full batch authorized. The evidence was supplied by Director, not
independently collected from the VPS in this work unit. See
`MCF-PROD-001-FEATURE-SIGNAL-MEMORY-REMEDIATION-001.md` for synthetic-only
engineering remediation; it grants no runtime authority.
