# CRL-004 — Historical point-in-time replay

Status: **ACTIVE — CRL-E003 PILOT OPEN / REPLAY IMPLEMENTATION PENDING**

Entry gate:
- CRL-003 deterministic validator accepted in CI and merged to `main`;
- real CRL-E003 quality manifest is PASS for all 6 required datasets;
- CRL-E003 has `replay_admitted=true`;
- no other event may enter replay until it independently receives CRL-003 admission.

Goal: replay the frozen strategy candle-by-candle as if history were unfolding live.

Rules:
- no future candle visibility;
- no post-event label visible to Strategy;
- accepted fee/slippage and risk semantics remain explicit;
- candidate/config used by a run is frozen before that run;
- deterministic replay must be byte-identical;
- historical replay never upgrades active P10 evidence;
- replay input must be addressed by accepted CRL-003 quality-manifest identity;
- Blind Holdout market outcomes remain sealed until their permitted final-evaluation stage.

Required outputs:
Net PnL after costs, drawdown, exposure, fills/trades, regime path, Kill Switch
events, time-to-protection, time-to-zero-exposure, false re-entry, recovery time and
canonical run identity.

First implementation target:
- Development event `CRL-E003` only;
- BTCUSDT/ETHUSDT × 15m/1h/4h admitted corpus;
- quality manifest SHA-256
  `9db76653f252ac16e44fdd701f606bcd1e177609cb4e342e4564dc8d9bd77451`;
- replay engine must consume candles strictly in timestamp order and expose no
  future row or post-event label to the strategy path;
- output must remain research-only and must not write to `/var/lib/yatl/p10/`.

Exit gate: deterministic replay works across the first accepted crisis dataset set.
