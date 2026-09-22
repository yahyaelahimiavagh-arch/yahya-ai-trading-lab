# CRL-004 — Historical point-in-time replay

Goal: replay the frozen strategy candle-by-candle as if history were unfolding live.

Rules:
- no future candle visibility;
- no post-event label visible to Strategy;
- accepted fee/slippage and risk semantics remain explicit;
- candidate/config used by a run is frozen before that run;
- deterministic replay must be byte-identical;
- historical replay never upgrades active P10 evidence.

Required outputs:
Net PnL after costs, drawdown, exposure, fills/trades, regime path, Kill Switch
events, time-to-protection, time-to-zero-exposure, false re-entry, recovery time and
canonical run identity.

Exit gate: deterministic replay works across the first accepted crisis dataset set.
