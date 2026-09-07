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
