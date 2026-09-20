# P8 — Dashboard implementation plan

Status: **P8-001 THROUGH P8-010 RUNTIME ACCEPTED / MERGED — PHASE CLOSED**

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

Accepted: PR #56 was squash-merged at
`23307f18588447e82f494d7c8ff461b3055eee05` after matching final-head Actions
run `35527548960` passed both jobs, the **962/962** complete suite and **26/26**
focused P8-005 tests. The accepted 19-metric projection preserved exact P7 Decimal
precision 256 values through `DashboardExactMetricValue`, reconciled aggregate
counts/PnL/cost/outcomes against the accepted SYMBOL segment, and enforced exact
once-only trade/analyst partitions without cross-dimension aggregation.
Runtime projection SHA-256:
`aef1b53a1762f134fad7bd37ee48d7bc5a722b98246021622f9e92531790f3b6`.
No dependency or `uv.lock` change was made.

### P8-006 — Quality and diagnostic view

Render bounded P7 quality/diagnostic status with stable severity/display mapping.
A failed or absent P7 quality state blocks normal analytics presentation and shows
only sanitized diagnostics already allowed by P7. Local paths, SQL, tracebacks or
private material must never be surfaced.

Acceptance: exact PASS/FAIL gating, bounded diagnostics, fail-closed unknown code
handling and no partial analytics display when source quality is not accepted.

Accepted: PR #57 was squash-merged at
`4ac351c384bebf5abd47ea1d6baee84f08a9bfc5` after matching final-head Actions
run `35529109856` passed both jobs, the **992/992** complete suite and **30/30**
focused P8-006 tests. PASS/FAIL/ABSENT quality presentation remained fail-closed,
FAIL/ABSENT exposed no analytics, and stable sanitized diagnostics preserved the
P7 quality boundary. Runtime projection SHA-256 values were:
PASS `dfcd7828b29ae569ade6e13611a8468093acc2d3d534eb51abad8bf9b4c199e8`,
FAIL `9a1c662966c9ee7498ae231ad9853293505a457081df76d428b987b34a42a6c3`,
ABSENT `db92ad16c4914ac56fdfd4a38344c9cc35d18a87e10b04fb482f849023cb77e6`.
No dependency or `uv.lock` change was made.

### P8-007 — Deterministic self-contained local dashboard renderer

Render the accepted view model into a self-contained local dashboard artifact.
HTML/CSS/optional inline JS must be generated deterministically with strict
escaping. The dashboard must not require CDN assets, remote fonts, fetch/XHR,
WebSocket, cookies, localStorage or provider transport. Any client-side behavior
may operate only on already embedded sanitized view data.

Acceptance: byte-identical rendering, HTML escaping/XSS tests, no remote-resource
references, bounded artifact size, stable dashboard SHA-256 and browser-openable
static output.

Accepted: PR #58 was squash-merged at
`ce1d7f5d5a8ea150e2ec92d9011765cdc4d79487` after matching final-head Actions
run `35529802550` passed both jobs, the **1026/1026** complete suite and
**34/34** focused P8-007 tests. Runtime produced a byte-identical self-contained
static dashboard of **10,587 bytes** with view-model SHA-256
`f0f4bc42f6abd9d0629a5314c734caa3d0c5264ac4a9136fc3aa7e35b0652abc`
and dashboard SHA-256
`a5d51099537c39b933c510161b2223b049ba78e38205284736a279199966d6ea`.
FAIL/ABSENT remained quality-only, no remote resource or script capability was
introduced and P8-007 performed no file publication. No dependency or
`uv.lock` change was made.

### P8-008 — Guarded dashboard CLI and atomic publication

Expose bounded noninteractive local commands such as validate/build/summary for
accepted P7 export → P8 dashboard artifact. Refuse overwrite by default; explicit
overwrite is required. Use same-directory temporary output and atomic publish.
Errors must use stable codes and must not echo rejected local paths or secret-like
input.

Acceptance: stable exit codes, noninteractive behavior, atomic output, no
overwrite by default, path/error redaction, deterministic output and no source
mutation.

Accepted: PR #59 was squash-merged at
`20df93ead290d918ce55c93c5f3beab090a14f62` after matching final-head Actions
run `35532396801` passed both jobs, the **1070/1070** complete suite and
**44/44** focused P8-008 tests. The guarded noninteractive CLI preserved the exact
accepted P8 rendered artifact (**10,587 bytes**) with dashboard SHA-256
`a5d51099537c39b933c510161b2223b049ba78e38205284736a279199966d6ea`,
refused overwrite by default, required explicit overwrite, published through a
same-directory temporary file with atomic link/replace semantics, re-read the
published bytes, redacted paths/errors and preserved the accepted P7 source bytes.
No dependency or `uv.lock` change was made.

### P8-009 — Adversarial dashboard matrix

Run fixed BTCUSDT/ETHUSDT scenarios covering P7 export tampering, fabricated
quality PASS, evidence-label upgrade, cross-symbol row injection, duplicate trade
identity, oversized input/output, HTML/script injection, path/private-material
smuggling and dashboard artifact mutation.

Acceptance: exact fail-closed outcomes, byte-identical replay, canonical evidence,
XSS/remote-resource prevention and unchanged accepted P7 identities.

Accepted: PR #60 was squash-merged at
`503e78dd6fb741f33dce838b70ff4c2c4fea3452` after matching final-head Actions
run `35533242415` passed both jobs, the **1107/1107** complete suite and
**37/37** focused P8-009 tests. The matrix completed **18/18** deterministic runs,
published exactly **19** canonical evidence files and froze index SHA-256
`38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608`.
Accepted export identities remained:
BTCUSDT `8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456`
and ETHUSDT `1ea65455e44f8723709f504f585da965683558608909bd2da75ab561c5e9c092`.
No dependency or `uv.lock` change was made.

### P8-010 — Independent final audit

Independently recompute the P8 policy, P7 export identity, all dashboard view
projections, renderer identity, adversarial outcomes, source safety and published
artifacts. P8 closes only after a matching final-head GitHub Actions run passes.

Current candidate: branch `p8-010-independent-final-audit` from accepted P8-009
checkpoint `503e78dd6fb741f33dce838b70ff4c2c4fea3452`.

The production audit imports only P8 Dashboard modules. It accepts the two
sanitized accepted P7 export files, the published P8-009 evidence directory and two
published static Dashboard HTML files. It independently verifies:

- frozen P8 policy SHA-256
  `b4534112975f519714592ad7468c950eb6aa112f49b9aee80b1d15bf51804c2e`;
- frozen accepted BTCUSDT and ETHUSDT P7 export SHA-256 values;
- frozen combined export-set SHA-256
  `6f884ea930cd929292f000e8ada2da370b4428d7173a1f3d2423deacc6523439`;
- deterministic replay of quality, overview, completed trades,
  performance/segmentation and renderer projections for both symbols;
- exact byte/hash equality of the published HTML against independently rendered
  artifacts plus no executable/remote-resource markup;
- deterministic replay of the full P8-009 matrix and exact byte-for-byte equality
  of all **19** published evidence files;
- frozen P8-009 index SHA-256
  `38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608`;
- no mutation of accepted export bytes during audit;
- production P8 source-safety boundaries across contracts, loader, views,
  renderer, CLI, scenarios and the audit itself.

Focused suite: **32 tests** covering frozen identities, no-write behavior,
projection/renderer recomputation, evidence coverage/canonicalization, export
tampering, evidence tampering, artifact tampering, symlink rejection and audit
result integrity. Runtime gate:

```powershell
uv run --locked python -m yatl.dashboard.audit_runtime --evidence data/p8/p8-009-evidence
```

No dependency or `uv.lock` change.

Accepted: PR #61 was marked Ready and squash-merged at
`fe973e8f55f0fb1d7a76015a0e3d0d043e278f2e` after matching exact final-head
GitHub Actions run `35534981625` passed both jobs, the **1139/1139** complete
suite and **32/32** focused P8-010 tests. Final candidate HEAD was
`05038f9955425ddc05f552e84d71b5625663a43d`.

The independent audit accepted **2 symbols**, **9 scenarios**, **18 runs**,
**19 evidence files** and **2 published HTML artifacts** with exact outcomes,
replay equality, projection/renderer recomputation, artifact verification,
no-write and source-safety all true. Frozen renderer-set SHA-256:
`17f8526ba74ea73a7915b8978d098ab567fe1e19a145f03c625246916e22ff0c`.

## Exit condition

P8 is complete only when an accepted P7 export can be transformed into a
deterministic, local, readable and independently auditable Dashboard while every
attempt to tamper with source identity, leak private material, inject executable
content, fabricate quality/readiness or create execution authority fails closed.

P8 completion does not grant TRADE permission, does not open Live, does not
change P3 evidence labels and does not prove strategy profitability. P9 Telegram
may consume only explicitly accepted/sanitized status and alert material from
closed upstream phases.


## Closure

P8 is **RUNTIME ACCEPTED / CLOSED** at checkpoint
`fe973e8f55f0fb1d7a76015a0e3d0d043e278f2e`.

Matching final-head Actions: `35534981625`.
Complete suite: **1139/1139 PASS**.
Focused P8-010: **32/32 PASS**.

Frozen identities remain:

- P8 policy SHA-256:
  `b4534112975f519714592ad7468c950eb6aa112f49b9aee80b1d15bf51804c2e`;
- P8-009 matrix index SHA-256:
  `38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608`;
- accepted BTCUSDT+ETHUSDT P7 export-set SHA-256:
  `6f884ea930cd929292f000e8ada2da370b4428d7173a1f3d2423deacc6523439`;
- final renderer-set SHA-256:
  `17f8526ba74ea73a7915b8978d098ab567fe1e19a145f03c625246916e22ff0c`.

P8 closure grants no TRADE permission, no Live capability and no profitability
claim. P3 remains `INSUFFICIENT_EVIDENCE`. P9 may open only as the
minimum-sufficient read-only notification/alert surface defined in
`P9-IMPLEMENTATION-PLAN.md`.
