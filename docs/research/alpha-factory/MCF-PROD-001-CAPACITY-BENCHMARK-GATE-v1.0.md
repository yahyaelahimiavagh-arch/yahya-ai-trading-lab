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
