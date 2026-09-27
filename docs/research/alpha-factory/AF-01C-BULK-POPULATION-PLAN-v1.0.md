# AF-01C — Bulk Opportunity-Data Population Plan v1.0

Status: **FROZEN BEFORE BULK ACQUISITION**
Date: 2026-09-27
Mode: DIRECTOR + WORK_IMPLEMENTATION + MANUAL_VPS_RUNTIME
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

## 1. Objective

Populate the AF-01B point-in-time data foundation with a broad historical
Binance Spot / USDT research corpus suitable for the first Mass Candidate
Factory Development generation.

This is a data population program, not strategy selection.

## 2. Public source lane

Primary source:
- Binance Public Data Spot kline archives;
- checksum-verified archive objects;
- daily/monthly archive layout;
- canonical fields matching the existing CRL candle schema.

Repository source adapter should reuse the existing bounded HTTPS/checksum/
archive-normalization semantics from `research/crisis_lab/acquisition.py`
where safe, but must remove the CRL-specific BTC/ETH symbol allowlist through a
new versioned opportunity-data adapter rather than mutating frozen CRL code.

## 3. Historical symbol inventory rule

Do NOT use current `exchangeInfo` as the sole historical symbol inventory.

Reason:
current-running symbols cannot establish completeness for symbols that were
historically delisted, renamed or migrated.

The bulk adapter must first create a content-addressed **archive inventory
snapshot** from the public historical archive object/index listing.

Inventory snapshot records:
- source endpoint(s);
- retrieved timestamp;
- every observed Spot kline object key in the registered Development range;
- parsed symbol;
- parsed interval;
- parsed year/month/day;
- raw inventory SHA-256;
- normalized inventory SHA-256.

If archive inventory enumeration cannot be made deterministic and auditable,
the run must stop with:
`HISTORICAL_SYMBOL_INVENTORY_UNPROVEN`

It must not silently fall back to current symbols.

## 4. Development time boundary

First mass-generation Development data boundary:

- population start: `2020-01-01T00:00:00Z`
- scored-search start: `2020-03-01T00:00:00Z`
- Development end exclusive: `2023-01-01T00:00:00Z`

January-February 2020 are available only as generic warmup/history for the first
scored-search date.

No timestamp on or after 2023-01-01 is needed for MCF-PROD-001 Development.

This deliberately reuses known historical Development territory and avoids
opening any later scarce evidence.

## 5. Base interval

Canonical base population interval:
`15m`

Higher research views:
- 1h
- 4h
- 1d

are derived deterministically through AF-01B whenever possible.

Do not separately download higher intervals for the first production corpus
unless required for source verification or recovery.

Benefits:
- one canonical source grid;
- lower duplicate storage;
- consistent gap propagation;
- deterministic cross-timeframe aggregation.

## 6. Candidate archive objects

Initial inventory candidates:
- Spot kline objects;
- symbols ending in `USDT`;
- periods overlapping 2020-01-01 through 2022-12-31;
- 15m interval.

Archive presence proves public historical data presence, not official listing
time.

## 7. Product classification

The population layer must distinguish:
- ordinary Spot candidate;
- known leveraged-token/synthetic product;
- unresolved product classification.

Known nonordinary products are excluded from production eligibility.

If product type cannot be supported by source evidence, retain the data as
admitted metadata if safe, but mark production eligibility blocked rather than
inventing certainty.

No current-status lookup is allowed to rewrite past existence.

## 8. Archive integrity policy

For every downloaded archive object:
- checksum required;
- archive SHA-256 verified;
- exactly expected member path/name;
- canonical column validation;
- timestamp-unit normalization;
- bounded extraction;
- immutable raw/cache artifact;
- canonical CSV SHA-256;
- source provenance record.

Monthly archive is preferred for throughput.

If a monthly object is:
- absent;
- checksum-missing;
- checksum-invalid;
- corrupt;
- structurally inconsistent;
- incomplete relative to expected archive coverage,

the adapter may attempt registered daily-object fallback for the same period.

Fallback must be explicit in the evidence manifest.

Never silently accept a failed monthly object.

## 9. Historical archive anomaly policy

Public archives are not assumed perfect.

Anomalies become explicit records:
- MISSING_ARCHIVE
- MISSING_CHECKSUM
- CHECKSUM_MISMATCH
- INVALID_ZIP
- INVALID_MEMBER
- INVALID_SCHEMA
- TIMESTAMP_ANOMALY
- CONTENT_GAP
- DAILY_FALLBACK_USED
- UNRECOVERABLE_SOURCE_GAP

No interpolation or fabricated candles.

## 10. Lifecycle inference

For each discovered symbol:
- `first_admitted_data_ms` = first canonical admitted 15m bar;
- `last_admitted_data_ms` = last canonical admitted bar within population range;
- official `listing_time_ms` = null unless independently evidenced;
- official `delisting_time_ms` = null unless independently evidenced.

Do not infer official listing time from first archive bar.

Archive disappearance alone does not prove official delisting.

## 11. Population phases

### P-A Inventory
Enumerate and freeze historical archive inventory.

### P-B Pilot
Populate a bounded 10-symbol sample spanning:
- early-listed;
- later-listed;
- at least one historically inactive/delisted candidate if discovered;
- one source-gap/anomaly case if available.

Pilot closes only after index rebuild and quality reconciliation.

### P-C Broad population
Populate all inventory-admitted USDT Spot candidate symbols for 15m in the
registered Development range.

### P-D Derived views
Build 1h / 4h / 1d views deterministically.

### P-E Index / liquidity
Build deterministic universe index and lagged liquidity metadata.

### P-F Freeze
Publish content-addressed population manifest and quality summary.

## 12. Restart / resume

Bulk runtime must be restartable.

Rules:
- immutable completed object artifacts;
- content-addressed filenames;
- no overwrite of differing bytes;
- per-object completion ledger;
- idempotent rerun;
- partial downloads never counted as admitted;
- run reconciliation required before population state becomes COMPLETE.

## 13. Runtime location

Suggested VPS runtime root:
`/var/lib/yatl/research/opportunity-data`

P10 paths remain protected and must never be descendants or parents of this
runtime root.

Repository remains free of bulk candle data.

## 14. Bulk population completion gate

Required:
- archive inventory frozen;
- every candidate object in final state;
- all checksum states reconciled;
- all admitted symbol datasets content-addressed;
- gap maps generated;
- lifecycle records generated;
- deterministic universe index generated;
- population manifest digest generated;
- quality summary generated;
- Fresh OOS false;
- recent reserve false;
- P10 read/write false.

Allowed population states:
- `POPULATION_COMPLETE`
- `POPULATION_COMPLETE_WITH_SOURCE_GAPS`
- `POPULATION_BLOCKED_INVENTORY`
- `POPULATION_BLOCKED_SOURCE`
- `POPULATION_INVALID`

A source-gap state may still support later production eligibility when the
frozen universe policy explicitly permits the observed gap rate.

## 15. No strategy outcomes

The bulk population process may inspect:
- archive availability;
- row counts;
- gaps;
- volumes;
- trade counts;
- lifecycle/data quality.

It must not inspect strategy PnL, Sharpe, drawdown, win rate or candidate
performance.

Universe-policy calibration from data/liquidity metadata must occur before any
MCF strategy result is exposed.
