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

## Completed single-run evidence

Preregistration commit `be1b6db5850868b069c104faee8ecc00f167904e` was published before any June acquisition; exact data commit `205adbe28737b3f77507ea73952a58fd23f69547` was published before replay. The protocol SHA256 is `ad8cea566868ca3443aa2faa9eaaddc323b948e9ceaa032deecb14702acb5585` and admitted manifest SHA256 is `e1dd5fbf91c1f9b80af1cc5d744485e1717f11531c8c803c01ebca3b119f8678`. Dataset identities:

- BTCUSDT: `2e79e8a2e70449ed3967ddf168d3fe123918f6298c7b6b81bd4a91c8a3642aef`.
- ETHUSDT: `9bdd49bc2e48f15e746e7fff1597bba74fa695186945a28a6d054229491c59a1`.

Both assets admitted exactly 2,880 June rows with zero gaps/duplicates. The exclusive reservation remains at `research/experiments/june_2026_backtest/results/reservation.json`; exactly one real-data replay completed with status `COMPLETED_SEEN_RESEARCH` and process exit0. Source/protocol parameters were not changed after freezing or observing results.

| Metric | Conservative | Aggressive |
| --- | ---: | ---: |
| Initial virtual equity, USDT | 10,000.00 | 10,000.00 |
| Final virtual equity, USDT | 9,992.83 | 9,982.07 |
| Net PnL, USDT | -7.17 | -17.93 |
| Net return | -0.0717% | -0.1793% |
| Observed maximum drawdown | 0.1424% | 0.3558% |
| Closed trades / wins / losses | 4 / 1 / 3 | 4 / 1 / 3 |
| Win rate | 25% | 25% |
| Profit factor | 0.4426 | 0.4425 |
| Average net PnL per trade, USDT | -1.79 | -4.48 |
| Largest net trade loss, USDT | -4.57 | -11.45 |
| Fees, USDT | 7.99 | 19.99 |
| Modeled slippage, USDT | 4.00 | 9.99 |
| Maximum committed capital at entry | 10.0000% | 25.0000% |
| Positions remaining at end | 0 | 0 |

The capital percentages shown above are rounded; exact values stayed below the10%/25% ceilings. Both accounts made the same four virtual trades (one ETH and three BTC), then latched `THREE_CONSECUTIVE_LOSSES` at **2026-06-16T08:00:00Z** (11:00 Istanbul). No later entries occurred. There were9 later setup signals vetoed by the latch in each account. Costs and stop budgets are retained unrounded in the ledgers.

| Passive control, final equity in USDT | Conservative capital ceiling | Aggressive capital ceiling |
| --- | ---: | ---: |
| Remain in cash | 10,000.00 | 10,000.00 |
| BTC from June9 12:00UTC, same costs | 9,932.04 | 9,830.10 |
| ETH from June9 12:00UTC, same costs | 9,937.40 | 9,843.51 |

The rule strategy lost less than these passive controls in this interval but underperformed cash. Controls match the allowed capital allocation, not stop risk, trading activity or realized exposure. This is not benchmark-24 or the sealed MCF batch.

An independent audit of the already-written ledgers (without another replay) reconciled every fill cash flow, fees/slippage, terminal equity and trade PnL; verified no overlapping or outside-June fills, no negative cash, planned stop-risk/capital ceilings, no post-latch entry, identity/safety matches, and716 hourly equity observations per account. The11 June tests and33 accepted-model tests passed before acquisition. See `results/validation.json` and `results/summary.json` for machine-readable evidence and the two ledgers for every decision digest, virtual fill, trade and equity observation.

**Conclusion:** this fixed strategy did not produce a positive net result in this June experiment. Four trades after limited within-month warmup and a permanent loss latch are too few to establish stable profitability or its absence. No strategy selection, live promotion, tuning or second run is authorized by these results. June remains seen research and cannot be reused as an untouched Fresh OOS validation month for work informed by this exposure.

Safety remains paper-only, live master lock OFF, P11 locked, no futures/leverage/short/orders/withdrawal, no P10 read/write, no recent reserve or other Fresh OOS reads, no selection, benchmark-24 retry or full-6852 authorization. Existing main, frozen MCF artifacts and the separate seven-day paper experiment remain unchanged.
