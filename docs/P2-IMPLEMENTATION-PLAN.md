# P2 — Backtesting Engine implementation plan

Status: **IN PROGRESS — P2-008 IMPLEMENTED AND RUNTIME VERIFIED, CHECKPOINT PENDING**
Entry baseline: P1 accepted in commit `4e77e34` with a clean working tree.
Exit condition: deterministic BTCUSDT/ETHUSDT Spot simulations pass unit, invariant,
reproducibility and real-dataset runtime gates with explicit fees and slippage.

## Fixed scope and simulation law

- Research data comes only from the accepted public Binance Spot data layer.
- Symbols are BTCUSDT and ETHUSDT. Primary decisions occur on aligned 1h boundaries;
  15m is context and 4h is regime. 5m remains disabled.
- A decision at time `t` may observe only closed candles with `close_time_ms < t`.
- A decision formed at `t` may first fill at the next primary open under the fixed
  `NEXT_PRIMARY_OPEN` policy. Same-candle close fills are forbidden.
- All money and quantity arithmetic uses `Decimal`; binary floating point is forbidden
  for accounting, costs and metrics.
- Simulations are Spot, long-only and unleveraged. Cash and asset balances cannot be negative.
- Fees and adverse slippage are explicit and cannot silently default to zero in acceptance runs.
- Every run is local and paper-only. No API credential, Testnet account transport, order,
  withdrawal, margin, Futures or AI execution interface may enter P2.
- P3 owns strategy logic. P2 uses deterministic scripted intents only to verify the engine.

## Delivery sequence

### P2-001 — Point-in-time contract and policy

Define immutable simulation configuration and a synchronized 1h/15m/4h market snapshot.
Reject open, future, stale, gapped, unordered, wrong-symbol or wrong-timeframe inputs. Lock
paper-only, Spot, long-only, no-leverage and next-primary-open behavior.

Acceptance: **PASS, checkpoint `30a6e6d`, 2026-09-09.** Unit tests cover every boundary;
the local runtime contract check and full suite passed before a clean checkpoint.

### P2-002 — Accepted dataset loader

Load exact half-open ranges from the P1 SQLite store only after the P1 manifest gate passes.
Build point-in-time snapshots without leaking later rows. Reject incomplete coverage, schema
drift, open candles and a database/manifest range mismatch.

Acceptance: **PASS, checkpoint `218a06e`, 2026-09-09.** Temporary-database tests cover exact
manifest matching, read-only behavior, point-in-time visibility, missing/open rows, schema
mismatch, invalid paths/ranges and bounded selection. Runtime loads passed against the
accepted P1 SQLite database for both BTCUSDT and ETHUSDT over the latest 24-hour run range.
The clean checkpoint was accepted before P2-003 started.

### P2-003 — Deterministic event clock

Advance one aligned primary boundary at a time. Emit the same ordered sequence for identical
inputs and seed. Expose only the snapshot legal at that instant and queue decisions for the
next primary open.

Acceptance: **PASS, checkpoint `275a163`, 2026-09-09.** Tests cover exact half-open boundaries,
sequence numbers, next-open eligibility, multi-timeframe visibility, lazy failure and
deterministic replay. Live read-only 24-hour clocks produced the same 24-event replay for
BTCUSDT and ETHUSDT. The clean checkpoint was accepted before P2-004 started.

### P2-004 — Paper intent and fill model

Define ENTER_LONG, EXIT_LONG and HOLD intents for scripted engine tests. Fill only at the
next 1h open, reject Short and overlapping positions, and define a conservative deterministic
rule for bars where stop and target are both touched.

Acceptance: **PASS, checkpoint `2d8940b`, 2026-09-09.** Exact lifecycle tests cover next-open
entry/scripted exit, Stop, Target, known opening gaps, ambiguous Stop-first handling,
same-bar protection, overlap rejection, candle volume bounds and transactional rollback.
The local runtime scenario produced an entry reference followed by
`AMBIGUOUS_STOP_PRIORITY`. These are uncosted references; P2-005 must apply costs before
portfolio accounting. The clean checkpoint was accepted before P2-005 started.

### P2-005 — Fees, slippage and precision

Apply adverse slippage by side and charge quote-currency fees on every fill using Decimal.
Quantize only at an explicit reporting boundary; preserve full internal precision.

Acceptance: **PASS, checkpoint `2b50013`, 2026-09-10.** Hand-calculated entry, exit and round-trip
vectors pass with 256-digit internal Decimal precision. Tests cover zero and maximum cost
bounds, very large exact products, tamper rejection and cost monotonicity. The runtime
scenario reports exact aggregate fee, slippage and net cash effect. Checkpoint remains
The clean checkpoint was accepted before P2-006 started.

### P2-006 — Portfolio ledger and invariants

Maintain cash, one long Spot position per symbol, realized/unrealized PnL and mark-to-market
equity. Every fill must balance and cash, quantity and equity inputs must remain valid.

Acceptance: **PASS, checkpoint `cd29f65`, 2026-09-10.** Tests cover exact entry basis,
conservative liquidation equity, balanced round trips, insufficient cash, duplicate/partial/
out-of-order fills, atomic batch rollback, cost-policy matching and symbol isolation. Local
runtime closed a costed round trip with cash/equity `999.4000000` from `1000` initial cash.
The clean checkpoint was accepted before P2-007 started.

### P2-007 — Performance metrics

Produce return, trade count, win rate, gross/net PnL, total costs, maximum drawdown and
risk-adjusted descriptive metrics with explicit undefined-sample handling.

Acceptance: **PASS, checkpoint `4dbb26e`, 2026-09-10.** The contract uses exact Decimal
arithmetic and requires a clean starting point and flat final portfolio. It reports total
return, trade outcomes, gross/net PnL, costs, drawdown and non-annualized descriptive
mean/volatility/downside ratios. Insufficient samples and zero denominators are explicitly
undefined. Tests cover hand-computed curves, no-trade/one-trade cases and lifecycle failures.
The local scenario reproduced gross PnL `20`, net PnL `19.37001` and maximum drawdown
`0.0006`. The clean checkpoint was accepted before P2-008 started.

### P2-008 — Reproducible artifacts

Write an atomic run manifest containing data identity, configuration, seed, engine version,
input digest, trades, equity curve summary and metrics. Exclude local paths and secrets.

Acceptance: **PASS in working tree, 2026-09-10.** Canonical sorted JSON records the
fixed safety configuration, accepted-data identity and hashes, engine version, input digest,
reconciled completed trades, equity summary and metrics. It excludes local paths, credentials
and run-time wall-clock fields and publishes through an atomic replace. Tests require
byte-identical results for identical inputs and changed digests for material inputs.
The local atomic write/read check reproduced input SHA-256
`f97ad5f66a8ac0ea1d59ee4a41e1238eb186008d961b612097069df4a21c62e4`.
Checkpoint remains required before P2-009.

### P2-009 — Real-data scripted runtime scenarios

Run deterministic no-strategy scenarios on accepted BTCUSDT and ETHUSDT datasets: no-trade,
single round trip and controlled multi-trade sequences. Confirm costs reduce results and the
engine never sees future data.

Acceptance: repeat each scenario, compare manifests and record exact runtime evidence.

### P2-010 — P2 final audit and checkpoint

Run the complete suite, accepted-data simulations, reproducibility replay, arithmetic invariant
audit, safety scan and artifact validation. Record exact evidence in `docs/STATUS.md`.

Acceptance: mark P2 runtime accepted only after every gate passes, commit the final baseline
and leave Git clean. P3 remains unopened until then.

## Intended module boundaries

```text
yatl/backtest/config.py       immutable simulation policy
yatl/backtest/models.py       point-in-time snapshots and core contracts
yatl/backtest/loader.py       manifest-gated P1 dataset access
yatl/backtest/clock.py        deterministic event sequence
yatl/backtest/fills.py        local intent and fill simulation
yatl/backtest/costs.py        Decimal fee and slippage model
yatl/backtest/portfolio.py    cash, positions and accounting invariants
yatl/backtest/metrics.py      deterministic performance calculations
yatl/backtest/artifacts.py    reproducible run manifests
yatl/backtest/audit.py        final P2 acceptance gate
```

Additional dependencies require a demonstrated need, a pinned lockfile update and checkpoint
evidence. P2-001 uses only the Python standard library and the accepted P1 contracts.
