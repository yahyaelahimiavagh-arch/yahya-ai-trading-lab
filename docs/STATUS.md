# P0 status — 2026-09-05

Scope: local development foundation and public market-data collection.

- Python target: 3.12.14.
- Dependencies: Python standard library only.
- Default environment: Binance Spot Testnet.
- No credentials, account endpoints or order execution in the application.
- `uv lock --offline` and `uv sync --locked --offline`: passed with Python 3.12.14.
- Seven unit tests: passed, including CSV round-trip, overwrite protection, malformed candles, input checks and rate limits.
- CLI help: passed.
- Live CLI ping: connection failed in the current restricted execution environment; no live candle download verified in this delivery.
- Earlier Windows preflight returned HTTP 200 from Binance public and Spot Testnet ping endpoints, outside the restricted environment. That does not establish a successful integration run for this new CLI.
- Test scratch files were placed in the workspace because the restricted Windows session could not use Python's private temporary directories.
- GitHub remote has not been created or connected.

Reference: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market
