# AF-01C — Historical Archive Inventory & Bulk Adapter Implementation Contract v1.0

Status: **FROZEN BEFORE IMPLEMENTATION**
Date: 2026-09-27
Mode: CHAT_DIRECTOR for contract; WORK_REQUIRED for implementation
Safety: PAPER / RESEARCH ONLY | P10 UNTOUCHED | P11 LOCKED

## 1. Goal

Implement the reusable source adapter required by
`AF-01C-BULK-POPULATION-PLAN-v1.0.md`.

The Work implementation builds:
- historical archive inventory discovery/snapshot;
- generalized Binance Spot 15m archive planning;
- checksum-verified monthly/daily acquisition;
- AF-01B admission/lifecycle population bridge;
- restartable object ledger;
- bounded pilot validation.

It does NOT run the full historical population.

## 2. Source boundary

Allowed remote hosts:
- `data.binance.vision`
- the exact official storage/listing host only if required to enumerate the same
  public archive and explicitly validated/allowlisted.

No account API, credentials or private endpoint.

Current `exchangeInfo` may be used only as optional present-day metadata and
must never be the sole historical symbol inventory.

## 3. Inventory discovery

Implement deterministic historical archive inventory discovery.

Required:
- enumerate archive object keys under the registered Spot kline prefix;
- retain raw listing pages/objects in content-addressed evidence;
- support pagination/continuation deterministically;
- normalize/sort object keys;
- parse symbol/interval/date;
- freeze raw and normalized inventory SHA-256;
- record retrieval timestamp/source endpoint.

If historical object enumeration is unavailable or non-reproducible:
`HISTORICAL_SYMBOL_INVENTORY_UNPROVEN`

No fallback to current-running symbols.

## 4. Inventory filter for MCF-PROD-001

Pre-performance inventory filter:
- path is Spot kline archive;
- interval = 15m;
- symbol ends with USDT;
- object period overlaps 2020-01-01 through 2022-12-31.

Do not use returns/PnL/volatility to discover symbols.

## 5. Generalized archive planner

Do not mutate frozen CRL-002 BTC/ETH scope.

Create a new opportunity-data acquisition adapter which may reuse trusted CRL
helpers but supports inventory-discovered symbols.

Planner must:
- create immutable per-symbol monthly/daily object plans;
- know Development start/end;
- handle source timestamp units;
- reject objects outside registered range;
- bind every plan to inventory SHA.

## 6. Archive policy

Monthly preferred.

For each object:
1. download CHECKSUM;
2. download bounded ZIP;
3. verify SHA-256;
4. verify expected member;
5. normalize canonical rows;
6. validate OHLC/volume/trade count/timestamps;
7. admit through AF-01B;
8. write immutable content-addressed evidence.

If monthly fails for a recoverable source reason, daily fallback is permitted
only for that same period and must be recorded explicitly.

## 7. Recovery/fallback classifications

- MONTHLY_SUCCESS
- DAILY_FALLBACK_SUCCESS
- MISSING_ARCHIVE
- MISSING_CHECKSUM
- CHECKSUM_MISMATCH
- INVALID_ZIP
- INVALID_MEMBER
- INVALID_SCHEMA
- TIMESTAMP_ANOMALY
- SOURCE_GAP
- UNRECOVERABLE

Never interpolate missing candles.

## 8. Object ledger

Append-only/reconciled object ledger:

- inventory object key
- symbol
- period
- transport source
- expected checksum
- observed archive SHA
- canonical SHA
- admission state
- fallback state
- row count
- gap count
- artifact refs
- record SHA

Exactly one final state per planned object.

## 9. Symbol/lifecycle build

After object reconciliation for a pilot symbol:
- concatenate nonoverlapping canonical rows;
- reject conflicting duplicate bars;
- construct first/last admitted data;
- listing/delisting remain null unless separately evidenced;
- produce AF-01B lifecycle record;
- build gap map / quality manifest;
- build deterministic index entry.

No automatic symbol-history splicing.

## 10. Product classification

Adapter must expose:
- ORDINARY_SPOT_CONFIRMED
- NONORDINARY_CONFIRMED
- PRODUCT_CLASSIFICATION_UNRESOLVED

Do not infer official product class solely from current listing status.

A conservative explicit known leveraged-token rule/list may classify confirmed
historical products, but unresolved assets remain blocked from later production
eligibility rather than silently treated as ordinary Spot.

## 11. Bounded pilot only during Work

Allowed pilot:
- <=10 symbols;
- <=3 representative months per symbol where possible;
- may include a deliberately known missing/corrupt/checksum fixture;
- source/network validation only.

Pilot status:
`AF01C_ENGINEERING_PILOT_NO_SELECTION`

No full 2020-2022 universe download in Work.

## 12. Runtime / storage

Default runtime outside Git:
`data/research/opportunity-data` for local fixture/pilot.

Production VPS root later:
`/var/lib/yatl/research/opportunity-data`

P10 path protections mandatory.

## 13. CLI

Suggested commands:
- `inventory`
- `plan`
- `pilot-acquire`
- `reconcile`
- `build-lifecycle`
- `population-status`

No trading command.

## 14. Tests

Inventory:
- pagination deterministic;
- duplicate key rejection;
- malformed key rejection;
- no current-symbol fallback;
- same listing bytes -> same normalized inventory SHA.

Acquisition:
- checksum success/failure;
- ZIP/member validation;
- monthly -> daily fallback explicit;
- timestamp normalization;
- duplicate/conflicting rows;
- immutable cache/restart.

Admission:
- AF-01B binding;
- lifecycle null official times;
- gap preservation;
- deterministic index.

Safety:
- P10/Fresh OOS/recent reserve rejected;
- host allowlist;
- no credentials/account/private endpoints;
- no Futures/leverage/short/Live/order path.

## 15. CI

Final HEAD:
- focused AF-01C tests;
- AF-01B tests;
- CRL acquisition compatibility tests;
- MCF safety tests;
- unit-and-safety;
- accepted-public-data.

## 16. Work output

Create branch:
`af-01c-historical-archive-adapter`

PR:
`research: implement AF-01C historical archive population adapter`

DO NOT MERGE.

No bulk population or strategy performance run.

Allowed closeout:
- AF_01C_ADAPTER_ACCEPTED
- AF_01C_ADAPTER_BLOCKED_INVENTORY
- AF_01C_ADAPTER_IMPLEMENTATION_BLOCKED
- AF_01C_ADAPTER_CI_BLOCKED
