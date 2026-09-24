# CRL-002 — Data Acquisition & Provenance

Status: **ACCEPTED — 2026-09-23 — CRL-003 OPEN**

Goal: collect bounded historical BTCUSDT/ETHUSDT data for the registered Crisis
Lab windows without creating any write path into active P10 evidence.

Canonical machine-readable acquisition registration:
`DATA-ACQUISITION-REGISTER-v0.1.0.json`.

## Scope

Primary profile `CRYPTO_CORE_V1`:
- Binance Spot public market data only;
- BTCUSDT and ETHUSDT;
- 15m / 1h / 4h;
- 14 calendar days of warm-up before each event's registered pre-event window;
- exact event windows come from `EVENT-CATALOG-v0.1.0.json` and are never
  recomputed from price outcomes.

This checkpoint does **not** alter the active P10 source, candidate, configuration,
fee/slippage, gates, sealed window, SQLite evidence, monitoring or P11 lock.

## Authoritative source order

### A. Primary bulk source — Binance Public Data

Use the official Binance public-data archive at `data.binance.vision`, preferably
daily Spot kline ZIPs for bounded event acquisition.

For each remote archive:
1. record the exact URL;
2. fetch its sibling `.CHECKSUM`;
3. verify the ZIP SHA-256 before extraction;
4. retain the raw ZIP and checksum in the research runtime tree;
5. hash the extracted CSV;
6. normalize to the canonical Crisis Lab representation;
7. hash the canonical dataset.

Binance documents that archived files may later be replaced when issues are
discovered. Therefore `retrieved_at_utc`, remote checksum, downloaded ZIP hash
and extracted-file hash are part of provenance and may not be discarded.

### B. Independent verification/fallback — public market-data REST

Use only the credential-free market-data host:

`https://data-api.binance.vision/api/v3/klines`

Rules:
- GET only;
- no API key, signature, account endpoint, user-data stream or order endpoint;
- `timeZone=0` / UTC semantics;
- explicit `startTime` and `endTime`;
- maximum 1000 rows per page;
- monotonically advancing pagination;
- bounded retries with logged failure class;
- no silent substitution when archive and REST disagree.

REST is a verification/fallback source, not permission to overwrite an archive
mismatch. A mismatch becomes **QUARANTINED_SOURCE_CONFLICT** until CRL-003
resolves it.

## Timestamp-unit rule

The official Binance public-data repository states that Spot archive timestamps
from **2025-01-01 onward are in microseconds**. Older Spot archive records are
millisecond-based.

Every source file must therefore record:
- `source_timestamp_unit`: `MILLISECOND` or `MICROSECOND`;
- the rule used to detect/validate it;
- canonical normalized timestamps;
- the raw source digest.

Unit normalization must be exact integer arithmetic. Magnitude/unit disagreement
fails closed; it is never repaired by guessing.

Historical Spot archives can contain an inconsistent kline `close_time` even
when the registered interval and `open_time` are valid. CRL-002 treats this as
a narrow source-metadata anomaly, never as permission to trust the row blindly:
the canonical close boundary is derived from `open_time + interval - 1`, the
raw ZIP/CSV and checksums remain immutable, and the entire normalized row must
match the public Spot REST kline at that open time after applying the same
interval-derived close boundary to REST. This exception is limited to the
close-time field: open time, OHLCV, quote volume, trade count, taker volumes and
the unused field must still match exactly. Any other field difference or missing
REST verification fails closed. REST-side close-boundary normalization is
explicitly counted in verification evidence; raw source responses remain
unchanged.

If an exact `startTime` + `endTime` kline query returns an empty list, CRL-002
may retry once with the same `startTime`, `limit=1`, and no `endTime`.
This follows the Spot REST contract that a start-time query returns the oldest
kline from that point. The returned row must still normalize to the exact target
open time and match all required fields. Non-empty malformed responses never
trigger this fallback, and fallback use is counted in evidence.

REST responses are normalized under the current official Spot API timestamp
contract and the requested time unit is recorded in provenance.

## Known Binance monthly archive divergences

A reproducible Binance Public Data issue documents Spot monthly kline rows that
disagree with both the corresponding daily archives and the current Spot API.
The affected scope includes BTCUSDT and ETHUSDT on 15m/1h for 2020-12-21, and
additional monthly-vs-daily discrepancies on 2021-09-29.

CRL-002 therefore uses deterministic source overrides where daily archives
have been independently corroborated against Spot REST. The globally registered
override dates are 2020-12-21 and 2021-09-29. In addition, BTCUSDT 15m/1h has a
scoped override for 2021-12-24 after direct daily-vs-REST equality was observed
at the conflicting candles. Rows in the affected scope are excluded from monthly
archive objects and replaced by the checksum-verified daily archive objects.
Raw monthly and daily source files remain immutable and separately provenanced.
This is a source-selection rule, not a value repair.

Reference: binance/binance-public-data issue #475.

## Verified exchange-wide gaps

A missing grid candle is not automatically treated as corrupt data. CRL-002
distinguishes an unknown acquisition gap from a public Spot REST-confirmed
absence.

For every missing canonical open time:
1. query Spot REST with the exact start/end interval window;
2. if that exact query returns `[]`, retry once from the same `startTime`
   without `endTime`;
3. classify the target as confirmed absent only when the fallback is also empty
   or its first returned candle opens strictly after the missing target;
4. classify any returned candle at the target open time as a source conflict;
5. fail closed on malformed responses, backward-moving fallback responses, or
   incomplete verification.

The dataset manifest records the gap count, checked/confirmed counts, a digest of
the exact missing-open-time set, fallback usage, and bounded transport evidence.
No synthetic candle is created and no timestamp is removed from the audit.
A dataset with gaps can advance to CRL-003 only when every recorded gap is
`ALL_CONFIRMED_ABSENT`; duplicates and unverified gaps remain structural
anomalies. CRL-003 independently recomputes the missing-open-time set from the
canonical file and requires the digest/count evidence to match before admission.

## Exact range semantics

The catalog's event timestamps remain exact and may be off the 15m/1h/4h candle
grid. Acquisition therefore has two ranges:

1. **semantic range** — from
   `pre_event.start - warmup` through `aftermath.end`;
2. **transport range** — rounded outward to full UTC candle/archive boundaries
   only so complete source candles can be downloaded.

Rounding is transport-only and never changes the registered event window.

Historical replay may consume a candle only after that candle is closed. If an
event occurs inside a candle, the event does not make the still-open candle
available early. CRL-004 must classify decisions using the candle's availability
time, not merely its open time.

All logical ranges are half-open `[start, end)`.

## Runtime layout

Bulk data stays out of Git:

```text
data/research/crisis-lab/
  raw/
    binance-vision/
      spot/daily/klines/<SYMBOL>/<INTERVAL>/
  extracted/
    binance-vision/
  canonical/
    event-catalog-v0.1.0/<EVENT_ID>/<SYMBOL>/<INTERVAL>/
  manifests/
    event-catalog-v0.1.0/
  quarantine/
  logs/
```

The repository root already ignores `/data/`.

Git may contain only bounded/canonical metadata such as:
- catalog and acquisition registrations;
- manifest schemas and accepted manifest summaries;
- dataset/hash indexes;
- intentionally bounded evidence required to reproduce an audit.

No raw ZIP, CSV, mutable SQLite database or full historical OHLCV corpus belongs
in Git.

## P10 hard isolation

Forbidden read/write targets for Crisis Lab acquisition include:
- `/var/lib/yatl/p10/`;
- `/var/lib/yatl/p10/p10-forward.sqlite3`;
- `/var/lib/yatl/p10/snapshot.json`;
- any active P10 candidate, registration, gate or evidence artifact.

The acquisition implementation must resolve/canonicalize paths before opening
files and fail closed if an input or output resolves inside the P10 runtime tree.
It must not copy P10 forward data into the research corpus.

A later runtime acceptance must include an explicit no-P10-write proof: hashes or
Git/file identities of protected P10 artifacts before and after CRL acquisition
must match where those artifacts are in scope for verification.

## Holdout handling

For `BLIND_HOLDOUT` events before final evaluation:
- automated download and structural data-quality checking are allowed;
- raw/canonical OHLCV must not be plotted, summarized or manually inspected for
  strategy design;
- emitted reports may expose identity, expected/actual row counts, timestamp
  bounds, gaps, duplicates, checksum/digest and PASS/FAIL structural status;
- they must not expose return, direction, drawdown, volatility rank, trade result
  or any YATL strategy metric;
- parameter selection from holdout values is forbidden.

Events marked `replay_eligible=false` may be acquired structurally, but cannot
enter historical replay until their timestamp/source conflict is closed by a new
versioned catalog decision.

## Provenance record — minimum fields

Each admitted source/dataset record must include:
- schema/version and catalog version;
- event_id, designation and replay-eligibility flag;
- source family, host and exact remote object/API identity;
- symbol and interval;
- semantic and transport UTC ranges;
- retrieval timestamp;
- source timestamp unit;
- remote checksum text where available;
- downloaded ZIP SHA-256;
- extracted CSV SHA-256;
- canonical dataset SHA-256;
- row count and first/last candle boundaries;
- retry/HTTP failure summary;
- archive-vs-REST verification method/result;
- normalization/tool version;
- quarantine reason when not admitted.

CRL-003 owns the canonical quality PASS manifest and its full replay-admission
gate. CRL-002 only establishes acquisition provenance.

## 1m extension policy

1m is **not** part of the v0.1 primary scorecard.

A separately versioned `EXTENSION_1M_V1` may be proposed only for a specific
research question that 15m cannot answer, such as:
- sub-15-minute outage/dislocation timing;
- data-gap diagnosis;
- time-to-protection measurement whose resolution would otherwise be censored.

The extension must not alter P10, replace the primary 15m/1h/4h comparison, or be
used to tune a holdout after outcome inspection.

## VPS execution target

CRL acquisition is designed for the existing Linux VPS and does not require
Windows or PowerShell.

Implementation target:
- Python 3.12 standard library where practical;
- optional shell primitives already present on Linux (`curl`, `sha256sum`,
  `unzip`) may be operator aids, not hidden dependencies;
- no secrets;
- no authenticated exchange access;
- resumable/idempotent bounded downloads;
- deterministic filenames and manifests;
- one event/symbol/interval failure does not silently pass the batch.

The research-only implementation now lives under `research/crisis_lab/` and is
invoked with `python -m research.crisis_lab`. Production YATL modules do not import
it. It uses only Python standard-library transport/parsing and adds no dependency.

Implemented v0.1 safeguards:
- exact HTTPS host allowlists for `data.binance.vision` and
  `data-api.binance.vision`;
- ambient proxies and redirects disabled;
- bounded response sizes/retries with sanitized per-URL retry/failure provenance;
- official `.CHECKSUM` verification before archive extraction;
- verified content-addressed ZIP cache reuse on repeated/resumed acquisition;
- immutable content-addressed raw/extracted/canonical runtime files;
- daily/monthly archive planning with full-month optimization;
- exact millisecond/microsecond boundary validation;
- semantic-vs-transport range separation;
- source-conflict quarantine instead of overwrite;
- sanitized Holdout/event CLI summaries;
- hard path rejection for `/var/lib/yatl/p10/`.

Operator procedure: `CRL-002-VPS-RUNBOOK.md`.

## Runtime acceptance evidence — 2026-09-23

Accepted pilot event: `CRL-E003` (Development).

Real VPS acquisition produced exactly six BTCUSDT/ETHUSDT × 15m/1h/4h dataset
manifests with event-level status `COMPLETE`, zero failures, exact expected row
counts, zero gaps, zero duplicates and `rest_verification_status=MATCH` for all
six datasets.

Event acquisition manifest:
- file SHA-256: `bb2986d87cb672eb91e2dccfbc7e593ea05c12b6f9a49d0d1ffd762b01b995cb`;
- runtime relative path:
  `manifests/event-catalog-v0.1.0/CRL-E003/event-acquisition-bb2986d87cb672eb91e2dccf.json`;
- retrieval timestamp: `2026-09-23T12:12:57Z`;
- market outcomes exposed: false;
- quality gate: `PENDING_CRL003`.

External P10 no-write proof was recorded immediately around the acquisition.
Before and after SHA-256 identities were identical:

- `/var/lib/yatl/p10/p10-forward.sqlite3`:
  `577fc15d3a8966c3f947166376b11945f93de0a32a57cdc4ec2958f7c2fad2f2`;
- `/var/lib/yatl/p10/snapshot.json`:
  `4fd18e0d3de9dca0978c9766867364313960db9c11f13583b49a793f03340687`.

The external `diff` of the before/after hash files was empty. The repository
checkout remained clean on `main...origin/main`.

This accepts the CRL-002 acquisition mechanism; it does **not** claim that the
entire 16-event corpus has already been admitted. Additional registered events
may be acquired incrementally through this accepted mechanism and are not
replay-admitted until CRL-003 issues a quality PASS manifest.

## CRL-002 exit status

- reproducible source/range design — **PASS**;
- machine-readable acquisition registration — **PASS**;
- holdout visibility policy — **PASS**;
- P10 no-write specification — **PASS**;
- research-only downloader/provenance implementation — **PASS**;
- matching Final-HEAD CI for implementation PR #86 / run `35783881556` — **PASS**;
- real VPS acquisition path — **PASS**;
- real immutable provenance manifests — **PASS**;
- archive-vs-REST boundary verification — **PASS**;
- external before/after no-P10-write runtime proof — **PASS**.

Therefore CRL-002 is **ACCEPTED**. CRL-003 is the active checkpoint. No CRL-002
result is profitability evidence, strategy acceptance, P10 modification or Live
authorization.
