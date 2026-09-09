# P1 — Market Data Layer implementation plan

Status: **IN PROGRESS — P1-002 IMPLEMENTED, CHECKPOINT PENDING**
Entry condition: P0 baseline commit accepted and working tree clean.  
Exit condition: public BTCUSDT/ETHUSDT datasets and health reports pass deterministic tests and live runtime checks.

## Fixed scope and policy

- Markets: BTCUSDT and ETHUSDT, Binance Spot only.
- Data source: public real Binance endpoints for research and backtesting.
- Timeframes: 1h primary analysis, 4h regime, 15m entry/context.
- 5m is excluded until a later execution requirement is justified and accepted.
- Spot Testnet remains isolated for execution testing; it is not a research dataset source.
- The public data layer accepts no API key and imports no authenticated account transport.
- No order, withdrawal, margin, futures, leverage or AI execution interface is in P1.

## Delivery sequence

### P1-001 — Candle contract and configuration

Define a canonical candle model with symbol, interval, open/close timestamps, OHLC,
base/quote volume, trade count, source and closed/open state. Store timestamps as UTC
milliseconds and financial values as original decimal strings. Reject unknown symbols,
intervals, negative/non-finite values, inconsistent OHLC and malformed timestamps.

Acceptance: **PASS in working tree, 2026-09-09.** Unit tests cover every invariant;
configuration contains exactly the approved symbols, intervals and public host. The runtime
smoke check constructed a closed BTCUSDT 1h candle and preserved its stable uniqueness key.
Checkpoint commit remains required before starting P1-002.

### P1-002 — Public Binance REST client

Build one credential-free client for fixed GET endpoints needed by P1: server time,
exchange metadata and klines. Enforce HTTPS host/path allowlists, response size/timeouts,
no redirects, bounded retries only for transient read failures, and explicit backoff for
rate limits. Never retry a structurally invalid response.

Acceptance: **PASS in working tree, 2026-09-09.** Transport tests pass. Live checks returned
Binance Spot public server time, `TRADING` exchange status and two 1h klines for both BTCUSDT
and ETHUSDT. The checkpoint commit remains required before P1-003 starts.

### P1-003 — Paginated historical OHLCV downloader

Download explicit `[start_time, end_time)` ranges in pages of at most 1000 candles.
Advance by interval boundaries, verify page monotonicity and stop deterministically at
the requested boundary. A resumed download must be idempotent.

Acceptance: pagination boundary tests, empty/partial page tests and a bounded live sample
for BTCUSDT and ETHUSDT on 15m, 1h and 4h.

### P1-004 — Normalization and candle state

Normalize REST and WebSocket payloads into the same contract. Mark a candle closed only
from the exchange close flag for streams or when its close boundary is safely behind the
verified server time for REST. Preserve the current open candle but exclude it by default
from backtest-ready views.

Acceptance: equivalent REST/stream payloads normalize identically; boundary tests cover
clock edges and open-to-closed transitions.

### P1-005 — SQLite storage and migrations

Create a versioned schema. Use a unique key of `(source, symbol, interval, open_time_ms)`.
Use transactions and upserts so reruns cannot duplicate candles; allow an open candle to
be updated and then finalized, while a closed candle cannot be silently rewritten with
conflicting values. Keep database files under ignored `data/`.

Acceptance: fresh migration, reopen, rollback, idempotent insert, open-candle update and
closed-candle conflict tests.

### P1-006 — Duplicate and missing-candle detection

Detect duplicate keys before/at persistence and identify gaps from the exact interval
grid within requested ranges. Distinguish an expected current open interval from a true
historical gap. Produce repair ranges without automatically looping forever.

Acceptance: synthetic duplicate/gap/DST-independent UTC tests and bounded repair tests.

### P1-007 — WebSocket market stream

Subscribe only to Binance Spot public kline streams for the approved symbol/timeframe
pairs. Normalize events, persist updates idempotently, reconnect with capped backoff and
REST-backfill the bounded disconnect range. No credentials are loaded by this process.

Acceptance: recorded-event tests for reconnect, duplicate events, out-of-order updates,
open-to-close transitions and backfill handoff; then a time-bounded live stream check.

### P1-008 — Data health report

Report per source/symbol/interval: requested and stored ranges, first/last candle, total
rows, closed/open counts, duplicates, gaps, malformed/conflicting rows, freshness and
whether the dataset is backtest-ready. Exit nonzero when required health gates fail.

Acceptance: deterministic JSON plus human-readable CLI output tested against healthy and
unhealthy fixtures.

### P1-009 — BTCUSDT and ETHUSDT datasets

Build bounded public-real datasets for 15m, 1h and 4h with a recorded range and retrieval
time. Database artifacts remain ignored; manifests and health summaries contain no secrets
and may be committed when stable.

Acceptance: both symbols have zero unresolved historical gaps/duplicates/conflicts and no
open candle in the backtest-ready view.

### P1-010 — P1 final audit and checkpoint

Run the full suite, clean-database rebuild, repeated idempotency run, live REST checks,
bounded live WebSocket check and health reports. Audit that authenticated code remains
isolated and that no execution endpoints exist.

Acceptance: record exact commands/results in `docs/STATUS.md`, mark P1 accepted only from
runtime evidence, commit the accepted baseline and leave Git clean. P2 remains unopened.

## Intended module boundaries

```text
yatl/data/config.py       approved markets, intervals and public host
yatl/data/models.py       canonical candle contract
yatl/data/rest.py         public REST transport
yatl/data/history.py      bounded pagination and resume
yatl/data/normalize.py    REST/WebSocket normalization
yatl/data/storage.py      SQLite migrations and persistence
yatl/data/quality.py      gaps, duplicates and health reports
yatl/data/stream.py       public WebSocket lifecycle and REST backfill
tests/fixtures/           deterministic REST/WebSocket payloads
data/                     ignored runtime databases and downloads
```

Dependencies are added only when a P1 requirement cannot be met safely with the standard
library. Any dependency change must update the lockfile and be justified in the checkpoint.
