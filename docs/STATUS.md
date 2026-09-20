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

Status: **CHECKPOINT ACCEPTED — `ab1fa24`**.

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

## P1-008 evidence — 2026-09-09

Status: **CHECKPOINT ACCEPTED — `fd7eb63`**.

- P1-007 checkpoint: `ab1fa24` with a clean working tree.
- Added immutable health reports with requested/stored boundaries, total/unique rows,
  closed/open counts, duplicate and gap timestamps, bounded repair ranges, malformed and
  conflict counters, freshness, current-open state and backtest-ready status.
- A current open candle is reported separately and allowed in the source dataset. Missing
  current-open data is not a historical gap. Historical open candles and stale required
  closed candles fail the readiness gate.
- JSON output is stable (`sort_keys` and compact separators); human output contains every
  required gate. An unhealthy report returns exit code 1.
- Tests cover healthy closed data, present/missing current open, duplicates, gaps, unexpected
  open candles, stale data, malformed/conflicting counters, invalid identities, deterministic
  JSON, human output and nonzero gate failure.
- Full suite: **104 passed, 0 failed**.
- Local `python -m yatl health-check`: PASS with 4 unique rows, 3 closed, 1 current open,
  zero duplicates/gaps/malformed/conflicts and `backtest_ready=true`.
- Local `python -m yatl health-check --json`: PASS and parsed as deterministic JSON.
- This checkpoint uses a canonical local fixture. Real BTCUSDT/ETHUSDT dataset collection and
  persisted health manifests belong to P1-009 and have not started.
- No network call, credential, order endpoint or execution logic was added.
- P1 as a whole is not accepted; P2 remains unopened.

## P1-009 evidence — 2026-09-09

Status: **IMPLEMENTED AND LIVE DATA VERIFIED — CHECKPOINT COMMIT PENDING**.

- P1-008 checkpoint: `fd7eb63` with a clean working tree.
- Added a bounded dataset builder that uses verified Binance server time, downloads exact
  closed half-open ranges, normalizes every REST row, persists idempotently and runs the
  P1-008 health gate before publishing an atomic manifest.
- Live 30-day public-real build at `2026-09-09T16:23:41.450Z`: **PASS**.
- BTCUSDT: 2,880 15m + 720 1h + 180 4h closed candles.
- ETHUSDT: 2,880 15m + 720 1h + 180 4h closed candles.
- SQLite direct audit: **7,560 total rows**, all 7,560 closed. Every dataset has zero
  duplicates, historical gaps, malformed rows, conflicts and unexpected open candles;
  all six report `fresh=true` and `backtest_ready=true`.
- An immediate second live build preserved 7,560 rows and all six health gates, confirming
  runtime idempotency for the same interval boundaries.
- The SQLite artifact remains ignored. The path-free deterministic manifest is tracked at
  `manifests/p1-market-data.json`.
- Full suite: **111 passed, 0 failed** before the final documentation/manifest audit.
- No `.env`, credential, Testnet account, user stream, order endpoint or execution logic was used.
- P1-009 checkpoint: `fa4de2d` with a clean working tree.
- P1-010 then performed the final P1 audit recorded below. P2 remained unopened.

## P1-010 final audit — 2026-09-09

Status: **P1 RUNTIME ACCEPTED**. This change is the final checkpoint baseline; P2 has
not started.

- Entry audit: HEAD `fa4de2d`; branch `main`; working tree clean.
- `uv run --locked python -m unittest discover -s tests -v`: **117 passed, 0 failed**.
- `uv lock --check`: PASS; two locked packages resolved without lock changes.
- `uv run --locked python -m compileall -q yatl`: PASS.
- A new empty SQLite file and manifest were used for a 30-day `dataset-build`. The build
  returned 2,880/720/180 closed rows for 15m/1h/4h for each of BTCUSDT and ETHUSDT;
  all six reports returned `backtest_ready=true`.
- The identical build was run immediately against the same SQLite file. Counts remained
  2,880/720/180 per symbol/timeframe and the manifest gate passed, demonstrating runtime
  idempotency without duplicate rows.
- Direct SQLite verification after the second build: schema version 1; 7,560 total rows;
  7,560 distinct canonical keys; 0 open rows.
- `python -m yatl p1-audit` passed for both the fresh audit manifest and tracked
  `manifests/p1-market-data.json`: 6 datasets, 7,560 closed rows, 30 days. Tests prove
  malformed, oversized, incomplete, duplicate-identity and unhealthy manifests fail closed.
- Live `data-check`: PASS; Binance Spot public time returned; BTCUSDT and ETHUSDT were
  `TRADING` and returned two 1h klines each.
- Live `history-check`: PASS; all six symbol/timeframe pairs returned two closed-range rows
  in two pages, exercising real pagination.
- Live `normalize-check`: PASS; all six pairs normalized two rows as `closed,open`.
- Live bounded WebSocket checks: PASS for BTCUSDT 1h and ETHUSDT 15m; each accepted one
  public kline into memory with zero reconnects and zero backfilled rows.
- Human and deterministic JSON `health-check` formats: PASS with
  `backtest_ready=true`; the required nonzero failure behavior remains covered by tests.
- Safety audit: `.env` is ignored and untracked; `data/p1/market.sqlite3` is ignored;
  authenticated production code contains only the exact Spot Testnet
  `GET /api/v3/account`; no order, order-list, withdrawal, Futures or user-stream route
  exists; `yatl/data/` has no authenticated-account import.
- `git diff --check`: PASS before final documentation update. No credential, raw account
  response, API key, secret, signature or signed URL was printed or persisted.

Accepted scope remains BTCUSDT + ETHUSDT, Spot only, 1h primary, 4h regime and 15m
context. 5m remains disabled. PAPER ONLY, LIVE_MASTER_LOCK=OFF, NO FUTURES, NO LEVERAGE,
NO WITHDRAWAL API and NO AI DIRECT EXECUTION remain enforced. TRADE permission remains
disabled and no execution endpoint was added.

## P2-001 evidence — 2026-09-09

Status: **IMPLEMENTED — CHECKPOINT PENDING**.

- Entry baseline: P1 final checkpoint `4e77e34`; branch `main`; working tree clean.
- Added an immutable BacktestSpec for BTCUSDT/ETHUSDT with aligned 1h ranges, explicit
  initial cash, fee and slippage Decimal strings, and a bounded deterministic seed.
- Safety fields fail closed unless paper-only, Spot-only, long-only, unleveraged and
  `LIVE_MASTER_LOCK=OFF`. The execution-price policy is fixed to `NEXT_PRIMARY_OPEN`.
- Added a point-in-time MarketSnapshot for synchronized 1h primary, 15m context and 4h
  regime histories. Inputs must be closed, contiguous, ordered, current at the decision
  boundary and strictly earlier than the decision time.
- Focused contract suite: **7 passed, 0 failed**.
- Full suite after implementation: **124 passed, 0 failed**; lock and compile checks passed.
- `python -m yatl backtest-contract-check`: PASS; verified a local point-in-time snapshot
  and next-primary-open policy without network, credentials or exchange orders.
- P2 delivery order and acceptance gates are fixed in `P2-IMPLEMENTATION-PLAN.md`.
- P2-002 has not started. P2 as a whole is not accepted; P3 remains unopened.

## P2-002 evidence — 2026-09-09

Status: **ACCEPTED — checkpoint `cc1a735`**.

- P2-001 checkpoint: `30a6e6d` with a clean working tree.
- Added manifest-gated, read-only SQLite loading. The accepted P1 manifest is snapshotted,
  passed through `p1-audit` and checked for changes before any candle is exposed.
- The loader verifies schema version, exact report range/count/grid, canonical identity and
  closed state. It rejects missing data, open rows, corrupt candle state, invalid paths,
  out-of-range specifications and database/manifest disagreement.
- `snapshot_at(t)` returns only candles with `close_time_ms < t`; future database rows remain
  outside the returned point-in-time view.
- Focused loader suite: **5 passed, 0 failed**.
- Full suite after implementation: **130 passed, 0 failed**; lock and compile checks passed.
- Runtime BTCUSDT load: PASS; stored 720/2,880/180 rows for 1h/15m/4h and the first
  24-hour-run snapshot exposed only the legal 696/2,783/174-row prefixes.
- Runtime ETHUSDT load: PASS with the same stored and visible counts.
- SQLite was opened with `mode=ro`; no network, credential or exchange order was used.
- P2-003 has not started. P2 as a whole is not accepted; P3 remains unopened.

## P2-003 evidence — 2026-09-09

Status: **IMPLEMENTED AND RUNTIME VERIFIED — CHECKPOINT PENDING**.

- P2-002 checkpoint: `218a06e` with a clean working tree.
- Added a lazy deterministic event clock over the exact half-open BacktestSpec range.
  Sequence numbers begin at zero, increase once per aligned 1h boundary and never emit
  the exclusive end boundary.
- Every DecisionEvent carries the legal point-in-time MarketSnapshot and identifies the
  same timestamp as the earliest eligible next-primary-open fill. The current candle price
  is not present in the decision snapshot.
- Invalid datasets, event fields or a snapshot gate failure stop the clock safely.
- Focused clock suite: **6 passed, 0 failed**.
- Full suite after implementation: **136 passed, 0 failed**; lock and compile checks passed.
- Runtime BTCUSDT 24-hour replay: PASS; 24 events from `1788883200000` through
  `1788966000000`; immediate second replay was equal.
- Runtime ETHUSDT 24-hour replay: PASS with the same event boundaries and equality gate.
- No network, credential, random wall-clock input or exchange order was used.
- P2-004 has not started. P2 as a whole is not accepted; P3 remains unopened.

## P2-004 evidence — 2026-09-09

Status: **IMPLEMENTED AND RUNTIME VERIFIED — CHECKPOINT PENDING**.

- P2-003 checkpoint: `275a163` with a clean working tree.
- Added strict HOLD, ENTER_LONG and EXIT_LONG paper intents. Entry requires positive Decimal
  quantity and a Stop/Target bracket around the next 1h open; Short and overlapping long
  positions have no representation and are rejected.
- FillReference records are explicitly uncosted inputs for P2-005. They can only use the
  event's eligible next-primary-open time and must match the engine, snapshot and candle symbol.
- Scripted exit fills at the next open. Protective Stop/Target processing then uses known
  opening gaps first; when both thresholds are touched intrabar, Stop wins conservatively.
- Same-bar entry protection is supported. Total reference quantity cannot exceed the candle's
  base volume; any failure restores the preceding engine position state.
- Focused fill suite: **9 passed, 0 failed**.
- Full suite after implementation: **145 passed, 0 failed**; lock and compile checks passed.
- `python -m yatl backtest-fill-check`: PASS; two local references ended with
  `AMBIGUOUS_STOP_PRIORITY` and explicitly reported `costs_pending=P2-005`.
- No network, credential, account transport or exchange order was used.
- P2-005 has not started. P2 as a whole is not accepted; P3 remains unopened.

## P2-005 evidence — 2026-09-09

Status: **IMPLEMENTED AND RUNTIME VERIFIED — CHECKPOINT PENDING**.

- P2-004 checkpoint: `2d8940b` with a clean working tree.
- Added self-validating CostedFill records. Entry slippage raises the reference price; exit
  slippage lowers it. Quote fees apply to the slipped gross value on every fill.
- Exact cash and asset deltas, fee quote and adverse slippage quote use Decimal inside a
  256-digit local context. Binary floating-point values are rejected.
- Hand-calculated quantity-2, price-100 vectors at 10 bps fee and 5 bps slippage pass:
  entry cash `-200.30010`, exit cash `199.70010`, round-trip cash `-0.60000`.
- Focused cost suite: **7 passed, 0 failed**. It covers zero/1,000-bps bounds, cost
  monotonicity, 40-digit price × 40-digit quantity without rounding, symbol mismatch and
  post-construction arithmetic tampering.
- Full suite after implementation: **152 passed, 0 failed**; lock and compile checks passed.
- `python -m yatl backtest-cost-check`: PASS; two references produced fee `0.1950025`,
  adverse slippage `0.0975` and net cash delta `-5.2925025`.
- No network, credential, account transport or exchange order was used.
- P2-006 has not started. P2 as a whole is not accepted; P3 remains unopened.

## P2-006 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `cd29f65`**.

- P2-005 checkpoint: `2b50013`; clean entry tree.
- Added exact cash, asset, cost-basis, realized/unrealized PnL, conservative liquidation
  equity, fee/slippage totals and closed-trade accounting.
- Rejects insufficient cash, duplicate/partial/out-of-order or wrong-symbol fills and cost
  policy mismatch. Batch failures restore the complete preceding ledger state.
- Focused suite: **7 passed, 0 failed**.
- Full suite after implementation: **159 passed, 0 failed**; lock and compile checks passed.
- `backtest-portfolio-check`: PASS; initial `1000` became cash/equity `999.4000000`,
  realized PnL `-0.6000000`, one closed trade, and zero asset balance.
- No network, credential or exchange order was used. P2-007 and P3 remain unopened.

## P2-007 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `4dbb26e`**.

- P2-006 checkpoint: `cd29f65`; clean entry tree.
- Added exact Decimal return, trade outcome, gross/net PnL, cost and drawdown metrics.
- Added non-annualized period mean, sample volatility, downside deviation and descriptive
  mean-to-risk ratios with explicit undefined-sample and zero-denominator handling.
- Metrics require an ordered, single-symbol lifecycle beginning clean and ending flat; invalid
  time, cost, realized-PnL or trade-count transitions fail closed.
- Focused metric suite: **8 passed, 0 failed**.
- Full suite after implementation: **167 passed, 0 failed**; lock and compile checks passed.
- `backtest-metrics-check`: PASS; the hand-computed profitable round trip reported gross PnL
  `20.0000000`, net PnL `19.3700100`, one winning trade and maximum drawdown `0.0006000`.
- No network, credential or exchange order is used. P2-008 and P3 remain unopened.

## P2-008 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `3a3c916`**.

- P2-007 checkpoint: `4dbb26e`; clean entry tree.
- Added canonical sorted JSON with fixed schema/engine identity, safety configuration,
  accepted-data hashes, input digest, reconciled trades, equity summary and metrics.
- Identical inputs produce byte-identical output; material candle or fill changes alter the
  SHA-256 input identity. Atomic replacement prevents publication of partial output.
- Local paths, credentials and run-time wall-clock fields are excluded and rejected.
- Focused artifact suite: **8 passed, 0 failed**.
- Full suite after implementation: **175 passed, 0 failed**; lock and compile checks passed.
- `backtest-artifact-check`: PASS; atomic write/read reproduced input SHA-256
  `f97ad5f66a8ac0ea1d59ee4a41e1238eb186008d961b612097069df4a21c62e4` with one
  reconciled trade and left no runtime artifact behind.
- No network, credential or exchange order is used. P2-009 and P3 remain unopened.

## P2-009 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `de63601`**.

- P2-008 checkpoint: `3a3c916`; clean entry tree.
- Added fixed no-trade, one-round-trip and three-trade schedules with no strategy signal.
  Fill prices use only the eligible current 1h open; every decision snapshot remains strictly
  point-in-time and excludes the current and future candle content.
- Focused scenario suite: **8 passed, 0 failed**. It covers exact trade counts, byte-identical
  replay, cost drag, future-field isolation, both symbols and fail-closed inputs.
- Full suite after implementation: **183 passed, 0 failed**; lock and compile checks passed.
- Runtime accepted-data matrix: **6/6 PASS** over the latest 24 hours for BTCUSDT and ETHUSDT.
  No-trade PnL was zero. Single/multi net PnL was `1.67995347405`/`-7.0106196582` BTC
  and `-0.151858701`/`-3.5036721285` ETH.
- Explicit fee/slippage drag was positive for every trading scenario: `2.36814652595` and
  `7.0942196582` BTC; `0.749858701` and `2.2466721285` ETH.
- No network, credential or exchange order was used. P2-010 is next; P3 remains unopened.

## P2-010 final acceptance evidence — 2026-09-10

Status: **P2 RUNTIME ACCEPTED — FINAL BASELINE CHECKPOINT READY**.

- P2-009 checkpoint: `de63601`; clean entry tree.
- Added an independent artifact audit that reconstructs every fill with the fixed fee/slippage
  policy, reconciles trade and portfolio totals, validates metric/equity summaries and
  recalculates both input and result SHA-256 digests.
- Final audit: **PASS** for 2 symbols, 6 real-data scenarios, 6 canonical artifacts and
  8 reconstructed completed trades. The accepted P1 manifest and P2 source safety scan passed.
- Artifact schema 2 / engine P2.2 adds a result digest and hardens Decimal output to plain
  exact strings; scientific notation is no longer emitted. Corrupt configuration, trade
  arithmetic, metrics, equity, JSON or digests fail closed.
- Focused P2-008/P2-009/P2-010 integration suites: **23 passed, 0 failed**.
- Complete repository suite: **190 passed, 0 failed**; lock and compile checks passed.
- All P2 runtime commands passed: point-in-time contract, accepted-data load and 24-event
  BTC/ETH clocks, conservative fills, costs, portfolio, metrics, artifact, scenario matrix
  and final audit.
- Safety remains: PAPER ONLY; `LIVE_MASTER_LOCK=OFF`; Spot long-only; no Futures, leverage,
  withdrawal, credential use, order endpoint or AI direct execution. P3 remains unopened.
- No blocker remains for the final P2 acceptance checkpoint.

## P3 planning baseline — 2026-09-10

Status: **PLANNED — IMPLEMENTATION NOT STARTED**.

- P2 final acceptance checkpoint: `9cbc197`; clean entry tree.
- Added `P3-IMPLEMENTATION-PLAN.md` with ten ordered delivery gates covering signal contracts,
  Decimal features, 4h regime, frozen registry, two transparent candidates, P2 adapter,
  anti-overfitting evaluation, accepted-data runs and final audit.
- Strategy output has no quantity, credential, broker or order interface. P4 owns sizing and
  risk controls; P5 owns any future paper/Testnet execution work.
- Framework acceptance is separate from performance evidence. The current 30-day dataset cannot
  alone justify a durable-edge claim and may only produce `INSUFFICIENT_EVIDENCE`.
- No P3 production code or strategy evaluation was started in this planning checkpoint.

## P3-001 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `9d83337`**.

- Planning checkpoint: `84fadcc`; clean entry tree.
- Added immutable strategy identity, point-in-time context, long setup and decision contracts.
  Actions are limited to `NO_TRADE`, `ENTER_LONG` and `EXIT_LONG`; reason codes are explicit.
- The context digest covers strategy identity/version, all visible 4h/1h/15m candles and the
  fixed paper-only safety policy. Material visible-data changes alter the SHA-256.
- P3 contracts contain no quantity, position size, account, credential, broker or order field.
- Focused contract suite: **9 passed, 0 failed**.
- Complete repository suite: **199 passed, 0 failed**; lock, compile and source safety scans passed.
- `strategy-contract-check`: PASS with deterministic context SHA-256
  `a0a540e025ab857ba626bdd4d4dc3b28e1dcbfd05807c755d57cf0a8441a6d9f`.
- No network, credential or exchange order was used. P3-002 is next; P4 remains unopened.

## P3-002 evidence — 2026-09-10

Status: **ACCEPTED — checkpoint `9412fd6`**.

- P3-001 checkpoint: `9d83337`; clean entry tree.
- Added point-in-time simple return, rolling high/low, SMA, EMA, Wilder ATR and Wilder RSI.
  All arithmetic uses a 256-digit local Decimal context; binary floating point is rejected.
- Every function requires an explicit decision time, declares warm-up and returns a typed
  unavailable result for insufficient history. Visible gaps, open candles and mixed identity
  fail closed.
- Future candle content and state are ignored at an earlier decision boundary; prefix-invariance
  tests cover all seven features. Zero volume and 40-digit price inputs remain valid.
- Focused feature suite: **9 passed, 0 failed**.
- Complete repository suite: **208 passed, 0 failed**; lock, compile and source safety scans passed.
- `strategy-feature-check`: PASS; seven features reproduced hand-computed SMA `12`, EMA `12.0`,
  ATR `2` and RSI `100`.
- No network, credential, sizing or exchange order was used. P3-003 is next; P4 remains unopened.

## P3-003 evidence — 2026-09-11

Status: **IMPLEMENTED AND RUNTIME VERIFIED — CHECKPOINT PENDING**.

- Entry checkpoint: `9412fd6`; verified clean tree.
- Frozen research rules SMA_4H_V1 use 20/50-close means, relative spread, one-bar slow-mean
  slope and price alignment. Exact formulas and inclusive range boundaries are in the P3 plan.
- Insufficient history and conflicting evidence remain UNKNOWN. Invalid point-in-time context
  is rejected; the result revalidates its measurements and rejects alteration.
- Focused suite: **8 passed, 0 failed**. Full suite: **216 passed, 0 failed**.
- Lock, compile, whitespace and strategy source transport/credential scans passed.
- Runtime `strategy-regime-check`: PASS on both accepted historical datasets, using
  174 closed 4h bars at decision time 1788883200000. BTCUSDT: UNKNOWN / CONFLICTING_EVIDENCE;
  ETHUSDT: TREND_UP / UP_ALIGNED; repeated results were equal.
- This is historical integration evidence, not live market analysis or strategy qualification.
- PAPER ONLY, LIVE_MASTER_LOCK=OFF and all execution restrictions remain in force.
  No network, account credentials or orders were used. P3-004 has not started.

## P3-004 evidence — 2026-09-11

- Entry checkpoint: `cc1a735`, main, clean working tree.
- Added immutable versioned registry, bounded numeric schema, canonical JSON and SHA-256.
- Nine registry tests cover canonicalization, material changes, exact types, range limits,
  unknown/missing/duplicate fields, registration versions, immutable input snapshots,
  fixed safety policy, tampering rejection and CLI output.
- Full suite: **225 passed, 0 failed**. Lock check and compileall: PASS.
- Runtime `strategy-registry-check`: **PASS**:
  `replay_equal=true changed_digest=true rejected=2`.
- Runtime is an offline metadata fixture. No market-performance or profitability claim.
- No network, credentials, sizing, exchange order or new dependency introduced.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
  NO WITHDRAWAL API; NO AI DIRECT EXECUTION. TRADE permissions unchanged.
- P3-004 runtime accepted in checkpoint `920ffaa`.

## P3-005 evidence — 2026-09-11

- Entry checkpoint: `920ffaa`, main, clean working tree.
- Added frozen `TREND_PULLBACK/1.0.0` research rules: 4h up-regime,
  closed 1h SMA(20) touch/reclaim, and closed two-candle 15m confirmation.
- Invalidation and 2R target derive only from visible 1h low and ATR(14).
  Existing research positions have explicit hold and exit decisions.
- Configuration SHA-256:
  `98301c6ee14e9ee01ffdbb1ca68cdce4c0ea0db6a504fc6e4e280bd9f027e20a`.
- Nine focused tests and the complete suite: **234 passed, 0 failed**.
  Lock check, compileall and restricted-source scan: PASS.
- Accepted historical runtime replay: BTCUSDT `NO_TRADE/REGIME_UNKNOWN`;
  ETHUSDT `ENTER_LONG/TREND_PULLBACK_ENTRY`; both replay-equal.
- The runtime result is an integration observation, not a profitability claim,
  recommendation or approval to trade. No rule was fitted to that result.
- No network request, credential, quantity, broker or exchange endpoint was added.
  PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
  NO WITHDRAWAL API; NO AI DIRECT EXECUTION. TRADE permissions remain disabled.
- P3-005 runtime accepted in checkpoint `a4a8ef8`.

## P3-006 evidence — 2026-09-11

- Entry checkpoint: `a4a8ef8`, main, clean working tree.
- Added independent frozen `RANGE_BREAKOUT/1.0.0`: 4h up-regime,
  preceding 20-bar 1h high, breakout quality and closed 15m confirmation.
- Invalidation and 2R target derive only from visible candle and prior ATR(14).
  False-breakout and regime-loss exits are deterministic.
- Configuration SHA-256:
  `03d9231addf92735bd3a1d4a956836277b54d0e514bbd9dec23b9dd123d77eea`.
- Nine focused tests and complete suite: **243 passed, 0 failed**.
  Lock check and compileall: PASS.
- Accepted historical replay: BTCUSDT `NO_TRADE/REGIME_UNKNOWN`;
  ETHUSDT `NO_TRADE/SETUP_ABSENT`; both replay-equal.
- Observations did not alter the frozen rules and do not establish profitability.
- No trend-strategy state, network request, credential, quantity, broker or
  exchange endpoint was added. PAPER ONLY; LIVE_MASTER_LOCK=OFF;
  NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API; NO AI DIRECT EXECUTION.
  TRADE permissions remain disabled.
- P3-006 runtime accepted in checkpoint `1e8ffb0`.

## P3-007 evidence — 2026-09-11

- Entry checkpoint: `1e8ffb0`, main, clean working tree.
- Added one-position strategy lifecycle and atomic adapter to the accepted P2
  next-open/protective fill engine.
- Candidate decisions map exactly to P2 HOLD/ENTER_LONG/EXIT_LONG intents.
  Duplicate, out-of-order, overlapping and invalid flat-state signals fail closed.
- Research quantity is fixed at `0.001` and cannot be passed to the adapter.
  It is a reproducible fixture, not account-based position sizing; P4 is unopened.
- Ten focused tests and complete suite: **253 passed, 0 failed**.
  Lock check, compileall and restricted-source scan: PASS.
- Runtime `strategy-adapter-check`: **PASS** and replay-equal; two fills,
  explicit fees/slippage, one closed paper trade and final quantity zero.
- P2 next-primary-open behavior and ambiguous Stop priority remain unchanged.
- No network, account, credentials, broker or exchange endpoint was added.
  PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
  NO WITHDRAWAL API; NO AI DIRECT EXECUTION. TRADE permissions remain disabled.
- P3-007 runtime accepted in checkpoint `2e43a12`.

## P3-008 evidence — 2026-09-11

- Entry checkpoint: `2e43a12`, main, clean working tree.
- Added frozen `P3_EVAL_V1` plans binding strategy version, parameter digest,
  separate training/evaluation windows, both symbols and three segments.
- Sample gates: at least 180 evaluation days, 30 trades per symbol and 60 pooled.
  Insufficient samples are not performance-ranked.
- Sufficient runs require replay, point-in-time and future isolation plus
  no-trade, Buy-and-Hold, drawdown and segment-stability gates for each symbol.
- Explicit labels: `INSUFFICIENT_EVIDENCE`, `REJECTED`,
  `QUALIFIED_FOR_P4_RESEARCH`; qualification is not trading approval.
- Twelve focused tests and complete suite: **265 passed, 0 failed**.
  Lock check, compileall and restricted-source scan: PASS.
- Future-cutoff test: mutations after evaluation end preserve the input digest;
  visible-data mutation changes it.
- Runtime reproduced all labels and the canonical report twice with SHA-256
  `c1e2c6a5c6a7d8a1b768122e2862d6a1eff83e5876126fd1650787f1449c97ec`.
- Runtime used deterministic fixtures to verify protocol logic. It did not
  evaluate profitability. Current accepted 30-day data is below the 180-day gate.
- No network, account, credential, sizing, broker or exchange endpoint added.
  PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
  NO WITHDRAWAL API; NO AI DIRECT EXECUTION. TRADE permissions remain disabled.
- P3-008 runtime accepted. Next: P3-009 accepted-data candidate runs; not started.

## P3-009 evidence — 2026-09-12

- Entry checkpoint: `1409bb6` on `main`; PR #1 was squash-merged after all runtime
  gates passed, producing checkpoint `013cbbc` on `main`.
- Added atomic reconstruction of the exact accepted public Spot checkpoint from
  the tracked P1 manifest. Runtime rebuilt six BTCUSDT/ETHUSDT datasets with
  **7,560 closed rows** and the unchanged manifest timestamp `1788971310603`.
- Added the deterministic four-run matrix for frozen `TREND_PULLBACK/1.0.0` and
  `RANGE_BREAKOUT/1.0.0`, each on BTCUSDT and ETHUSDT through the accepted P2
  paper clock, signal adapter, fills, costs, ledger, metrics and artifacts.
- Every run includes costed and zero-cost candidate artifacts, no-trade and
  Buy-and-Hold baselines, explicit cost drag, decision trace, input SHA-256,
  point-in-time proof and future-cutoff mutation proof: **21 files total**.
- GitHub Actions run `34687728494`: both candidate matrices completed and the
  recursive replay diff passed byte-for-byte. Evidence index SHA-256:
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
- `TREND_PULLBACK`: BTCUSDT 12 trades, ETHUSDT 19, pooled 31; report SHA-256
  `d2e4ec2d1c8064bf2c133439293880890a5fcf72a7f23329172d44b5e7f7be82`.
- `RANGE_BREAKOUT`: BTCUSDT 1 trade, ETHUSDT 3, pooled 4; report SHA-256
  `63be327a16cd922088923f108b964ff7d24d1a9a4cec6149669cb291c8dd99d0`.
- Both candidates are **`INSUFFICIENT_EVIDENCE`**, with frozen reasons
  `EVALUATION_WINDOW_TOO_SHORT` and `MINIMUM_TRADES_NOT_MET`. This is not a
  rejection, qualification, profitability claim or permission to trade. No
  parameter or window was changed after observing the results.
- Complete suite: **278 passed, 0 failed**. Compile, whitespace, `.env`, forbidden
  endpoint and strategy credential-import scans passed. The accepted-data job,
  two-run replay and evidence publication also passed.
- During runtime hardening, exact Decimal reconciliation and cost-drag arithmetic
  were made independent of ambient precision; evidence is quantized only at the
  explicit 40-decimal reporting boundary using deterministic half-even rounding.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P3-010 final audit evidence — 2026-09-12

- Entry checkpoint: `013cbbc` on `main`; PR #2 was squash-merged after all runtime
  gates passed, producing checkpoint `90d5847` on `main`.
- Added a fail-closed independent P3 audit that validates the accepted P1 manifest,
  source safety boundaries, frozen candidate configuration digests, exact expected
  evidence mapping and every embedded P2 artifact.
- The audit rejects missing, extra, changing, oversized or symlinked evidence and
  locks exact trade counts, report hashes, evidence labels and frozen reasons.
- GitHub Actions run `34699232936` restored six accepted datasets with **7,560
  closed rows**, ran the candidate matrix twice with a recursive byte-equal diff,
  then recomputed and audited it independently a third time.
- Every computation produced evidence index SHA-256
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
  Final audit: **2 candidates, 2 symbols, 4 runs, 21 files, 16 P2 artifacts,
  35 closed trades**.
- The complete suite passed **283/283**. Compile, whitespace, lock, `.env`, forbidden
  endpoint and credential-import gates passed; evidence publication also passed.
- Runtime exposed and closed one audit-contract gap: P2 now correctly accepts
  same-bar protective exits where `entry_time == exit_time`, matching the already
  accepted fill/artifact contracts, with a regression test.
- Both candidates remain **`INSUFFICIENT_EVIDENCE`** for
  `EVALUATION_WINDOW_TOO_SHORT` and `MINIMUM_TRADES_NOT_MET`. No parameter or
  evaluation window was changed after observing results.
- P3 framework runtime is accepted; this is not candidate qualification,
  profitability evidence or permission to trade. P4 has not started.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-001 implementation record — 2026-09-12

- Entry checkpoint: `90d5847` on `main`; PR #3 was squash-merged after all final
  gates passed, producing checkpoint `be3c042` on `main`.
- Frozen the sequential P4 plan and conservative `P4_RISK_V1` engineering policy.
- Added immutable policy, portfolio-state, risk-request and risk-decision contracts
  with canonical SHA-256 binding strategy context, evidence eligibility and exact
  point-in-time portfolio facts.
- Current P3 candidates are explicitly prevented from Paper entry approval while
  their label remains `INSUFFICIENT_EVIDENCE`.
- Kill Switch blocks entry approval but cannot block a matching risk-reducing exit.
- Ten focused tests and the complete suite passed **293/293** in GitHub Actions
  run `34700810982`. `risk-contract-check` deterministically returned
  `REJECT/EVIDENCE_NOT_QUALIFIED` for entry and `APPROVE_PAPER` for the matching
  exit under Kill Switch; request SHA-256:
  `af474a99f84d4303d092f1a9e86de74b444ac7938f38776573dca6910fbf3414`.
- Compile, whitespace, lock and restricted-source scans passed. The accepted P3
  evidence replay and final audit also passed with the unchanged index SHA-256
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
- This checkpoint adds contracts only; sizing, state transitions and circuit-breaker
  engines remain ordered future P4 steps and are not claimed complete.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.
- P4-001 is runtime accepted and merged.

## P4-002 implementation record — 2026-09-12

- Entry checkpoint: `be3c042` on `main`; PR #4 was squash-merged after all final
  gates passed, producing checkpoint `bc2bd30` on `main`.
- Added exact cost-aware loss-budget sizing for qualified Paper-only entry fixtures.
  Current `INSUFFICIENT_EVIDENCE` candidates fail closed before any quantity is
  calculated.
- Frozen costs match accepted P2 defaults: 10 bps fee and 5 bps adverse slippage
  on entry and stop. Quantity is rounded downward to the `0.000001` research step.
- The sizing result binds the P4 request SHA-256 and records adjusted prices, budget,
  loss per unit, fee, slippage and planned loss. Any tampering is rejected.
- Calculations use an isolated 256-digit Decimal context and are independent of
  ambient precision. Exposure, cash and notional limits remain P4-003 and no
  approval is emitted by this sizing step.
- Twelve focused sizing tests and the complete local suite passed **305/305**.
  Deterministic CLI, compile, whitespace, lock and restricted-source scans passed.
- GitHub Actions run `34702613220` passed **305/305** tests, deterministic sizing
  runtime, compile, whitespace, lock and restricted-source scans. Both P3 replays
  and the independent final audit passed with the unchanged evidence index.
- Qualified fixture runtime: quantity `9.708733`, risk budget `100.00`, planned
  loss `99.9999984436650`, request SHA-256
  `393d74071bc590b80ddbdc53ce6bcc250091e0b0b60b89f52fe907b548825590`.
- P4-002 is runtime accepted and merged.

## P4-003 implementation record — 2026-09-12

- Entry checkpoint: `bc2bd30` on `main`; work is isolated on branch
  `p4-003-exposure-limits`.
- Added an immutable cash/notional/exposure assessment bound to the P4-002 sizing
  result and original risk-request SHA-256.
- Entry notional includes adverse entry slippage; cash required also includes the
  entry fee. Insufficient cash is rejected without leverage.
- The prospective position must satisfy both the 25% single-position cap and the
  25% gross-exposure cap. Combined cap violations take deterministic precedence
  over cash shortage; all outputs are canonical and tamper-checked.
- This step emits PASS/REJECT assessment evidence only, never a risk approval or
  P2 intent. Point-in-time state transitions remain P4-004.
- Nine focused limit tests and the complete local suite passed **314/314**.
  Deterministic CLI, compile, whitespace, lock and restricted-source scans passed.
- GitHub Actions run `34714934702` passed both jobs: all **314/314** tests and
  safety gates, plus accepted-public-data reconstruction, two byte-equal candidate
  runs and the independent P3 audit. The unchanged evidence index SHA-256 is
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
- Exact limit runtime: `normal=PASS/WITHIN_LIMITS`,
  `low_cash=REJECT/CASH_INSUFFICIENT`, notional `1019.9266734825`, cap `2500.00`.
- P4-003 was runtime accepted and squash-merged from PR #5, producing checkpoint
  `27dfd86` on `main`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-004 implementation record — 2026-09-12

- Entry checkpoint: `27dfd86` on `main`; work is isolated on branch
  `p4-004-portfolio-session-state`.
- Added complete aligned hourly portfolio observations and deterministic immutable
  state transitions. Every state binds its observation and predecessor with
  canonical SHA-256 digests.
- State tracks UTC session start time/equity, session realized PnL, all-time peak
  equity, one-position gross Spot exposure and consecutive closed losses using an
  isolated 256-digit Decimal context.
- Duplicate, missing, stale, out-of-order and cross-symbol observations fail
  closed. Close/PnL mismatches, silent position changes, invalid UTC session resets
  and tampered transition results are rejected.
- The managed state projects validated facts into the accepted P4-001 contract;
  it does not activate circuit breakers, approve a trade or submit an order.
  Protective gates remain P4-005 and circuit breakers remain P4-006.
- Twelve focused state tests and the complete local suite passed **326/326**.
  Deterministic CLI, compile, whitespace, lock and restricted-source scans passed.
- GitHub Actions run `34717094100` passed both jobs: all **326/326** tests and
  safety/runtime gates, plus public-checkpoint reconstruction, two byte-equal
  candidate runs and the independent P3 audit. Evidence index SHA-256 remained
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
- Exact state runtime: sequence `2`, session PnL `-100`, consecutive losses `1`,
  gross exposure `0`, state SHA-256
  `1b6700b922e2f7f6693b381222c81ebc10a1362c01dc4eca576dc6cb02e05bd0`.
- P4-004 was runtime accepted and squash-merged from PR #6, producing checkpoint
  `99cd8d5` on `main`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-005 implementation record — 2026-09-13

- Entry checkpoint: `99cd8d5` on `main`; work is isolated on branch
  `p4-005-protective-cost-gate`.
- Added an immutable protective assessment bound to the accepted P4-003 limit
  evidence, P4-002 sizing result and original risk-request SHA-256.
- Independently recomputes adverse entry, stop and target execution prices, quote
  fees on both sides, worst planned stop loss and net target reward using the
  frozen P2 costs: 10 bps fee and 5 bps adverse slippage.
- Prior cash/notional/exposure rejection has deterministic priority. Otherwise,
  invalid protective levels, loss-budget breach and non-positive post-cost reward
  fail closed. Worst loss must exactly match the accepted sizing evidence.
- This gate emits canonical PASS/REJECT evidence and a material SHA-256 only; it
  cannot approve a trade, create a P2 intent or submit an order. Circuit-breaker
  decisions remain P4-006.
- Twelve focused gate tests, 55 focused P4 tests and the complete local suite
  passed **338/338**. Deterministic CLI, compile, whitespace, lock and restricted-
  source scans passed.
- Runtime normal fixture: `PASS/PROTECTIVE_GATE_PASSED`, worst loss
  `99.9999984436650`, net reward `93.8834966536650`, gate SHA-256
  `950dd5ed79315453701b122ddd2e3a93b9002d8c2e1628e5ba3e89d048718ae9`.
  A raw-positive weak target is rejected as `NON_POSITIVE_POST_COST_REWARD`.
- GitHub Actions run `34747422371` passed both jobs: all **338/338** tests and
  safety/runtime gates, plus public-checkpoint reconstruction, two byte-equal
  candidate runs and the independent P3 audit. Evidence index SHA-256 remained
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
- Final HEAD GitHub Actions run `34747781858` passed both jobs. P4-005 was
  squash-merged from PR #7 in checkpoint `41411ef`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-006 implementation record — 2026-09-13

- Entry checkpoint: P4-005 squash-merged in `41411ef`; implementation branch
  `p4-006-circuit-breakers`.
- Added an immutable circuit assessment bound to both the exact P4 risk-request
  SHA-256 and P4-004 managed-state SHA-256.
- Exact 256-digit Decimal checks trigger at session loss greater than or equal to
  2% of session-start equity and drawdown greater than or equal to 10% of peak
  equity. A streak triggers at three or more consecutive closed losses.
- Stable reason order is session loss, drawdown, then consecutive losses. Any
  active breaker blocks entry; `NO_TRADE` remains no action and risk-reducing exits
  remain allowed even when all three breakers are active.
- Recovery is observational and fail-closed: only a subsequent valid managed state
  below the relevant boundary clears it. A valid UTC session reset clears session
  loss; a recorded win or breakeven resets the streak. Latching and manual reset
  remain exclusively P4-007.
- Fourteen focused circuit tests, 69 focused P4 tests and the complete local suite
  passed **352/352**. Deterministic CLI, compile, whitespace, lock and restricted-
  source scans passed.
- Runtime fixture: `boundary=BLOCK_ENTRY/MULTIPLE_LIMITS`, triggered session-loss
  and consecutive-loss breakers, `recovered=CLEAR/WITHIN_LIMITS`, exact session
  loss `200/200.00`, circuit SHA-256
  `4ebfb40ed34e5157a25878e37ac1b51eb85feb42d7b179f57ba530dfa5c10180`.
- GitHub Actions run `34749363210` passed both jobs: all **352/352** tests and
  safety/runtime gates, plus public-checkpoint reconstruction, two byte-equal
  candidate runs and the independent P3 audit.
- Runtime public-data evidence remained 6 datasets, 7,560 closed rows, 2
  candidates, 2 symbols, 4 runs, 21 files, 16 P2 artifacts and 35 trades. Index
  SHA-256 remained
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a` and both
  labels remain `INSUFFICIENT_EVIDENCE`.
- Final HEAD GitHub Actions run `34749628926` passed both jobs. P4-006 was
  squash-merged from PR #8 in checkpoint `98320df`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-007 implementation record — 2026-09-13

- Entry checkpoint: P4-006 squash-merged in `98320df`; implementation branch
  `p4-007-kill-switch-state-machine`.
- Added explicit immutable `STARTUP`, `CIRCUIT_OBSERVATION` and `MANUAL_RESET`
  events with deterministic canonical SHA-256 identities.
- Startup is unconditionally fail-closed as `TRIGGERED/FAIL_CLOSED_STARTUP`.
  Sequence and event time must increase strictly, circuit evidence cannot be from
  the future, and duplicate or stale circuit state cannot be consumed twice.
- Any active circuit reason latches the switch and breaker reasons accumulate in
  stable policy order. A later clear observation records
  `LATCHED_UNTIL_MANUAL_RESET` and cannot reset automatically.
- Reset requires a triggered prior state, explicit manual confirmation and newer
  clear circuit evidence. The resulting state is hash-chained to its predecessor.
- The state flag blocks qualified entry through the existing P4 sizing boundary
  while an exact risk-reducing exit remains allowed.
- Thirteen focused Kill Switch tests, 82 focused P4 tests and the complete local
  suite passed **365/365**. Deterministic CLI, compile, whitespace, lock and
  restricted-source scans passed.
- Runtime lifecycle:
  `TRIGGERED/INACTIVE/TRIGGERED/TRIGGERED/INACTIVE`; startup reason
  `FAIL_CLOSED_STARTUP`; clear observation remains
  `LATCHED_UNTIL_MANUAL_RESET`; final state SHA-256
  `fba2237ec930c44a4e87b9be4fcb45baaa497e96ff279095d7b06047a0cd02ec`.
- Final HEAD GitHub Actions run `34754437777` passed both jobs: all **365/365** tests and every
  safety/runtime gate, plus public-checkpoint reconstruction, two byte-equal
  candidate runs and the independent P3 audit.
- Runtime public-data evidence remained 6 datasets, 7,560 closed rows, 2
  candidates, 2 symbols, 4 runs, 21 files, 16 P2 artifacts and 35 trades. Index
  SHA-256 remained
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`; both
  labels remain `INSUFFICIENT_EVIDENCE`.
- P4-007 was runtime accepted and squash-merged from PR #9 in checkpoint `e09dc0e`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-008 implementation record — 2026-09-13

- Entry checkpoint: P4-007 squash-merged in `e09dc0e`; implementation branch
  `p4-008-risk-adapter`.
- Added a deterministic `RiskAuthorization` that binds the P3 decision, P4 request,
  managed portfolio state, latest circuit evidence, Kill Switch state, optional
  protective assessment and recomputed final P4 decision.
- The guarded adapter accepts no raw strategy/risk decision. Qualified entry needs
  complete matching evidence, a clear latest circuit and an inactive Kill Switch;
  only the exact approved quantity can reach the P2 Paper adapter.
- Missing, insufficient or rejected entry evidence becomes `HOLD` without a fill.
  Exact position-reducing exits remain available under an active Kill Switch.
- Adapter state changes only after P2 succeeds, so a P2 failure is atomic and the
  same event can be retried. The accepted P3 research adapter remains unchanged and
  is not the P4 execution path.
- Sixteen adapter tests, 98 focused P4 tests and the complete local suite passed
  **381/381**. Deterministic CLI, compile and whitespace gates passed.
- Runtime approved entry quantity `18.894653`, blocked insufficient evidence,
  exited safely under Kill Switch and produced authorization SHA-256
  `3c65d4dca84c2ef17b73130461ee19552e3279a4b7a9753f0206fd8628b0ae72`.
- GitHub Actions run `34764015703` passed both jobs: all **381/381** tests, every
  safety/runtime gate, public-checkpoint reconstruction, two byte-equal candidate
  matrices and the independent P3 audit.
- Runtime public-data evidence remained 6 datasets, 7,560 closed rows, 2 candidates,
  2 symbols, 4 runs, 21 files, 16 P2 artifacts and 35 trades. Index SHA-256 remained
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`; both labels
  remain `INSUFFICIENT_EVIDENCE`.
- Final HEAD GitHub Actions run `34764434584` passed both jobs. P4-008 was
  squash-merged from PR #10 in checkpoint `b268fa7`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-009 implementation record — 2026-09-13

- Entry checkpoint: P4-008 squash-merged in `b268fa7`; implementation branch
  `p4-009-adversarial-scenarios`.
- Added eight pre-registered adversarial scenarios for each BTCUSDT and ETHUSDT
  accepted public Spot dataset: session-loss boundary, gap, post-cost rejection,
  consecutive-loss boundary, drawdown boundary, stale state, insufficient evidence
  and Kill Switch exit.
- Boundary, cost and evidence failures block entry without a fill. Gap and stale-
  state failures preserve adapter state atomically; the gap event can be retried.
  Exact risk-reducing exit remains available under an active Kill Switch.
- Each of 16 runs emits canonical JSON bound to policy, dataset/context digests and
  the full P4 evidence chain. The index is deterministic, the atomic writer refuses
  overwrite, and CI runs the matrix twice with a recursive byte comparison.
- Eleven scenario tests, 109 focused P4 tests and the complete local suite passed
  **392/392**. Compile and whitespace gates passed.
- GitHub Actions final HEAD run `34770395981` passed both jobs: all **392/392**
  tests, every safety/runtime gate, public-checkpoint reconstruction, two byte-equal P3 matrices,
  the independent P3 audit and two byte-equal 16-run P4 scenario matrices.
- P4 scenario index SHA-256 is
  `56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783`; the complete
  17-file evidence package was published as `p4-009-evidence`.
- Runtime public-data evidence remained 6 datasets, 7,560 closed rows and 35 P3
  trades. Both candidate labels remain `INSUFFICIENT_EVIDENCE`.
- P4-009 was runtime accepted and squash-merged from PR #11 in checkpoint
  `23b2f5b`.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P4-010 implementation record — 2026-09-13

- Entry checkpoint: P4-009 squash-merged in `23b2f5b`; implementation branch
  `p4-010-final-audit`.
- Added a separate fail-closed P4 auditor that freezes the canonical
  `P4_RISK_V1` policy digest, accepts exactly the expected 17 regular evidence
  files and rejects symlinks, extras, omissions, size violations, noncanonical
  JSON, forbidden secret material and changed internal/index SHA-256 values.
- The auditor independently checks exact decisions for all eight scenarios on
  both symbols, including boundary breakers, post-cost/evidence blocks, atomic
  gap and stale-state rejection, exact approved Paper quantity and the
  risk-reducing exit under active Kill Switch.
- It recomputes all 16 runs from the accepted BTCUSDT/ETHUSDT public Spot
  checkpoint and requires the complete evidence package to match byte-for-byte.
- Nine focused audit tests, 118 focused P4 tests and the complete suite passed
  **401/401**. Compile, lock, whitespace and restricted-source scans passed.
- GitHub Actions run `34771596172` passed both jobs. It rebuilt 6 datasets and
  7,560 closed rows, reproduced both 16-run P4 matrices byte-for-byte and passed
  the independent 16-run/17-file final P4 audit with exact decisions and replay
  equality.
- The evidence index SHA-256 remains
  `56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783`; frozen
  policy SHA-256 is
  `cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7`.
- Final HEAD GitHub Actions run `34771969717` passed both jobs with **401/401**
  tests and unchanged deterministic evidence. P4-010 was squash-merged from PR
  #12 in checkpoint `f3a5575`; P4 is closed and P5 remains unopened.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P5 planning baseline — 2026-09-13

Status: **PLANNED BEFORE IMPLEMENTATION**.

- Entry baseline: authoritative `main` commit `c0d94d2`; P4 checkpoint `f3a5575`.
- The unchanged baseline suite passed **401/401** locally before P5 work.
- `P5-IMPLEMENTATION-PLAN.md` freezes ten ordered checkpoints for local Paper
  contracts, journal/idempotency, lifecycle, P2 fills, portfolio projection,
  reconciliation, recovery, CLI, adversarial scenarios and final audit.
- `OPEN-SOURCE-DESIGN-REFERENCES.md` records official repository, license and exact
  reference SHA for NautilusTrader, Jesse, Freqtrade, Hummingbot and CCXT.
- No external source code was copied and no dependency or lockfile changed.

## P5-001 implementation record — 2026-09-13

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `5577471`**.

- Added immutable `P5_LOCAL_PAPER_V1` policy. It rejects any external transport,
  credential, order endpoint, leverage, withdrawal, AI execution or master-lock
  change.
- Recovery readiness defaults to
  `RECOVERY_REQUIRED/FAIL_CLOSED_STARTUP`. A ready state requires a canonical
  reconciliation SHA-256; failed reconciliation remains not ready.
- Only a reconstructable P4 `RiskAuthorization` is accepted. Raw strategy/risk
  decisions and forged authorization inputs fail closed.
- Qualified entry and risk-reducing exit fixtures remain `HOLD` until recovery is
  ready. After ready evidence, their exact P4 quantities are preserved in a
  local-only authorization. No effect, fill, persistence or network request is
  performed by P5-001.
- Current `INSUFFICIENT_EVIDENCE` entry remains
  `BLOCKED/RISK_NOT_APPROVED` regardless of recovery readiness.
- Thirteen focused tests and the complete suite passed **414/414** locally.
- Deterministic runtime recorded qualified quantity `18.894653` and decision
  SHA-256
  `4de1cda05b4dd3778e5dd18e1b8f633b76e77e8ba0572e6d1e4ce2e819c51f05`.
- Compile, whitespace, locked sync and restricted-source scans passed. `uv.lock`
  SHA-256 remained
  `03cbb4101a3f90b2f387d82295f835fff607f53b4476059e01c7f0c8d85e289b`.
- Final-HEAD GitHub Actions run `34782981428` passed both `unit-and-safety` and
  `accepted-public-data` on commit `b665f2b`. This included **414/414** complete
  tests, **13/13** focused P5-001 tests, the safety scan, P5 runtime, deterministic
  replay and independent P3/P4 audits.
- PR #14 was squash-merged into `main` at checkpoint
  `557747194fe8cdda75704d1bc3d067901f184450`. P5-001 is runtime accepted and
  merged; P5-002 subsequently opened and completed as recorded below.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P5-002 implementation record — 2026-09-14

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `ab9d38a`**.

- Added a standard-library SQLite journal that accepts only a reconstructable
  `ACCEPT_LOCAL_PAPER` P5 decision; blocked, no-action, raw and forged inputs fail
  before a write.
- The P4 authorization SHA-256 is the unique durable local-effect identity.
  Identical retry returns the verified existing record; changed readiness/decision
  evidence for the same authorization conflicts and rolls back.
- The journal transactionally creates one record, verifies stored fields and digest
  on every read/export, rejects newer schemas and exports stable sorted canonical
  JSON. SQLite binary bytes are not deterministic evidence.
- Twelve focused tests passed rollback-after-insert, uniqueness, reopen, canonical
  export, four concurrent duplicate attempts with one committed effect, tampering,
  schema drift and safe CLI behavior.
- The complete local suite passed **426/426**. Compile, whitespace, lockfile and
  restricted-source gates passed; `uv.lock` and dependencies are unchanged.
- `paper-execution-journal-check` recorded `effects=1`, `replay_equal=true`,
  `reopen_equal=true`, exact quantity `18.894653`, intent SHA-256
  `206920d659e27113762959457eb88e7124582eb365963694fbd70c56af4e620a` and canonical
  evidence SHA-256
  `fd7aa4412b9c2fd6b10a5167465aae27bee0d515cf02cf8e7112ea435b881cb6`.
- Final-HEAD GitHub Actions run `34899971951` passed both
  `unit-and-safety` and `accepted-public-data` on commit `b498759`, including
  **426/426** tests, locked sync, compile/whitespace, restricted-source scans,
  P5-001/P5-002 runtimes and deterministic accepted-data replay/audits.
- PR #16 was squash-merged into `main` at checkpoint
  `ab9d38a55688f772c2c7ca166584e0978fd6163d`. P5-002 is runtime accepted and
  merged; P5-003 subsequently opened and completed as recorded below.
- No P2 fill, order lifecycle, external transport, endpoint or permission was
  added. PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE;
  NO WITHDRAWAL API; NO TRADE PERMISSION; NO ORDER ENDPOINTS;
  NO AI DIRECT EXECUTION.

## P5-003 implementation record — 2026-09-15

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `c96293f`**.

- Added a separate local-only order schema for reconstructable P5-002 intents.
  The only path is `PENDING_LOCAL` → `ACTIVE_LOCAL` → `CANCELLED_LOCAL`; no fill
  or remote venue state is represented.
- Every event carries a fixed immutable reason, a strictly increasing sequence and
  timestamp, the previous event SHA-256 and its own canonical SHA-256. Replay
  verifies the complete chain and current materialized projection.
- Impossible, skipped, duplicate, stale, out-of-order, intent-mismatched and
  tampered events fail closed. Event insertion and state projection update use one
  `BEGIN IMMEDIATE` transaction; injected post-insert failure leaves neither
  durable event nor projected state.
- Fourteen focused tests and the complete local suite passed **440/440**. Compile,
  whitespace, lockfile and restricted-source gates passed; `uv.lock` and
  dependencies are unchanged.
- `paper-order-state-check` recorded three events, replay equality, final state
  `CANCELLED_LOCAL`, final-state SHA-256
  `a5d3bbee2a561b5a195ef92e3c6c5a08f3442a2e91bc0fe2c25d54bbdbdb9796` and
  canonical evidence SHA-256
  `6364285fae61a03cacde2f20bf5e42a0c6f4f7e674b387c76a68973dee8f25fe`.
- Implementation-head GitHub Actions run `35029425081` passed both
  `unit-and-safety` and `accepted-public-data` on commit `fbca913`, including
  **440/440** tests, runtime, safety, deterministic replay and independent audits.
- Final-HEAD GitHub Actions run `35029938678` passed both jobs on commit `f52b0ff`
  with the same **440/440** complete suite and deterministic evidence. PR #18 was
  squash-merged into `main` at checkpoint
  `c96293f038436258a30c9030cbce778750180c1f`. P5-003 is runtime accepted and
  merged; P5-004 subsequently opened as the candidate recorded below.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P5-004 accepted implementation record — 2026-09-16

Status: **RUNTIME ACCEPTED AND MERGED**.

- Added a local-only adapter that requires matching reconstructable P5 execution
  decision, durable intent and active P5-003 order state before calling P2.
- Reuses the accepted P2 `PaperFillEngine` and `apply_costs` directly; no alternate
  fill, fee, slippage, same-bar or volume economics were implemented.
- Executes P2 against a temporary engine copy and commits state only after all fill
  references and costs succeed. Missing, open, future, gapped, low-volume,
  out-of-bracket and cost-policy-mismatched inputs fail without a partial position.
- Exact P4-approved quantity `18.894653` reaches both the P2 intent and fill. Entry
  and exit complete flat; the accepted ambiguous same-bar rule remains stop-first.
- Fifteen focused P5-004 tests, **54/54** focused P5 regressions and the complete
  local suite passed **455/455**. Compile, whitespace, lockfile and restricted-source
  gates passed; `uv.lock` and dependencies are unchanged.
- `paper-fill-cost-check` recorded `steps=2`, `fills=2`, `replay_equal=true`, exact
  total cost quote `5.6967284321735` and canonical evidence SHA-256
  `504156f0bdd29bc276e404021deabd63518f5404c315ea13a3a281c23a9a3d79`.
- Implementation-head GitHub Actions run `35056541281` passed both
  `unit-and-safety` and `accepted-public-data` on commit `f0e4f0f`.
- Final-HEAD GitHub Actions run `35056981878` passed both jobs on commit `b8f113e`,
  including **455/455** tests, runtime, safety, deterministic replay and independent
  audits. PR #20 was squash-merged into `main` at checkpoint
  `ce655d0535ce9b8bac22c6525e68e115ea8626f2`. P5-004 is runtime accepted and
  merged; P5-005 remains unopened.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P5-005 accepted implementation record — 2026-09-16

Status: **RUNTIME ACCEPTED AND MERGED**.

- Added canonical, order-bound local fill-event identities for accepted P5-004
  costed fills. Each event is bound to the durable intent, active local order-state
  digest, P5-004 fill-step digest and deterministic batch index.
- Added one SQLite transaction for the complete fill batch and materialized cash,
  asset, cost basis, position, realized/unrealized PnL, equity, fees, slippage and
  closed-trade projection. Failure at either fill or projection write boundary
  rolls back every row.
- Every operation replays durable fills through the accepted P2 `PortfolioLedger`
  before mutation. Duplicate fills, insufficient cash, exit without position,
  changed spec, invalid mark price, tampered fill/order/projection evidence and
  newer or missing schema fail closed.
- Sixteen focused P5-005 tests, **70/70** focused P5 regressions and the complete
  local suite passed **471/471**. No dependency or `uv.lock` change exists.
- `paper-portfolio-check` recorded two fills, duplicate rejection, deterministic
  reopen, final `FLAT` position, cash `10013.1979245678265`, realized PnL
  `13.1979245678265`, projection SHA-256
  `11af7bcf91cd47e1809562f1b04f28c714676643f81e99fbfcfd0546ba93df09` and
  evidence SHA-256
  `03a52caa7914d711a4c8634dcf7f29b366cd1af9b98f0058cb9458f9252bd921`.
- Implementation-head GitHub Actions run `35142189459` passed both
  `unit-and-safety` and `accepted-public-data` on commit `f5f2392`, including
  **471/471** tests, runtime, safety, deterministic replay and independent audits.
- Final-HEAD GitHub Actions run `35142873676` passed both jobs on commit `919d331`.
  PR #22 was squash-merged into `main` at checkpoint
  `39e83aedae4ec3b29345bb23ee121bb77e4bd8f8`. P5-005 is runtime accepted and
  merged; P5-006 remains unopened.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.


## P5 final closeout — 2026-09-19

Status: **P5 RUNTIME ACCEPTED AND MERGED — PHASE CLOSED**.

Ordered final checkpoints:
- P5-008 PR #26: clean post-rebase final-head `0b93f908...`; Actions
  `35443813531` PASS; **506/506** complete and **13/13** focused; squash-merged
  at `9189033a2d57b89f35b47c773e19b47c675328a0`.
- P5-009 PR #27: clean post-P5-008 rebase HEAD `43999ae6...`; Actions
  `35449469004` PASS; deterministic 18-scenario matrix and byte-identical replay;
  squash-merged at `8a0fd0ec5950e85f16089ea53e74a36d57dfc9ed`.
- P5-010 PR #28: clean post-P5-009 rebase HEAD `e9e019d8...`; Actions
  `35449752993` PASS; **524/524** complete and **9/9** focused independent-audit
  tests; squash-merged at final P5 checkpoint
  `cd5ff5651e2d1df509dba6de8bc717a3ba7bf34f`.

Final P5 independent audit:
- symbols=2, scenarios=9, runs=18, evidence files=19;
- exact_outcomes=true;
- replay_equal=true;
- source_safe=true;
- P5-009 evidence index SHA-256:
  `7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa`;
- P5 execution-policy SHA-256:
  `d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72`.

Safety status remains unchanged: PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES;
NO LEVERAGE; NO WITHDRAWAL API; NO TRADE PERMISSION; NO ORDER ENDPOINTS;
NO AI DIRECT EXECUTION. Current P3 candidate strategies remain
`INSUFFICIENT_EVIDENCE`; P5 engineering fixtures are not strategy-readiness evidence.

Next phase: **P6 AI Analyst**. P6 begins analysis-only and may not call or influence
the P5 executor directly.


## P6 final closeout — 2026-09-20

Status: **P6 RUNTIME ACCEPTED AND MERGED — PHASE CLOSED**.

- P6-009 PR #38 final-head `200097635eeb12135b7c4d26f4045527aeed0145`;
  Actions `35503798774` PASS; **690/690** complete and **13/13** focused;
  deterministic 16-run adversarial matrix with byte-identical replay; squash-merged
  at `9ece941fe79139d55c5c349c3774720563a4ef28`.
- P6-010 PR #39 final-head `b3a3c677eed854ee9738e67d5c06dcb96236be22`;
  Actions `35504753305` PASS; **703/703** complete and **13/13** focused
  independent-audit tests; squash-merged at final P6 checkpoint
  `f07f2209cac5b46be8f9d74da2d162925ed8ab65`.
- Final P6 independent audit: symbols=2, scenarios=8, runs=16, files=17,
  exact_outcomes=true, replay_equal=true, source_safe=true.
- P6-009 index SHA-256:
  `a5a09bdde1600c706bdc3665b46f334ae04fd5fc4fe364613cc9ed7913018524`.
- P6 analyst-policy SHA-256:
  `355ad5a2ed274878db4c9a56e15b14548ee6ba0c16016c7cc3b04b02120bbe44`.
- P6 evidence-manifest SHA-256:
  `93dd09b73d439ed60b781f38783f2fb716689210ad66fb7ed5a395ed7b5b5f0f`.
- P3 remains `INSUFFICIENT_EVIDENCE` for TREND_PULLBACK and RANGE_BREAKOUT.
- PAPER ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO WITHDRAWAL API;
  NO TRADE PERMISSION; NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

Next phase: **P7 Journal / Analytics**. P7 is read-only over accepted durable
evidence and may not modify P5/P6 journals or create execution authority.

## P7 planning baseline — 2026-09-20

Status: **PLANNED BEFORE IMPLEMENTATION**.

- Entry baseline: authoritative `main` commit
  `f07f2209cac5b46be8f9d74da2d162925ed8ab65`.
- `P7-IMPLEMENTATION-PLAN.md` freezes ten ordered checkpoints for analytics
  policy/contracts, read-only ingestion, unified timeline, trade reconstruction,
  performance metrics, segmentation, reconciliation/quality, guarded export/CLI,
  adversarial matrix and independent final audit.
- P7 must consume only accepted/canonical P5/P6 evidence or explicit immutable
  fixtures; it cannot mutate upstream SQLite journals.
- P7 outputs are descriptive analytics only and cannot upgrade P3
  `INSUFFICIENT_EVIDENCE`, create RiskAuthorization, quantity, order, permission
  changes or Live readiness.
- No code, dependency or lockfile change is part of this planning closeout.


## P7-001 accepted implementation — 2026-09-20

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `53e3cde`**.

- Entry baseline: P6 closeout plan merge checkpoint
  `99198e33713517f7257b3c1e5e1eb1d8275459bf`.
- Branch `p7-001-analytics-contracts` adds only immutable P7 policy/contracts,
  focused tests, an offline deterministic runtime gate and CI/safety coverage.
- Frozen policy ID: `P7_ANALYTICS_V1`; mode: `READ_ONLY_ANALYTICS`.
- Source identities are read-only, provenance-bound and restricted to BTCUSDT /
  ETHUSDT with strategy evidence fixed to `INSUFFICIENT_EVIDENCE`.
- Upstream journal-event references and P7-derived fields have explicit, distinct
  origins. Reports cannot create execution, risk, quantity or permission authority.
- No P5/P6 journal ingestion, persistence, metrics, CLI, dependency or lockfile
  change is included in this checkpoint.
- Final-head GitHub Actions run `35506503002` passed both jobs with **721/721**
  complete tests and **18/18** focused P7-001 tests.
- Runtime policy SHA-256:
  `534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9`;
  scope SHA-256:
  `11d3aaf68daf8299599cd7651e558ab5bb396a24167417e94205da98a574f4a2`;
  report SHA-256:
  `b59f847dd18e63f4d7f2022770ca27b66e79794cd354180de3a5988c4516e2ba`.
- PR #41 was squash-merged at
  `53e3cde1956b130c940aebc12adaaa4d905e132f`. P7-002 opened next.


## P7-002 accepted implementation — 2026-09-20

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `4059355`**.

- Entry checkpoint: P7-001 merged at
  `53e3cde1956b130c940aebc12adaaa4d905e132f`; implementation branch
  `p7-002-readonly-ingestion`.
- Adds bounded read-only ingestion for the accepted P5 intent journal and sanitized
  P6 analyst trace journal without importing execution/account/risk modules into
  P7 production code.
- Every source requires an expected raw SQLite SHA-256 and is opened with
  `mode=ro` and `PRAGMA query_only=ON`. File identity/stat is checked before
  and after ingestion; no path is emitted in the manifest.
- P5/P6 migration versions and exact relevant table schemas are checked. P5 intent
  digest bindings and P6 trace plus nested grounding bindings are independently
  verified before a canonical source digest is accepted.
- The manifest requires exactly one P5 and one P6 source, same symbol, unique sorted
  IDs and point-in-time observations not later than the snapshot. P3 remains
  `INSUFFICIENT_EVIDENCE`.
- Missing, empty, symlinked, oversized, changed, newer-schema, duplicate-path,
  tampered or provider/secret-bearing inputs fail closed.
- No dependency or `uv.lock` change; no upstream mutation, credential, network,
  provider, execution, RiskAuthorization, quantity, trade or order capability is
  added.


## P7-003 accepted implementation — 2026-09-20

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `9d22817`**.

- Entry checkpoint: P7-002 merged at
  `40593552a056bc0280fc9ce32ccb60efa817760b`; branch
  `p7-003-unified-timeline`.
- Builds a canonical read-only point-in-time timeline spanning P5 accepted intent
  identity, local order events, durable fill events, the portfolio projection and
  sanitized P6 analyst traces.
- P5 intent rows have no native timestamp; P7 does not invent one. Their timeline
  placement is explicitly `RELATED_ORDER_TIME` at the first durable order event.
  Other time bases are explicit: upstream order-event time, upstream fill time,
  last-fill time for the projection, and P6 source-observed time.
- P4/P5 risk/execution identities, intent/order/fill links and P6 request/bundle/
  input/report identities are retained as immutable SHA-256 relationships only.
- Order chains and derived order-state hashes are independently replayed. Fill
  identities must bind an accepted intent and historical ACTIVE_LOCAL state.
  Portfolio projection must bind the complete fill history and final fill.
- Orphan, duplicate, broken-chain, out-of-order, cross-symbol, future-linked and
  relationship-tampered material fails closed.
- No dependency or `uv.lock` change; no credentials, provider/network,
  upstream mutation, RiskAuthorization mutation, quantity, trade, order or AI
  execution authority is added.


## P7-004 accepted implementation — 2026-09-20

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `2fece9c`**.

- Entry checkpoint: P7-003 merged at
  `9d22817d0ac76c4e724120d9189de3100ef03b58`; branch
  `p7-004-completed-trades`.
- Reconstructs completed/open long-only local-Paper episodes from validated durable
  P5 fill and final portfolio evidence; no new fill, price or cost model is used.
- Every entry/exit record copies accepted P5 fill economics. Completed-trade
  realized PnL is only the exact sum of accepted entry/exit cash deltas and must
  reconcile to final P5 portfolio realized PnL. Fee/slippage totals and closed
  trade count must also reconcile exactly.
- Open accepted entries remain explicitly `OPEN` with no invented exit or
  realized PnL; LONG asset quantity and cost basis must match that entry.
- Includes a narrow P7-003 compatibility correction for the already-valid P5
  same-bar protective two-fill pattern; all existing digest/order/symbol/time
  fail-closed checks remain.
- Real accepted P5 test fixtures cover normal closed trade, still-open trade and
  same-bar protective exit.
- Fabricated final PnL, missing exits, orphan fills, overlapping episodes,
  cross-symbol sources and upstream mutation fail closed.
- No dependency or `uv.lock` change; no execution/backtest import in P7 trade
  production code, no credentials/network/provider, no RiskAuthorization or
  quantity authority, no TRADE permission/order endpoint and no AI execution.


## P7-005 accepted implementation — 2026-09-20

Status: **RUNTIME ACCEPTED AND MERGED — CHECKPOINT `7c623e8`**.

- Entry checkpoint: P7-004 merged at
  `2fece9cc70bf6762a24540311876eb6e6d2be51e`; branch
  `p7-005-performance-metrics`.
- Computes deterministic descriptive metrics only from reconstructed completed
  P7-004 Paper trades; open trades are flagged but excluded from completed-trade
  performance denominators.
- Gross return is capital-weighted from accepted execution `gross_quote` values;
  net return is accepted realized cash PnL divided by accepted entry cash outflow.
  Per-trade denominator bases are retained so the report self-recomputes exactly.
- Includes realized/gross PnL, fees, slippage, total cost, win/loss/breakeven
  counts, win rate, maximum cumulative-realized-PnL drawdown in quote units,
  holding-time aggregates and best/worst trade PnL.
- Empty/no-completed-trade inputs remain `INSUFFICIENT_DATA`; denominator-based
  metrics are `null`. No annualization, extrapolation, volatility score, forecast
  or profitability/readiness conclusion is produced.
- Decimal-only arithmetic, deterministic report SHA-256, replay/no-write,
  monotonic aggregate checks and report-tamper rejection are covered.
- No dependency or `uv.lock` change; no execution/backtest/account/risk import
  in P7 metrics production code, no credentials/network/provider, no
  RiskAuthorization/quantity authority, TRADE permission/order endpoint or AI
  execution.


## P7-006 current candidate — 2026-09-20

Status: **IMPLEMENTED — FINAL-HEAD CI / MERGE APPROVAL PENDING**.

- Entry checkpoint: P7-005 merged at
  `7c623e8056e2f7bc0ea319816ebb95d9cabf06e1`; branch
  `p7-006-evidence-segmentation`.
- Completed-trade analytics and sanitized P6 traces remain separate populations.
  Each dimension family must conserve every member exactly once with no duplicate
  membership.
- Trade partitions: symbol, strategy identity, evidence label. Durable P5 does
  not persist a strategy identifier, so strategy attribution is explicitly
  `UNATTRIBUTED_DURABLE_P5`; opaque hashes are not renamed into strategies.
  Evidence stays `INSUFFICIENT_EVIDENCE`.
- Analyst-trace partitions: disposition, grounding code and accepted/rejected
  state. No trade-to-analyst-disposition link or causal statement is invented.
- Stable segment IDs hash only population/dimension/value; exact membership and
  summary material use a separate segment SHA-256.
- Trade-segment summaries conserve accepted realized PnL, accepted fee/slippage
  cost and win/loss/breakeven counts.
- Report is bound to immutable P7-005 source metrics and canonical sanitized P6
  source SHA-256; replay and source files remain read-only.
- No dependency or `uv.lock` change; no execution/backtest/account/risk import,
  credentials/network/provider, RiskAuthorization/quantity authority, TRADE
  permission/order endpoint or AI execution.
