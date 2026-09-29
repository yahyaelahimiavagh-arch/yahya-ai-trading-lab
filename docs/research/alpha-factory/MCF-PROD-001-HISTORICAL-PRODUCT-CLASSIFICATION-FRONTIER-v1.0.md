# MCF-PROD-001 — Historical Product Classification Frontier v1.0

Status: **PRE-PERFORMANCE / CLASSIFICATION FRONTIER CONTRACT**

Date: 2026-09-29

Starting main:

`8faaa84038aa1614a0964b35788390f949d18626`

This work unit follows the accepted production-binding preflight in PR #162.
It fixes the remaining gap between "all historically data-eligible symbols"
and the smaller set whose product type can actually change a frozen monthly
top-50 membership.

## 1. Objective

Resolve only the historical product classifications necessary to make every
MCF-PROD-001 monthly membership snapshot deterministic.

The contract explicitly does **not** require classification of a lower-ranked
symbol once fifty higher-ranked symbols are independently confirmed ordinary
Spot for that month.

This is a data-governance closure step. It reads no strategy outcome.

## 2. Frozen universe rule

The existing universe policy remains unchanged:

- Binance Spot / USDT;
- UTC month-start reconstitution;
- lagged trailing-30d quote volume;
- maximum 50 members;
- if fewer than 50 eligible, use all eligible;
- minimum 60 admitted history days;
- >=99.5% trailing 30-day 15m continuity;
- ordinary Spot only;
- known nonordinary/leveraged products excluded;
- unresolved product classification cannot silently enter or be silently
  discarded.

## 3. Exact frontier semantics

For each month:

1. rank every data-eligible symbol by the frozen lagged-liquidity ordering;
2. skip a row already confirmed `NONORDINARY_CONFIRMED`;
3. ordinary and unresolved rows are both still capable of occupying a slot;
4. inspect the first 50 such potentially ordinary rows;
5. every unresolved row inside that prefix is the **current classification
   frontier** for the month.

The next acquisition wave is the union of those monthly frontier symbols.

After the wave is classified, rerun the preflight.

If a frontier symbol resolves as nonordinary, the next lower-ranked unresolved
symbol may enter the following wave. This expansion is deterministic and uses
no performance information.

Membership is resolved when every monthly frontier is empty.

Full classification of every data-eligible historical symbol is not required
once unresolved symbols are provably below the resolved membership boundary.

## 4. Empty / sparse months

The accepted AF-01C population preserves source gaps and timestamp anomalies.
Some monthly boundaries therefore have zero data-eligible symbols.

The frozen universe policy says:

`if_fewer_than_maximum = USE_ALL_ELIGIBLE`

Therefore a zero-eligible month freezes an empty membership snapshot. It is not
an integrity error and must not be filled, interpolated or repaired.

The no-op month remains explicit negative opportunity evidence for later
Development accounting.

## 5. Historical product evidence

Current `exchangeInfo` is not historical product-classification evidence.

A valid per-symbol record continues to use:

- schema: `MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0`;
- source type: `INDEPENDENT_HISTORICAL_PRODUCT_RECORD`;
- reviewed: `true`;
- classification:
  - `ORDINARY_SPOT_CONFIRMED`, or
  - `NONORDINARY_CONFIRMED`;
- nonempty historical source reference;
- content-addressed filename.

### Acceptable source hierarchy

Prefer the strongest contemporaneous historical record available:

1. explicit Binance historical announcement identifying the product and trading
   pair type;
2. archived Binance support/listing/delisting announcement with historical
   publication timestamp;
3. independently archived historical market/product record that unambiguously
   identifies the pair and product type.

Examples of strong nonordinary evidence exist in Binance historical support
announcements that explicitly call UP/DOWN products "Binance Leveraged Tokens"
and state that they represent baskets of perpetual positions.

Examples include historical announcements for:

- ADAUP / ADADOWN / LINKUP / LINKDOWN;
- ETHUP / ETHDOWN;
- EOSUP / EOSDOWN / TRXUP / TRXDOWN / XRPUP / XRPDOWN / DOTUP / DOTDOWN;
- BCHUP / BCHDOWN;
- UNIUP / UNIDOWN;
- LTCUP / LTCDOWN;
- SXPUP / SXPDOWN.

An `UP` or `DOWN` suffix by itself remains insufficient evidence. Absence
from a leveraged-token list is also insufficient proof of ordinary Spot.

For ordinary products, the evidence must positively establish the historical
Spot product/pair; it cannot rely on present-day status.

## 6. Acquisition wave discipline

Each wave must:

- use only symbols emitted by
  `next_classification_frontier_symbols`;
- preserve source URL/identity and historical publication timestamp where
  available;
- preserve raw retrieval content or a reproducible immutable source identity;
- emit one canonical reviewed evidence record per resolved symbol;
- rebuild one canonical classification map;
- rerun the production-binding preflight;
- stop if `membership_resolved=true`.

Do not bulk-classify all unresolved symbols "for completeness".

## 7. Binding output semantics

The preflight now distinguishes:

- `classification_complete`: every data-eligible symbol is classified;
- `membership_resolved`: unresolved symbols can no longer change any monthly
  membership;
- `next_classification_frontier_symbols`: exact next acquisition wave.

Production binding becomes ready when:

`membership_resolved=true`

It does not require:

`classification_complete=true`

provided all remaining unresolved symbols are below the deterministic monthly
membership boundary.

## 8. Safety

This work unit must not read:

- candidate returns;
- PnL;
- Sharpe;
- drawdown;
- Fresh OOS;
- recent reserve;
- P10.

Hard state:

- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- NO FUTURES
- NO LEVERAGE
- NO SHORT
- NO LIVE EXECUTION
- NO ORDER ENDPOINT
- NO AI DIRECT EXECUTION
- P10 untouched
- P11 locked

## 9. Acceptance gates

Implementation acceptance requires:

1. deterministic frontier tests;
2. known nonordinary rows do not consume a top-50 ordinary slot;
3. lower-ranked unresolved rows enter the next wave when a higher-ranked row is
   confirmed nonordinary;
4. unresolved rows below fifty confirmed ordinary symbols do not block;
5. fewer-than-50 months remain blocked until every potentially entering symbol
   is resolved;
6. zero-data-eligible months freeze as empty membership, not an error;
7. no performance/OOS/P10 read;
8. green CI;
9. real VPS rerun against the accepted AF-01C P-C corpus.

## 10. Next gate

After this implementation is accepted, historical source acquisition for the
first corrected frontier is a **WORK_REQUIRED** bulk evidence task.

That acquisition does not authorize strategy performance.

Only after a rerun returns:

`READY_FOR_PRODUCTION_BINDING`

may the project freeze exact monthly membership snapshots and proceed to
selected-union 15m/1h/4h materialization.
