# CRL-006 — Synthetic adversarial stress matrix

Goal: test failure modes not sufficiently represented by historical candles.

Initial scenario families:
- abrupt gap/jump shocks;
- 2x/5x/10x fee/slippage stress;
- spread/liquidity degradation proxies;
- missing/stale candle sequences;
- delayed data;
- disconnect/restart;
- shock while position is open;
- repeated whipsaw shocks;
- delayed regime recognition;
- recovery/re-entry pressure.

Synthetic evidence is labeled SYNTHETIC and never mixed with historical PnL.

Exit gate: fixed scenario registry, deterministic two-run equality, explicit
survival/failure outcomes and no production authority.


## Open-position sudden-shock track

Historical data may not naturally place the frozen strategy in a position at the
exact registered crisis anchor. That absence must not be "fixed" by forcing a
historical entry.

CRL-006 therefore contains a distinct **SYNTHETIC_OPEN_POSITION_SHOCK_V1**
diagnostic:
- source state must come from a real permitted Development `ENTER_LONG` episode
  selected by the CRL-005 strategy-active rule;
- preserve the exact frozen candidate, quantity, fees, risk limits and portfolio
  state;
- inject the shock only after the Paper position is confirmed open;
- fixed first matrix: next-primary-open adverse gaps of **-5%, -10%, -20%**;
- for each gap run normal costs plus **2x and 5x slippage** sensitivity variants;
- Strategy never receives the synthetic scenario label as a decision feature;
- record stop/exit response, maximum equity excursion, time-to-zero-exposure,
  Kill Switch state, re-entry behavior and recovery;
- synthetic PnL is labeled SYNTHETIC and never pooled with historical returns.

The source entry episode may be selected from entry occurrence only. Its future
PnL/path cannot be inspected before scenario construction.
