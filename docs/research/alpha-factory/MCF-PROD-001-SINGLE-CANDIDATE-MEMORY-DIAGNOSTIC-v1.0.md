# MCF-PROD-001 single-candidate peak-memory diagnostic

Status: DRAFT IMPLEMENTATION / NO RUNTIME AUTHORIZATION / NO MERGE.

Starting main verified directly on GitHub:
`da0b34adf83f0e824b501d54e3597717c8dc4ea6`.
Actions run 36909952232 (#493): completed/success on that exact SHA.

## Frozen target

Production generator `freeze_executable_generation(BLOCKED_FAMILIES)` feeds the
unchanged `select_benchmark_candidates` algorithm. Only position nine (index 8)
is used; no candidate override, position option, outcome input, or retry loop.

- Candidate: `MCF-PROD-001-004784`.
- Spec SHA: `73395d80d49f24818b9aedf8dbbfac35df3ad585f7d510a11d90778e0861f6c9`.
- Benchmark-selection SHA: `03f02f30f576b9e71c906d47ee15c200364f04cd187f229c00e54030c50a5248`.

## Architecture and actual stages

`production_memory_diagnostic` has metadata-only `preflight`, isolated parent
`diagnose`, and internal `worker` commands. Preflight checks paths/HEAD and
frozen metadata; it neither admits datasets nor claims runner-input verification.
It cannot start a child. Diagnose and worker each independently require a new,
canonical, content-addressed Director authorization. None is created in this PR.

Opt-in ContextVar telemetry leaves ordinary accounting/results unchanged.
Each stage emits begin immediately before work and end only on success:

| Stage | Natural code boundary |
| --- | --- |
| frozen_input_admission | FrozenRunnerInput manifest, provenance and safety admission |
| runtime_initialization | ProductionRuntime.from_frozen_input |
| dataset_loading | FrozenRunnerInput.load_timeframe |
| feature_cache_initialization | admitted bars validation and feature-cache timestamp indexes |
| liquidity_percentiles | optional family-conditioned liquidity matrix construction |
| feature_signal_compilation | compile_candidate across caches; features and signal state are interleaved here |
| simulation_replay | run_candidate base/stress simulator loop |
| result_accounting | existing evaluable/fold/daily aggregate accounting |
| result_construction | existing result object and per-symbol daily series construction |
| result_digest | canonical result digest; potentially large transient serialization |
| result_discard | identity verification and deletion, without economics projection |
| cleanup | transient cache release, reader/runtime deletion and GC |

Eligibility occurs within liquidity, rule compilation and simulation; no invented
standalone eligibility matrix is claimed. Diagnostic projection is discard only;
there is no distributed compact-result writer. Existing F0-F3 computations remain
internal parts of unchanged accounting and cannot be inspected or emitted. No
F0-F7 adjudication is authorized.

## Exact output contract

Checkpoint keys (exact allowlist): `stage`, `phase`, `rss_kib`, `peak_rss_kib`,
`elapsed_seconds`, `pid`, `candidate_id`, `candidate_spec_sha256`,
`runner_input_sha256`, `git_sha`. Stage/phase enums, pinned identity, PID,
positive integer RSS, finite nonnegative elapsed time, monotonic elapsed/HWM,
ordered nonrepeated stages and bounded line/count are enforced before append.
RSS and process high-water mark come from Linux `/proc/self/status` in KiB.
No profiler or new dependency is used.

Summary keys: `schema`, `status`, the four identity fields above,
`last_checkpoint`, `last_completed_stage`, `active_stage`, `child_returncode`,
`child_exit_code`, `child_signal`, `termination`, `diagnostic_completed`,
`candidate_performance_exposed`, `performance_artifacts_written`,
`selection_authorized`, `full_batch_authorized`, `benchmark_retry_authorized`,
`safety`. All outcome/authority flags are false. The status describes engineering
completion only. Summary is constructed by the parent, never accepted from child
strategy results. `last_checkpoint` is already strictly validated.

Preflight keys: `schema`, `status`, four identity fields, static
`benchmark_selection_sha256`, `safety`, `runtime_authorized`,
`benchmark_retry_authorized`, `full_batch_authorized`. Blocked CLI output contains
only schema/status and false authorization flags; exception messages are omitted.

No PnL, returns, drawdown, Sharpe/DSR/PBO, trades/signals, gates, survivors,
ranking/score, promotion, strategy comparisons, per-symbol economics, or result
hash is permitted. Raw stdout/stderr are sent to /dev/null, core dumps disabled,
and no result artifact or partial strategy result is written. Unknown checkpoint
fields (including exception text) stop the child and never enter the journal.

## Kill-safe persistence

Dedicated inherited pipe descriptor is the capacity diagnostic log channel.
Worker synchronously writes and flushes each checkpoint before the next stage.
Parent validates then appends, flushes and fsyncs `checkpoints.jsonl` immediately.
A fresh output directory is mandatory; prior evidence cannot be overwritten.
Parent persists `summary.json` after child exit, even if SIGKILL prevented final
worker output. Last successful stage and innermost active stage are distinguished.
Incomplete/open stages and nonzero exits can never imply completion.

Negative returncode -9 is SIGKILL; positive 137 is compatible with signal-wrapper
exit, but not independent proof of a signal or OOM. Termination label deliberately
says `SIGKILL_OR_EXIT_137_OOM_UNCONFIRMED`; kernel evidence must establish OOM.
If the whole machine or parent dies, validated fsynced journal lines survive;
summary may be absent. No in-process observer can identify a substage peak within
one span. HWM captures an earlier transient; stage brackets localize it, and the
active begin bracket survives kill. Parent survival is not guaranteed under a
global machine OOM. No claim of infrastructure remediation is made.

## Separate future authorization contract

Runtime approval must be a canonical object containing exactly:
`schema=MCF_SINGLE_CANDIDATE_MEMORY_AUTHORIZATION/1.0.0`,
`scope=MCF-PROD-001-SINGLE-CANDIDATE-PEAK-MEMORY-DIAGNOSTIC`,
`authorized=true`, `candidate_position=9`, `candidate_count=1`, static selection
SHA, four pinned identity fields, exact unchanged capacity `SAFETY` dictionary,
and `authorization_sha256=digest(all other fields)`.
This is an auditable scope/binding artifact, not cryptographic signer authentication;
only Director-approved deployment should supply it. Benchmark tokens, arbitrary
candidate identities, changed safety, and distributed full-run artifacts fail closed.

The diagnostic does not import a coordinator command, initiate a benchmark loop,
write distributed outcomes, mint a capacity success artifact, or mint full-run
approval. PAPER/RESEARCH ONLY, LIVE_MASTER_LOCK=OFF, no futures/leverage/short,
no live/order endpoint/AI execution, Fresh OOS/recent reserve unread, P10 unread
and unwritten, P11 locked remain unchanged. All data access uses FrozenRunnerInput
and its Development-only content-addressed admission and existing path guards.
No other evidence root or input substitution is provided.

## Code identity and acceptance hold

Runtime, accounting and the lightweight telemetry module participate in the
runner code identity. Old runner inputs fail admission after these changes.
A future Director decision must address a no-performance refreeze and verification
against the same 525 datasets and memberships before separately approving any
single-candidate runtime. This PR changes no input semantics, candidate identity,
parameters, family definition, cost policy, neighbor graph, statistical criteria,
or evidence boundary. No refreeze or real performance is performed here.

Tests use only metadata, small synthetic bars and synthetic subprocesses (including
real SIGKILL). Review/CI must complete, then return to Director and stop. This
implementation never grants a ninth-candidate run, 24 retry, 6,852 execution,
profit inspection, F0-F7, Fresh OOS, recent reserve, P10/P11 or Live permission.
