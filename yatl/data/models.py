"""Canonical, lossless candle contract shared by future REST and streams."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS


DECIMAL_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?")


class CandleValidationError(ValueError):
    """The candle violates the fixed P1 data contract."""


def _decimal(value, field, *, allow_zero):
    if not isinstance(value, str) or DECIMAL_PATTERN.fullmatch(value) is None:
        raise CandleValidationError(f"{field} must be a plain non-negative decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise CandleValidationError(f"{field} is invalid") from None
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise CandleValidationError(f"{field} is outside the allowed range")
    return number


@dataclass(frozen=True, slots=True)
class Candle:
    """One Binance Spot candle with exchange decimal strings preserved."""

    source: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: str
    high: str
    low: str
    close: str
    base_volume: str
    quote_volume: str
    trade_count: int
    is_closed: bool

    def __post_init__(self):
        if self.source != DATA_SOURCE:
            raise CandleValidationError("Unsupported candle source")
        if self.symbol not in SYMBOLS:
            raise CandleValidationError("Unsupported candle symbol")
        if self.interval not in INTERVAL_MILLISECONDS:
            raise CandleValidationError("Unsupported candle interval")
        if (type(self.open_time_ms) is not int or type(self.close_time_ms) is not int
                or self.open_time_ms < 0):
            raise CandleValidationError("Candle timestamps must be non-negative integers")
        duration = INTERVAL_MILLISECONDS[self.interval]
        if self.open_time_ms % duration != 0:
            raise CandleValidationError("Candle open timestamp is not interval-aligned UTC")
        if self.close_time_ms != self.open_time_ms + duration - 1:
            raise CandleValidationError("Candle close timestamp does not match its interval")
        if type(self.trade_count) is not int or self.trade_count < 0:
            raise CandleValidationError("Trade count must be a non-negative integer")
        if type(self.is_closed) is not bool:
            raise CandleValidationError("Candle closed state must be boolean")

        opened = _decimal(self.open, "open", allow_zero=False)
        high = _decimal(self.high, "high", allow_zero=False)
        low = _decimal(self.low, "low", allow_zero=False)
        closed = _decimal(self.close, "close", allow_zero=False)
        _decimal(self.base_volume, "base_volume", allow_zero=True)
        _decimal(self.quote_volume, "quote_volume", allow_zero=True)
        if not low <= min(opened, closed) <= max(opened, closed) <= high:
            raise CandleValidationError("Candle OHLC values are inconsistent")

    @property
    def key(self):
        """Stable SQLite uniqueness key planned for P1-005."""
        return self.source, self.symbol, self.interval, self.open_time_ms

    def as_record(self):
        """Return storage-ready primitives without changing decimal precision."""
        return {
            "source": self.source,
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "base_volume": self.base_volume,
            "quote_volume": self.quote_volume,
            "trade_count": self.trade_count,
            "is_closed": self.is_closed,
        }
