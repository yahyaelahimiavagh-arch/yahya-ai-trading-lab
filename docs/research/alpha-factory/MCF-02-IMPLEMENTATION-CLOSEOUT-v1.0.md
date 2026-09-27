# MCF-02 Mass Candidate Engine — Implementation Closeout

Status: **IMPLEMENTATION_ACCEPTED / MERGED**

Work unit:
`MCF-02-MASS-CANDIDATE-ENGINE-IMPLEMENTATION`

Merged PR:
`#144 research: implement MCF-02 deterministic mass candidate engine`

Implementation branch Final HEAD:
`637b865c097246a901c937bb1de8fc4b90c8f8c3`

Merged main commit:
`2adb89eb2eae1c3160e0adb66aabbb2c2dd85f66`

Starting main:
`a95cfe76ae802e40fb620ae55a44df1f83a16dc8`

GitHub Actions:
- Run ID: `36332442478`
- `unit-and-safety`: SUCCESS
- `accepted-public-data`: SUCCESS

## Implementation scope

20 changed files:
- 12 engine/runtime files under `research/mass_candidate_factory/`
- 8 fixture/test files

No dependency change.

Implemented responsibilities:
- manifest validation;
- deterministic candidate generation;
- typed bounded operators;
- shared feature cache;
- deterministic sharding;
- append-only/reconciled ledger;
- F0-F3 screening infrastructure;
- exact recompute path;
- screening/evidence identity binding;
- safety/evidence isolation;
- engineering-only calibration.

## Determinism / reconciliation

Accepted:
- stable candidate identity;
- stable candidate spec SHA;
- stable manifest SHA;
- shard rerun/idempotence;
- ledger reconciliation;
- `BATCH_COMPLETE` behavior.

## Numerical calibration

Synthetic fixture:
- maximum observed float-vs-Decimal discrepancy: approximately `6.43e-13`.

This is engineering calibration only and not strategy evidence.

## Engineering calibration

`MCF-ENGINE-CALIBRATION-001`

State:
`ENGINEERING_ONLY_NO_SELECTION`

Observed:
- 1,000 specs;
- about 9,419 specs/sec generation;
- about 49 screening candidates/sec;
- about 12,587 candidate-bars/sec;
- peak memory about 5.5 MB;
- deterministic repeat execution.

No candidate was promoted.

## Tests

Focused:
- MCF: 11/11 PASS
- GEN2: 31/31 PASS

Full local suite:
- 1,733 tests;
- 6 legacy P7/P8/P10 audit failures reproduced on clean main;
- classification: `CURRENT_MAIN_BASELINE_FAILURE`;
- no MCF regression.

Exact Final-HEAD GitHub Actions: green.

## Evidence boundary

- Fresh OOS read: false
- recent reserve read: false
- P10 runtime-store read/write: false/false
- performance selection run: false
- production 1k/10k/100k batch: false
- P11: locked
- Live: unauthorized

## Interpretation

MCF-02 proves the reusable factory infrastructure is implementation-ready.

It does NOT prove:
- 10k/100k throughput at production scale;
- profitability of any strategy family;
- survivor quality;
- Fresh OOS readiness;
- portfolio readiness;
- Forward readiness.

## Next production prerequisites

Before the first true mass Development selection batch:

1. AF-02B bounded Registry v2 migration accepted.
2. AF-01B admitted point-in-time opportunity data foundation accepted.
3. executable family parameter domains frozen.
4. production trial budgets frozen.
5. evidence policy frozen.
6. multiple-testing / neighbor / clustering route defined.
7. batch manifest frozen before outcome.

Until these close, MCF is infrastructure-ready but production-selection locked.
