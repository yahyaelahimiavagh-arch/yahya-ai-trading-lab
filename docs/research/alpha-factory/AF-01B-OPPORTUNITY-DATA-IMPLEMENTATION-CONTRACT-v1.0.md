# YATL AF-01B — Opportunity Data Foundation Implementation Contract v1.0

Status: DESIGN FROZEN BEFORE IMPLEMENTATION
Established: 2026-09-27
Mode: CHAT_DIRECTOR for contract; WORK_REQUIRED for implementation
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

## 1. Purpose

AF-01B builds the reusable point-in-time data foundation required before any
true Mass Candidate Factory production selection batch.

This work must solve:
- survivorship-by-current-listing;
- explicit asset/venue identity;
- lifecycle metadata;
- gap-aware admitted market data;
- lagged liquidity/opportunity metadata;
- deterministic derived views;
- Development evidence isolation.

AF-01B is infrastructure/data admission. It is not a strategy-selection run.

## 2. Scope boundary

AF-01B implementation may:
- define and validate point-in-time universe/lifecycle records;
- generalize canonical Spot loaders/manifests;
- compute lagged liquidity metadata from admitted bars;
- expose deterministic research views;
- build bounded acquisition/import tooling;
- validate a bounded fixture/reference dataset.

AF-01B must NOT:
- run MCF production candidate selection;
- choose strategy winners;
- open Fresh OOS;
- inspect recent reserve;
- read/write P10 runtime evidence;
- enable Live/Futures/leverage/short/order execution.

## 3. Primary research venue

Initial primary discovery lane:

- Binance Spot public market data;
- USDT-quoted Spot instruments;
- research-only.

This is a data/research venue choice, not Live authorization.

Cross-venue context remains a separate future read-only lane.

## 4. Universe lifecycle record

Required per instrument:

- symbol;
- base_asset;
- quote_asset;
- venue;
- instrument_type;
- spot_allowed;
- leveraged_token_flag;
- first_admitted_data_ms;
- last_admitted_data_ms;
- listing_time_ms nullable;
- delisting_time_ms nullable;
- lifecycle_status;
- lifecycle_source_refs;
- record_sha256.

Important distinction:

`first_admitted_data_ms` is NOT automatically equal to official listing time.

If exact official listing/delisting timestamps are unavailable, store null and
preserve first/last admitted data separately. Never invent exact lifecycle
timestamps.

## 5. Product exclusions

The initial research universe must exclude:
- Futures;
- Margin-only instruments;
- leveraged-token products;
- synthetic/index products not ordinary Spot;
- instruments outside the registered quote lane.

Stablecoin-base assets are not silently excluded by infrastructure; whether a
production batch excludes them belongs in a frozen production universe policy.

## 6. Point-in-time eligibility API

Implement a deterministic API that answers:

"Was symbol X research-eligible at timestamp t under policy P?"

Eligibility must use only information available by t.

Infrastructure-level eligibility requires:
- symbol/instrument exists in admitted lifecycle records by t;
- ordinary Spot product;
- quote asset matches policy;
- required admitted data history exists;
- required data quality passes;
- no future listing/delisting/current-status information leaks backward.

Strategy-specific liquidity/history thresholds are policy inputs, not hardcoded
globally.

## 7. Universe policy separation

AF-01B must separate:

A. DATA_ADMITTED universe
from
B. PRODUCTION_RESEARCH_ELIGIBLE universe.

The foundation may know hundreds of historical instruments without declaring all
of them eligible for a given production batch.

Exact production thresholds such as:
- top-N liquidity;
- minimum trailing quote volume;
- minimum history;
- maximum gap rate

must live in a versioned frozen universe policy referenced by the later batch.

Do not choose those thresholds from strategy PnL.

## 8. Liquidity metadata

From completed admitted observations only, support lagged point-in-time metrics
such as:

- trailing quote volume;
- trailing base volume;
- trailing trade count;
- candle continuity / gap rate;
- active trading-day count;
- simple turnover/liquidity proxies.

Metric identity must bind:
- symbol;
- venue;
- interval;
- trailing window;
- ending timestamp;
- source dataset identity;
- metric-engine version.

No future bars may enter a historical liquidity metric.

## 9. Base data and derived views

Support deterministic research views for:
- 15m
- 1h
- 4h
- 1d

Implementation should avoid unnecessary duplicate storage.

A valid design may:
- admit interval-specific canonical datasets;
or
- derive higher intervals deterministically from a lower admitted interval.

Whichever route is used must freeze:
- UTC alignment;
- completed-bar semantics;
- aggregation rules;
- missing-bar behavior;
- volume/trade-count aggregation;
- OHLC construction.

No silent bar interpolation.

## 10. Gap-aware policy

Required:
- duplicate timestamps rejected;
- non-monotonic timestamps rejected;
- invalid OHLC rejected;
- negative volume/trade count rejected;
- explicit expected interval cadence;
- explicit gap map;
- explicit row count;
- explicit first/last timestamp;
- content digest;
- quality verdict.

A dataset with gaps may still be admitted if policy permits it, but the gaps
must remain visible to downstream candidate protocols.

No price forward-fill for performance.

## 11. Provenance

Every admitted dataset/manifold must bind:
- provider/source;
- venue;
- symbol;
- interval;
- requested/semantic date range;
- actual admitted date range;
- retrieval/import timestamp;
- source object references;
- row count;
- duplicate count;
- gap count;
- quality manifest;
- content SHA-256.

Bulk market data should remain outside Git.
Only bounded manifests/fixtures belong in the repository.

## 12. Existing CRL compatibility

Reuse existing accepted CRL acquisition/canonicalization primitives where safe.

Do not create conflicting definitions of:
- candle fields;
- timestamps;
- OHLC;
- quote/base volume;
- trade count;
- gap detection.

AF-01B should generalize existing trusted contracts rather than fork them
without reason.

## 13. Candidate data dependency API

Registry/MCF candidates must be able to query whether required dependencies are
admitted:

- PRICE_OHLC
- VOLUME
- TRADE_COUNT
- MULTI_ASSET
- MULTI_VENUE
- EXTERNAL_CONTEXT
- ORDER_BOOK
- ON_CHAIN
- NEWS_SENTIMENT
- MACRO_RELEASE

AF-01B v1 only needs to fully support:
- PRICE_OHLC
- VOLUME
- TRADE_COUNT
- MULTI_ASSET within the primary Spot lane.

Other dependencies remain explicitly unavailable/blocked until later adapters.

## 14. Development evidence isolation

AF-01B Development loaders must fail closed if requested path/manifest points to:
- Fresh OOS;
- recent reserve;
- P10 runtime state;
- unregistered evidence partition;
- unknown quality manifest.

Add explicit tests.

## 15. Storage layout

Use a deterministic runtime layout outside Git, for example:

data/research/opportunity-data/
  canonical/
  manifests/
  quality/
  lifecycle/
  liquidity/
  indexes/

Exact runtime root may be configurable.

Repository contains only:
- schema;
- code;
- bounded fixtures;
- bounded test manifests.

## 16. Universe index

Implement a compact deterministic index that can answer:
- symbols known at timestamp;
- admitted intervals per symbol;
- first/last admitted data;
- lifecycle metadata;
- quality status;
- lagged liquidity availability.

Index rebuild from canonical manifests must be deterministic.

## 17. Historical delisting/survivorship

AF-01B must never require a symbol to be currently listed in order to appear in
historical research.

If historical data exists and is admitted, the instrument remains queryable for
historical timestamps.

Current exchangeInfo/current listing status cannot be used as the sole
historical universe source.

## 18. Symbol changes / rebrands

Infrastructure must support nullable relationships for:
- rename;
- redenomination;
- migration;
- predecessor/successor symbol.

Do not automatically splice different symbols into one price history unless a
future explicit policy authorizes it.

## 19. Initial bounded implementation validation

AF-01B implementation may use a bounded public-data validation set.

It should demonstrate at minimum:
- multiple symbols;
- at least two intervals or deterministic derived views;
- a known gap case;
- lifecycle/first-data distinction;
- lagged liquidity metrics;
- point-in-time eligibility;
- deterministic rebuild.

This validation is infrastructure evidence only, not strategy selection.

## 20. Bulk population gate

Do not automatically download the entire historical Binance Spot universe during
the implementation Work unit unless needed for bounded validation.

A later Director-supervised bulk population step may populate the foundation
after:
- implementation CI green;
- storage/runtime estimates reviewed;
- acquisition plan frozen;
- no sealed evidence conflict.

This prevents implementation debugging from being mixed with a giant data job.

## 21. Tests

Minimum tests:

### Lifecycle
- first_admitted_data != inferred listing time;
- nullable listing/delisting supported;
- historical delisted symbol remains queryable;
- leveraged/non-Spot product blocked.

### Eligibility
- point-in-time only;
- no future lifecycle leakage;
- quote policy enforced;
- insufficient history fails closed.

### Canonical data
- duplicates rejected;
- cadence/gaps explicit;
- deterministic digest;
- OHLC/volume/trade-count validation.

### Derived views
- UTC boundaries;
- deterministic OHLC aggregation;
- volume/trade count sums;
- gap propagation.

### Liquidity
- trailing window excludes current/future incomplete data;
- exact ending timestamp bound;
- deterministic output.

### Safety
- Fresh OOS blocked;
- recent reserve blocked;
- P10 blocked;
- no Futures/leverage/short/Live/order capability.

## 22. CI acceptance

Final implementation HEAD must pass:
- focused AF-01B tests;
- relevant CRL acquisition/replay/controls tests;
- MCF safety tests;
- repository unit-and-safety;
- accepted-public-data.

Any full-suite baseline failures must be reproduced/classified against clean
main before being called AF-01B regressions.

## 23. Implementation package

Suggested package:

research/opportunity_data/
- models.py
- lifecycle.py
- canonical.py
- quality.py
- eligibility.py
- liquidity.py
- index.py
- views.py
- cli.py

Reuse existing modules when safer than duplication.

Tests:
- test_opportunity_data_lifecycle.py
- test_opportunity_data_eligibility.py
- test_opportunity_data_quality.py
- test_opportunity_data_views.py
- test_opportunity_data_liquidity.py
- test_opportunity_data_safety.py

## 24. CLI

Useful commands may include:

- validate-manifest
- build-index
- inspect-symbol
- compute-liquidity
- check-eligibility
- validate-runtime-root

No trading/execution CLI.

## 25. Work-token policy

AF-01B is a justified WORK_REQUIRED package because it is one reusable
multi-file data foundation.

Do not use Work per symbol or per later candidate.

After implementation, bulk population and mass candidate runs should happen via
deterministic runtime/VPS jobs.

## 26. Exit state

Allowed final states:

- AF_01B_IMPLEMENTATION_ACCEPTED
- AF_01B_PRECONDITION_BLOCKED
- AF_01B_IMPLEMENTATION_BLOCKED
- AF_01B_CI_BLOCKED

Implementation acceptance does not itself authorize the first MCF production
selection batch.

After AF-01B implementation, the Director must still freeze:
- actual bulk acquisition/population plan;
- first production universe policy;
- executable family parameter domains;
- trial budgets;
- evidence policy;
- MCF-04 statistical/cluster route.
