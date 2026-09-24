# CRL-005 — Control windows and baselines

Status: **SPEC EXPANDED — ORDINARY-MARKET CORPUS + STATE-TRANSITION PROTOCOL REGISTERED / IMPLEMENTATION PENDING**

Every crisis result must be interpreted against:
- pre-event window;
- event window;
- aftermath/recovery window;
- ordinary/unlabelled control windows;
- strategy-active ordinary diagnostics;
- NO-TRADE / CASH baseline;
- BUY-AND-HOLD research baseline.

Control windows are registered before replay outcomes are inspected. Crisis-only
cherry-picking is forbidden.

Canonical protocol:
`CONTROL-WINDOW-PROTOCOL-v0.1.0.json`.

Continuous Development corpus registration:
`CONTROL-DATA-ACQUISITION-REGISTER-v0.1.0.json`.

## Why ordinary market data is required

Crisis evidence alone cannot answer whether a behavior is special to stress or
simply the normal behavior of the frozen strategy. CRL-005 therefore adds a
continuous BTCUSDT/ETHUSDT Development corpus using the same 15m / 1h / 4h
semantics as Crisis Lab.

The registered Development pool spans:
- acquisition start: **2019-12-18 00:00 UTC**;
- unbiased analysis pool: **2020-01-01 00:00 UTC through 2023-01-01 00:00 UTC**;
- 14 days of warm-up before the analysis pool;
- BTCUSDT + ETHUSDT;
- 15m / 1h / 4h;
- the same Binance Public Data + REST verification + SHA-256 provenance chain as
  CRL-002/CRL-003.

The pool ends before the first registered Blind Holdout era. It is Development
evidence only and cannot upgrade P10 or open P11.

The corpus may contain known crisis periods. That is intentional: the raw corpus
is continuous, while the unbiased ordinary-window selector excludes every
registered crisis window plus a seven-day guard band.

## Unbiased ordinary controls

`ORDINARY_QUARTERLY_30D_V1` is frozen before control outcomes are inspected.

Rule:
- candidate months are January / April / July / October;
- anchor is the first Monday at 00:00 UTC;
- each analysis window is 30 days;
- each window receives 14 days of prior warm-up;
- reject any candidate whose warm-up-through-analysis interval overlaps a
  registered crisis pre-event/core/aftermath interval expanded by seven days;
- do not use price return, volatility, trade count, strategy action, PnL or
  drawdown to select or discard a window.

Eight windows are already registered in
`CONTROL-WINDOW-PROTOCOL-v0.1.0.json`. They must remain in the evidence set even
if YATL makes no trade or performs badly.

The word "ordinary" means **calendar-selected and outside registered crisis
buffers**. It does not mean low-volatility or safe; regime and volatility are
measured only after selection.

## Strategy-active ordinary diagnostics

A second cohort answers a different question: **what does YATL do in ordinary
markets when it actually opens a position?**

This cohort is diagnostic, not unbiased performance evidence.

Rule:
- scan the Development control pool chronologically;
- exclude all crisis guard bands;
- retain the first 10 permitted `ENTER_LONG` episodes separated by at least
  seven days;
- selection may use only the fact that an entry occurred;
- later PnL, drawdown, exit quality and future price path are forbidden selection
  inputs.

This lets us inspect normal entry/hold/exit behavior without pretending that an
entry-conditioned sample is an unbiased return sample.

## Historical ordinary → crisis transition

Every Development crisis replay must remain continuous across its registered
event anchor. The portfolio, active setup, strategy state and risk state are
**not reset at the crisis timestamp**.

Required transition evidence:
- `position_at_event_anchor`;
- quantity and equity at the anchor;
- whether a pre-event entry remained open into the crisis;
- first protection/risk response after the anchor;
- time to zero exposure;
- Kill Switch behavior;
- false re-entry count after the shock;
- recovery behavior.

If the frozen strategy happens to be flat at an historical anchor, that result is
kept. We do not manufacture a historical position.

CRL-006 owns a separate synthetic open-position shock test for cases where a
controlled "position already open, then sudden shock" experiment is required.

## Baselines

Every eligible comparison includes:
1. **NO-TRADE / CASH**;
2. **BUY-AND-HOLD research baseline**.

Additional baselines require separate preregistration.

Research question:
Did YATL survive/preserve/grow capital differently because of its architecture,
or would the same behavior appear in ordinary markets? And when exposure already
exists, does the transition into stress remain controlled?

Exit gate: canonical control-corpus quality PASS, deterministic ordinary-window
replay, strategy-active diagnostic evidence, continuous anchor-transition
evidence and deterministic CASH/BUY-AND-HOLD calculations.
