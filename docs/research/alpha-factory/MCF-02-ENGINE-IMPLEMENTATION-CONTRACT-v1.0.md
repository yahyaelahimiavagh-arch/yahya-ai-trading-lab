# YATL MCF-02 — Mass Candidate Engine Implementation Contract v1.0

Status: DESIGN FROZEN BEFORE ENGINE IMPLEMENTATION
Established: 2026-09-27
Mode: CHAT_DIRECTOR for contract; WORK_REQUIRED for substantial implementation
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

## 1. Purpose

MCF-02 defines the reusable software engine that will generate and evaluate very
large canonical candidate populations without one-code-file-per-strategy
or one-interactive-task-per-candidate.

The implementation must optimize throughput while preserving:
- deterministic identity;
- reproducibility;
- complete negative-evidence retention;
- evidence partition locks;
- exact recomputation before survivor freeze;
- safety constraints.

MCF-02 implementation does NOT itself authorize a production 10k/100k
selection run.

## 2. Required package structure

Preferred package:

research/mass_candidate_factory/
- __init__.py
- models.py
- manifest.py
- generator.py
- feature_cache.py
- screening.py
- exact.py
- ledger.py
- shards.py
- cli.py

Tests:
- tests/test_mcf_manifest.py
- tests/test_mcf_generator.py
- tests/test_mcf_shards.py
- tests/test_mcf_ledger.py
- tests/test_mcf_screening.py
- tests/test_mcf_exact_recompute.py
- tests/test_mcf_safety.py

Exact filenames may be minimally adjusted if repository conventions require it,
but responsibilities must stay separated.

## 3. Manifest validator

The validator must:
- bind MCF-01 manifest schema identity;
- reject unknown/missing fields;
- reject unsafe absolute paths;
- reject symlink traversal;
- reject unsupported dependency labels;
- reject unbounded parameter domains;
- reject hidden-trial flags;
- reject leverage/short/Futures/Live capability;
- compute canonical manifest SHA-256;
- emit no market outcome.

CLI:
python -m research.mass_candidate_factory.cli validate-manifest ...

## 4. Deterministic generator

Input:
- frozen family manifest(s);
- batch generation ID;
- generator version.

Output:
- batch manifest;
- canonical candidate JSONL;
- generation digest;
- structural-invalid JSONL when applicable.

Requirements:
- stable enumeration order;
- same inputs -> same candidate IDs and spec SHAs;
- candidate IDs assigned before performance;
- no outcome read path;
- no random source unless an explicit deterministic seed/sampling contract is
  frozen;
- structural constraints applied before economic evaluation;
- duplicates detected from canonical spec identity.

Preferred storage:
- JSONL/NDJSON rather than one file per candidate;
- optionally compressed only if deterministic compression metadata is controlled.

## 5. Batch identity

Batch manifest must bind:
- batch_id;
- generator_version;
- family manifest SHAs;
- evidence policy ref;
- universe policy ref;
- cost policy ref;
- candidate ordinal ranges;
- raw candidate count;
- structural-valid count;
- structurally-invalid count;
- shard layout;
- candidate-ledger SHA.

No later shard may add candidates not present in the frozen batch manifest.

## 6. Sharding

Candidates must be split into deterministic ordinal ranges.

Example:
- shard 000: candidates 000000-000999
- shard 001: candidates 001000-001999

Shard identity depends only on:
- batch identity;
- ordinal range;
- shard schema version.

Requirements:
- idempotent rerun;
- content-addressed result artifact;
- safe restart after interruption;
- existing complete shard must not be silently overwritten;
- collision with different bytes is fatal;
- incomplete checkpoint is never treated as complete evidence.

## 7. Shared feature cache

The engine should avoid recomputing identical features for every candidate.

Cache keys must bind:
- dataset identity;
- symbol;
- timeframe;
- feature family;
- parameter(s);
- code/version identity.

Examples:
- moving-average windows;
- rolling high/low;
- rolling mean/std;
- lagged returns;
- rolling volume statistics;
- volatility estimates;
- session/time masks.

No cached feature may cross evidence partitions.

Cache content is an implementation acceleration, not evidence.

## 8. Screening numerical engine

To make 10k-100k scale feasible, MCF may use fast floating-point screening.

Preferred research dependency:
- pinned NumPy for vectorized screening if benchmarked and accepted.

If NumPy is added:
- pin the exact version in project/lock files;
- keep it research-only where repository packaging allows;
- do not use pandas as an implicit dependency;
- record NumPy version in batch artifacts.

Float screening never becomes canonical survivor evidence by itself.

## 9. Screening vs exact recompute safety

Every hard threshold needs a gray-zone rule.

A candidate near a screening boundary must be routed to exact recompute rather
than rejected from float rounding.

Required calibration:
- compare float-screening outputs to the existing Decimal/exact accounting on a
  bounded fixture set;
- record maximum observed metric error;
- define conservative guard bands before production use;
- any mismatch that can flip a hard gate is a blocker.

Candidates considered for DEVELOPMENT_SURVIVOR require exact recompute.

## 10. Engineering calibration is non-selection

Before any production mass search, run an engineering calibration batch.

Calibration goals:
- ID determinism;
- manifest determinism;
- candidate count reconciliation;
- shard restart/recovery;
- throughput;
- RAM;
- cache behavior;
- screening/exact agreement;
- ledger integrity.

Calibration outcomes are:
ENGINEERING_ONLY_NO_SELECTION

Rules:
- no winner may be promoted from calibration;
- no strategy conclusion is drawn from calibration PnL;
- calibration may use synthetic fixtures and/or already-known Development data;
- if known market data is used, it creates no new Fresh/OOS claim;
- production candidate domains must not be tuned from calibration market
  outcomes.

## 11. Production screening stages

The reusable engine should support:

F0_STRUCTURAL_VALIDITY
F1_OPPORTUNITY_VALIDITY
F2_AFTER_COST_DEVELOPMENT
F3_TEMPORAL_ROBUSTNESS

F4-F6 analytics may initially be implemented as separate modules/jobs:
- neighbor stability;
- multiple-testing;
- duplication/common-factor clustering.

This reduces MCF-02 implementation risk.

## 12. Result ledger

Use append-only/shard-reconciled ledgers.

Each candidate result must include:
- candidate_id;
- candidate_spec_sha256;
- batch_id;
- shard_id;
- screening_engine_version;
- dataset/evidence identity;
- result_state;
- failure reasons;
- opportunity metrics;
- base/stress economics;
- temporal metrics;
- exact_recompute_state;
- result_record_sha256.

No candidate disappears because it failed.

## 13. Batch reconciliation

A batch closes only if:
- every frozen candidate ID appears exactly once in a final state;
- no unregistered candidate appears;
- no duplicate result row exists;
- all shard SHAs reconcile;
- result count matches batch manifest;
- structural-invalid count reconciles;
- safety flags match;
- no forbidden evidence read is reported.

Output:
BATCH_COMPLETE or BATCH_INVALID.

Partial success is not canonical batch completion.

## 14. Safety

The engine must not contain:
- order placement;
- API trade permission;
- withdrawal code;
- Futures;
- leverage;
- short execution;
- Live enablement;
- P10 write path;
- Fresh OOS read path during Development;
- recent reserve read path.

Mass scale must not create a shortcut around existing locks.

## 15. Evidence path allowlist

Development runtime should require explicit evidence-root and allowed manifest.

Fail closed if:
- path resolves into P10 state;
- Fresh OOS partition is requested before freeze;
- recent reserve is requested;
- unknown quality manifest is supplied;
- dataset identity mismatches batch evidence policy.

## 16. Performance architecture

Avoid:
candidate_count x raw_feature_recomputation.

Preferred flow:
1. load admitted dataset;
2. build shared feature arrays once;
3. evaluate candidate masks/signals in batches;
4. compute screening metrics;
5. persist result shard;
6. exact-recompute qualifying/gray-zone candidates.

The engine should expose throughput counters:
- candidates/sec;
- candidate-bars/sec;
- feature-cache build time;
- screening time;
- exact recompute time;
- peak memory;
- artifact bytes.

## 17. Concurrency

Concurrency must be bounded and deterministic at the result layer.

Allowed:
- process-level shard parallelism;
- deterministic independent worker assignment.

Requirements:
- worker count does not affect candidate identities;
- worker count does not affect numerical results;
- output order is canonicalized before hashing;
- interrupted workers are restartable.

Avoid hidden thread-level nondeterminism when it affects numerical reduction.

## 18. Initial family implementation scope

MCF-02 does not need to implement all 16 catalog families.

First reusable engine should support enough primitive operators to cover several
families without hardcoding each candidate.

Initial primitives:
- lagged return;
- moving average;
- rolling min/max;
- rolling mean/std;
- OHLC range;
- volume / quote-volume rolling statistics;
- trade-count rolling statistics;
- UTC time/session masks;
- cross-asset lagged relation for BTC/ETH where admitted.

Initial rule operators:
- greater/less threshold;
- cross above/below;
- z-score threshold;
- breakout/reentry;
- conjunction/disjunction of preregistered conditions;
- long/cash state machine;
- fixed quantity;
- nonlevered scale in [0,1] when authorized by family manifest.

No generic unrestricted expression language in v1.

## 19. No strategy DSL free-for-all

MCF v1 must NOT accept arbitrary Python/eval expressions from manifests.

Reason:
- security;
- reproducibility;
- hidden degrees of freedom;
- impossible audit surface.

Use a bounded typed operator schema.

New operators require code review and versioned engine changes.

## 20. Cost model

Screening must support existing YATL base/stress fee/slippage assumptions.

A family may bind another preregistered cost policy only through a versioned
policy reference.

No candidate-specific cost optimism.

## 21. Exact accounting

Exact recompute should reuse or share trusted existing YATL accounting
primitives where possible.

Do not create a second incompatible definition of:
- fills;
- fees;
- adverse slippage;
- realized PnL;
- equity;
- drawdown.

Any deliberate difference requires explicit versioning.

## 22. Tests

Minimum acceptance tests:

Manifest:
- valid accepted;
- missing field rejected;
- unknown field rejected where schema is exact;
- unsafe paths rejected;
- forbidden safety flag rejected.

Generator:
- same manifest -> identical IDs/SHAs;
- order stable;
- invalid parameter combos excluded deterministically;
- duplicates detected.

Shards:
- deterministic ranges;
- restart idempotence;
- collision fails closed;
- missing shard prevents closeout.

Ledger:
- exactly-once result identity;
- reconciliation count;
- negative results retained.

Screening:
- deterministic repeated result;
- costs applied;
- no lookahead;
- opportunity metrics correct.

Exact:
- screening/exact fixture comparison;
- gray-zone route;
- exact survivor recomputation.

Safety:
- no P10 write;
- no Fresh OOS Development read;
- no recent reserve read;
- no leverage/short/Futures/Live/order endpoint.

## 23. CI acceptance

MCF-02 Final HEAD must:
- pass focused MCF tests;
- pass repository unit-and-safety;
- pass accepted-public-data;
- preserve existing P10 tests;
- contain no market-selection output from engineering calibration.

## 24. First runtime after implementation

Allowed first runtime:
MCF-ENGINE-CALIBRATION-001

State:
ENGINEERING_ONLY_NO_SELECTION

It may benchmark approximately 1,000 fixture/canonical specs for throughput and
determinism.

It must not:
- create DEVELOPMENT_SURVIVOR;
- open Fresh OOS;
- tune production family domains from market PnL;
- write P10.

## 25. Production gate

A true mass Development batch is authorized only after:
- MCF-02 engine accepted;
- AF-01B required data foundation accepted for that batch;
- Registry v2 migration/ledger integration accepted;
- family parameter domains frozen;
- trial budgets frozen;
- evidence policy frozen;
- multiple-testing accounting route defined.

## 26. Work-token policy

This is an appropriate WORK_REQUIRED package because it is one substantial
reusable multi-file implementation.

Use one Work package for the engine, not Work per candidate.

After implementation, candidate generation and batch execution should run
deterministically on the VPS/runtime with Director-supervised checkpoints.
