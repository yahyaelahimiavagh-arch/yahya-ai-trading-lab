# MCF-PROD-001 — Historical Product Classification Wave 002

Status: **INPUT FROZEN / SOURCE ACQUISITION NOT STARTED**

Date: 2026-09-30

## 1. Purpose

Freeze the exact second historical product-classification acquisition wave
emitted by the real-VPS production-binding preflight after Wave 001
materialization.

This checkpoint does not read strategy performance.

Wave 001 acquisition Final HEAD:

`03881059571b9bb9f1c4e1421ed6c068cffd65eb`

Source preflight artifact SHA-256:

`c8c38375ecffaa03bb30262ae14ca9b431e242b622d693214ed1a938330fad2a`

Source preflight state:

- `CLASSIFICATION_INCOMPLETE`;
- `membership_resolved=false`;
- `classification_complete=false`;
- unresolved data-eligible symbols: 208;
- next classification frontier symbol count: 2;
- performance read: false.

## 2. Frozen input

Manifest:

`MCF-PROD-001-CLASSIFICATION-WAVE-002.json`

Expected manifest SHA-256:

`0c13bc82422b2fb667c11450bc0ce456ca85b0a1a064e781d2dd9c33a6ef3fb4`

Exact frontier, lexicographically sorted:

1. `BTSUSDT`
2. `OCEANUSDT`

No symbol may be added, removed or reordered during Wave 002 acquisition.

## 3. Evidence contract

Each resolved symbol must use the already accepted historical classification
contract:

- schema `MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0`;
- exact symbol;
- classification `ORDINARY_SPOT_CONFIRMED` or
  `NONORDINARY_CONFIRMED`;
- `reviewed=true`;
- `source_type=INDEPENDENT_HISTORICAL_PRODUCT_RECORD`;
- nonempty historical source reference;
- content-addressed evidence identity.

Current `exchangeInfo`, current listing status, ticker suffix inference, price
behavior and strategy outcomes remain prohibited as historical product
classification evidence.

## 4. Closeout rule

After Wave 002 acquisition:

1. extend the canonical classification map without mutating accepted Wave 001
   evidence;
2. rerun production-binding preflight against the same accepted AF-01C P-C
   corpus;
3. inspect `next_classification_frontier_symbols`;
4. if nonempty, freeze the next deterministic wave;
5. if empty and `membership_resolved=true`, proceed to exact monthly
   point-in-time membership freeze.

Classification of all 208 unresolved data-eligible symbols is not required if
the remaining symbols cannot alter monthly membership.

## 5. Safety boundary

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
