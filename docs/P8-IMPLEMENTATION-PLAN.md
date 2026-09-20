# P8 — Dashboard implementation plan

Status: **P8-004 RUNTIME ACCEPTED / MERGED — P8-005 CURRENT CANDIDATE**

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

Accepted: PR #52 was squash-merged at
`e675fd06461e9bbd168404eda3b42dd53d3ef2b8` after matching final-head Actions
run `35522537152` passed both jobs, the **863/863** complete suite and **21/21**
focused P8-001 tests. The runtime froze policy SHA-256
`b4534112975f519714592ad7468c950eb6aa112f49b9aee80b1d15bf51804c2e`,
preserved `INSUFFICIENT_EVIDENCE`, rejected schema smuggling and retained the
local/read-only/display-only boundary with no execution/account/risk/network
capability. No dependency or `uv.lock` change was made.

### P8-002 — Accepted P7 export loader and provenance binding

Load one bounded canonical P7 export read-only. Verify exact schema, canonical
JSON, export SHA-256, accepted quality status, segmentation identity and frozen
P7 safety fields before any dashboard projection. Reject missing, tampered,
oversized, noncanonical, secret-bearing, symlinked or unsupported-version input.

Acceptance: byte-identical reopen, exact P7 export digest binding, no-write proof,
bounded read and fail-closed invalid/tampered fixtures.

Accepted: PR #53 was squash-merged at
`a9112a525e07de0e4b5cc8a02433f636246b683f` after matching final-head Actions
run `35523493929` passed both jobs, the **886/886** complete suite and **23/23**
focused P8-002 tests. The loader runtime bound the canonical accepted P7 export
SHA-256 `8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456`,
quality SHA-256
`2c62a387c8ad24535eb9c4a2bd828d05ef6a8269cdd4529d261544c991e39a07`
and segmentation SHA-256
`be0a03a702b4b672e912c54435a37ce6c2b910f0cf0cd40e147ccfed4eefcba0`.
It preserved read-only/no-write behavior, exact expected-digest binding,
`INSUFFICIENT_EVIDENCE`, fail-closed tamper handling and the no
execution/account/risk/network boundary. No dependency or `uv.lock` change was
made.

### P8-003 — System / safety / quality overview projection

Project a bounded overview containing symbol, snapshot identity/time, Paper state,
`LIVE_MASTER_LOCK=OFF`, strategy evidence, quality status, completed/open trade
counts and accepted chain identities. No new health or readiness inference may be
invented beyond accepted P7 fields.

Acceptance: exact source-field conservation, explicit stale/unknown handling,
stable overview SHA-256 and no conversion of descriptive status into trade/live
permission.

Accepted: PR #54 was squash-merged at
`2a74006dd42ba3755c4f0382847a165d7ef485ce` after matching final-head Actions
run `35524331648` passed both jobs, the **910/910** complete suite and **24/24**
focused P8-003 tests. The deterministic 15-card overview preserved accepted P7
source fields, kept `open_trade_count=UNKNOWN` and
`snapshot_freshness=UNKNOWN`, and froze overview SHA-256
`00230798934c6d967833a7f3fbc53cffa6f0cf428db4f1369653fb55fc37ed2d`.
No health, profitability, readiness or live/trade-permission inference was added.
No dependency or `uv.lock` change was made.

### P8-004 — Completed-trade table projection

Create deterministic completed-trade rows from accepted P7 trade metrics with
bounded sort/filter/page contracts. Open/incomplete trades remain visually
separate and never become completed rows. All numeric fields remain exact strings
from accepted analytics; display formatting cannot alter stored semantics.

Acceptance: stable ordering, bounded page size, exact row-to-trade identity,
filter/sort determinism, open-trade isolation and duplicate/missing-ID rejection.

Accepted: PR #55 was squash-merged at
`6388eaab83bd756f26ed09a57ac3cc2015d48782` after matching final-head Actions
run `35525173631` passed both jobs, the **936/936** complete suite and **26/26**
focused P8-004 tests. The completed-trade table preserved exact accepted P7 numeric
strings, bounded deterministic filter/sort/page behavior and explicit
open/incomplete isolation. Runtime table SHA-256:
`bbe247686fe7289d1cf88bad02dc153b05492f0d8d2fa44d3650ae2d4c7076c1`.
No execution-level entry/exit time, quantity or price was invented. No dependency
or `uv.lock` change was made.

### P8-005 — Performance and segmentation views

Project accepted P7 metrics and segment summaries into display-safe cards/tables:
realized/gross/net figures where defined, fees/slippage, win/loss/breakeven,
drawdown, holding duration and existing symbol/evidence/analyst segmentation.
Undefined values remain explicitly unavailable; no extrapolation or causality is
added.

Acceptance: metric/segment conservation against P7 source values, exact null/
insufficient handling, no double counting and no evidence-label upgrade.

Current candidate: branch `p8-005-performance-segmentation-views` from accepted
P8-004 checkpoint `6388eaab83bd756f26ed09a57ac3cc2015d48782`.

P8-005 reconstructs the canonical completed-trade aggregate from accepted P7
`trade_metrics` using the same bounded Decimal semantics as P7 and projects a
fixed **19-metric** display set: completed/win/loss/breakeven counts, realized and
gross PnL, fees, slippage, total cost, gross/net return, win rate, maximum realized
drawdown, total/min/max/average holding duration and best/worst trade PnL. Values
that are undefined with zero completed trades remain explicit `UNAVAILABLE`; no
zero or forecast value is invented.

To prevent double counting, aggregate values are reconciled against the single
accepted `SYMBOL` trade segment on member count, realized PnL, total cost and
win/loss/breakeven counts. Every trade segmentation dimension
(`SYMBOL/STRATEGY_IDENTITY/EVIDENCE_LABEL`) and every analyst dimension
(`ANALYST_DISPOSITION/GROUNDING_CODE/TRACE_ACCEPTANCE`) must partition the exact
accepted member set **once and only once**. Segment IDs and segment SHA-256 values
are recomputed before display.

Trade segments preserve realized PnL, total cost and outcome counts independently;
they are never summed across dimensions. Analyst segments use explicit trace-count
semantics instead of being mislabeled as completed trades. Strategy evidence stays
`INSUFFICIENT_EVIDENCE`; source interpretation must remain correlation-only with
no causality or attribution upgrade.

Focused suite: **26 tests**. Runtime gate:

```powershell
uv run --locked python -m yatl.dashboard.performance_views_runtime
```

No dependency or `uv.lock` change. Exact final-head GitHub Actions evidence is
required before P8-005 acceptance or merge.

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
