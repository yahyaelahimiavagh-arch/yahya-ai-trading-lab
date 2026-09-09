# P2 — Backtesting Engine implementation plan

Status: **IN PROGRESS — P2-002 IMPLEMENTED AND RUNTIME VERIFIED, CHECKPOINT PENDING**
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

Acceptance: **PASS in working tree, 2026-09-09.** Temporary-database tests cover exact
manifest matching, read-only behavior, point-in-time visibility, missing/open rows, schema
mismatch, invalid paths/ranges and bounded selection. Runtime loads passed against the
accepted P1 SQLite database for both BTCUSDT and ETHUSDT over the latest 24-hour run range.
Checkpoint remains required before P2-003.

### P2-003 — Deterministic event clock

Advance one aligned primary boundary at a time. Emit the same ordered sequence for identical
inputs and seed. Expose only the snapshot legal at that instant and queue decisions for the
next primary open.

Acceptance: boundary, start/end, multi-timeframe synchronization and look-ahead trap tests.

### P2-004 — Paper intent and fill model

Define ENTER_LONG, EXIT_LONG and HOLD intents for scripted engine tests. Fill only at the
next 1h open, reject Short and overlapping positions, and define a conservative deterministic
rule for bars where stop and target are both touched.

Acceptance: exact lifecycle tests with no exchange transport or order endpoint.

### P2-005 — Fees, slippage and precision

Apply adverse slippage by side and charge quote-currency fees on every fill using Decimal.
Quantize only at an explicit reporting boundary; preserve full internal precision.

Acceptance: hand-calculated vectors, zero/maximum bounds and cost-monotonicity properties.

### P2-006 — Portfolio ledger and invariants

Maintain cash, one long Spot position per symbol, realized/unrealized PnL and mark-to-market
equity. Every fill must balance and cash, quantity and equity inputs must remain valid.

Acceptance: conservation identities, round-trip accounting, insufficient-cash rejection and
multi-symbol isolation tests.

### P2-007 — Performance metrics

Produce return, trade count, win rate, gross/net PnL, total costs, maximum drawdown and
risk-adjusted descriptive metrics with explicit undefined-sample handling.

Acceptance: hand-computed equity curves, no-trade/one-trade cases and drawdown edge cases.

### P2-008 — Reproducible artifacts

Write an atomic run manifest containing data identity, configuration, seed, engine version,
input digest, trades, equity curve summary and metrics. Exclude local paths and secrets.

Acceptance: byte-identical results for identical inputs and changed digest for material inputs.

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
