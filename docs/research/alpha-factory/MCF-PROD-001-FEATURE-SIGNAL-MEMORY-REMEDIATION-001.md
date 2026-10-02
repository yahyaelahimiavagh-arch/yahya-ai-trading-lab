# MCF-PROD-001 feature-signal memory remediation

Work unit: `MCF-PROD-001-FEATURE-SIGNAL-MEMORY-REMEDIATION-001`.
Status: DRAFT / DIRECTOR REVIEW REQUIRED / ENGINEERING ONLY / NO RUNTIME AUTHORIZATION.
Starting main verified directly through GitHub before local audit:
`37ed99d4c636646909cb23cf59b0f9ad554fedb0` (accepted PR #177).
Branch: `mcf-prod-001-feature-signal-memory-remediation`.

## Independently derived frozen ninth candidate

The ordered family-domain plan has 128 + 640 + 1,280 + 1,536 + 1,200 raw
Cartesian members before SESSION_TIME_EFFECT: its first raw ordinal is **4,784**.
The generator assigns raw ordinals before structural filtering, without
renumbering surviving identities. SESSION_TIME_EFFECT has 360 parameter vectors
per timeframe (6 starts × 3 lengths × 5 lookbacks × 4 thresholds), with `15m`
first and `1h` second. Local ordinal zero selects the first value in each domain:

| Field | Derived value |
| --- | --- |
| Candidate | `MCF-PROD-001-004784` |
| Family / family ID | `SESSION_TIME_EFFECT` / `MCF-P1-F06` |
| Timeframe | `15m` |
| Parameter vector | `session_start_utc=0`, `session_length_hours=4`, `return_lookback=1`, `return_threshold="0"` |
| Candidate spec SHA-256 | `73395d80d49f24818b9aedf8dbbfac35df3ad585f7d510a11d90778e0861f6c9` |
| Family spec SHA-256 | `5d119ddd9c183fdb18c8671f06ba95e73237e0930d439d4bb0a32d9da8c63bd5` |
| Domain plan SHA-256 | `63582afc846d9ed3e5e21024264fb40b89e9b8d3d09e54921f430ecd9b6b9c8d` |
| Search budget SHA-256 | `f0bd1bde092dc20fed0407e013f6c80ba1330ed15f0c9ac87ac008dd623dfbc1` |
| Universe policy SHA-256 | `9202869aad47591461f9d41c927ed48a2697f5a3f59a6e79b3de13586d14e251` |

The structural condition 0 + 4 <= 24 passes. Running **metadata generation only**
confirmed the exact identity/spec digest above. No real candidate was compiled,
simulated, refrozen or diagnosed. The synthetic stress fixture uses the same
family/timeframe/parameters with a distinct `SYNTHETIC-SIGNAL-*` identity.

## Evidence and root cause

The fifth incident is appended separately to
`MCF-PROD-001-CAPACITY-BENCHMARK-GATE-v1.0.md`. It is Director-provided VPS
telemetry, not a new VPS observation. All earlier incidents remain unchanged.
PR #177 successfully completed feature-cache initialization at the same resident
RSS at entry/exit. Its removal of `_index` and validation copies stays intact.

**CONFIRMED CURRENT BOTTLENECK:** the kernel killed the same Python worker during
`feature_signal_compilation`. The checkpoints locate the stage, but do not
identify the exact last allocation or last symbol at the moment of death.
The source audit finds avoidable **cross-symbol retention** at that stage:

- `ProductionRuntime.run()` eagerly retains a full `ProductionSeries` per symbol.
  `times`, `opens` and `closes` are references to immutable source tuples, not
  copies. The independently owned arrays are `desired_state` and
  `feature_available`, both unchanged boolean tuples.
- `compile_candidate()` materializes final boolean outputs, but the feature
  cache retains candidate-derived float tuples afterward. For the exact session
  shape, each symbol retains a lagged-return tuple after its last consumer.
  No downstream accounting or simulation reads feature caches.
- A float feature tuple costs roughly **32N bytes** (8N references + approximately
  24N float objects, excluding tuple header/None warm-up slots). The two boolean
  tuples cost **16N bytes + 80 bytes** on measured 64-bit CPython; singleton bool
  objects are shared. A series instance adds 48 bytes in this runtime, excluding
  its small instance dictionary. Eight 90,000-row synthetic symbols retain
  exactly 23,040,128 bytes of unique lagged-return tuples/floats before the change.
- Before cleanup, completed symbols grow by roughly **48N** bytes each for this
  session shape (32N feature + 16N outputs). After cleanup, they grow by **16N**,
  with only the current symbol's feature/intermediate working set added.
- General compiler `entry`, `exit_`, `available` each need an N-sized reference
  list under the current design: approximately 24N bytes combined. `_state`
  temporarily has its growing output list plus final tuple; tuple conversion
  for `available` also overlaps live input/output lists. These remain symbol-local.
  Trend formerly allocated three outer N-sized lists it never used, in addition
  to the three lists allocated inside `_cross_state`; those outer lists are removed.
- Zscore holds lagged mean, std and z arrays; an optional MA200 adds another.
  Lead-lag holds a peer index while computing peer returns. Liquidity ranking
  holds all symbols' trailing sums, timestamp indexes and output percentiles
  until its cross-symbol calculations complete. Their formulas/precision and
  cross-symbol consumers are unchanged.

The existing runtime contract documents 175 union symbols and 525 datasets.
Without reading production rows, let M be the sum of admitted row counts: final
boolean tuple storage is exactly **16M + 80S bytes**, where S is series count,
plus small series/map objects; source tuples remain shared. A full-history
mathematical bound of 175 × 105,216 15m rows would yield 294,618,800 bytes
(~281 MiB) of boolean tuple containers. That is an illustrative upper-bound
arithmetic, **not actual production row counts or capacity evidence**. The
actual retained source matrix is already about 3.036 GiB in supplied telemetry.

## Minimal changes and ownership boundary

Only three production modules change:

1. `production_runtime.py`: release leftovers from prior candidate runs, compile
   each symbol in the same order, then clear only that symbol's derived cache
   in `finally`. The compiler has returned independent boolean outputs before
   release. Lead-lag's peers reference source bars, not another cache's arrays.
2. After liquidity ranking returns, its trailing-sum caches have no remaining
   consumer and are cleared. The independent percentile mapping stays alive
   through every compiler call. After all symbol compilation (or an exception),
   transient caches/percentiles are cleared before simulation. Runtime source
   bars and timeframe caches remain reusable; clearing is idempotent.
3. `production_rules.py`: allocate general N-sized scratch lists after the trend
   early-return branch; no rule, parameter, arithmetic or state transition changes.
4. `production.py`: proactive, bounded `ProductionSeries.validate()` scans use
   `pairwise` and `chain` instead of slices/concatenation. Decimal conversion is
   performed on every price in the original order while retaining only the
   current value and invalid flag. Rejection is deferred until the sequence is
   fully converted, preserving conversion-exception precedence over invalid
   prices. Every validation remains enabled; types/messages remain equivalent.

Runtime reuse is intentional: `production_worker_runner.run_microshard()` creates
one runtime then runs multiple candidates and releases transients after each.
The new release makes ordinary reuse bounded without relying on that external
cleanup. Recalculation can cost CPU, but does not change any feature values.
No streaming architecture, array representation change, alternate precision,
retuning, data reduction, history truncation, swap or RAM increase is introduced.

## Synthetic memory measurements

Python 3.12.14, Linux, fresh process per mode; eight preconstructed synthetic
15m symbols, 90,000 rows each, SESSION_TIME_EFFECT vector above. Bars/cache
initialization happens before measurement. Simulation is replaced by a test
stub that returns the exact signal series: **no economics are computed** in
these probes. Normal RSS and tracemalloc are separate executions.
Raw per-symbol records and auxiliary measurements are committed in
`MCF-PROD-001-FEATURE-SIGNAL-MEMORY-EVIDENCE-001.json`.

| Metric | Accepted-main baseline | Remediated |
| --- | ---: | ---: |
| Normal RSS before compilation, KiB | 231,612 | 231,524 |
| Normal RSS after compilation, KiB | 273,384 | 247,380 |
| Process peak RSS, KiB | 273,252 | 249,344 |
| Feature-cache retained bytes before | 0 | 0 |
| Feature-cache retained bytes after | 23,040,128 | 0 |
| Owned series instance + boolean tuple bytes (source refs excluded) | 11,521,024 | 11,521,024 |
| Traced retained compilation bytes | 34,570,976 | 11,534,096 |
| Maximum measured compilation allocation, bytes | 36,816,953 | 16,657,618 |

Traced peak reduction: **54.76%**; traced retained reduction: **66.64%**.
RSS/HWM sampling interfaces differ slightly; measurements are not exact
allocator contracts and a sampled RSS can differ from `ru_maxrss`. Released
Python objects do not guarantee immediate RSS reduction. Tracemalloc's own
memory overhead is excluded from normal RSS comparisons.

Per-symbol traced retained bytes (baseline after compiler return; remediated
immediately after safe feature release; includes series and small instrumentation):

| Completed symbols | Baseline | Remediated |
| --- | ---: | ---: |
| 1 | 4,328,280 | 1,450,751 |
| 2 | 8,649,575 | 2,891,949 |
| 3 | 12,970,670 | 4,333,139 |
| 4 | 17,291,757 | 5,774,321 |
| 5 | 21,612,836 | 7,215,527 |
| 6 | 25,933,939 | 8,656,901 |
| 7 | 30,255,210 | 10,098,059 |
| 8 | 34,576,257 | 11,539,201 |

Auxiliary synthetic 20,000-row allocation peaks:

| Operation | Before, bytes | After, bytes |
| --- | ---: | ---: |
| Series validation | 4,506,578 | 900 |
| Prewarmed trend compiler (isolating dead scratch lists) | 1,294,512 | 814,344 |

Reproduce each fresh-process probe from the repository root:

```bash
PYTHONPATH=tests:. uv run --locked python tests/mcf_signal_memory_probe.py baseline
PYTHONPATH=tests:. uv run --locked python tests/mcf_signal_memory_probe.py remediated
PYTHONPATH=tests:. uv run --locked python tests/mcf_signal_memory_probe.py baseline --trace-allocation
PYTHONPATH=tests:. uv run --locked python tests/mcf_signal_memory_probe.py remediated --trace-allocation
```

These are **SYNTHETIC ONLY / NOT PRODUCTION CAPACITY EVIDENCE**. They do not prove
that the real ninth worker, another family, the benchmark, or the full population
fits the VPS. They do prove removal of the measured avoidable retention.

## Semantic and safety evidence

The test-only old compiler/runtime are copied from accepted main with only import
routing altered. Their restored-source SHA-256 and the validator's normalized AST
hash are pinned in `test_mcf_signal_memory.py`; production never imports them.
Features inherit the unchanged accepted implementation, and are compared as
canonical exact arrays (no tolerance). The synthetic frozen-reader test double
is explicitly restricted to `SYNTHETIC-*` identities and source bars; it does not
replace or weaken real input admission.

The 11 new tests cover:

- Exact canonical series and complete candidate output bytes/digests, including
  accounting, fills, costs and F0–F3 results, for all 10 executable families on
  15m/1h/4h synthetic bars (30 family/timeframe fixtures).
- Exact requested features and liquidity percentile arrays; price source tuples
  remain identical objects. Source gaps and a membership boundary removing AAA
  and BTC are present in the fixtures.
- Exact session stress-shape vector on synthetic 15m data, UTC session boundaries,
  and 14 different candidates sequentially on the **same** runtime. Includes
  BTC/ETH peers, momentum/reversal, changed windows and liquidity ranks.
- Release after the last feature/percentile consumer and before simulation;
  compiler failure cleanup and successful reuse afterward.
- Fail-closed validator behavior for identity/length/time ordering/cadence,
  nonboolean signals, NaN/sNaN/infinity/zero/negative/malformed prices and multiple
  simultaneous faults, including Decimal conversion traps enabled/disabled.
- Bounded validation allocation, dead-trend peak reduction and a multi-symbol
  memory regression with unchanged owned output size.
- Actual synthetic-runtime diagnostic telemetry has exactly `CHECKPOINT_KEYS`;
  no economics enter it. All execution and evidence safety flags stay unchanged.

Existing input-admission/diagnostic/worker tests cover Fresh OOS and recent reserve
inaccessibility, P10 read/write=false, P11 locked, live/order/AI execution rejection,
changed input/code identities, gaps and membership tampering. No new permission,
telemetry field, checkpoint stage or result field is added. The immutable safety
contract remains PAPER/RESEARCH ONLY, LIVE_MASTER_LOCK=OFF, no futures, leverage,
short, live, order endpoint or AI direct execution.

Validation results and exact final PR HEAD/Actions are returned in the PR and
Director handoff; this document does not claim production runtime acceptance.

## Potential next bottlenecks and Director hold

**POTENTIAL NEXT BOTTLENECK**, not an observed OOM: `simulation_replay` still holds
all compiled boolean series, scored integer-index lists, Decimal mark/member-mark
lists, conversion of marks to `(timestamp, string)` tuples and retained base/stress
results for every symbol. Later fold accounting rematerializes all marks as
Decimals and creates multiple lists. Final canonical JSON/digest construction
may also have a large peak. The source matrix still dominates baseline RSS.

The validator's avoidable copies are removed proactively, but simulation/replay
result retention is unchanged. A separate bounded engineering remediation is
**likely to be needed**, based on those allocation mechanisms and limited headroom;
no diagnostic evidence yet proves that stage will OOM. Liquidity's all-symbol
indexes/rank outputs and lead-lag's per-symbol peer index remain further risks.
This PR does not expand into those architectures.

All five OOM incidents remain preserved. Changed files participate in frozen code
identity checks: old runner input and old Git-bound authorization cannot admit the
new code. Any future no-performance refreeze/runtime needs a separate Director
work unit and explicit authorization. This PR grants none. No real Development
candidate, ninth diagnostic, 24-candidate benchmark, 6,852 run or profitability
inspection occurred. No Fresh OOS/recent reserve/P10 data were read or written;
P11 stays locked. Do not merge. STOP for Director review.
