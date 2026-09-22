# CRL-002 — Data Acquisition & Provenance

Status: **ACQUISITION SPEC v0.1.0 REGISTERED — RUNTIME DATA NOT YET ACQUIRED**

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

REST responses are normalized under the current official Spot API timestamp
contract and the requested time unit is recorded in provenance.

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

A future research-only implementation belongs under `research/crisis_lab/`.
Production YATL modules must never import it.

## CRL-002 exit status

- reproducible source/range design — **PASS**;
- machine-readable acquisition registration — **PASS**;
- holdout visibility policy — **PASS**;
- P10 no-write specification — **PASS**;
- live/bulk acquisition on VPS — **PENDING**;
- provenance manifests from real downloaded files — **PENDING**;
- before/after no-P10-write runtime proof — **PENDING**.

Therefore CRL-002 is **IN PROGRESS**. Planning/registration is complete, but the
checkpoint is not accepted until real acquisition evidence exists.
