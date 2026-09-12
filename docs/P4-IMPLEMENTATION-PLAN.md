# P4 — Risk Manager implementation plan

Status: **IN PROGRESS — P4-003 MERGED; P4-004 RUNTIME ACCEPTED ON PR #6**
Entry baseline: P3 runtime accepted and squash-merged in commit `90d5847` with all
283 tests and GitHub Actions run `34699734574` passing.
Exit condition: an independent, deterministic and fail-closed manager binds each
strategy decision to point-in-time portfolio state, evidence eligibility and a
frozen risk policy; computes paper quantity; enforces loss, exposure and circuit-
breaker limits; and emits reproducible approvals/rejections without any exchange
execution capability.

## Fixed boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF` remain hard invariants.
- Only long-only BTCUSDT/ETHUSDT Spot research is representable. No Short, Margin,
  Futures, leverage, withdrawal, broker or order endpoint is permitted.
- P4 is independent from strategy logic. It may reject any entry and may not alter
  a P3 signal, setup, parameter, evidence label or market input.
- An entry cannot receive paper approval unless its frozen P3 evidence label is
  `QUALIFIED_FOR_P4_RESEARCH`. Current accepted candidates remain
  `INSUFFICIENT_EVIDENCE` and therefore cannot be approved for entry.
- Risk-reducing exits remain allowed while a kill switch is active; new or
  increased exposure is blocked.
- All financial inputs and calculations use validated decimal strings and
  deterministic `Decimal` arithmetic. Float, implicit rounding and guessed state
  are rejected.
- P4 consumes no API credential, account endpoint, network transport or AI output.
  It produces a local Paper decision, never an exchange order.

## Frozen initial policy `P4_RISK_V1`

- maximum planned loss per trade: 1% of point-in-time equity;
- maximum single-position notional: 25% of equity;
- maximum total gross exposure: 25% of equity;
- maximum concurrent open positions: one;
- session-loss circuit breaker: 2% of session-start equity;
- peak-to-current drawdown circuit breaker: 10%;
- consecutive-loss circuit breaker: three closed losing trades;
- approved markets: BTCUSDT and ETHUSDT Spot, long-only, Paper only.

These are conservative engineering fixtures for P4 validation, not a live-risk
recommendation. Any future change requires a new policy version and new evidence.

## Delivery sequence

### P4-001 — Risk contracts and safety boundary

Define immutable policy, portfolio state, request and decision records. Bind each
request to strategy context/evidence/state with a canonical SHA-256. Enforce
fail-closed action/reason/quantity semantics and prove that insufficient evidence
cannot receive entry approval while exits remain possible under Kill Switch.

Acceptance: focused unit tests, complete regression suite, deterministic offline
CLI, compile/whitespace/lock checks and source scans proving no credentials,
network client or exchange-order path.

Acceptance: **PASS, runtime 2026-09-12, GitHub Actions run `34700810982`.** Ten
focused tests and the complete suite passed **293/293**. The deterministic
`risk-contract-check` blocked the current insufficient-evidence entry and permitted
the matching exit under Kill Switch with request SHA-256
`af474a99f84d4303d092f1a9e86de74b444ac7938f38776573dca6910fbf3414`.
Compile, whitespace, lock and restricted-source scans passed. The accepted P3
matrix replay and final audit also passed unchanged. P4-002 has not started.

### P4-002 — Exact loss-budget position sizing

Compute quantity from equity, entry, invalidation and the 1% loss budget, including
explicit P2 fees/slippage. Round downward to frozen research increments and reject
zero, non-finite, over-budget or under-specified results.

Acceptance: **PASS, runtime 2026-09-12, GitHub Actions run `34702613220`.** Exact
256-digit local Decimal arithmetic uses the accepted P2
defaults of 10 bps fee and 5 bps adverse slippage on both entry and stop. The 1%
equity budget is divided by the complete cost-adjusted loss per unit and rounded
down to the frozen `0.000001` research quantity step. The immutable result records
budget, adjusted prices, loss per unit, total fee/slippage, planned loss and the
bound request SHA-256. Twelve focused sizing tests and the complete suite passed
**305/305**. The qualified fixture produced quantity `9.708733`, budget `100.00`
and planned loss `99.9999984436650`; request SHA-256 is
`393d74071bc590b80ddbdc53ce6bcc250091e0b0b60b89f52fe907b548825590`.
Current candidates were blocked before sizing. Compile, whitespace, lock,
deterministic CLI, restricted-source scans and unchanged P3 evidence gates passed.
Exposure and cash caps are implemented by the subsequent P4-003 checkpoint.

### P4-003 — Cash, notional and exposure limits

Enforce the 25% single-position and gross-exposure caps, one-position limit and
cash sufficiency without leverage. Reject overlapping or exposure-increasing
requests atomically.

Implementation: an immutable assessment binds the accepted P4-002 sizing result
and records entry notional, entry fee, required cash, current/prospective gross
exposure and both frozen 25% limits. It rejects limit breaches before cash
shortage when both apply, rejects insufficient cash without leverage, and emits
no approval. The one-position invariant remains enforced by the P4 request/sizing
contracts.

Acceptance: **PASS, runtime 2026-09-12, GitHub Actions run `34714934702`.** Nine
focused limit tests and the complete suite passed **314/314**. The deterministic
runtime recorded `normal=PASS/WITHIN_LIMITS`,
`low_cash=REJECT/CASH_INSUFFICIENT`, entry notional `1019.9266734825` and cap
`2500.00`. Compile, whitespace, lock and restricted-source scans passed. The
accepted public checkpoint was rebuilt with 7,560 rows; the candidate matrix was
byte-equal across two runs and the independent P3 audit retained index SHA-256
`59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
P4-003 was squash-merged from PR #5 in checkpoint `27dfd86`.

### P4-004 — Point-in-time portfolio/session state

Build deterministic state transitions for equity peak, session start, realized
loss, open exposure and consecutive losses. Reject stale, duplicate, missing or
out-of-order state.

Implementation: complete aligned hourly paper observations are applied only in a
strictly increasing, gap-free sequence. Every resulting immutable state binds the
observation SHA-256 and predecessor state SHA-256. The engine deterministically
maintains UTC session start time/equity, session realized PnL, all-time equity peak,
one-position gross Spot exposure and consecutive closed losses. Close outcome/PnL,
position disappearance or mutation, session boundary, symbol and sequence
inconsistencies fail closed. It can project validated facts into the accepted
P4-001 request contract but cannot activate a Kill Switch, approve a trade or emit
an order.

Acceptance: **PASS, runtime 2026-09-12, GitHub Actions run `34717094100`.** Twelve
focused state tests and the complete suite passed **326/326**. The deterministic
loss fixture ended at sequence 2 with session PnL `-100`, one consecutive loss,
zero gross exposure and state SHA-256
`1b6700b922e2f7f6693b381222c81ebc10a1362c01dc4eca576dc6cb02e05bd0`.
Compile, whitespace, lock and restricted-source scans passed. The accepted public
checkpoint rebuilt 7,560 rows; two candidate runs were byte-equal and the
independent P3 audit retained evidence index SHA-256
`59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
P4-005 has not started.

### P4-005 — Protective-level and cost-aware gate

Validate that every approved long entry has a reachable protective stop below
entry, positive post-cost reward and a quantity whose worst planned paper loss
does not exceed the frozen budget.

### P4-006 — Loss and drawdown circuit breakers

Trigger entry blocks at the frozen session-loss, drawdown and consecutive-loss
limits, including exact-boundary and recovery semantics. Never block risk-reducing
exits.

### P4-007 — Kill Switch state machine

Implement explicit inactive, triggered and manually-resettable Paper states with
immutable reasons, monotonic event time, deterministic replay and fail-closed
startup. No automatic reset is permitted.

### P4-008 — P3-to-P2 risk adapter

Place P4 between P3 decisions and P2 paper intents. Prove that no entry reaches the
P2 adapter without a matching P4 approval and exact approved quantity, while exits
remain safe and atomic.

### P4-009 — Deterministic adversarial scenario matrix

Replay boundary, gap, cost, loss-streak, drawdown, stale-state, insufficient-
evidence and Kill Switch scenarios for BTCUSDT/ETHUSDT. Repeat and byte-compare
canonical evidence artifacts.

### P4-010 — P4 final audit and checkpoint

Independently recompute sizing, limits, transitions and artifacts; run the complete
suite and safety scans; verify policy/configuration digests and exact decisions.
Accept P4 runtime only when every gate passes. P5 remains unopened and no trading
permission is granted by P4 acceptance.

## Intended module boundaries

```text
yatl/risk/contracts.py      immutable policy, state, request and decision records
yatl/risk/sizing.py         exact cost-aware loss-budget sizing
yatl/risk/limits.py         cash, notional and exposure checks
yatl/risk/state.py          point-in-time portfolio/session transitions
yatl/risk/protective.py     stop, reward and worst-loss validation
yatl/risk/circuit.py        loss, drawdown and streak breakers
yatl/risk/kill_switch.py    explicit deterministic state machine
yatl/risk/adapter.py        guarded P3-to-P2 paper bridge
yatl/risk/scenarios.py      deterministic adversarial evidence matrix
yatl/risk/audit.py          independent final P4 acceptance gate
```

No new dependency is planned. Any addition requires demonstrated need, a pinned
lock update and its own checkpoint evidence.
