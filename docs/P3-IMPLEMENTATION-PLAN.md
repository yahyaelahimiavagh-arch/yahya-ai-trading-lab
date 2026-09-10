# P3 — Strategy Framework implementation plan

Status: **IN PROGRESS — P3-001 IMPLEMENTED AND RUNTIME VERIFIED, CHECKPOINT PENDING**
Entry baseline: P2 accepted in commit `9cbc197` with a clean working tree.
Exit condition: deterministic, versioned BTCUSDT/ETHUSDT Spot strategy candidates produce
point-in-time signals through the accepted P2 engine, pass anti-lookahead and reproducibility
gates, and report evidence strength without claiming profitability from an inadequate sample.

## Fixed boundaries

- P3 consumes only closed 4h/1h/15m candles exposed by `MarketSnapshot`; 5m stays disabled.
- Output is `NO_TRADE`, `ENTER_LONG` or `EXIT_LONG` research intent. P3 cannot submit a fill,
  exchange request or order and cannot read API credentials.
- P3 never chooses account quantity. Position sizing, exposure limits and kill switches belong
  to P4. The P2 adapter uses an explicit fixed research quantity only for backtest evidence.
- Long-only Spot remains fixed. Short, Margin, Futures, leverage and withdrawal APIs have no
  representation.
- Every feature and decision uses deterministic `Decimal` arithmetic and carries strategy ID,
  version, decision time and machine-readable reason codes.
- Insufficient warm-up, missing inputs, ambiguous regime, invalid levels or non-finite values
  return `NO_TRADE` or fail closed according to the contract; they never guess a signal.
- Strategy parameters are versioned and frozen before evaluation. P3 has no brute-force search,
  genetic optimization, online learning, LLM decision or automatic parameter selection.
- Framework correctness and strategy performance evidence are separate gates. Thirty days can
  validate integration but cannot by itself establish durable edge.

## Delivery sequence

### P3-001 — Signal contract and safety boundary

Define immutable strategy context, action, reason, setup and decision records. Enforce symbol,
time, level, version and point-in-time identity. Ensure quantity, broker, credential and order
fields cannot enter the strategy interface.

Acceptance: **PASS in working tree, 2026-09-10.** Immutable identity, context, setup and decision
records enforce semantic versions, exact long levels and the fixed paper/Spot/long-only safety
policy. Action/reason/setup mismatches and policy tampering fail closed. The context SHA-256 is
byte-stable and changes with visible candle material. Tests and source scan prove there is no
sizing, credential, broker or execution endpoint. Checkpoint remains required before P3-002.

### P3-002 — Point-in-time feature primitives

Implement exact returns, rolling high/low, SMA, EMA, ATR and RSI over closed canonical candles.
Each function declares warm-up length and returns an explicit unavailable result until ready.

Acceptance: hand-computed vectors, flat/rising/falling series, gaps, zero-volume inputs, extreme
Decimal precision and prefix-invariance tests. Appending future candles cannot change an earlier
feature value.

### P3-003 — Higher-timeframe regime classifier

Classify the closed 4h prefix as `TREND_UP`, `TREND_DOWN`, `RANGE` or `UNKNOWN` using one frozen,
versioned ruleset. The regime is context and cannot create an order.

Acceptance: boundary vectors, insufficient-history behavior, deterministic reason codes and
future-append invariance.

### P3-004 — Strategy registry and frozen configuration

Register strategies by immutable ID/version and canonical parameter payload. Reject duplicate
IDs, unknown parameters, unsafe ranges and runtime mutation. Hash configuration for artifacts.

Acceptance: byte-stable configuration, changed digest for material changes and fail-closed
registry/config tests.

### P3-005 — Trend-pullback candidate v1

Implement a transparent long-only candidate: 4h up-regime filter, 1h trend/pullback setup and
closed 15m confirmation. Entry invalidation and target levels must be derived only from visible
candles and emitted with exact reason codes.

Acceptance: positive/negative hand-built scenarios, gap/insufficient-data rejection, explicit
exit rules and no current/future candle access.

### P3-006 — Breakout candidate v1

Implement a second transparent long-only candidate using a closed 4h regime filter, confirmed
1h range breakout and 15m context. It must remain independent of the trend-pullback state.

Acceptance: breakout/false-breakout/range/low-quality vectors, deterministic exits and the same
point-in-time safety gates as P3-005.

### P3-007 — Signal lifecycle and P2 research adapter

Track one strategy position state and translate accepted signals into P2 paper intents with a
fixed test quantity. Preserve next-primary-open fills, conservative Stop priority, explicit
costs and flat final portfolios. P4 sizing is deliberately absent.

Acceptance: `NO_TRADE`, entry, hold and exit lifecycles; duplicate/overlapping signal rejection;
replay equality; no exchange, account or credential transport.

### P3-008 — Evaluation protocol and anti-overfitting gates

Pre-register candidate versions and evaluation windows. Report each symbol separately and pooled;
compare against no-trade and buy-and-hold research references; include costs, trade count, return,
drawdown and stability by chronological segment. Never select a candidate on one headline metric.

Acceptance: train/evaluation separation, minimum-sample rules, parameter-lock digest, future-data
mutation tests and explicit `INSUFFICIENT_EVIDENCE`, `REJECTED` or `QUALIFIED_FOR_P4_RESEARCH`
labels. Qualification is not approval for live trading.

### P3-009 — Accepted-data candidate runs

Run both frozen candidates on BTCUSDT and ETHUSDT through P2, repeat every run, validate artifacts
and record exact results. The current accepted 30-day dataset is an integration/smoke window; if
sample gates fail, retain `INSUFFICIENT_EVIDENCE` and do not tune around the result.

Acceptance: deterministic artifacts for every candidate/symbol/baseline pair, explicit cost drag,
point-in-time proof and honest evidence labels.

### P3-010 — P3 final audit and checkpoint

Recompute features, decisions, fills, metrics and artifacts; run the complete suite and safety
scan; verify frozen configuration digests and evidence labels.

Acceptance: mark P3 runtime accepted only when every software gate passes and commit a clean
baseline. A strategy may remain unqualified; P4 can still build independent risk controls, but
no candidate proceeds toward P5/P10 without its required evidence.

## Intended module boundaries

```text
yatl/strategy/contracts.py    immutable signal and safety contracts
yatl/strategy/features.py     point-in-time Decimal indicators
yatl/strategy/regime.py       frozen 4h regime classification
yatl/strategy/registry.py     versioned strategy configuration
yatl/strategy/trend.py        trend-pullback candidate v1
yatl/strategy/breakout.py     breakout candidate v1
yatl/strategy/adapter.py      paper-only bridge to P2
yatl/strategy/evaluate.py     evidence protocol and labels
yatl/strategy/audit.py        final P3 acceptance gate
```

No new dependency is planned. Any addition requires demonstrated need, a pinned lock update and
its own checkpoint evidence.
