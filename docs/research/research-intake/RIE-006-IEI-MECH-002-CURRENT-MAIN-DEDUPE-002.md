# RIE-006 — IEI-MECH-002 Current-Main Dedupe + Prereg Readiness 002

Status: **BLOCKER CLOSED / DISTINCT FROM FROZEN MCF-PROD-001 RULES / AF-04A PREREGISTRATION READY / NO PERFORMANCE READ**

Date: 2026-10-06

Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

## Authoritative refs

- current `main`: `58b6c74a834d51f0d68e06fbe5f1885057e9df9a`
- Research branch starting HEAD: `ae720f17b56727b5728892a1848f1c2566387d5a`
- PR #152: OPEN / DRAFT / UNMERGED
- MCF-PROD-001 monthly membership freeze is present on current main after merged PR #168.
- accepted preflight state recorded by the freeze: `READY_FOR_PRODUCTION_BINDING`, `membership_resolved=true`, 34 monthly memberships.

No merge, rebase, force-push or history rewrite is performed.

## Boundary

PAPER / RESEARCH ONLY. No candidate returns, PnL, Sharpe, drawdown, outcome ranking or other performance evidence read. Fresh OOS and recent reserve remain sealed. P10 is not read or written. P11 remains locked. `LIVE_MASTER_LOCK=OFF`. No Futures execution, leverage, short, Live/order endpoint or AI execution authority.

## 1. Blocker resolution

The prior bounded readiness unit required waiting until current-main MCF-PROD-001 froze and accepted exact historical ordinary-Spot monthly membership.

Current main now contains `MCF-PROD-001-MONTHLY-MEMBERSHIP-FREEZE-v1.0.md`, which records an accepted production-binding preflight with `membership_resolved=true` and 34 monthly memberships. It explicitly preserves empty months rather than filling, carrying forward or repairing them after outcome observation.

Therefore the specific MECH-002 PIT-membership blocker is closed.

## 2. Exact economic fingerprint

MECH-002 remains:

`PIT-eligible Spot cross-section | completed historical same-weekday observations only | cross-sectional weekday ranking | long/cash allocation | lagged admitted price + frozen monthly membership`.

It is not a generic weekday dummy and not a per-symbol calendar clone.

## 3. Dedupe against frozen MCF-PROD-001

The frozen production family-domain plan contains 12 families:

`TREND_CROSSOVER`, `BREAKOUT_CHANNEL`, `SHORT_HORIZON_MEAN_REVERSION`, `CRASH_REBOUND`, `VOLUME_CONFIRMED_DIRECTION`, `SESSION_TIME_EFFECT`, `LIQUIDITY_CONDITIONED_ENTRY`, `LEAD_LAG`, `PRICE_VOLUME_INTERACTION`, `SIMPLE_STATISTICAL_DEVIATION`, `TRADE_COUNT_CONFIRMED_DIRECTION`, and `RANGE_COMPRESSION_BREAKOUT`.

No frozen rule implements cross-sectional ranking of same-weekday historical observations.

Closest semantic neighbors are:
- `SESSION_TIME_EFFECT`: intraday UTC session gating plus lagged directional return, not weekday cross-sectional ranking;
- `LEAD_LAG`: BTC/ETH peer-return response, not same-weekday cross-sectional ranking;
- `LIQUIDITY_CONDITIONED_ENTRY`: liquidity eligibility plus own lagged directional return, not weekday cross-sectional ranking.

Therefore:

`IEI-MECH-002 = DISTINCT_FROM_FROZEN_MCF_PRODUCTION_RULES`.

This does not create a new Alpha Factory family. Taxonomically it remains covered by existing TIME/RELATIVE mechanism space. No mechanism-count inflation is allowed.

## 4. Preregistration readiness

The membership prerequisite is now accepted and the frozen production plan does not contain an exact duplicate. Required price history is ordinary completed-bar market data; exact daily aggregation, observation window, minimum-history rule, ranking/tie rule, decision clock, long/cash allocation, eligibility timing, source-gap handling and cost/opportunity accounting must be frozen before any outcome is read.

Disposition:

`IEI-MECH-002 = AF-04A_PREREGISTRATION_READY / PERFORMANCE_NOT_AUTHORIZED`.

## 5. Mandatory preregistration contents

AF-04A must freeze, before outcome access:

1. UTC daily aggregation and decision eligibility clock;
2. same-weekday historical lookback window;
3. minimum completed same-weekday observations;
4. PIT monthly-membership timing and no-survivorship rule;
5. cross-sectional score/ranking formula;
6. deterministic ties and missing-data behavior;
7. long/cash selection rule with no shorting;
8. turnover/cost convention;
9. source-gap and empty-month behavior;
10. opportunity-starvation accounting, including eligible-opportunity count and explicit zero-opportunity periods;
11. comparators sufficient to distinguish calendar rank from simpler momentum/time explanations;
12. one-shot falsification and no-retune rule;
13. dedupe fingerprint and taxonomy mapping.

No parameter may be selected from candidate outcomes.

## 6. Negative evidence preserved

- COT PIT provenance remains failed/blocked and is not reopened.
- MECH-021 PIT label/snapshot blocker remains unresolved.
- empty PIT membership months remain valid negative/opportunity-starvation evidence.
- unresolved/source-gap states are not imputed into eligibility.
- no broad institutional-edge sweep is restarted.

## 7. Next allowed action

Proceed only to bounded `AF-04A — IEI-MECH-002 EXACT PREREGISTRATION`.

Expected route: `CHAT_DIRECTOR`.

AF-04B implementation would be a separate `WORK_REQUIRED` unit and must trigger the exact mandatory Work warning before execution.

No performance run is authorized by this closeout.

**MERGED=NO**
