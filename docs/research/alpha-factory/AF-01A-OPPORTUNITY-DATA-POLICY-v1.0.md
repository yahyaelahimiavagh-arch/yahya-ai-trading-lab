# YATL Alpha Factory — AF-01A Opportunity Data Policy v1.0

Status: DESIGN FROZEN BEFORE AF-01B IMPLEMENTATION
Established: 2026-09-27
Mode: CHAT_DIRECTOR
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

Purpose: define the point-in-time research universe and data boundaries required
to discover independent opportunity without introducing survivorship, venue
confusion, hidden OOS access, or accidental execution capability.

This document is policy/design only. It does not acquire new datasets and does
not open Fresh OOS or the recent reserve.

## 1. Two-dimensional universe

YATL must distinguish:

1. ASSET_UNIVERSE
2. VENUE_UNIVERSE

An asset claim and a venue claim are different.

A candidate must state whether it is:
- single-asset;
- multi-asset;
- single-venue;
- multi-venue;
- venue-specific microstructure;
- market-wide.

No candidate may silently substitute one for another.

## 2. Canonical reference lane

Existing canonical BTCUSDT and ETHUSDT evidence remains unchanged and continues
to serve as the historical reference lane.

AF-01 must not rewrite, rename, or retrospectively reclassify existing canonical
Generation/P10 datasets.

## 3. Primary discovery venue

The first broadened discovery implementation should remain bounded to the
existing Spot research ecosystem rather than simultaneously adding new
execution venues.

Primary discovery venue:
- Binance Spot market data, research-only.

Primary quote dependency:
- USDT-quoted Spot pairs where historical point-in-time data is admissible.

This is a research-universe choice, not Live venue authorization.

Candidates whose mechanism explicitly requires cross-venue information must use
a separate VENUE_CONTEXT lane and cannot pretend a single-venue proxy is a
source reproduction.

## 4. Point-in-time asset eligibility

Historical eligibility at timestamp t must use only information known by t.

Required eligibility dimensions:
- symbol exists/listed by t;
- Spot instrument, not Futures/Margin execution;
- quote asset matches the registered research lane;
- symbol is not a leveraged-token product;
- symbol has enough completed historical observations for the candidate's
  preregistered warmup;
- required source data up to t passes quality checks;
- any liquidity/volume eligibility uses only lagged completed observations;
- delisted or later-inactive assets remain in historical research when their
  historical data is admissible.

Current listing status must never be used as a proxy for past eligibility.

## 5. Survivorship controls

The universe registry must preserve:
- listing timestamp;
- delisting/inactivation timestamp where known;
- symbol rename/rebrand/redenomination events;
- quote-asset changes where relevant;
- historical trading-status intervals;
- reason/source/provenance for eligibility changes.

A historical asset must not disappear from Development solely because it is not
listed today.

## 6. Liquidity and opportunity layers

AF-01 separates existence from liquidity.

Each timestamped symbol may have:
- LISTED;
- DATA_ADMITTED;
- LIQUID_ELIGIBLE;
- RESEARCH_ELIGIBLE_FOR_<candidate family>.

Liquidity eligibility may use only point-in-time, lagged fields available from
admitted data, such as:
- quote notional volume;
- base volume;
- trade count when available;
- candle continuity;
- realized turnover proxies.

Exact thresholds/ranks belong in the AF-01B implementation contract and must be
frozen before they are used to select candidate outcomes.

No threshold may be chosen after inspecting strategy PnL.

## 7. Timeframes

Canonical derived research views may include:
- 15m
- 1h
- 4h
- 1d

Higher-frequency data is a separate future extension and requires its own data
quality/cost/microstructure policy.

Derivation rules must be deterministic, UTC-aligned, and use completed source
bars only.

## 8. Venue-context lane

A separate read-only VENUE_CONTEXT lane may later support research such as:
- cross-exchange price dispersion;
- venue fragmentation;
- lead-lag;
- venue-specific liquidity;
- regime detection requiring multiple exchanges.

Rules:
- no order/execution capability;
- venue identity and timezone/provenance explicit;
- historical exchange availability point-in-time;
- no substitution of current exchange coverage for historical coverage;
- if a source depends on several venues, missing venues are a source/adaptation
  limitation, not something to silently impute.

RIE-CAND-0028 is the motivating example: its source uses daily Bitcoin price
vectors from seven exchanges. That source cannot be called reproduced by a
single-venue BTC/ETH intraday proxy.

## 9. Quote-asset dependency

USDT is not treated as economically invisible.

Candidate metadata must state whether results are:
- USDT-specific;
- quote-asset dependent;
- expected to generalize across quote assets;
- untested outside the registered quote.

Depeg or quote-asset stress may later be represented as event/context data, but
must not be backfilled with future knowledge.

## 10. Gap and missing-data policy

Core rules:
- no silent interpolation;
- no price forward-fill for performance;
- duplicate timestamps rejected;
- non-monotonic timestamps rejected;
- closed-bar status required where available;
- source gaps retained in explicit gap maps;
- candidate-specific behavior for exposed gaps must be preregistered;
- flat periods may not fabricate PnL;
- unavailable liquidity/context fields remain unavailable unless a protocol
  explicitly defines a safe fallback before outcome.

## 11. Provenance and immutability

Every admitted dataset must bind:
- provider/source;
- symbol;
- venue;
- interval;
- UTC range;
- retrieval timestamp;
- row count;
- duplicate count;
- gap count/map;
- content digest;
- acquisition manifest;
- quality manifest;
- research designation.

Bulk runtime data remains outside Git unless intentionally bounded.

## 12. Evidence partitions

The existing Generation-2 evidence map remains authoritative:
- known Development material remains known Development;
- Fresh OOS remains sealed until the appropriate survivor freeze;
- recent reserve remains sealed;
- P10 operational forward evidence remains independent.

AF-01B Development loaders must fail closed if asked to read:
- Fresh OOS through a Development route;
- recent reserve;
- P10 forward stores.

Universe expansion does not grant access to sealed time partitions.

## 13. Data dependency declaration

Registry v2 candidates must declare one or more dependencies:
- PRICE_OHLC;
- VOLUME;
- TRADE_COUNT;
- MULTI_ASSET;
- MULTI_VENUE;
- EXTERNAL_CONTEXT;
- ORDER_BOOK;
- ON_CHAIN;
- NEWS_SENTIMENT;
- MACRO_RELEASE.

A candidate cannot progress to implementation if its required dependency is not
available in an admitted point-in-time form.

## 14. Early capacity metadata

AF-01 should collect enough point-in-time liquidity metadata to enable an early
coarse capacity sanity check.

This is not full AF-12 capacity certification.

Allowed early questions:
- is the candidate obviously dependent on illiquid symbols?
- would a modest participation-rate assumption make the opportunity implausible?
- is most apparent opportunity concentrated in assets that could not support the
  intended research capital scale?

No precise capacity claim is made at AF-01.

## 15. Universe-selection blind spots

Mandatory checks:
- survivorship by current listing;
- lookahead through future liquidity rankings;
- symbol migration double-counting;
- stablecoin/quote dependence;
- venue substitution;
- ignoring delisted winners/losers;
- using revised external context;
- current market-cap rankings applied historically;
- cross-sectional ranks with unavailable historical constituents;
- capacity filters that accidentally select on realized strategy outcome.

## 16. AF-01A decisions vs AF-01B implementation

Frozen now:
- asset and venue are separate universe dimensions;
- primary discovery implementation remains Binance Spot / USDT research;
- cross-venue research uses a separate read-only context lane;
- eligibility is point-in-time;
- delisted history is retained when admissible;
- gaps are explicit;
- no sealed-evidence Development read path;
- liquidity eligibility is lagged and outcome-independent;
- capacity metadata is collected early but certified later.

Deferred to AF-01B before acquisition/selection:
- exact liquid-universe threshold or rank;
- exact minimum history per generic universe membership;
- exact supported symbol list;
- data-provider/API mechanics;
- acquisition batching;
- storage/index schema;
- exact venue-context providers.

Those implementation choices must be frozen without looking at strategy
performance produced by the new universe.

## 17. Exit condition for AF-01A

AF-01A closes when:
- this policy is committed;
- Alpha Factory/Execution Board points to it;
- no existing frozen evidence is changed;
- CI is green.

AF-01B then becomes the first implementation package and is WORK_REQUIRED only
because it involves multi-file loaders/manifests and bulk data handling.

No Work is required for AF-01A itself.
