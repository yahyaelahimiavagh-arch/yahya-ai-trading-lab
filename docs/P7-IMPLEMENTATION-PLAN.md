# P7 — Journal / Analytics implementation plan

Status: **P7-001 CURRENT CANDIDATE — FINAL-HEAD CI REQUIRED**

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

Current candidate: branch `p7-001-analytics-contracts` defines frozen
`P7_ANALYTICS_V1` contracts for read-only upstream source identities, upstream
journal/trace event references, point-in-time analytics scopes, explicitly
P7-derived field identities and conservative report dispositions. The P7-local
strategy-evidence enum exposes only `INSUFFICIENT_EVIDENCE`; no upgrade state
exists. Reports containing accepted events can only be `DESCRIPTIVE_ONLY`;
empty reports become `INSUFFICIENT_DATA`. The policy hard-disables upstream
mutation, external transport, credentials, execution import, RiskAuthorization
mutation, quantity authority, trade permission, order endpoints, leverage,
futures/margin/short and AI direct execution. No upstream journal reader,
SQLite persistence, metric engine or CLI is added in P7-001. Matching final-head
GitHub Actions evidence is required before acceptance.

### P7-002 — Read-only upstream ingestion manifest

Create bounded readers/adapters for accepted P5 durable execution evidence and P6
sanitized analyst traces. Every source is bound to schema version, file/database
identity, canonical digest and read-only mode. Missing, newer-schema, mutable,
secret-bearing or ambiguous inputs fail closed.

Acceptance: reopen equality, upstream tamper detection, no-write tests and
deterministic ingestion manifest digest.

### P7-003 — Unified point-in-time timeline

Build a canonical ordered timeline that correlates accepted analyst input/report,
risk/execution identities, intent/order/fill/portfolio events and timestamps
without changing upstream semantics. Orphan, duplicate, cross-symbol,
out-of-order or future-linked records fail closed.

Acceptance: stable ordering, exact relationship checks, cross-symbol/time
isolation and byte-identical replay.

### P7-004 — Completed Paper trade reconstruction

Reconstruct completed local-Paper trade episodes only from accepted durable
P5 fill/portfolio evidence. Entry/exit quantities, costs and realized PnL must be
copied/reconciled from accepted evidence rather than recomputed with new economics.
Open/incomplete or ambiguous episodes are reported separately and cannot be
silently closed.

Acceptance: exact P2/P5 economics preservation, duplicate/orphan rejection,
open-trade handling and deterministic trade SHA-256.

### P7-005 — Deterministic performance metrics

Compute descriptive analytics from reconstructed completed Paper trades: realized
PnL, gross/net return where defined, fees/slippage, win/loss counts, win rate,
drawdown, holding duration and bounded aggregates. Undefined denominators or
insufficient samples remain explicitly undefined/insufficient; no extrapolation.

Acceptance: Decimal-safe deterministic arithmetic, empty/zero-denominator tests,
metric monotonicity checks and exact replay.

### P7-006 — Strategy / evidence segmentation

Segment analytics by symbol, strategy identity, evidence label, analyst
disposition and other already-accepted immutable dimensions. Segmentation may
describe correlations but cannot assert causality or upgrade
`INSUFFICIENT_EVIDENCE`.

Acceptance: exact partition conservation, no double counting, stable segment IDs
and conservative insufficient-evidence labeling.

### P7-007 — Reconciliation and analytics-quality gate

Add a fail-closed quality report covering missing sources, orphan relationships,
duplicate identities, timeline gaps, inconsistent totals, changed upstream
digests, future timestamps and report-level arithmetic reconciliation.

Acceptance: healthy fixture PASS, fixed failure matrix, bounded diagnostics and
no partial analytics publication on quality failure.

### P7-008 — Guarded analytics export and CLI

Expose bounded local, noninteractive commands for ingest/validate, summary,
completed-trade view and canonical analytics export for future P8 consumption.
Outputs must be sanitized and deterministic; rejected local paths or secret-like
input must not be echoed.

Acceptance: stable exit codes, bounded JSON output, atomic export, no overwrite by
default, noninteractive behavior and source scans.

### P7-009 — Adversarial analytics matrix

Run fixed BTCUSDT/ETHUSDT scenarios for upstream tampering, duplicate/orphan
fills, cross-symbol linkage, future timestamps, changed cost/equity totals,
fabricated profitability, evidence-label upgrade attempts, journal mutation and
schema smuggling.

Acceptance: two byte-identical runs, exact fail-closed outcomes, canonical
published evidence and unchanged P3/P4/P5/P6 accepted identities.

### P7-010 — Independent final audit

Independently recompute the P7 policy, ingestion identities, reconstructed trades,
metrics, segmentation, adversarial outcomes, source safety and accepted artifacts.
P7 closes only after matching final-head GitHub Actions pass.

## Exit condition

P7 is complete only when accepted P5/P6 evidence can be consumed read-only and
turned into deterministic, reproducible, reconciled analytics while every attempt
to mutate upstream state, fabricate performance, upgrade strategy evidence or
create execution/risk authority fails closed.

P7 completion does not grant TRADE permission, does not open Live, does not change
P3 evidence labels and does not prove strategy profitability. P8 Dashboard may
consume only accepted/sanitized P7 outputs.
