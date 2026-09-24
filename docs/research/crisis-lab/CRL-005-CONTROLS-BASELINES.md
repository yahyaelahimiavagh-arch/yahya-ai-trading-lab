# CRL-005 — Control windows and baselines

Status: **ORDINARY CONTROL REPLAY ACCEPTED / STRATEGY-ACTIVE DIAGNOSTIC IMPLEMENTED — FINAL-HEAD CI PENDING**

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

The baseline semantics are frozen in
`CONTROL-WINDOW-PROTOCOL-v0.1.0.json` before ordinary-market outcomes are
replayed. CASH never enters the market. BUY-AND-HOLD uses the same frozen YATL
research quantity, fee bps and adverse slippage bps; it buys at the first 1h open
inside the analysis window, liquidates at the last 1h close, and leaves all
unused quote balance as cash. This is a matched-size research comparator, not a
production strategy.

Additional baselines require separate preregistration.

## Ordinary control replay runtime

Research-only implementation:
`research/crisis_lab/controls.py`.

The runtime:
- accepts only the CRL-003-admitted continuous Development control corpus;
- verifies the full content-addressed quality/acquisition/canonical chain again;
- slices each registered control from its frozen warm-up start through its
  exclusive analysis end, so later corpus candles cannot enter the run;
- executes decisions only inside the registered 30-day analysis interval;
- reuses the frozen CRL-004 strategy, risk, Paper fill and cost semantics;
- emits YATL, CASH and matched-size BUY-AND-HOLD evidence side by side;
- writes immutable content-addressed per-window replay manifests;
- has no network, account, credential, order, AI execution or P10 write
  capability.

CLI:

```bash
uv run --locked python -m research.crisis_lab.controls \
  --runtime-root data/research/crisis-lab \
  --quality-manifest <control-event-quality-relative-path> \
  --quality-manifest-sha256 <full-sha256>
```

A subset may be replayed with repeated `--control CRL-C00X` arguments.

## Strategy-active diagnostic runtime

Research-only implementation:
`research/crisis_lab/active_diagnostic.py`.

The scanner evolves the same frozen Strategy, Risk tracker, Paper fill engine,
portfolio accounting and costs continuously across the registered Development
pool. It does **not** select entries from later performance.

An eligible source episode is now frozen as:
- a real `ENTER_LONG` signal;
- accepted by the frozen risk veto;
- actually filled by the Paper `NEXT_PRIMARY_OPEN` engine;
- still open after same-candle protective processing;
- outside every registered crisis interval plus the seven-day guard band.

Candidates from BTCUSDT and ETHUSDT are combined and ordered by
`decision_time_ms ASC`, then symbol lexical order. The first 10 episodes with
at least seven days between selected episodes are retained. Selection cannot use
future price path, later PnL, drawdown, maximum excursion, exit quality or
recovery.

Each retained episode stores the exact entry setup, pre-entry risk state,
pre/post-entry portfolio state, entry fill and the fully processed entry candle.
The close of that already-processed candle is the frozen last-known primary mark
for the later synthetic gap; the real next candle is not inspected to construct
the shock. These fields seed the separate CRL-006 synthetic open-position shock
matrix. Historical and synthetic outcomes
remain separate.

CLI:

```bash
uv run --locked python -m research.crisis_lab.active_diagnostic \
  --runtime-root data/research/crisis-lab \
  --quality-manifest <control-event-quality-relative-path> \
  --quality-manifest-sha256 <full-sha256>
```

Research question:
Did YATL survive/preserve/grow capital differently because of its architecture,
or would the same behavior appear in ordinary markets? And when exposure already
exists, does the transition into stress remain controlled?

Exit gate: canonical control-corpus quality PASS, deterministic ordinary-window
replay, strategy-active diagnostic evidence, continuous anchor-transition
evidence and deterministic CASH/BUY-AND-HOLD calculations.
