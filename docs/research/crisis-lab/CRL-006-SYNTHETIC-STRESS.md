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
