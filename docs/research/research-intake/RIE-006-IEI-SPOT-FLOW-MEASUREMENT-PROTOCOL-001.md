# RIE-006 — IEI Spot Flow Measurement Protocol 001

Work Unit ID: `RIE-006-IEI-SPOT-FLOW-MEASUREMENT-PROTOCOL-001`  
Status: **SPECIFICATION COMPLETE / NO ARCHIVE ACQUISITION / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `cbbc3274b29b4471ca971f2915566e956ad2d7ab`
- PR #152: OPEN / DRAFT / UNMERGED

Parent checkpoint:
- `AF-03D-CORPUS-SYNTHESIS-CHECKPOINT-v1.0.md`
- queue item: **AF-03D-FU-03 Spot flow measurement protocol**

Boundary:
- PAPER / RESEARCH ONLY
- `LIVE_MASTER_LOCK=OFF`
- no Futures execution / leverage / short / Live / order endpoint / AI execution
- no prices joined to future outcomes, returns, backtests or parameter sweeps
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED

## 1. Purpose

Specify a causal, reproducible public-Spot trade-flow measurement contract for
`IEI-MECH-009` order-flow toxicity / adverse-selection state and
`IEI-MECH-017` clock-phase algorithmic flow, while forcing future tests to
distinguish any claimed increment from a simple signed-flow ratio and generic UTC
time gate.

This document does not establish a predictive or tradable edge.

## 2. Primary public source contract

Initial source family:
- Binance public **Spot** archive only;
- raw families: `trades` and/or `aggTrades`, selected explicitly by a later
  preregistration;
- official archive: `data.binance.vision`;
- public REST cross-check surface: Spot `/api/v3/aggTrades` where applicable.

Official Binance public-data documentation defines Spot `aggTrades` fields as:
aggregate trade ID, price, quantity, first trade ID, last trade ID, timestamp,
buyer-maker flag and best-price-match flag. It also states that daily data are
published the next day, monthly data at the first Monday of the month, each ZIP
has a sibling `.CHECKSUM`, and archived files may later be replaced after
discovered issues.

The same documentation states that Spot archive timestamps from
**2025-01-01 onward are microseconds**. Earlier archive timestamps are treated as
milliseconds unless source evidence for a specific file proves otherwise.

Sources:
- https://github.com/binance/binance-public-data/blob/master/README.md
- https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints

## 3. AggTrade semantics and non-equivalence to individual trades

An `aggTrade` is an aggregate object. Its aggregate ID and first/last underlying
trade IDs must be preserved separately.

Therefore:
- one aggTrade row MUST NOT be called one individual fill;
- aggTrade row count MUST NOT be called trade count;
- `last_trade_id - first_trade_id + 1` may be retained as a source-range
  diagnostic but is not silently substituted for a raw-trades count without a
  source-validated continuity rule;
- a future VPIN-like or toxicity construction must freeze whether it consumes
  raw `trades` or `aggTrades`; it may not switch after seeing outcomes.

## 4. Aggressor sign semantics

For Spot `aggTrades`, the buyer-maker boolean is interpreted mechanically:
- `buyer_is_maker = true` -> the buyer supplied resting liquidity; the seller
  was the taker/aggressor -> signed aggressor direction `-1`;
- `buyer_is_maker = false` -> the buyer was the taker/aggressor -> signed
  aggressor direction `+1`.

This is a trade-initiation convention, not proof that the taker was informed.

Signed base quantity:
`signed_base_qty = aggressor_sign * quantity`.

Signed quote notional:
`signed_quote = aggressor_sign * price * quantity`.

Both unsigned and signed quantities must be preserved.

## 5. Event ordering contract

Canonical ordering is source-ID first, timestamp second only as a validation
field.

For aggTrades:
1. require strictly increasing aggregate trade IDs within an admitted continuous
   segment;
2. require `first_trade_id <= last_trade_id`;
3. require nondecreasing timestamps after normalization;
4. duplicate aggregate IDs are invalid unless byte-identical duplicate handling
   is explicitly documented upstream;
5. equal timestamps do not imply simultaneous economic ordering and MUST NOT be
   tie-broken by price/quantity;
6. source ID ordering must not be reconstructed from file row number if IDs
   disagree.

A gap in aggregate IDs or an impossible underlying-ID range creates a segment
boundary or rejection according to the later acquisition protocol. It is never
silently interpolated.

## 6. Timestamp normalization

Store:
- raw timestamp integer;
- detected source unit;
- normalized UTC timestamp at microsecond precision;
- source-file date;
- parser version.

Rules:
- pre-2025 Spot archive: millisecond interpretation unless file-specific source
  evidence says otherwise;
- 2025-01-01 onward: microseconds per Binance public-data notice;
- no heuristic division solely because a timestamp “looks large” after the
  transition rule is known;
- mixed precision inside one source file is fail-closed;
- UTC is the only canonical phase clock.

## 7. Integrity, corrections and provenance

For every admitted archive object preserve:
- exact source URL/object key;
- retrieval timestamp;
- ZIP bytes SHA-256;
- official `.CHECKSUM` contents and verification result;
- CSV member name and raw/normalized hash;
- parser/schema version;
- timestamp-unit rule;
- source update/replacement ledger entry if applicable.

Binance explicitly documents that archived files can be updated and publishes
old/new checksum information for archive corrections. Therefore object path alone
is not an immutable version identifier.

Never silently replace an earlier archived version with a corrected modern
version in a PIT research corpus.

## 8. Gap and missing-data rules

No forward fill.

No synthetic trades.

No interpolation across missing IDs/files.

Required diagnostics per admitted segment:
- first/last aggregate ID;
- first/last underlying trade ID;
- first/last normalized timestamp;
- row count;
- aggregate-ID gap count and ranges;
- timestamp regression count;
- duplicate-ID count;
- checksum status;
- source revision state.

Any downstream bucket crossing a rejected/missing segment must be marked
incomplete and excluded under a preregistered rule, not repaired after outcomes.

## 9. Frozen measurement primitives

This protocol defines primitives only; it does not freeze trading thresholds.

### 9.1 Simple signed-flow control

For causal bucket `B`:

`SFR_B = sum(signed_quote) / sum(abs(quote_notional))`

with denominator > 0 required.

This is the mandatory simple-flow comparator for any later toxicity claim.

### 9.2 Causal volume buckets

A VPIN-like construction, if later preregistered, must:
- use only events observed up to the bucket close;
- use a fixed volume/notional bucket definition frozen before outcomes;
- never use future events to rebalance an already closed bucket;
- specify deterministic treatment of the event that crosses the bucket boundary;
- preserve incomplete buckets across gaps as invalid rather than filling them;
- compute state only after the required number of completed historical buckets
  exists.

The term “VPIN-like” is required unless the implementation exactly reproduces a
cited canonical VPIN estimator and assumptions.

### 9.3 Adverse-selection state

Without L2/order-book history, trade flow alone cannot directly measure queue
position, spread capture or realized adverse selection of a passive strategy.

Any later `adverse-selection state` from public trades is therefore a proxy
state and must be compared with:
- simple signed-flow ratio;
- realized volatility control available at decision time;
- generic activity/volume control.

It must not be described as proven informed trading.

### 9.4 UTC clock phase

Clock phase is derived only from normalized UTC event time.

A later phase hypothesis must preregister:
- exact phase partition;
- DST-independent UTC semantics;
- whether weekends/weekday are separate dimensions;
- minimum history before a phase state is eligible.

No phase boundaries may be moved after performance inspection.

## 10. Mandatory non-duplicate controls

Before `IEI-MECH-009` or `017` can count as a distinct mechanism, any later
test must include unchanged controls for:

1. simple signed-flow ratio / taker imbalance;
2. generic UTC time/phase gate;
3. generic volume/activity state;
4. generic volatility state where relevant.

If the complex state adds no residual information/economic effect over these
controls, classify it as duplicate or non-incremental rather than a new edge.

This preserves AF-03D's cluster:
`OFI / toxicity / clock phase -> adverse-selection cluster`.

## 11. Historical versus live observability

Historical archive availability is not live observability.

For future research preserve separately:
- event/exchange timestamp;
- archive publication/retrieval time;
- live receipt time if/when a paper collector exists;
- state-computation completion time;
- decision eligibility time.

Daily archives published the next day can support historical method development
but cannot establish that the same archive object was available intraday.

A future Forward/Paper implementation would need its own live public Spot stream
and receipt-clock protocol. This document does not authorize it.

## 12. Opportunity-starvation accounting

Every future filter/state built from this protocol must retain counters for:
- raw eligible opportunities;
- state-computable opportunities;
- accepted;
- delayed;
- skipped due to state;
- skipped due to missing/gap data;
- completed trades if a later trading protocol exists;
- exposure time;
- missed moves/opportunity cost;
- estimated cost saved;
- net economic effect.

A state that suppresses nearly all opportunities is not successful merely because
it avoids losses.

## 13. Fail-closed rules

Reject or segment data when:
1. checksum fails or is absent where the official sidecar should exist;
2. archive revision/version cannot be identified sufficiently for the intended
   PIT claim;
3. timestamp unit is ambiguous;
4. source IDs regress or duplicate unexpectedly;
5. required IDs/fields are missing;
6. buyer-maker field is invalid;
7. source family changes mid-corpus without a frozen bridge;
8. a gap is silently filled;
9. aggTrade count is represented as individual-trade count;
10. historical next-day archive availability is represented as intraday live
    availability.

## 14. Cheapest future falsification

No economic run is authorized here.

Before scarce evidence, a later bounded acquisition should only test whether a
small predetermined Spot archive sample:
- verifies official checksums;
- parses deterministically across the 2024/2025 timestamp boundary;
- preserves monotonic IDs and exposes gaps;
- reproduces buyer-maker sign semantics;
- can construct causal SFR and causal bucket states without future events;
- retains opportunity counters.

If substantial archive acquisition/transformation is required, the Execution
Mode Matrix requires a new `WORK_REQUIRED` gate before execution.

## 15. Disposition

AF-03D-FU-03 is complete as a specification.

`IEI-MECH-009`:
**METHOD_SPECIFIED / HISTORICAL_FEED_INTEGRITY_UNVALIDATED / LIVE_OBSERVABILITY_UNVALIDATED / L2_LIMITATION_PRESERVED**

`IEI-MECH-017`:
**METHOD_SPECIFIED / UTC_PHASE_SEMANTICS_FROZEN / INCREMENTALITY_UNTESTED / LIVE_OBSERVABILITY_UNVALIDATED**

No candidate is registered and no performance test is authorized.

Next bounded AF-03D queue item:
`AF-03D-FU-04 PIT public-data feasibility triage`.

Expected route for the bounded triage: `CHAT_DIRECTOR`.

## 16. Closeout

- Work Unit ID: `RIE-006-IEI-SPOT-FLOW-MEASUREMENT-PROTOCOL-001`
- execution mode: `CHAT_DIRECTOR`
- GitHub authoritative starting main:
  `ce8e7b747f712779ed5e16144d74bda013226948`
- starting branch HEAD:
  `cbbc3274b29b4471ca971f2915566e956ad2d7ab`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item addressed: `AF-03D-FU-03`
- files changed: this specification only
- sources inspected: official Binance public-data README; official Binance Spot
  market-data semantics
- blocker resolved: deterministic trade-flow/time/gap/sign measurement contract
- blockers remaining: historical archive integrity sample; live receipt-clock
  observability; L2 unavailable for direct queue/adverse-selection measurement;
  future incremental test versus simple controls
- negative evidence: aggTrade rows are not individual fills; next-day archives
  do not establish intraday availability; archive objects can be revised;
  trade-flow toxicity is only a proxy without L2
- duplicate/mechanism cluster: 009/017 remain in adverse-selection cluster until
  incremental evidence exists
- tests: specification/source audit only; no code tests
- CI: documentation-only; final commit status must not be called PASS without a
  reported status
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next allowed action: `AF-03D-FU-04 PIT public-data feasibility triage`
- merge status: NO

**MERGED=NO**
