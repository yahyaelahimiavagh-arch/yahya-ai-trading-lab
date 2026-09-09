# P0 status — 2026-09-07

Scope: public market data plus authenticated read-only Spot Testnet account access.

- Python target remains 3.12.14; standard library only; no new dependencies.
- Baseline commit: d879e17.
- `uv run --locked python -m unittest discover -s tests -v`: **22/22 PASS** (7 existing, 15 new).
- Tests cover an RFC 4231 HMAC vector, signed query/header, env parsing/BOM/quotes/conflicts,
  credential redaction, exact host/path/method restrictions, redirects, disabled ambient proxies,
  malformed/oversized responses, transport errors without retries, Unicode assets and safe CLI output.
- Live `uv run --locked python -m yatl account`: **PASS**, 2026-09-07.
  Validated SPOT summary: 504 assets, 504 with nonzero test balances.
  No raw account payload, amounts, API key, secret or signed URL printed or persisted.
- Initial live response revealed an ASCII-only asset validation assumption. Unicode alphanumeric
  names now pass; control characters remain rejected, with a regression test.
- `.env` remains ignored and unchanged; `.env.example` remains tracked.
- Sandbox access to the existing uv cache failed; tests and live read ran with approved access.
- Earlier public ping and 100 BTCUSDT 1h candle downloads were user-reported successes,
  not repeated in this delivery.

## Enforced boundaries

- Authenticated transport: only GET https://testnet.binance.vision/api/v3/account.
- Required configuration: testnet and LIVE_MASTER_LOCK=OFF. Invalid or conflicting config fails closed.
- No redirects or ambient proxies; default verified TLS; 15-second timeout; 2 MB response limit;
  5-second receive window; no automatic retries; no raw server errors displayed.
- Only a sanitized account summary is returned. Public market data remains credential-free.
- PAPER ONLY; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API; NO AI DIRECT EXECUTION.
- No order endpoints or permission-changing API calls.

## Limits and next steps

- USER_DATA-only key permissions are user-confirmed in Testnet management. The account response
  does not independently establish key-level TRADE permissions; canTrade describes the account.
  No order request is used to probe permissions.
- Requires a synchronized local clock and direct HTTPS connectivity.
- GitHub remote/CI and historical-data quality checks remain future work.

Reference: [Official Spot Testnet REST API](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/rest-api.md)

## Project position reconciliation — 2026-09-07

P0 remains IN PROGRESS / CLOSURE PENDING. Authenticated account access has passed;
P0 as a whole has not been accepted. See [MASTER-PLAN.md](MASTER-PLAN.md) for the
recovered phase sequence, P0 item status and source limitations.
Next: P0-007/008/010 onboarding and manual Paper workflow, then P0 final audit.
No completed Paper trade or verified TradingView Paper session is recorded yet.
Scaffold/config scope and private repository status require reconciliation in that audit.
The previous suggestion to move straight to candle quality (P1) was premature.
This documentation update does not change code, credentials, permissions or execution locks.

## P0 closure evidence — 2026-09-09 (supersedes earlier current-status sections)

Status: **P0 RUNTIME ACCEPTED**. P1 is planned but implementation has not started.

- Pre-change audit: HEAD `a11f854`; branch `main`; working tree clean; no Git remote configured.
- Pre-change full suite: 22 passed, 0 failed.
- P0 closure full suite: **28 passed, 0 failed**.
- `python -m yatl paper-check`: PASS for deterministic BTCUSDT and ETHUSDT fixtures.
  Both define Entry, Stop, Target and Position Size; each uses 0.5% risk, R:R 2,
  Spot Long-only and notional no greater than paper equity.
- Fail-closed tests reject live mode, LIVE_MASTER_LOCK other than OFF, exchange submission,
  Futures, Short, unapproved symbols/timeframes, risk above 1%, leverage, inconsistent
  arithmetic, schema changes, malformed/oversized fixture files and invalid decimal values.
- Live `python -m yatl ping`: PASS against Binance Spot Testnet.
- Live authenticated `GET /api/v3/account`: **PASS**; validated SPOT summary contained
  502 assets with nonzero test balances at this run. No key, secret, signature, signed URL,
  account identifier or balance amount was printed or persisted.
- `.env` is ignored and untracked. No order endpoint or permission-changing call exists.
- The default uv cache was inaccessible in this managed session. All tests and runtime commands
  used the locked project with an explicit writable uv cache; this is an environment permission
  issue, not a project test failure.
- Manual Paper is accepted through the repository fixture. TradingView remains optional and
  was not claimed as runtime-tested. The fixture is a teaching calculation, not a market trade.
- Private GitHub remote/CI is not configured and moves to the P1 engineering backlog; it does
  not block the local P0 runtime or safety gate.

Safety baseline remains: PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
NO WITHDRAWAL API; NO AI DIRECT EXECUTION; current API key remains USER_DATA only.

P1 exact plan: [P1-IMPLEMENTATION-PLAN.md](P1-IMPLEMENTATION-PLAN.md). P2 remains unopened.

## P1-001 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `38f4e78`**.

- Added immutable P1 configuration with only the public Binance Spot host, BTCUSDT/ETHUSDT,
  15m/1h/4h and execution timeframe `NOT_ENABLED`.
- Added a frozen canonical Candle contract with lossless decimal strings, UTC interval-aligned
  timestamps, OHLC consistency, volume/trade-count validation, closed/open state and stable key.
- Full suite: **36 passed, 0 failed**.
- Runtime smoke check constructed a closed BTCUSDT 1h candle and returned its expected stable key.
- No dependency or lockfile change. No network, credentials, order endpoint or execution logic added.
- Corrected `.gitignore` from `data/` to `/data/` so root runtime datasets remain ignored while
  the source package `yatl/data/` is tracked.
- P1-002 has not started. P1 as a whole is not accepted; P2 remains unopened.

## P1-002 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `bff4d24`**.

- P1-001 checkpoint: `38f4e78` with a clean working tree.
- Added a credential-free Binance Spot public REST client restricted to GET server time,
  single-symbol exchange information and klines on `https://api.binance.com`.
- Only BTCUSDT/ETHUSDT and 15m/1h/4h are accepted; kline pages are limited to 1000 rows.
- Redirects and ambient proxies are disabled. Responses have an 8 MB cap and 15-second timeout.
- HTTP 418 stops immediately. HTTP 429 uses bounded `Retry-After`; transient network/5xx
  failures use bounded backoff with at most three attempts. Client errors and malformed
  responses are not retried and raw URLs/server messages are not displayed.
- Full suite: **48 passed, 0 failed**.
- Live `python -m yatl data-check`: PASS. Server time returned; BTCUSDT and ETHUSDT both
  reported `TRADING` and returned two public-real 1h klines.
- No API key/header, environment credential, account import, order endpoint, persistence,
  WebSocket or execution logic was added.
- P1-003 has not started. P1 as a whole is not accepted; P2 remains unopened.

Reference: https://developers.binance.com/en/docs/products/spot/rest-api

## P1-003 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `c5d6f0e`**.

- P1-002 checkpoint: `bff4d24` with a clean working tree.
- Added explicit half-open `[start, end)` historical ranges aligned to 15m/1h/4h UTC grids.
- Binance requests use inclusive `endTime=end-1`, pages of at most 1000 and a hard range cap
  of 100,000 candles. Pagination must advance monotonically and stops on an empty page.
- Rows outside the range, malformed timestamps, wrong close boundaries, duplicates and
  out-of-order pages fail closed before any persistence.
- Known open timestamps can be supplied so a repeated/resumed collection returns only new rows.
- Full suite: **56 passed, 0 failed**.
- Live `python -m yatl history-check`: PASS. For each of BTCUSDT/ETHUSDT and 15m/1h/4h,
  two closed-range candles were fetched in two pages with `page_limit=1`.
- Runtime check performed no persistence, loaded no credentials and exposed no execution path.
- P1-004 has not started. P1 as a whole is not accepted; P2 remains unopened.

## P1-004 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `0982f21`**.

- P1-003 checkpoint: `c5d6f0e` with a clean working tree.
- Added one normalizer for REST rows and public raw/combined WebSocket kline events.
- Both transports produce the same frozen Candle contract and preserve exchange decimal strings.
- REST closed/open state uses Binance server time: a candle becomes closed only when server time
  is greater than its inclusive close timestamp. WebSocket state uses the exchange `x` boolean.
- Stream wrapper name, event type/time, outer/inner symbol, interval, required fields, reserved REST
  field and canonical Candle invariants fail closed. Upstream invalid values are not echoed.
- Full suite: **64 passed, 0 failed**.
- Live `python -m yatl normalize-check`: PASS. For BTCUSDT/ETHUSDT on 15m/1h/4h,
  the latest two rows normalized as `closed,open` in every case.
- No local clock decision, persistence, credential, authenticated stream or execution path added.
- P1-005 has not started. P1 as a whole is not accepted; P2 remains unopened.

Reference: https://developers.binance.com/en/docs/products/spot/testnet/web-socket-streams

## P1-005 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `a02acb4`**.

- P1-004 checkpoint: `0982f21` with a clean working tree.
- Added SQLite schema version 1 and a unique primary key of
  `(source, symbol, interval, open_time_ms)` for canonical candles.
- Decimal strings round-trip without conversion. Identical writes are idempotent; an open
  candle can update and finalize, while any conflicting rewrite or downgrade of a closed candle
  raises a fail-closed error.
- Batch writes are transactional and roll back earlier rows when a later row conflicts.
  Invalid batches, non-Candle values, invalid keys and databases with newer schemas are rejected.
- File databases use WAL, a five-second busy timeout and explicit reopen verification. Runtime
  databases remain under ignored `/data/` in normal project use.
- Full suite: **74 passed, 0 failed**.
- Live local `python -m yatl storage-check`: PASS. A temporary file database completed migration,
  insert, identical replay, open update, finalization, close/reopen round trip and closed-candle
  conflict protection, then removed its temporary database files.
- The managed Codex process could not write runtime files inside the older repository checkout;
  the same project code and locked environment were therefore run with its temporary database in
  the current approved workspace. This was an environment path restriction, not a test failure.
- No network request, credential, authenticated import, order endpoint or execution logic was added.
- P1-006 has not started. P1 as a whole is not accepted; P2 remains unopened.

## P1-006 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `c63d88e`**.

- P1-005 checkpoint: `a02acb4` with a clean working tree.
- Added deterministic inspection of half-open UTC ranges for BTCUSDT/ETHUSDT and
  15m/1h/4h, with the same 100,000-candle bound as historical collection.
- Duplicate timestamps are reported once per range. A separate canonical-key check detects
  repeated Candle keys before persistence; SQLite's primary key remains the persistence guard.
- Missing historical timestamps are grouped into minimal half-open repair ranges. The report
  is capped at 1,000 repair ranges and never starts a download or retry loop itself.
- A missing current open interval is identified separately and does not make an otherwise
  healthy historical range fail. Ranges extending beyond that interval fail closed.
- Tests cover healthy ranges, contiguous gaps, duplicates, the current-open distinction,
  all approved UTC grids across a DST transition date, invalid/future/oversized input and
  repair-range exhaustion.
- Full suite: **84 passed, 0 failed**.
- Local `python -m yatl quality-check`: PASS. It classified one duplicate, one historical
  repair range and one expected missing current-open interval without network or persistence.
- No credential, network request, automatic repair, order endpoint or execution logic was added.
- P1-007 has not started. P1 as a whole is not accepted; P2 remains unopened.

## P1-007 evidence — 2026-09-09

Status: **IMPLEMENTED AND LIVE RUNTIME VERIFIED — CHECKPOINT COMMIT PENDING**.

- P1-006 checkpoint: `c63d88e` with a clean working tree.
- Added one combined public kline stream restricted to the market-data-only
  `wss://data-stream.binance.vision` host and the six approved symbol/interval pairs.
- Connection settings disable ambient proxies and compression, cap messages at 64 KiB,
  bound the receive/open/close waits and rely on the protocol library for server ping replies.
- Normalized candles persist idempotently. Duplicate events are harmless, open candles update
  and finalize, and older or unsubscribed events fail closed.
- Disconnect/server-shutdown handling allows at most two reconnects with 1/2-second backoff.
  Before resuming it REST-backfills only completed intervals from the last observed candle,
  with a hard 1,000-candle limit and no unbounded retry loop.
- Added and locked the single dependency `websockets==17.1`, compatible with Python 3.12.
- Full suite: **93 passed, 0 failed**.
- Live `python -m yatl stream-check --symbol BTCUSDT --interval 1h --messages 1`: PASS.
  One public message normalized and stored as one in-memory SQLite row with zero reconnects.
- No `.env`, API key, account/user stream, order endpoint or execution logic was used.
- P1-008 has not started. P1 as a whole is not accepted; P2 remains unopened.

References: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
and https://pypi.org/project/websockets/
