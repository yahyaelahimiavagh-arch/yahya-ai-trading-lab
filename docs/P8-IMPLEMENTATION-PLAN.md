# P8 — Dashboard implementation plan

Status: **P8-001 IMPLEMENTED — FINAL-HEAD CI / MERGE ACCEPTANCE PENDING**

Entry baseline: P7 runtime accepted and merged at checkpoint
`93b9d87cf23fe8a52470c4a01b480b0935be87c3`. Final P7 Actions run
`35516951238` passed both jobs, the **842/842** complete suite and **17/17**
focused P7-010 tests. The independent final audit froze P7 policy SHA-256
`534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9`,
P7-009 index SHA-256
`f13a322e7071b48a8b05182fceee8024ee6d22d6b08a7b223d337e5f7850e60b`
and the accepted BTCUSDT+ETHUSDT chain-set SHA-256
`76face2aa41fbea1dc0ae718964eb77b5990d258beb41312c74132c8bb5c1209`.

## Purpose

P8 adds a deterministic local Dashboard over **accepted and sanitized P7 export
artifacts only**. Its job is presentation: show system/safety state, completed
Paper trades, descriptive performance, segmentation and quality/error
diagnostics in a readable UI without creating a new source of truth.

P8 is not an execution console, broker terminal, AI command surface, strategy
optimizer or Live-control panel. It may transform already accepted P7 fields into
bounded view models and a local dashboard artifact, but it cannot change P7
analytics, reach P5/P6 journals directly, create trading authority or reinterpret
`INSUFFICIENT_EVIDENCE`.

## Non-negotiable boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF`.
- NO FUTURES, NO MARGIN, NO LEVERAGE, NO SHORT.
- NO WITHDRAWAL API.
- NO TRADE PERMISSION and NO ORDER ENDPOINTS.
- NO AI DIRECT EXECUTION.
- P8 consumes only accepted/sanitized P7 export material; no direct P5/P6 database
  ingestion or journal access.
- P8 may not import/call execution, account, risk-authority or exchange-order
  modules.
- P8 may not create, edit or replay `RiskAuthorization`, approved quantity,
  intent/order/fill state or portfolio state.
- P8 may not upgrade P3 strategy evidence; current candidates remain
  `INSUFFICIENT_EVIDENCE`.
- P8 must clearly label Paper/descriptive data and must not present historical
  metrics as forecasts, Live readiness or profitability claims.
- No credential, secret, account identifier, private account payload, raw model
  response or local source database path may enter dashboard output.
- No remote assets, analytics beacons, external scripts/styles, provider calls,
  WebSocket, REST fetch or hidden network transport are required for the P8
  dashboard.
- User-visible text originating in accepted artifacts must be escaped before HTML
  rendering; it must never become executable markup/script.
- Dashboard output must be deterministic, bounded and provenance-bound to the P7
  export SHA-256 that produced it.
- No dependency change unless a later checkpoint explicitly requires and audits
  it. The default design uses Python stdlib plus self-contained local HTML/CSS/JS.

## Delivery sequence

### P8-001 — Dashboard policy and immutable view contracts

Define frozen `P8_DASHBOARD_V1` policy and canonical immutable contracts for
dashboard source identity, safety banner, overview cards, trade rows, metric
values, segment rows and diagnostics. Explicitly separate display fields from
authority-bearing fields and forbid execution/account/risk/network capability.

Acceptance: deterministic canonical serialization/SHA-256, invalid-field and
schema-smuggling rejection, fixed Paper/insufficient-evidence labels and source
scan proving no direct execution/account/risk/network/provider capability.

Current candidate: branch `p8-001-dashboard-policy-contracts` from post-P7-closeout
baseline `9344d0d6a45ac77b5ea676a119b8cd7e782f00da`. It adds the frozen
`P8_DASHBOARD_V1` local/read-only/display-only policy and immutable contracts for
accepted/sanitized P7 export identity, the fixed safety banner, overview cards,
completed Paper trade rows, metric values, segment rows and bounded diagnostics.
Canonical records use deterministic JSON/SHA-256 identities and exact reconstruction
rejects unexpected top-level or nested fields. The strategy evidence enum contains
only `INSUFFICIENT_EVIDENCE`; authority-bearing field names are rejected from
generic display dimensions. The focused suite contains **21 tests** and the offline
runtime gate is:

```powershell
uv run --locked python -m yatl.dashboard.contract_runtime
```

The workflow adds a focused P8 contract gate, runtime gate and source-safety scan for
the new `yatl/dashboard` package. No dependency or `uv.lock` change is made.
Final-head GitHub Actions evidence is required before P8-001 acceptance or merge.

### P8-002 — Accepted P7 export loader and provenance binding

Load one bounded canonical P7 export read-only. Verify exact schema, canonical
JSON, export SHA-256, accepted quality status, segmentation identity and frozen
P7 safety fields before any dashboard projection. Reject missing, tampered,
oversized, noncanonical, secret-bearing, symlinked or unsupported-version input.

Acceptance: byte-identical reopen, exact P7 export digest binding, no-write proof,
bounded read and fail-closed invalid/tampered fixtures.

### P8-003 — System / safety / quality overview projection

Project a bounded overview containing symbol, snapshot identity/time, Paper state,
`LIVE_MASTER_LOCK=OFF`, strategy evidence, quality status, completed/open trade
counts and accepted chain identities. No new health or readiness inference may be
invented beyond accepted P7 fields.

Acceptance: exact source-field conservation, explicit stale/unknown handling,
stable overview SHA-256 and no conversion of descriptive status into trade/live
permission.

### P8-004 — Completed-trade table projection

Create deterministic completed-trade rows from accepted P7 trade metrics with
bounded sort/filter/page contracts. Open/incomplete trades remain visually
separate and never become completed rows. All numeric fields remain exact strings
from accepted analytics; display formatting cannot alter stored semantics.

Acceptance: stable ordering, bounded page size, exact row-to-trade identity,
filter/sort determinism, open-trade isolation and duplicate/missing-ID rejection.

### P8-005 — Performance and segmentation views

Project accepted P7 metrics and segment summaries into display-safe cards/tables:
realized/gross/net figures where defined, fees/slippage, win/loss/breakeven,
drawdown, holding duration and existing symbol/evidence/analyst segmentation.
Undefined values remain explicitly unavailable; no extrapolation or causality is
added.

Acceptance: metric/segment conservation against P7 source values, exact null/
insufficient handling, no double counting and no evidence-label upgrade.

### P8-006 — Quality and diagnostic view

Render bounded P7 quality/diagnostic status with stable severity/display mapping.
A failed or absent P7 quality state blocks normal analytics presentation and shows
only sanitized diagnostics already allowed by P7. Local paths, SQL, tracebacks or
private material must never be surfaced.

Acceptance: exact PASS/FAIL gating, bounded diagnostics, fail-closed unknown code
handling and no partial analytics display when source quality is not accepted.

### P8-007 — Deterministic self-contained local dashboard renderer

Render the accepted view model into a self-contained local dashboard artifact.
HTML/CSS/optional inline JS must be generated deterministically with strict
escaping. The dashboard must not require CDN assets, remote fonts, fetch/XHR,
WebSocket, cookies, localStorage or provider transport. Any client-side behavior
may operate only on already embedded sanitized view data.

Acceptance: byte-identical rendering, HTML escaping/XSS tests, no remote-resource
references, bounded artifact size, stable dashboard SHA-256 and browser-openable
static output.

### P8-008 — Guarded dashboard CLI and atomic publication

Expose bounded noninteractive local commands such as validate/build/summary for
accepted P7 export → P8 dashboard artifact. Refuse overwrite by default; explicit
overwrite is required. Use same-directory temporary output and atomic publish.
Errors must use stable codes and must not echo rejected local paths or secret-like
input.

Acceptance: stable exit codes, noninteractive behavior, atomic output, no
overwrite by default, path/error redaction, deterministic output and no source
mutation.

### P8-009 — Adversarial dashboard matrix

Run fixed BTCUSDT/ETHUSDT scenarios covering P7 export tampering, fabricated
quality PASS, evidence-label upgrade, cross-symbol row injection, duplicate trade
identity, oversized input/output, HTML/script injection, path/private-material
smuggling and dashboard artifact mutation.

Acceptance: exact fail-closed outcomes, byte-identical replay, canonical evidence,
XSS/remote-resource prevention and unchanged accepted P7 identities.

### P8-010 — Independent final audit

Independently recompute the P8 policy, P7 export identity, all dashboard view
projections, renderer identity, adversarial outcomes, source safety and published
artifacts. P8 closes only after a matching final-head GitHub Actions run passes.

## Exit condition

P8 is complete only when an accepted P7 export can be transformed into a
deterministic, local, readable and independently auditable Dashboard while every
attempt to tamper with source identity, leak private material, inject executable
content, fabricate quality/readiness or create execution authority fails closed.

P8 completion does not grant TRADE permission, does not open Live, does not
change P3 evidence labels and does not prove strategy profitability. P9 Telegram
may consume only explicitly accepted/sanitized status and alert material from
closed upstream phases.
