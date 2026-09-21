# P10 — Forward / Paper Validation implementation plan

Status: **P10-002 RUNTIME ACCEPTED / MERGED — P10-003 CURRENT CANDIDATE**

Entry baseline: P9 runtime accepted and merged at checkpoint
`60d7e267fdd878f513afb2a8febb30d509b61314`. Final P9-006 candidate HEAD
`f7ff546d7310876fd969f03c4f2d153137889de1` passed matching GitHub Actions
run `35566103007` with both jobs PASS, **1275/1275** complete tests and
**34/34** focused P9-006 tests.

## Purpose

P10 is the economic validation phase. It tests the **already-frozen baseline**
on genuinely new / forward Paper data and asks whether there is enough evidence
of a repeatable economic edge after costs and under the accepted risk controls.

P10 is not a strategy-development sandbox. Once the validation window opens,
candidate logic, economic thresholds and risk limits may not be tuned in response
to observed validation results. A failed or insufficient P10 result returns the
project to a separate research/strategy iteration; it does not silently rewrite
the gate.

The primary economic criterion is **Net PnL after fees and slippage on new data**,
but a positive number alone is not sufficient. Acceptance also requires the
pre-registered drawdown, sample-size, consistency, regime-stability,
failure/recovery and risk-control gates.

P10 completion is not a guarantee of future profit. P11 remains a separately
controlled Tiny Live candidate and is locked unless P10-010 explicitly accepts
the full pre-registered gate.

## Economic doctrine

- Profitability > Complexity.
- Evidence > Number of analyses.
- OOS / Forward evidence > attractive backtest.
- Risk-adjusted persistence > raw profit.
- One profitable edge > many unproven signals.
- Baseline without AI is measured first.
- AI may only be considered later as decision-support if it demonstrates
  incremental OOS/forward value over the frozen baseline.
- NO AI DIRECT EXECUTION remains permanent.

## Non-negotiable boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF` throughout P10.
- NO FUTURES, NO MARGIN, NO LEVERAGE, NO SHORT.
- NO WITHDRAWAL API.
- NO TRADE PERMISSION and NO ORDER ENDPOINTS.
- NO AI DIRECT EXECUTION.
- P10 may not mutate P4 RiskAuthorization or create quantity authority.
- Existing P4 limits remain inherited unless a future research phase explicitly
  changes them outside the active P10 window:
  - risk per trade: 1%;
  - maximum session loss: 2%;
  - maximum drawdown: 10%;
  - maximum consecutive losses: 3.
- P10 may not upgrade `INSUFFICIENT_EVIDENCE` before the final independent
  P10-010 verdict.
- Candidate identity and economic thresholds must be frozen before the forward
  window opens.
- Window identity and cutoff must be sealed before any P10 forward data is
  admitted.
- No post-open parameter tuning, threshold tuning, symbol substitution,
  lookahead, historical backfill disguised as forward evidence or selective
  deletion of losing observations.
- Fees and slippage remain part of economics; gross profit cannot substitute for
  Net PnL after costs.
- Data-quality failure, provenance ambiguity or safety/risk breach fails closed.
- No P10 checkpoint may infer Live readiness merely from engineering PASS.
- No dependency change unless a later checkpoint explicitly requires and audits it.

## Fixed delivery sequence

### P10-001 — Validation policy and immutable preregistration contracts

Define frozen `P10_VALIDATION_V1` policy and canonical preregistration charter.
Freeze the evaluation dimensions:
Net PnL after costs, drawdown, sample size, consistency, regime stability,
failure/recovery and risk controls.

P10-001 is deliberately **preregistration-only**:
- no P10 numeric economic thresholds are registered yet;
- candidate is not frozen yet;
- validation window is not open;
- new forward data collection is not authorized;
- economic evaluation is not authorized;
- strategy evidence stays `INSUFFICIENT_EVIDENCE`.

It also freezes that Net PnL must include fee/slippage, point-in-time/no-lookahead
semantics apply, no post-open tuning is allowed, and P4 risk limits above are
inherited.

Acceptance: deterministic immutable policy/charter digests, strict
reconstruction, schema-smuggling rejection, direct comparison with accepted P4
risk limits, no PASS/Live-ready disposition, and source scan proving no
data/execution/account/risk/network/provider capability.

Accepted: PR #68 exact final candidate HEAD
`ea6532c617b7c78137fc3c396055bc314e70e464` passed matching Actions run
`35573516304` with both jobs PASS, **1296/1296** complete tests and **21/21**
focused P10-001 tests. Frozen policy SHA-256:
`a85981d7ec835b584907bc89f3cff62b662a11d46c163900101ad46a213aa2c2`.
Frozen preregistration charter SHA-256:
`9d44d28de13445fcacbf5dad85ec0257ae65d198cf75ec26fb95c81fb1dffa71`.
PR #68 was squash-merged on `main` at checkpoint
`326bc85b0c7cf2b456f4a51ad648330b8a9845a0`.

### P10-002 — Candidate freeze and pre-registered economic gates

Freeze the exact baseline candidate identity/configuration and register the
numeric/evaluable thresholds **before** opening the forward window.

The registry must cover all seven P10-001 criteria. At minimum:
- Net PnL after fee/slippage must be strictly positive;
- drawdown cannot weaken the accepted P4 maximum;
- minimum sample and/or observation-duration requirements must be explicit;
- consistency and regime-coverage rules must be explicit;
- failure/recovery acceptance must be explicit;
- all inherited risk-control breaches remain disqualifying.

No threshold may be inferred from or optimized against future P10 observations.

Acceptance: frozen candidate/config digest, frozen gate-registry digest,
P10-001 criterion coverage, no missing/duplicate gate and proof that no forward
data was consumed before registration.

Accepted: PR #69 exact final candidate HEAD
`8161f96dff29e076ef34cc8198073c18c42a647f` passed matching Actions run
`35574963153` with both jobs PASS, **1319/1319** complete tests and **23/23**
focused P10-002 tests. Frozen candidate SHA-256:
`64f2e116616f84e09fbf70a19977395eac99b16fe7e24a283dd53a8b0b84ac86`.
Frozen economic-gate registry SHA-256:
`f8d706df050bb095219ae4b76e400eff73e1a7a6755c4a197d489b03117a3e95`.
Frozen candidate+gate registration SHA-256:
`0e4914e98754bceebf9dc99cc0ae7ab65b2b1a5b135c1fd9d736a071d843f14e`.
PR #69 was squash-merged on `main` at checkpoint
`e327e2b99a0883fc096941db18b27e572561a7d1`.

The single baseline is `TREND_PULLBACK/1.0.0` with configuration SHA-256
`98301c6ee14e9ee01ffdbb1ca68cdce4c0ea0db6a504fc6e4e280bd9f027e20a`.
Selection is based only on accepted sample feasibility (31 P3 trades versus
4 for RANGE_BREAKOUT); both historical candidates remain
`INSUFFICIENT_EVIDENCE`, and historical return is explicitly not used to
select the P10 baseline.

Frozen economics and execution context:
- BTCUSDT + ETHUSDT;
- 1h primary / 15m context / 4h regime;
- next-primary-open execution policy;
- initial Paper equity 10,000 quote units;
- 10 bps fee + 5 bps adverse slippage;
- accepted P4 risk policy unchanged.

Pre-registered gates:
- at least **90 calendar days**;
- at least **60 completed trades pooled**;
- at least **20 completed trades per symbol**;
- net return after fee/slippage at least **+2%**;
- profit factor after costs at least **1.10**;
- maximum validation drawdown **8%**;
- 3 equal validation segments, at least **2 positive**;
- no segment loss worse than **-4%**;
- each symbol must have positive net PnL after costs;
- at least **2 distinct market regimes observed** in the decision stream;
- entries are allowed only in `TREND_UP`; out-of-regime entries allowed: **0**;
- unresolved data-quality/reconciliation failures: **0**;
- safety breaches and entries while Kill Switch is active: **0**;
- recovery requires a valid clear observation and manual reset;
- risk-policy violations/order-endpoint/AI-execution events: **0**.

Candidate and gate identities are immutable before P10-003. The validation window,
forward data and economic evaluation remain unopened.

### P10-003 — New-data window seal and no-peek boundary

Seal the exact forward validation start/cutoff semantics after P10-002.
Bind the window to:
- candidate digest;
- gate-registry digest;
- symbols;
- time basis;
- accepted data source;
- a historical cutoff proving the validation observations were not part of the
  candidate-development evidence.

The window may open only after candidate and thresholds are frozen.

Acceptance: deterministic window identity, cutoff/no-overlap checks,
future-only admission, no lookahead and no post-open candidate/gate mutation.

Current candidate: branch `p10-003-forward-window-seal` from accepted P10-002
checkpoint `e327e2b99a0883fc096941db18b27e572561a7d1`.

Frozen no-peek chronology:
- accepted P3 development evidence end:
  **2026-09-09 00:00:00 UTC** (`1788912000000`);
- accepted P1 historical source maximum requested end:
  **2026-09-09 16:15:00 UTC** (`1788970500000`);
- P10-003 seal timestamp:
  **2026-09-21 08:07:00 UTC** (`1789978020000`);
- P10 forward window start:
  **2026-09-22 00:00:00 UTC** (`1790035200000`);
- earliest economic evaluation date after the pre-registered 90-day gate:
  **2026-12-21 00:00:00 UTC** (`1797811200000`).

The start is aligned simultaneously to 15m / 1h / 4h UTC grids. Any observation
with an open time before the P10 start is ineligible, even if it is fetched later.
The accepted source remains `BINANCE_SPOT_PUBLIC`; symbol scope remains
BTCUSDT + ETHUSDT.

P10-003 does not load market values. It freezes an identity-only admission
boundary for closed observations and rejects source substitution, pre-window
backfill, cross-symbol/cross-interval material, misaligned timestamps, open
observations, candidate mutation, gate mutation and lookahead.

The 90-day date is a minimum, not a forced end. If the 60 pooled / 20-per-symbol
sample gate is not satisfied then, forward observation may continue without
changing the candidate or gates. Economic evaluation remains forbidden in
P10-003.

### P10-004 — Read-only forward market-data ingestion and quality gate

Admit only bounded public Spot market data that belongs to the sealed P10 window.
Reuse accepted P1 data semantics where applicable while preserving an independent
P10 provenance manifest.

Reject gaps, duplicates, malformed/conflicting candles, open historical candles,
cross-symbol material, data before the sealed window and provenance drift.

Acceptance: exact provenance/data-range manifest, health/quality PASS,
no-write upstream proof and deterministic replay.

### P10-005 — Frozen baseline forward Paper runner

Run the frozen P10-002 baseline against the admitted new data using accepted
point-in-time strategy semantics, P4 risk controls and Paper-only P5-style
execution economics. No strategy/threshold tuning is permitted after the window
opens.

The first P10 baseline is **non-AI** for economic attribution clarity. Existing
P6 AI material may not directly choose quantity, mutate risk or execute.

Acceptance: deterministic forward Paper lifecycle, exact candidate/window
bindings, no-lookahead proof, no post-open mutation and Paper-only execution
evidence.

### P10-006 — Cost- and risk-aware forward economics

Compute validation metrics from accepted forward Paper evidence:
- Net PnL after fees and slippage;
- gross PnL and total costs;
- completed trade/sample counts;
- realized drawdown;
- wins/losses/breakeven where defined;
- exposure/holding summaries required by the registered gate.

Undefined or insufficient quantities remain explicit. No favorable extrapolation.

Acceptance: Decimal-safe arithmetic, reconciliation against forward Paper
evidence, exact cost inclusion, deterministic replay and no evidence upgrade.

### P10-007 — Consistency, regime stability and failure/recovery gate

Evaluate the remaining pre-registered criteria without changing them:
time consistency, symbol/regime stability as registered, safety/risk incidents,
kill-switch behavior, data outages and recovery behavior.

The gate disposition is one of:
- `INSUFFICIENT_DATA`;
- `FAIL`;
- `PASS_CANDIDATE`.

`PASS_CANDIDATE` remains Paper-only and does not itself open P11.

Acceptance: all registered criteria evaluated exactly once, no cherry-picking,
fail-closed missing evidence, deterministic disposition and preserved safety locks.

### P10-008 — Guarded validation export and CLI

Expose bounded local noninteractive status/summary/export commands for P10
evidence. Export the candidate, gate registry, window, provenance, forward Paper
metrics and gate result as one canonical audit package.

No command may tune the candidate/gates, submit an order or mutate upstream P10
evidence.

Acceptance: stable exit codes, bounded/redacted output, atomic no-overwrite
export, canonical SHA-256 and source-safety scans.

### P10-009 — Adversarial forward-validation matrix

Run fixed BTCUSDT/ETHUSDT scenarios for:
- pre-window data contamination;
- candidate mutation after seal;
- threshold mutation after seal;
- fee/slippage removal;
- fabricated positive PnL;
- drawdown suppression;
- sample deletion/cherry-picking;
- cross-symbol/cross-window material;
- data-quality failure;
- risk/safety breach;
- evidence-label / Live-readiness upgrade attempts.

Acceptance: exact fail-closed outcomes, byte-identical replay, canonical evidence
and unchanged accepted P10 identities.

### P10-010 — Independent final economic audit

Independently recompute the full P10 chain:
candidate freeze, gate registry, window/cutoff, data provenance/quality, forward
Paper evidence, costs, metrics, consistency/regime/failure gates and adversarial
evidence.

Final P10 disposition:
- `INSUFFICIENT_DATA`: P11 stays locked; continue forward observation without
  changing the registered candidate/gates.
- `FAIL`: P11 stays locked; end this validation attempt and return to a new
  research/strategy iteration with a new future P10 registration.
- `PASS_CANDIDATE`: P10 is economically accepted as a **Paper validation
  candidate only**. P11 may then be considered under separate security/account/
  risk/operator approval.

Even `PASS_CANDIDATE` is not a guarantee of future profit.

Acceptance: independent exact recomputation, no hidden threshold/candidate drift,
matching Final-HEAD CI evidence and explicit operator merge approval.

## Phase transition

P11 remains **LOCKED** for all P10 checkpoints before P10-010 acceptance.

Engineering completion is not economic acceptance. P10 exists specifically to
allow the answer to be "no edge demonstrated" without weakening the evidence
standard.
