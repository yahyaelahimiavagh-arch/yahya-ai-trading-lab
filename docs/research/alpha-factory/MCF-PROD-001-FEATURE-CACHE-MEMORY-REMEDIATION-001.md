# MCF-PROD-001 feature-cache memory remediation

Status: DRAFT ENGINEERING CHANGE / DIRECTOR REVIEW REQUIRED / NO RUNTIME AUTHORIZATION.

Starting main verified directly through GitHub before audit:
`890c47ce2c75774ab5f5e4aebcc0cbfddfb7c866`.
Branch: `mcf-prod-001-feature-cache-memory-remediation`.

## Fourth incident: one-time diagnostic OOM

Director-provided diagnostic and kernel evidence, not independently collected
from the VPS in this implementation unit:

- Candidate: `MCF-PROD-001-004784` (fixed ninth capacity member).
- Candidate spec: `73395d80d49f24818b9aedf8dbbfac35df3ad585f7d510a11d90778e0861f6c9`.
- Runner input: `c7763433e8e4a14c5ba93b58b936ff828709517eea0ed829527bb3fe87f20a36`.
- Git: `890c47ce2c75774ab5f5e4aebcc0cbfddfb7c866`.
- Benchmark selection: `03f02f30f576b9e71c906d47ee15c200364f04cd187f229c00e54030c50a5248`.
- Diagnostic: `DIAGNOSTIC_INCOMPLETE`; last completed stage `dataset_loading`;
  active stage `feature_cache_initialization`.
- Dataset-loading end and cache-initialization begin: RSS 3,181,220 KiB,
  peak 3,213,048 KiB; elapsed 343.646712 seconds.
- Child return code -9, exit code 137, signal 9. Kernel reports global OOM for
  the same python PID 59773: total-vm 3,628,592 kB, anon-rss 3,563,328 kB,
  file-rss 2,432 kB. Host MemTotal approximately 3,911,552 kB, SwapTotal 0.
- Classification: `CONFIRMED_OOM_DURING_FEATURE_CACHE_INITIALIZATION`.

The raw KiB values are authoritative: 3,181,220 KiB is approximately **3.034 GiB**.
The Director incident shorthand was "around 3.18 GiB"; it must not replace the
raw telemetry or its binary-unit conversion.

No economics were exposed, no performance artifact was written, no selection
was authorized, and neither a benchmark retry nor 6,852 execution occurred.
The first, second and third capacity OOM incidents remain in
`MCF-PROD-001-CAPACITY-BENCHMARK-GATE-v1.0.md`. This fourth incident and the earlier
ones are retained negative evidence; this engineering patch neither erases nor
supersedes any of them. Stage evidence localizes the kill; it does not identify
the exact allocation at the instant of the kill.

## Repository audit and bounded change

The checkout had 616 tracked files, including 442 Python files. Repository-wide
text searches covered `ProductionBars`, `ProductionFeatureCache`, `_index`,
`load_timeframe`, `_timeframe_caches`, dynamic attribute access, serialization
and copying. The following four modules were read in full before editing:
`production_features.py`, `production_runtime.py`, `production_runner_input.py`,
`production_memory_diagnostic.py`. Feature methods, rule compiler, admission,
storage reader and MCF tests were inspected for ownership and validation.

Only `production_features.py` changes in production:

| Allocation | Before | After |
| --- | --- | --- |
| Timestamp validation | `times[1:]` copies N-1 references | `pairwise(times)` keeps iterator state |
| Price positivity scan | Left-associated tuple additions allocate 2N, 3N, 4N reference tuples; 3N and 4N coexist at final addition | `chain(opens, highs, lows, closes)` keeps original field and element order without copies |
| Activity sign scan | Tuple additions allocate 2N and 3N references, coexisting at final addition | `chain(base_volume, quote_volume, trade_count)` without copies |
| Every cache's retained `_index` | Timestamp dictionary plus one integer position per bar | Removed: no consumer exists |

On this 64-bit Python, price concatenation alone has roughly 56N bytes of
simultaneously allocated tuple-reference storage, excluding headers. Activity
concatenation has roughly 40N bytes. Those scans are sequential, not additive
peaks. Removal changes no float/Decimal precision, value or arithmetic order.

Strictly increasing timestamps already reject duplicates before constructor
index creation. Thus its duplicate-length check could not fail for valid admitted
bars. Repository consumers use positional windows directly; `peer_return` builds
its own actually-used `peer_index`, and `liquidity_percentiles` builds separate
actually-used cross-sectional `indexes`. Both are deliberately unchanged.
The new AST audit test checks all visible Python sources for `_index` attribute
or string accesses, excluding only the new test and its test-only old baseline.
No reflective/serialization consumer of the removed cache field was found.

All existing validation calls remain: loader validation, runtime admission,
constructor own bars and peer validation. Repeated scans consume CPU but now have
bounded temporary storage. No trusted/skip-validation flag, admission token,
shared memo or constructor bypass is introduced. Error ordering and messages
remain identical on synthetic valid and invalid fixtures.

`FrozenRunnerInput.load_timeframe` still eagerly loads every selected-union symbol
for one requested timeframe. `load` retains a raw CanonicalRow tuple during that
symbol's conversion to numeric bars, then releases it at function return. Across
symbols, the resulting bars remain resident. Runtime `admitted` and peer maps
copy only references; caches point to the same bars and tuple fields. There is
no second numeric-array matrix created during cache initialization. The small
peer-map copy remains. No loader, gap, membership, dataset, formula, parameter,
family, accounting, cost or statistical-gate change is made.

## Synthetic memory evidence

Python 3.12.14, Linux, four preconstructed synthetic 15m symbols with 90,000 rows
each. Fresh process for each probe, no candidates or source files read. Baseline
validation and constructor are test-only copies of accepted main; their ASTs
were compared to that commit and are identical except the validation function
name. Feature methods are inherited without changes.

Normal RSS measurements (tracemalloc disabled):

| Operation | Baseline RSS before / after, KiB | Remediated RSS before / after, KiB |
| --- | --- | --- |
| Validate four symbols | 127,036 / 130,188 | 126,988 / 127,000 |
| Construct four retained caches | 126,992 / 163,372 | 126,980 / 126,992 |

Separate probes with tracemalloc enabled, measuring only the operation after
constructing synthetic bars:

| Operation | Baseline current / peak, bytes | Remediated current / peak, bytes |
| --- | --- | --- |
| Validate four symbols | 496 / 5,042,452 | 384 / 2,812 |
| Construct four retained caches | 31,025,168 / 33,574,952 | 2,000 / 4,300 |

Reproduction (each command starts a new process):

```bash
PYTHONPATH=tests:. uv run --locked python tests/mcf_memory_probe.py baseline validate
PYTHONPATH=tests:. uv run --locked python tests/mcf_memory_probe.py remediated validate
PYTHONPATH=tests:. uv run --locked python tests/mcf_memory_probe.py baseline cache
PYTHONPATH=tests:. uv run --locked python tests/mcf_memory_probe.py remediated cache
```

Append `--trace-allocation` for separate allocation measurements. Defaults are
90,000 rows and four symbols, bounded to synthetic fixtures. RSS/HWM vary with
allocator and environment; regression tests assert traced allocation bounds,
not exact RSS. These numbers are not production capacity acceptance and cannot
predict full-run peak memory.

## Equivalence and safety tests

`test_mcf_feature_cache_memory.py` checks:

- Old/new validation return or exception type/message, including all timeframes,
  boundaries, source gaps, zero activity, every column's NaN/inf/-inf, price zero,
  negative activity, length/identity/cadence/ordering faults, duplicate timestamps
  and multiple faults that establish unchanged error precedence.
- Direct own-bar and peer rejection, mismatched symbol/timeframe, and all 14
  validation calls for four admitted bars with BTC/ETH peers.
- Every field's seven rolling statistics at lag 0/1; returns, zscores, peer and
  absent-peer returns, range fraction, cache identity and liquidity percentiles.
- Canonical signal-series bytes and full candidate-result bytes, including digest
  and Decimal accounting, for one **synthetic** fixture per each of the 10
  executable families. Source/peer gaps and point-in-time membership remain.
- Repository-wide absence of removed-index consumers and source-object sharing.
- Validation allocation bounds at 10,000/20,000 rows and cache retained allocation.
- Actual remediated synthetic runtime telemetry admits only `CHECKPOINT_KEYS`,
  includes no economics/results, and retains all safety flags.

`test_mcf_runtime_input_freeze.py` adds exact eager-union loading/order/equality
and fail-closed admission of a rehashed manifest carrying old/mismatched code
identity before any dataset access. Existing diagnostic tests reject economics,
arbitrary targets, changed safety, missing new authorization, and Fresh OOS,
recent reserve, P10, P11 and Live paths. Existing reader tests check changed
manifest/data/gaps, outside symbols/timeframes, sealed partitions and symlinks.

## Remaining risks and Director hold

The initial bar matrix still costs roughly 3 GiB on the reported VPS before
features. Peer-return, liquidity, feature/signal arrays, simulation and result
serialization retain their existing allocations; later stages may still OOM.
The retained-index removal is a proven engineering reduction, not proof that
the real ninth worker or all families fit. Repeated validation scans remain a
CPU cost. No real Development runtime or refreeze was performed here.

`production_features.py` participates in `CODE_PATHS`, so the existing runner
input and old Git-bound authorization cannot authorize the changed code.
A future Director decision must address a no-performance refreeze preserving
all 525 datasets/memberships, then separately consider runtime authorization.
This document gives neither. No swap, host limit increase, data reduction,
history truncation, precision change, candidate retuning or retry is proposed.

PAPER/RESEARCH ONLY, LIVE_MASTER_LOCK=OFF, no futures/leverage/short/live/order
endpoint/AI execution, Fresh OOS/recent reserve unread, P10 unread/unwritten and
P11 locked remain unchanged. No merge, ninth-candidate rerun, 24-candidate
benchmark retry, 6,852 execution or performance selection is authorized.
Return the final HEAD, draft PR, focused/full test results and exact-HEAD Actions
status to Director, then STOP.
