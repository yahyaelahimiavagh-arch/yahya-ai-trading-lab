# P7 — Journal / Analytics implementation plan

Status: **P7-001 / P7-002 / P7-003 / P7-004 / P7-005 / P7-006 / P7-007 / P7-008 / P7-009 RUNTIME ACCEPTED / MERGED — P7-010 CURRENT CANDIDATE**

Entry baseline: P6 runtime accepted and merged at checkpoint
`f07f2209cac5b46be8f9d74da2d162925ed8ab65`. Final P6 Actions run
`35504753305` passed **703/703** complete tests, **13/13** focused P6-010 tests,
the independent final audit and unchanged P3/P4 regression gates.

## Purpose

P7 adds a deterministic, auditable Journal / Analytics layer over accepted P5
local-Paper execution evidence and sanitized P6 analyst traces. It is a read-only
consumer of upstream evidence. It may reconstruct timelines, completed Paper
trades and descriptive performance metrics, but it cannot modify P5/P6 journals,
create execution decisions, change risk authority, upgrade strategy evidence or
claim Live readiness.

P7 output is descriptive engineering/research analytics. A positive metric does
not establish strategy edge, profitability or permission to trade.

## Non-negotiable boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF`.
- NO FUTURES, NO MARGIN, NO LEVERAGE, NO SHORT.
- NO WITHDRAWAL API.
- NO TRADE PERMISSION and NO ORDER ENDPOINTS.
- NO AI DIRECT EXECUTION.
- P7 may not import/call exchange order submission or any new remote transport.
- P7 may not mutate P5 execution journals, portfolio stores or recovery state.
- P7 may not mutate P6 analyst journals or provider/model material.
- P7 may not manufacture or modify P4 `RiskAuthorization`.
- P7 may not create quantity authority or reinterpret historical approved quantity.
- Current P3 strategies remain `INSUFFICIENT_EVIDENCE`; analytics cannot upgrade
  that label.
- Engineering fixtures and Paper outcomes remain engineering evidence, not proof
  of real strategy readiness.
- All ingested records must be provenance-bound, schema/version checked and
  point-in-time consistent.
- Secrets, credentials, account identifiers, raw private account payloads and raw
  provider/model responses remain outside P7.
- No dependency change unless a later checkpoint explicitly requires and audits it.

## Delivery sequence

### P7-001 — Analytics policy and immutable contracts

Define a frozen `P7_ANALYTICS_V1` policy and canonical records for source
identity, journal events, analytics scope and report disposition. The contract
must explicitly distinguish upstream evidence from P7-derived fields and prohibit
execution/risk/permission authority.

Acceptance: deterministic construction/reconstruction, canonical SHA-256,
invalid-field rejection, P3 `INSUFFICIENT_EVIDENCE` preservation and source
scan proving no execution/account/network/provider capability.

Accepted: PR #41 was squash-merged at
`53e3cde1956b130c940aebc12adaaa4d905e132f` after matching final-head Actions
run `35506503002` passed both jobs, the **721/721** complete suite and **18/18**
focused P7-001 tests. Runtime froze policy SHA-256
`534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9`,
scope SHA-256
`11d3aaf68daf8299599cd7651e558ab5bb396a24167417e94205da98a574f4a2`
and report SHA-256
`b59f847dd18e63f4d7f2022770ca27b66e79794cd354180de3a5988c4516e2ba`.
The P7-local strategy-evidence enum exposes only `INSUFFICIENT_EVIDENCE`, and
the policy keeps upstream mutation, transport, credentials, execution/risk/
quantity/trade authority disabled.

### P7-002 — Read-only upstream ingestion manifest

Create bounded readers/adapters for accepted P5 durable execution evidence and P6
sanitized analyst traces. Every source is bound to schema version, file/database
identity, canonical digest and read-only mode. Missing, newer-schema, mutable,
secret-bearing or ambiguous inputs fail closed.

Acceptance: reopen equality, upstream tamper detection, no-write tests and
deterministic ingestion manifest digest.

Accepted: PR #42 was squash-merged at
`40593552a056bc0280fc9ce32ccb60efa817760b` after matching final-head Actions
run `35507684476` passed both jobs, the **735/735** complete suite and **14/14**
focused P7-002 tests. The accepted runtime proved `reopen_equal=true` and
`no_write=true` with P5 canonical SHA-256
`67625cb2784a8cd09dc877b3bda1dd49a24b555305bacc957930975354dfcd05`,
P6 canonical SHA-256
`a47c628dcce75500ffdd0c7a92835e1872e31eebaf3f9aee3802ab8f7a3d81c0`
and ingestion-manifest SHA-256
`56211a6cebd0af00ca28deda1ac06f24346f4267d9e377f3a2f2604f7de49550`.
SQLite remained `mode=ro/query_only`; raw file identity, schema, P5 intent
digests and P6 nested grounding bindings were verified without exporting paths or
adding execution/account/risk/network/provider capability.

### P7-003 — Unified point-in-time timeline

Build a canonical ordered timeline that correlates accepted analyst input/report,
risk/execution identities, intent/order/fill/portfolio events and timestamps
without changing upstream semantics. Orphan, duplicate, cross-symbol,
out-of-order or future-linked records fail closed.

Acceptance: stable ordering, exact relationship checks, cross-symbol/time
isolation and byte-identical replay.

Accepted: PR #43 was squash-merged at
`9d22817d0ac76c4e724120d9189de3100ef03b58` after matching final-head Actions
run `35508427366` passed both jobs, the **750/750** complete suite and **15/15**
focused P7-003 tests. The accepted runtime produced six canonical entries and
timeline SHA-256
`945324f10b7107d8ab13f42d0c5c9207bc8cf0aa6a650d2765275d6f8d26e535`
with `replay_equal=true` and `no_write=true`. Intent placement explicitly
uses `RELATED_ORDER_TIME`; order/fill/portfolio/P6 entries retain their own
provenance-preserving time basis.

P7-004 includes one compatibility correction to that accepted timeline validator:
a valid P5 same-bar protective exit is a second `EXIT_LONG` fill inside the same
`ENTER_LONG` fill-step. The correction permits exactly that two-fill pattern
only when the second fill shares the same accepted intent/order state, quantity
and fill time and has a protective reason (`STOP`, `TARGET` or
`AMBIGUOUS_STOP_PRIORITY`). It does not weaken orphan, ordering, symbol, time
or digest validation.

### P7-004 — Completed Paper trade reconstruction

Reconstruct completed local-Paper trade episodes only from accepted durable
P5 fill/portfolio evidence. Entry/exit quantities, costs and realized PnL must be
copied/reconciled from accepted evidence rather than recomputed with new economics.
Open/incomplete or ambiguous episodes are reported separately and cannot be
silently closed.

Acceptance: exact P2/P5 economics preservation, duplicate/orphan rejection,
open-trade handling and deterministic trade SHA-256.

Accepted: PR #44 was squash-merged at
`2fece9cc70bf6762a24540311876eb6e6d2be51e` after matching final-head Actions
run `35509089440` passed both jobs, the **761/761** complete suite and **11/11**
focused P7-004 tests. The runtime reconstructed one completed FLAT Paper trade
with `replay_equal=true` and `no_write=true`, trade SHA-256
`f08daef518cd64108bc6b135e77d4fb088af0224ec97b851cdb3189b17902b54`
and reconstruction SHA-256
`2162b742d014f9cb00dd959fae04309a7aaa6824cdd65e79037166c5c384ecab`.
Normal closed, still-open and same-bar protective-exit fixtures all passed with
exact accepted P2/P5 economics reconciliation.

### P7-005 — Deterministic performance metrics

Compute descriptive analytics from reconstructed completed Paper trades: realized
PnL, gross/net return where defined, fees/slippage, win/loss counts, win rate,
drawdown, holding duration and bounded aggregates. Undefined denominators or
insufficient samples remain explicitly undefined/insufficient; no extrapolation.

Acceptance: Decimal-safe deterministic arithmetic, empty/zero-denominator tests,
metric monotonicity checks and exact replay.

Accepted: PR #45 was squash-merged at
`7c623e8056e2f7bc0ea319816ebb95d9cabf06e1` after matching final-head Actions
run `35509873943` passed both jobs, the **772/772** complete suite and **11/11**
focused P7-005 tests. The accepted runtime preserved one completed Paper trade,
`replay_equal=true` and `no_write=true`, with metrics SHA-256
`d2aa2ad3cf2b29aef0eb5ce1db21fb1dfda6ebeef2dfa142d61bda815f6b3dbb`.
Return denominators remain self-verifying from accepted trade fields; empty
completed-trade populations remain explicitly `INSUFFICIENT_DATA`.

### P7-006 — Strategy / evidence segmentation

Segment analytics by symbol, strategy identity, evidence label, analyst
disposition and other already-accepted immutable dimensions. Segmentation may
describe correlations but cannot assert causality or upgrade
`INSUFFICIENT_EVIDENCE`.

Acceptance: exact partition conservation, no double counting, stable segment IDs
and conservative insufficient-evidence labeling.

Accepted: PR #46 was squash-merged at
`ec7a73cc27ba6d6075c2f291f10254a358b4bf29` after matching final-head Actions
run `35511737947` passed both jobs, the **784/784** complete suite and **12/12**
focused P7-006 tests. The runtime conserved one completed trade and one sanitized
analyst trace across three independent partition families each, preserved
`UNATTRIBUTED_DURABLE_P5` strategy attribution and
`INSUFFICIENT_EVIDENCE`, and produced segmentation SHA-256
`be0a03a702b4b672e912c54435a37ce6c2b910f0cf0cd40e147ccfed4eefcba0`
with `replay_equal=true` and `no_write=true`.

### P7-007 — Reconciliation and analytics-quality gate

Add a fail-closed quality report covering missing sources, orphan relationships,
duplicate identities, timeline gaps, inconsistent totals, changed upstream
digests, future timestamps and report-level arithmetic reconciliation.

Acceptance: healthy fixture PASS, fixed failure matrix, bounded diagnostics and
no partial analytics publication on quality failure.

Accepted: PR #47 was squash-merged at
`7e57edee4ec90b63afc6e837536bb3286b03d528` after matching final-head Actions
run `35512606439` passed both jobs, the **796/796** complete suite and **12/12**
focused P7-007 tests. The healthy quality fixture passed the full chain, the fixed
six-case fail-closed matrix matched exact diagnostic codes, no failure exposed a
partial analytics payload, and runtime quality SHA-256 was
`2c62a387c8ad24535eb9c4a2bd828d05ef6a8269cdd4529d261544c991e39a07`
with `replay_equal=true` and `no_write=true`.

### P7-008 — Guarded analytics export and CLI

Expose bounded local, noninteractive commands for ingest/validate, summary,
completed-trade view and canonical analytics export for future P8 consumption.
Outputs must be sanitized and deterministic; rejected local paths or secret-like
input must not be echoed.

Acceptance: stable exit codes, bounded JSON output, atomic export, no overwrite by
default, noninteractive behavior and source scans.

Accepted: PR #48 was squash-merged at
`3aad07f7ad110a66a3d0b494fb9b8e8e81279cc7` after matching final-head Actions
run `35514904769` passed both jobs, the **812/812** complete suite and **16/16**
focused P7-008 tests. The accepted runtime verified four noninteractive commands,
stable exit codes, bounded JSON, atomic export, no-overwrite by default, path
redaction, `replay_equal=true` and `no_write=true`, with canonical export
SHA-256
`8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456`.

### P7-009 — Adversarial analytics matrix

Run fixed BTCUSDT/ETHUSDT scenarios for upstream tampering, duplicate/orphan
fills, cross-symbol linkage, future timestamps, changed cost/equity totals,
fabricated profitability, evidence-label upgrade attempts, journal mutation and
schema smuggling.

Acceptance: two byte-identical runs, exact fail-closed outcomes, canonical
published evidence and unchanged P3/P4/P5/P6 accepted identities.

Accepted: PR #49 was squash-merged at
`840a3d471ad0ea0b0f120d99920bd3ccf7a557f3` after matching final-head Actions
run `35515929819` passed both jobs, the **825/825** complete suite and **13/13**
focused P7-009 tests. The accepted matrix covered **9 scenarios × 2 symbols = 18
runs**, reproduced byte-for-byte across two full executions, published 19 canonical
evidence files and froze P7-009 index SHA-256
`f13a322e7071b48a8b05182fceee8024ee6d22d6b08a7b223d337e5f7850e60b`.
The matrix also tightened diagnostic precision for explicit cross-symbol fill
linkage to `SOURCE_IDENTITY_INVALID`; all validation remained fail-closed.

### P7-010 — Independent final audit

Independently recompute the P7 policy, ingestion identities, reconstructed trades,
metrics, segmentation, adversarial outcomes, source safety and accepted artifacts.
P7 closes only after matching final-head GitHub Actions pass.

Current candidate: branch `p7-010-independent-final-audit` independently audits
the complete P7 boundary. It reconstructs the frozen `P7_ANALYTICS_V1` policy
and requires policy SHA-256
`534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9`.
It reads the P7-009 evidence directory twice, requires exactly 19 nonsymlink
canonical JSON files under strict per-file/total bounds, independently checks
every scenario's exact expected/observed outcome and fixed safety fields, verifies
every index-to-file digest, then independently regenerates the full adversarial
matrix and requires exact byte equality with published evidence. The audit also
rebuilds healthy closed-trade analytics chains separately for BTCUSDT and
ETHUSDT: ingestion manifest, unified timeline, Paper trade reconstruction,
performance metrics, segmentation, quality gate and sanitized export identity are
each executed twice and must match exactly without changing either source
database. The BTC chain is compared against the previously accepted P7-007/P7-008
frozen runtime digests; both-symbol chain identities are then aggregated into one
canonical chain-set SHA-256. Source safety is scanned across the full
`yatl/analytics` package for execution/backtest/account/risk imports,
order/withdrawal endpoints, environment credentials and network/provider clients.
The discovery candidate run `35516730233` independently recomputed the
two-symbol chain-set SHA-256 as
`76face2aa41fbea1dc0ae718964eb77b5990d258beb41312c74132c8bb5c1209`. That digest is now frozen in code and is required by both the
audit result contract and focused regression tests. The discovery run is not
acceptance evidence; a replacement exact Final-HEAD run is required before
P7-010 acceptance.

## Exit condition

P7 is complete only when accepted P5/P6 evidence can be consumed read-only and
turned into deterministic, reproducible, reconciled analytics while every attempt
to mutate upstream state, fabricate performance, upgrade strategy evidence or
create execution/risk authority fails closed.

P7 completion does not grant TRADE permission, does not open Live, does not change
P3 evidence labels and does not prove strategy profitability. P8 Dashboard may
consume only accepted/sanitized P7 outputs.
