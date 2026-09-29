# AF-01C P-C — Fast-Path Benchmark Evidence at 1,200 Identities

Status: **PASS / RUNTIME EVIDENCE / ACCEPTED INTO AF-01C CLOSEOUT**

Date: 2026-09-29

Implementation HEAD under test:
`7966423b2aeea07d4c85434a825237b28c62d1de`

Runtime root:
`/var/lib/yatl/research/opportunity-data-pc`

## Preconditions

- baseline completed identities: 1,100 / 9,306
- baseline status SHA-256:
  `7cc196fa6d93e050fb40105ed2a219055cec4cb302a878c52039fe70f31dbebc`
- local focused tests: 8 / 8 PASS
- GitHub Actions P5 deterministic gates run #330: SUCCESS
- unit-and-safety: SUCCESS
- accepted-public-data: SUCCESS
- P10 untouched
- Fresh OOS unread
- recent reserve unread
- P11 locked
- LIVE_MASTER_LOCK=OFF
- MERGED=NO

## Benchmark configuration

- target: 1,100 -> 1,200 identities
- new identities: 100
- internal batches: 4
- per-batch limit: 25
- workers: 4
- daily fallback: OFF
- repair: NO
- interpolation: NO

## Result

- benchmark verdict: PASS
- completed identities: 1,200 / 9,306
- remaining identities: 8,106
- success count: 839
- source-gap-or-failure count: 361
- final state counts:
  - INVALID_SCHEMA: 1
  - MONTHLY_SUCCESS: 839
  - SOURCE_GAP: 167
  - TIMESTAMP_ANOMALY: 193
- final status SHA-256:
  `4cfa2af9e636f1cff8c0f9b574c9b48561d991c4767cd2f8124077d1a6c5cfdd`
- fast-run SHA-256:
  `62491971aff37c2239c3beda335b02154abc7f45888966fb999c5c854c5200d5`
- elapsed seconds: 64.66
- measured throughput: 5,567.6 identities/hour
- measured seconds per identity: 0.647
- max RSS: 507,452 KB
- duplicate identities: 0
- independent full post-status: PASS
- inline status SHA matched independent full status SHA: YES

## Interpretation

The bounded fast path materially improves measured throughput on this 100-identity
sample while preserving immutable-ledger derivation and independent status
verification.

The measured rate is benchmark evidence, not a guarantee of linear scaling over
the remaining population. Broad continuation remains bounded by the same
25-identity batch semantics, 4-worker ceiling, storage gates, immutable artifacts
and fail-closed reconciliation rules.

The benchmarked executable code remains pinned to implementation HEAD
`7966423b2aeea07d4c85434a825237b28c62d1de` for runtime continuation.

Implementation subsequently merged to `main` through PR #157; this document records the pre-merge benchmark evidence.
