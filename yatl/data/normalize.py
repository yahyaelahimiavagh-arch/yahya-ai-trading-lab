"""Normalize Binance Spot REST and WebSocket klines into one Candle contract."""

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from .models import Candle, CandleValidationError


class NormalizationError(Exception):
    """A market payload cannot be represented by the canonical contract."""


def _build_candle(*, symbol, interval, open_time, close_time, opened, high, low,
                  closed, base_volume, quote_volume, trade_count, is_closed):
    try:
        return Candle(
            source=DATA_SOURCE,
            symbol=symbol,
            interval=interval,
            open_time_ms=open_time,
            close_time_ms=close_time,
            open=opened,
            high=high,
            low=low,
            close=closed,
            base_volume=base_volume,
            quote_volume=quote_volume,
            trade_count=trade_count,
            is_closed=is_closed,
        )
    except (CandleValidationError, TypeError):
        raise NormalizationError("Kline payload violates the canonical candle contract") from None


def normalize_rest_kline(symbol, interval, row, server_time_ms):
    """Normalize one REST row; exchange server time determines closed state."""
    if symbol not in SYMBOLS or interval not in INTERVAL_MILLISECONDS:
        raise NormalizationError("Unsupported REST kline market or interval")
    if type(server_time_ms) is not int or server_time_ms <= 0:
        raise NormalizationError("A positive Binance server timestamp is required")
    if not isinstance(row, (list, tuple)) or len(row) != 12:
        raise NormalizationError("REST kline row must contain exactly 12 fields")
    if row[11] not in (0, "0"):
        raise NormalizationError("REST kline reserved field is unexpected")
    close_time = row[6]
    if type(close_time) is not int:
        raise NormalizationError("REST kline close timestamp is invalid")
    return _build_candle(
        symbol=symbol,
        interval=interval,
        open_time=row[0],
        close_time=close_time,
        opened=row[1],
        high=row[2],
        low=row[3],
        closed=row[4],
        base_volume=row[5],
        quote_volume=row[7],
        trade_count=row[8],
        is_closed=server_time_ms > close_time,
    )


def normalize_websocket_kline(payload):
    """Normalize one raw or combined public UTC kline stream event."""
    if not isinstance(payload, dict):
        raise NormalizationError("WebSocket kline payload must be an object")
    if set(payload) >= {"stream", "data"}:
        stream = payload.get("stream")
        event = payload.get("data")
        if not isinstance(stream, str) or not isinstance(event, dict):
            raise NormalizationError("Combined WebSocket wrapper is invalid")
    else:
        stream = None
        event = payload
    if event.get("e") != "kline" or type(event.get("E")) is not int:
        raise NormalizationError("WebSocket event is not a timestamped kline")
    symbol = event.get("s")
    kline = event.get("k")
    if symbol not in SYMBOLS or not isinstance(kline, dict):
        raise NormalizationError("WebSocket kline market is unsupported")
    required = {"t", "T", "s", "i", "o", "h", "l", "c", "v", "n", "x", "q"}
    if not required <= set(kline):
        raise NormalizationError("WebSocket kline fields are incomplete")
    interval = kline["i"]
    if kline["s"] != symbol or interval not in INTERVAL_MILLISECONDS:
        raise NormalizationError("WebSocket kline identity is inconsistent")
    if stream is not None and stream != f"{symbol.lower()}@kline_{interval}":
        raise NormalizationError("Combined WebSocket stream name is inconsistent")
    if type(kline["x"]) is not bool:
        raise NormalizationError("WebSocket closed state must be boolean")
    return _build_candle(
        symbol=symbol,
        interval=interval,
        open_time=kline["t"],
        close_time=kline["T"],
        opened=kline["o"],
        high=kline["h"],
        low=kline["l"],
        closed=kline["c"],
        base_volume=kline["v"],
        quote_volume=kline["q"],
        trade_count=kline["n"],
        is_closed=kline["x"],
    )
