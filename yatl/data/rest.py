"""Credential-free Binance Spot public REST transport for P1."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .config import (BINANCE_MARKET_DATA_BASE_URL, BINANCE_PUBLIC_BASE_URL,
                     INTERVAL_MILLISECONDS, SYMBOLS)


ENDPOINT_PARAMETERS = {
    "/api/v3/time": frozenset(),
    "/api/v3/exchangeInfo": frozenset({"symbol"}),
    "/api/v3/klines": frozenset({"symbol", "interval", "limit", "startTime", "endTime"}),
}
MAX_RESPONSE_BYTES = 8_000_000
PUBLIC_BASE_URLS = (BINANCE_PUBLIC_BASE_URL, BINANCE_MARKET_DATA_BASE_URL)


class PublicRestError(Exception):
    """A stable public-data error that does not echo URLs or server payloads."""


class NoPublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicRestError("Public market-data redirects are forbidden")


def _positive_milliseconds(value, name):
    if type(value) is not int or value <= 0:
        raise PublicRestError(f"{name} must be a positive integer timestamp")
    return value


class BinancePublicRestClient:
    """Three allowlisted GET operations against the primary Binance Spot host."""

    def __init__(self, *, timeout=15, max_attempts=3, opener=None, sleeper=None,
                 base_url=BINANCE_PUBLIC_BASE_URL):
        if type(timeout) not in (int, float) or isinstance(timeout, bool) or not 1 <= timeout <= 30:
            raise ValueError("timeout must be between 1 and 30 seconds")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if base_url not in PUBLIC_BASE_URLS:
            raise ValueError("Public REST base URL is not allowlisted")
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._opener = opener or build_opener(ProxyHandler({}), NoPublicRedirects())
        self._sleep = sleeper or time.sleep
        self._base_url = base_url

    def _url(self, endpoint, params):
        if endpoint not in ENDPOINT_PARAMETERS:
            raise PublicRestError("Public REST endpoint is not allowlisted")
        if not isinstance(params, dict) or set(params) - ENDPOINT_PARAMETERS[endpoint]:
            raise PublicRestError("Public REST parameters are not allowlisted")
        query = urlencode(list(params.items()))
        url = self._base_url + endpoint
        return url + ("?" + query if query else "")

    @staticmethod
    def _retry_after(error):
        value = error.headers.get("Retry-After") if error.headers else None
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return 1
        return min(max(seconds, 1), 60)

    def _get(self, endpoint, params=None):
        url = self._url(endpoint, params or {})
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "YATL/0.1"}, method="GET")
        for attempt in range(1, self._max_attempts + 1):
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    if response.status != 200:
                        raise PublicRestError("Unexpected public REST status")
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise PublicRestError("Public REST response exceeds size limit")
                    return json.loads(raw)
            except HTTPError as error:
                code = error.code
                error.close()
                if code == 418:
                    raise PublicRestError("Binance public API IP ban; stop requests") from None
                if code == 429 and attempt < self._max_attempts:
                    self._sleep(self._retry_after(error))
                    continue
                if 500 <= code <= 599 and attempt < self._max_attempts:
                    self._sleep(0.25 * (2 ** (attempt - 1)))
                    continue
                if code == 429:
                    raise PublicRestError("Binance public API rate limit; retry later") from None
                raise PublicRestError("Binance public API rejected the request") from None
            except (URLError, TimeoutError, OSError):
                if attempt < self._max_attempts:
                    self._sleep(0.25 * (2 ** (attempt - 1)))
                    continue
                raise PublicRestError("Public market-data connection failed") from None
            except (ValueError, UnicodeError):
                raise PublicRestError("Public REST returned invalid JSON") from None
        raise PublicRestError("Public REST attempt limit reached")

    def server_time(self):
        payload = self._get("/api/v3/time")
        if not isinstance(payload, dict) or set(payload) != {"serverTime"}:
            raise PublicRestError("Unexpected server-time response")
        return _positive_milliseconds(payload["serverTime"], "serverTime")

    def exchange_info(self, symbol):
        if symbol not in SYMBOLS:
            raise PublicRestError("Unsupported exchange-info symbol")
        payload = self._get("/api/v3/exchangeInfo", {"symbol": symbol})
        if not isinstance(payload, dict) or payload.get("timezone") != "UTC":
            raise PublicRestError("Unexpected exchange-info response")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list) or len(symbols) != 1 or not isinstance(symbols[0], dict):
            raise PublicRestError("Unexpected exchange-info symbols")
        if symbols[0].get("symbol") != symbol or not isinstance(symbols[0].get("status"), str):
            raise PublicRestError("Exchange-info symbol mismatch")
        return {"symbol": symbol, "status": symbols[0]["status"], "timezone": "UTC"}

    def klines(self, symbol, interval, *, limit=1000, start_time=None, end_time=None):
        if symbol not in SYMBOLS:
            raise PublicRestError("Unsupported kline symbol")
        if interval not in INTERVAL_MILLISECONDS:
            raise PublicRestError("Unsupported kline interval")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise PublicRestError("Kline limit must be between 1 and 1000")
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = _positive_milliseconds(start_time, "startTime")
        if end_time is not None:
            params["endTime"] = _positive_milliseconds(end_time, "endTime")
        if start_time is not None and end_time is not None and start_time >= end_time:
            raise PublicRestError("Kline startTime must be earlier than endTime")
        payload = self._get("/api/v3/klines", params)
        if not isinstance(payload, list) or len(payload) > limit:
            raise PublicRestError("Unexpected kline response")
        if any(not isinstance(row, list) or len(row) != 12 for row in payload):
            raise PublicRestError("Unexpected kline row")
        return payload
