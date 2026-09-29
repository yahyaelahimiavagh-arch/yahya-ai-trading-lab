# AF-01C P-C — Throughput Optimization v1.0

Status: **IMPLEMENTED FOR REVIEW / BENCHMARK PENDING / UNMERGED**

Date: 2026-09-29

Base:
- P-C broad-population branch HEAD:
  `11678da2bcba3fc719c2c612fd3bde865c8032e4`
- frozen broad-population contract remains authoritative;
- this optimization does not change the 9,306-identity plan or evidence semantics.

## Objective

Reduce repeated verification and network idle time during P-C population without
weakening restartability, immutable-ledger derivation, checksum validation or final
reconciliation.

## Non-negotiable invariants

- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- P10 UNTOUCHED
- P11 LOCKED
- Fresh OOS read=false
- recent reserve read=false
- MAX_CANARY_BATCH remains 25
- deterministic ordered identity selection
- official CHECKSUM verification remains required
- ZIP/member/canonical validation remains required
- SOURCE_GAP and TIMESTAMP_ANOMALY remain preserved
- no interpolation or repair
- no hidden retry / favorable batch selection
- every final ledger remains immutable and content-addressed
- final full reconciliation remains required
- no merge without Director authorization

## Identified bottlenecks

The accepted P-C path was correct but repeatedly paid broad verification costs:

1. full population status before a 25-identity batch;
2. another ordered ledger scan to locate missing identities;
3. per-period full-plan verification inside `acquire_period`;
4. full population status again after the batch;
5. external wrappers could add additional pre/post status scans.

Those costs grow with completed population size.

## Fast-path design

The new `pc-acquire-fast` path is bounded:

- per internal batch limit: <=25 identities;
- max internal batches per process: 40;
- max workers: 4;
- max identities per fast process: 1,000.

At process start:

1. load and verify the frozen plan/inventory once;
2. verify every pre-existing ledger once;
3. derive completed/missing state from immutable ledgers;
4. verify continuation acceptance when above the canary boundary.

During the process:

- selected identities remain in frozen plan order;
- preverified bindings avoid repeating full-plan verification per period;
- up to four independent period acquisitions may run concurrently;
- shared artifact writes remain write-once/content-addressed;
- returned records are not trusted directly: every newly written ledger is re-read
  and verified before it contributes to status;
- batch artifacts are still emitted for each <=25 group;
- status is updated from the verified starting scan plus newly re-read immutable
  ledgers, never from an external progress counter.

A fast-run manifest records:

- requested/completed internal batch count;
- per-batch bound;
- worker count;
- batch refs and SHA-256 identities;
- final verified status SHA.

## Fail-closed behavior

The fast path stops on:

- plan/inventory binding failure;
- continuation-acceptance failure;
- storage-preflight failure;
- checksum/archive/schema failure that raises outside registered final-state handling;
- immutable artifact collision;
- ledger verification mismatch;
- worker/batch bound violation.

Partial completed ledgers remain immutable and are verified/skipped on restart.

## Benchmark gate

No speed claim is accepted from code inspection.

Required VPS comparison after the current 100→1,100 wave is complete:

- baseline: accepted sequential path;
- candidate: `pc-acquire-fast`;
- same frozen root/plan semantics;
- compare elapsed time per newly acquired identity;
- compare resulting ledger states and hashes;
- verify no duplicate identities;
- verify final `population_status` SHA matches an independent full status scan.

Recommended first benchmark:

- 100 new identities;
- 4 internal batches × 25;
- workers=4;
- daily fallback OFF.

The optimization is accepted for broad continuation only if correctness remains
identical and measured throughput improves materially.

**MERGED=NO**
