"""Fixed public GET endpoints; no account or order API support."""

import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

HOSTS = {
    "testnet": "https://testnet.binance.vision",
    "public": "https://api.binance.com",
}
INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
FIELDS = (
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_volume", "trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "unused",
)


class MarketDataError(Exception):
    """A concise error safe to display to the user."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get(environment, endpoint, params=None):
    if environment not in HOSTS or endpoint not in {"ping", "klines"}:
        raise ValueError("Unsupported environment or endpoint")
    url = f"{HOSTS[environment]}/api/v3/{endpoint}"
    if params:
        url += "?" + urlencode(params)
    try:
        with build_opener(NoRedirects()).open(url, timeout=15) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise MarketDataError("Response exceeds the size limit")
            return json.loads(raw)
    except HTTPError as exc:
        if exc.code in {418, 429}:
            raise MarketDataError("API rate limit: stop and retry later") from None
        raise MarketDataError(f"API returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise MarketDataError("Connection failed; check network, proxy and TLS") from None
    except (ValueError, UnicodeError):
        raise MarketDataError("API returned invalid JSON") from None


def ping(environment="testnet"):
    if _get(environment, "ping") != {}:
        raise MarketDataError("Unexpected ping response")


def candles(environment="testnet", symbol="BTCUSDT", interval="1h", limit=100):
    symbol = symbol.upper()
    if not re.fullmatch(r"[A-Z0-9]{5,30}", symbol):
        raise ValueError("Symbol must contain 5–30 letters or digits")
    if interval not in INTERVALS:
        raise ValueError("Unsupported candle interval")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000")
    result = _get(environment, "klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(result, list) or not result or len(result) > limit:
        raise MarketDataError("Unexpected candle response")
    previous_open = -1
    for row in result:
        if not isinstance(row, list) or len(row) != len(FIELDS):
            raise MarketDataError("Unexpected candle row")
        if any(type(row[i]) is not int or row[i] < 0 for i in (0, 6, 8)):
            raise MarketDataError("Invalid candle timestamps or trade count")
        if row[0] <= previous_open or row[6] < row[0]:
            raise MarketDataError("Candle timestamps are out of order")
        previous_open = row[0]
        try:
            values = [Decimal(str(row[i])) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
        except InvalidOperation:
            raise MarketDataError("Invalid candle numeric value") from None
        if any(not value.is_finite() or value < 0 for value in values):
            raise MarketDataError("Invalid candle numeric value")
        opened, high, low, close = values[:4]
        if not low <= min(opened, close) <= max(opened, close) <= high:
            raise MarketDataError("Inconsistent candle prices")
        if row[11] not in (0, "0"):
            raise MarketDataError("Unexpected reserved candle field")
    return result


def save_csv(rows, destination):
    """Preserve exchange decimal strings; never overwrite an existing file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return destination
