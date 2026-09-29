# MCF-PROD-001 — Historical Product Classification Wave 001

Status: **INPUT FROZEN / SOURCE ACQUISITION NOT STARTED / WORK_REQUIRED**

Date: 2026-09-29

Starting main:

`6420b34f32db6a0773b16962edb4269409e9c3b9`

## 1. Purpose

Freeze the exact first historical product-classification acquisition wave
derived from the accepted real-VPS production-binding preflight.

This checkpoint does not classify products and does not read strategy
performance.

Source preflight:

`eff8f60b4a92be2a2e3266de86f9ad5a7c0bb9aaa8f25dc1a4a35805f058aa34`

Frozen wave manifest:

`MCF-PROD-001-CLASSIFICATION-WAVE-001.json`

Expected manifest SHA-256:

`1a2a2b35efbec3a1cd96174e190d5dce0352e2a43d6da7a975928062c5aaad58`

Frontier:

- 176 symbols;
- unique;
- lexicographically sorted;
- no symbol may be added, removed or reordered during acquisition.

## 2. Why 176

The accepted frontier-closure implementation treats confirmed nonordinary
products as non-members when determining the first 50 potentially ordinary
symbols for each month.

The corrected real-VPS rerun therefore expanded the prior raw-top-50 union from
174 to 176 symbols. This is expected: a confirmed nonordinary row does not
consume an ordinary-Spot membership slot, so a lower-ranked symbol can become
classification-relevant.

No performance information contributed to this expansion.

## 3. Required evidence record

Every resolved symbol must eventually produce one canonical content-addressed
record accepted by the existing production-binding validator:

- schema: `MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0`;
- exact symbol;
- classification:
  - `ORDINARY_SPOT_CONFIRMED`, or
  - `NONORDINARY_CONFIRMED`;
- reviewed: `true`;
- source_type: `INDEPENDENT_HISTORICAL_PRODUCT_RECORD`;
- nonempty source_reference;
- content-addressed filename.

Current `exchangeInfo` is prohibited as historical evidence.

## 4. Source admissibility hierarchy

Use the strongest historical evidence available.

### Tier A — preferred

Contemporaneous first-party Binance publication that explicitly identifies:

- the trading pair;
- trading venue/product;
- historical listing/trading time where relevant;
- leveraged-token status when nonordinary.

Historical Binance listing announcements that say Binance will "open trading"
for a named `TOKEN/USDT` pair are strong ordinary-Spot product evidence unless
the same publication explicitly identifies a different product class.

Historical Binance Leveraged Token announcements are strong nonordinary
evidence because they explicitly identify the product as a Binance Leveraged
Token and describe the leveraged exposure.

Verified examples before acquisition planning:

- ADAUP / ADADOWN / LINKUP / LINKDOWN:
  `https://www.binance.com/en/support/announcement/detail/73a5d3352ae944fe8e899d2602bee27c`
- EOSUP / EOSDOWN / TRXUP / TRXDOWN / XRPUP / XRPDOWN / DOTUP / DOTDOWN:
  `https://www.binance.com/en/support/announcement/detail/ae11a54c49aa4bc2aa465531859d6c69`
- BNBUP / BNBDOWN / XTZUP / XTZDOWN:
  `https://www.binance.com/en/support/announcement/detail/b46a1de6f7a8493eb35cfdde55af6ad4`
- COTI ordinary historical listing example:
  `https://www.binance.com/en/support/announcement/detail/360039754952`
- SRM ordinary historical listing example:
  `https://www.binance.com/en/support/announcement/detail/0ddf896b01a943819e8a5f04a2070fd9`

### Tier B — acceptable with review

Archived first-party Binance support/listing/delisting publication with a
preserved historical publication timestamp and unambiguous product identity.

### Tier C — fallback

Independent historical market/product archive with an immutable/versioned
record that positively identifies the historical pair and product type.

Tier C cannot override contradictory first-party evidence.

## 5. Prohibited inference

Do not classify from:

- current `exchangeInfo`;
- current exchange listing status;
- ticker suffix alone;
- token name alone;
- absence from a leveraged-token list;
- current CoinMarketCap/CoinGecko category alone;
- retrospective provider labels without historical provenance;
- price behavior;
- strategy outcomes.

An `UP` or `DOWN` suffix is a search clue, not proof.

## 6. Acquisition output

The WORK_REQUIRED acquisition must produce:

1. raw/source provenance ledger for every attempted frontier symbol;
2. accepted evidence files for resolved symbols;
3. unresolved ledger entries with explicit blocker reason;
4. one canonical classification map containing all accepted evidence collected
   through the wave;
5. source counts by tier and classification;
6. duplicate-source and conflict diagnostics;
7. no silent substitution for unresolved symbols.

A symbol can remain unresolved.

## 7. Wave closeout

After acquisition:

1. rerun the accepted production-binding preflight with the classification map;
2. inspect `next_classification_frontier_symbols`;
3. if nonempty, freeze a new deterministic wave;
4. if empty, `membership_resolved=true` and exact monthly membership may be
   frozen.

The project does not need to classify all 384 data-eligible unresolved symbols
if the remaining unresolved symbols cannot alter any monthly membership.

## 8. Safety boundary

- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- no Futures
- no leverage
- no short
- no Live execution
- no order endpoint
- no AI direct execution
- no performance read
- Fresh OOS sealed
- recent reserve sealed
- P10 untouched
- P11 locked

## 9. Execution-mode gate

The next step requires bulk source discovery, retrieval, provenance
normalization, classification review, canonical evidence generation and
reconciliation across 176 historical symbols.

Therefore:

`⚠️ WORK_REQUIRED — MCF-PROD-001-CLASSIFICATION-WAVE-001-ACQUISITION`

This document and manifest freeze the input only. Bulk acquisition must not be
performed as an implicit continuation of the design step.
