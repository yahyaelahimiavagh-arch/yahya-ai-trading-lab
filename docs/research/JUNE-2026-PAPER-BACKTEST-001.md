# June 2026 paper backtest — preregistered research exception

The Director explicitly approved opening **only June 2026 BTCUSDT/ETHUSDT Spot public candles** on 2026-10-03 (Europe/Istanbul), after being told that June belongs to sealed Fresh OOS and would become seen research. His confirmation was «باشه». June must therefore be excluded from any later claim of independent Fresh OOS evidence for work informed by this experiment. This exception does not open other Fresh OOS months, the recent reserve, P10 or P11.

## Fixed scope before acquiring June data

- Expected GitHub main: `58b6c74a834d51f0d68e06fbe5f1885057e9df9a`.
- Separate unmerged branch: `research/june-2026-paper-backtest`.
- Experiment: `JUNE-2026-PAPER-001`; at most one canonical replay containing the two specified accounts. No parameter search or outcome-dependent strategy edits.
- Public, credential-free Binance data-only REST host, `/api/v3/klines`; request range `[2026-06-01T00:00:00Z, 2026-07-01T00:00:00Z)`. Exactly 2,880 contiguous closed 15-minute rows per asset; derive 720 hourly and 180 four-hour candles. Reject gaps, duplicates and any outside-range row. No May warmup or July execution bar.
- Reuse existing `TREND_PULLBACK` 1.0.0 with its unchanged ATR14, SMA20, pullback3, reward/risk2 and stop ATR fraction0.25. The existing four-hour regime needs 51 completed bars: first possible entry is June 9 at 12:00 UTC. Decisions receive only bars closed before the decision time.
- Two independent virtual 10,000-USDT accounts: conservative planned stop risk at most 0.25% and capital ceiling10%; aggressive planned stop risk at most1% and capital ceiling25%. These are controlled relative risk profiles, not an unconstrained maximum-risk mode. One position across both assets per account; BTC priority when simultaneous signals occur.
- Long-only Spot; no real balances, order endpoints, exchange account, provider AI calls or paid API. This is the frozen rule-based YATL strategy, distinct from the existing seven-day ChatGPT forward paper experiment.
- Entry at the next hourly open, subject to bracket validity, costs and size limits; accepted protective fill logic prioritizes the stop if both stop and target occur in a bar and accounts for adverse opening gaps. Do not enter a second asset after observing an intrabar exit in the same hour.
- Fixed costs per side:10bps fee plus5bps slippage. Quantity step0.000001 and previous closed hour's base-volume participation cap1%. This is a hypothetical execution model, not live exchange lot-size/min-notional validation or an order-book simulation.
- Daily observed loss2%, observed drawdown10%, or three consecutive losses latch entry shutdown for the remainder of the month; existing position liquidates at the next hour open. Gap losses can exceed planned stop budgets. At month end, liquidate virtually at the last June close with exit costs.
- Report net PnL/return, closed trades, win rate, profit factor, expectancy, fees/slippage, observed drawdown and any latch. Retain decision digests, fills, trade ledger and hourly equity. Compare cash and separate exposure-ceiling-matched BTC/ETH passive holdings from the first eligible June open with the same costs; these controls do not match stop risk or realized exposure.

## Identities and one-run boundary

`research/experiments/june_2026_backtest/protocol.json` binds the new module SHA256, the aggregate SHA256 of all existing `yatl/**/*.py` source hashes, unchanged strategy parameters, dates, assets, costs, account rules and safety flags. Publish code and this protocol before public acquisition. The acquired files and manifest bind response-page and dataset hashes. The `results` directory is an exclusive run reservation: never delete or reuse it, even after a failure. Synthetic fixture tests do not constitute an extra historical replay.

The narrowly scoped module commands, in order, are:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m research.model_lab.june_paper_backtest freeze
PYTHONDONTWRITEBYTECODE=1 python -m research.model_lab.june_paper_backtest acquire
PYTHONDONTWRITEBYTECODE=1 python -m research.model_lab.june_paper_backtest run
```

These commands refer to the separate June experiment. They do not refreeze or alter the MCF runner input, create MCF authorization, or rerun its incomplete memory diagnostic.

## Validation before acquisition

Eleven synthetic June-specific tests cover exact date/data admission, request bounds and page hashes, future exclusion, frozen identity/safety, sizing, accepted cost accounting, loss latches, no forced trades, deterministic simultaneous-signal priority, intrabar no-reentry and exclusive run reservation. Thirty-three existing tests cover accepted fill/cost models and the frozen trend/regime logic. All passed before data acquisition.

## Evidence status

Preregistered; June public acquisition and the single canonical replay are pending. Actual data and results will be appended without changing this protocol. One month cannot establish a stable profitable edge, authorize live trading, select a candidate or promote a strategy.

Safety remains paper-only, live master lock OFF, P11 locked, no futures/leverage/short/orders/withdrawal, no P10 read/write, no recent reserve or other Fresh OOS reads, no selection, benchmark-24 retry or full-6852 authorization. Existing main, frozen MCF artifacts and the separate seven-day paper experiment remain unchanged.
