# MCF-PROD-001 — Pre-Run Domain Audit v1.0

Status: **PASS / NO PERFORMANCE READ**
Date: 2026-09-27

Purpose: verify the frozen search-space arithmetic, family concentration and
lineage before any MCF-PROD-001 market-performance output exists.

## Frozen counts

| Family | Raw upper bound | Expected valid after declarative constraints |
|---|---:|---:|
| TREND_CROSSOVER | 128 | 116 |
| BREAKOUT_CHANNEL | 640 | 416 |
| SHORT_HORIZON_MEAN_REVERSION | 1280 | 1240 |
| CRASH_REBOUND | 1536 | 1536 |
| VOLUME_CONFIRMED_DIRECTION | 1200 | 1200 |
| SESSION_TIME_EFFECT | 720 | 600 |
| LIQUIDITY_CONDITIONED_ENTRY | 240 | 240 |
| LEAD_LAG | 288 | 288 |
| PRICE_VOLUME_INTERACTION | 1200 | 1200 |
| SIMPLE_STATISTICAL_DEVIATION | 384 | 352 |
| TRADE_COUNT_CONFIRMED_DIRECTION | 1200 | 1200 |
| RANGE_COMPRESSION_BREAKOUT | 360 | 252 |
| **TOTAL** | **9176** | **8640** |

Structural filtering removes 536 combinations before economic evaluation.

## Concentration

Expected valid candidate count:
`8640`

Largest single family:
`CRASH_REBOUND = 1536 / 8640 = 17.777...%`

This is below the frozen 20% single-family cap.

TREND_CROSSOVER + BREAKOUT_CHANNEL:
`532 / 8640 = 6.157...%`

This is below the frozen 25% combined trend/breakout cap.

Twelve mechanism families are represented, above the minimum-eight requirement.

## Lineage / salvage audit

MCF-PROD-001 deliberately excludes:
- `SIZING_OVERLAY`
- `EXIT_OVERLAY`

from the first broad generation because those categories are too close to prior
Generation overlay outcomes and could create ambiguous same-evidence salvage
lineage on the known Development calendar.

They may return only through explicit new-candidate lineage and a separately
registered evidence policy.

The first broad generation instead includes:
- trade-count-confirmed direction;
- range-compression breakout;

which are independent pre-outcome mechanism definitions using admitted market
fields.

## Deferred family

`RELATIVE_STRENGTH` is not part of MCF-PROD-001 v1 because the frozen
MCF-03 tested object is `PER_SYMBOL_RULE_ACROSS_DYNAMIC_UNIVERSE`.

Cross-sectional portfolio/ranking candidates require a separately versioned
tested-object contract and are not silently approximated.

## Pre-performance implementation rule

If an MCF-03 typed operator required by a frozen family cannot be implemented
faithfully, that family is marked `BLOCKED_IMPLEMENTATION` before any
performance result is read.

The Work implementation may not:
- replace it with a different signal;
- alter its parameter domain;
- add nearby parameters;
- transfer its trial budget to a family that already produced a favorable
  result.

If a family is blocked, exact generated candidate count is recomputed and
frozen before the canonical Development run.

## Evidence boundary

This audit used:
- frozen JSON domain definitions;
- declarative structural constraints;
- arithmetic only.

It did not read:
- candle returns;
- strategy PnL;
- Sharpe;
- drawdown;
- candidate screening results;
- Fresh OOS;
- recent reserve;
- P10.

Result:
`PRE_RUN_DOMAIN_AUDIT_PASS`
