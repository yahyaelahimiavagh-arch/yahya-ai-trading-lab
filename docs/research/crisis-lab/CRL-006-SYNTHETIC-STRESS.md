# CRL-006 — Synthetic adversarial stress matrix\n\nStatus: **OPEN-POSITION SHOCK MATRIX PREREGISTERED / 006A RUNTIME IMPLEMENTED — VALIDATION PENDING**

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


## Registered open-position matrix

Canonical registry:
`SYNTHETIC-SHOCK-REGISTRY-v0.1.0.json`.

Before any synthetic outcome is inspected, the first open-position matrix is
frozen to the exact Cartesian product:

- adverse gap: 5%, 10%, 20%;
- slippage sensitivity: 1x, 2x, 5x frozen candidate slippage;
- frozen candidate fee remains unchanged;
- total: 9 scenarios per selected CRL-005 source episode.

### CRL-006A — Immediate open-position shock

006A isolates the immediate mechanics of the shock.

The source position must already be open after the entry candle has been fully
processed. The last-known point-in-time anchor is that entry candle's close.
The real next candle is **not** read to construct the synthetic gap.

At the next primary decision:
- the Strategy snapshot contains only source-corpus data through the processed
  entry candle;
- the active setup remains the exact source setup;
- the Strategy does not receive scenario identity or shock magnitude;
- synthetic open = entry-candle close × (1 - registered gap);
- the synthetic stress bar is flat at that open
  (open=high=low=close) to isolate the gap effect;
- only slippage is multiplied by the registered 1x/2x/5x sensitivity;
- outputs include immediate exit/protection response, equity excursion,
  remaining exposure, costs and immediate time-to-zero exposure where applicable.

Kill-switch observation, false re-entry and recovery are intentionally **not**
fabricated from a single synthetic bar.

### CRL-006B — Post-shock continuation

006B continues from the exact 006A identity and source episode. It owns:
- next-observation risk state;
- Kill Switch behavior;
- time-to-zero exposure when not immediate;
- false re-entry;
- whipsaw/repeated-shock continuation;
- recovery.

006B cannot reselect a more favorable source entry after 006A outcomes are
known.


## CRL-006A runtime

Research-only implementation:
`research/crisis_lab/synthetic_shock.py`.

006A consumes an immutable CRL-005 strategy-active diagnostic artifact and the
registered nine-scenario matrix. For every selected source episode it runs each
scenario twice and requires byte-identical equality.

Pre-shock equity is valued using the frozen candidate's baseline fee/slippage.
The registered 1x/2x/5x slippage multiplier applies only to the synthetic
shock-side valuation/exit, so scenario sensitivity cannot move the pre-shock
starting point.

A direct synthetic exit must also satisfy the Paper base-volume limit. No real
next candle is used to construct the gap, and Strategy receives only source
history through the fully processed entry candle.

Kill-switch, delayed zero-exposure, false re-entry and recovery remain deferred
to CRL-006B.
