# MCF-03 — Production Universe Integration & Development Runner Contract v1.0

Status: **FROZEN BEFORE IMPLEMENTATION**
Date: 2026-09-27
Safety: PAPER / RESEARCH ONLY | P10 UNTOUCHED | P11 LOCKED

## 1. Goal

Turn the accepted MCF-02 engineering engine into a production-capable
Development runner that can evaluate frozen rule candidates across the AF-01B
point-in-time dynamic universe without opening Fresh OOS.

MCF-03 does not authorize Fresh OOS or Forward.

## 2. Versioning

Do not loosen MCF-02 v1 validators in place.

Introduce explicit production versions for:
- manifest schema;
- universe binding;
- feature cache;
- Development runner;
- result ledger.

Existing MCF-02 engineering fixtures must remain valid and immutable.

## 3. Candidate tested object

MCF-PROD-001 v1 uses:
`PER_SYMBOL_RULE_ACROSS_DYNAMIC_UNIVERSE`

One candidate means:
- one frozen signal/entry/exit/sizing rule;
- same rule logic across all point-in-time eligible symbols;
- independent per-symbol simulation;
- no symbol-specific parameter tuning;
- no portfolio-weight optimization.

Cross-sectional portfolio strategies are deferred to a separately versioned
tested-object type.

## 4. Universe binding

Every candidate evaluation binds:
- `MCF-PROD-001-UNIVERSE-EVIDENCE`;
- monthly membership snapshots;
- symbol eligibility SHA per reconstitution;
- population manifest SHA;
- quality/index SHA;
- Development partition.

A candidate never chooses its own symbol set.

## 5. Development clock

Scored period:
`2020-03-01T00:00:00Z` inclusive through
`2023-01-01T00:00:00Z` exclusive.

Bars prior to scored start are warmup only.

No result may consume a bar at or after Development end.

## 6. Execution semantics

Long/cash only.

Decision:
completed bar t.

Fill:
next eligible bar open.

No same-bar fill.

If a required bar is absent:
- no interpolation;
- no synthetic fill;
- state behavior follows the candidate/family gap policy frozen before outcome.

## 7. Comparable per-symbol accounting

To avoid asset-price-scale bias:

Virtual per-symbol account:
- initial equity: 10,000 USDT;
- target entry notional: 1,000 USDT;
- quantity determined from next-open reference and target notional;
- no leverage;
- no borrowing;
- if available cash cannot fund entry under costs, entry fails closed and is
  recorded.

This accounting is research normalization, not position-size authority for P10
or Live.

## 8. Cost policy

`MCF-SPOT-COST-v1`

Base, per side:
- fee: 10 bps
- adverse slippage: 5 bps

Stress, per side:
- fee: 20 bps
- adverse slippage: 10 bps

No candidate-specific cost override in MCF-PROD-001.

## 9. F1 opportunity gates

A candidate cannot qualify by rarely trading.

Across the dynamic universe scored period:
- at least 15 evaluable symbols;
- at least 250 completed trades total;
- at least 10 symbols with >=5 completed trades;
- eligible-bar exposure coverage reported;
- turnover reported.

These are minimum activity gates, not survivor quotas.

## 10. F2 after-cost economics

Required under exact accounting:
- aggregate base net return > 0;
- aggregate stress net return > 0;
- median per-symbol base net return > 0;
- median per-symbol stress net return > 0;
- at least 60% of evaluable symbols have stress net return > 0.

Aggregate return is equal-weight across evaluable per-symbol normalized account
returns. It is not capital-optimized portfolio PnL.

## 11. F3 temporal robustness

Frozen scored folds:

1. 2020-03-01 → 2020-09-01
2. 2020-09-01 → 2021-03-01
3. 2021-03-01 → 2021-09-01
4. 2021-09-01 → 2022-03-01
5. 2022-03-01 → 2022-09-01
6. 2022-09-01 → 2023-01-01

Candidate requirements:
- stress aggregate positive in at least 4/6 folds;
- base aggregate positive in at least 5/6 folds;
- no fold may be missing solely because a losing period was dropped;
- symbol entry/exit follows point-in-time membership within each fold.

Fold metrics are reset for reporting, while feature history may use earlier
Development/warmup bars point-in-time. Strategy state reset semantics must be
explicitly versioned and identical across candidates.

## 12. Result series required for MCF-04

For candidates passing F0-F3, emit content-addressed:
- daily normalized candidate return series;
- per-symbol normalized return series;
- position/exposure summary;
- trade count/turnover;
- fold metrics;
- parameter-neighbor identity;
- family identity.

Daily candidate return series is equal-weight over point-in-time evaluable
symbol subaccounts and is used only for Development statistical adjudication.

## 13. Family execution scope

MCF-PROD-001 should prioritize rule families executable from admitted
PRICE_OHLC/VOLUME/TRADE_COUNT/MULTI_ASSET data.

MULTI_VENUE and unavailable external dependencies remain blocked.

No family is approximated with substitute data.

## 14. Pre-outcome manifest gate

Before performance:
- every family manifest validated;
- exact candidate count known;
- exact candidate IDs/spec SHAs known;
- family concentration checked against search budget;
- parameter-neighbor graph constructed;
- evidence/universe/cost policy SHAs frozen;
- all candidate files generated without reading performance.

Only then may the Development runner execute.

## 15. Screening and exact recompute

Fast screening is permitted.

Any candidate that could pass F0-F3 must undergo exact accounting before its
F0-F3 pass is canonical.

Gray-zone rules remain fail-safe.

## 16. Outputs

Batch-level artifacts:
- generation manifest;
- membership/index binding;
- F0-F3 result ledger;
- exact recompute ledger;
- daily-return artifact index for F0-F3 passers;
- family failure summary;
- batch reconciliation.

No `DEVELOPMENT_SURVIVOR` state is assigned by MCF-03 alone.

Only MCF-04/05 may convert an F0-F3 passer into a frozen Development survivor.

## 17. Safety

Hard false:
- Fresh OOS read
- recent reserve read
- P10 read/write
- Live
- Futures
- leverage
- short
- order endpoint
- AI direct execution
