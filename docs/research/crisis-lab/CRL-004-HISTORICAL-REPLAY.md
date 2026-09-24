# CRL-004 — Historical point-in-time replay

Status: **ACTIVE — v0.1.0 CORE REPLAY IMPLEMENTED / CI + REAL CRL-E003 RUN PENDING**

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

## v0.1.0 core replay contract

Research-only implementation: `research/crisis_lab/replay.py`.

The first implementation reuses accepted YATL components rather than defining a
second historical strategy:

- frozen P10 candidate: `P10_BASELINE_TREND_PULLBACK_V1`;
- strategy: `TREND_PULLBACK/1.0.0`;
- primary/context/regime: `1h / 15m / 4h`;
- regime warm-up: **51 closed 4h candles**;
- quantity: accepted P3/P10 fixed research quantity `0.001`;
- execution: accepted P2 `NEXT_PRIMARY_OPEN` Paper fill engine;
- costs: `10 bps` fee + `5 bps` adverse slippage;
- risk: accepted P10 P4-equivalent entry-veto envelope and latch-only tracker;
- initial equity: `10000` quote units independently per symbol.

The loader starts only from a content-addressed CRL-003 event-quality manifest.
It re-verifies the event-quality, dataset-quality, acquisition and canonical CSV
SHA-256 chain before a candle can reach Strategy. v0.1.0 is Development-only:
`BLIND_HOLDOUT` input fails before outcome replay.

Each decision is constructed by the accepted `BacktestClock` and
`MarketSnapshot`. Every candle visible to Strategy must have
`close_time_ms < decision_time_ms`. The event label/window is not supplied to
`StrategyContext`.

Core v0.1.0 output records:
- every decision context digest, regime, strategy action/reason and effective intent;
- entry safety veto evidence;
- Paper fills and explicit costs;
- sampled portfolio state and final portfolio;
- Net PnL / return after costs;
- realized and liquidation-unrealized PnL;
- fee/slippage totals;
- completed-trade/open-position counts;
- sampled liquidation drawdown;
- Kill Switch state and first latch time;
- byte-deterministic symbol and event identities.

Crisis-relative derived measures such as time-to-protection, time-to-zero-exposure,
false re-entry classification and recovery time must receive explicit frozen
definitions before they are used for cross-event scoring. They must not be
post-hoc defined after inspecting CRL-E003 outcomes. The core replay may run
before those derived-score definitions are added; the overall CRL-004 exit gate
remains open until the required derived measures are frozen and emitted.

## First real target

- Development event `CRL-E003` only;
- BTCUSDT/ETHUSDT × 15m/1h/4h admitted corpus;
- quality manifest SHA-256
  `9db76653f252ac16e44fdd701f606bcd1e177609cb4e342e4564dc8d9bd77451`;
- output remains under `data/research/crisis-lab/replay/`;
- `/var/lib/yatl/p10/` remains a forbidden read/write target;
- real CRL-E003 run occurs only after matching Final-HEAD CI acceptance.

CLI:

```bash
uv run --locked python -m research.crisis_lab.replay \
  --runtime-root data/research/crisis-lab \
  --quality-manifest <event-quality-relative-path> \
  --quality-manifest-sha256 <full-sha256>
```

Exit gate: deterministic replay plus the frozen derived crisis measures work
across the first accepted crisis dataset set.
