"""Deterministic duplicate and missing-candle checks for bounded UTC ranges."""

from dataclasses import dataclass

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from .history import MAX_RANGE_CANDLES
from .models import Candle


MAX_REPAIR_RANGES = 1_000


class QualityError(ValueError):
    """Quality inputs are unsafe, inconsistent or exceed fixed bounds."""


@dataclass(frozen=True, slots=True)
class RangeQualityReport:
    source: str
    symbol: str
    interval: str
    start_time_ms: int
    end_time_ms: int
    expected_rows: int
    observed_rows: int
    observed_unique_rows: int
    duplicate_open_times: tuple
    historical_gap_open_times: tuple
    expected_current_open_time_ms: int | None
    expected_current_open_missing: bool
    repair_ranges: tuple

    @property
    def healthy(self):
        return not self.duplicate_open_times and not self.historical_gap_open_times


def duplicate_candle_keys(candles):
    """Return each repeated canonical key once, before persistence."""
    if not isinstance(candles, (list, tuple)) or len(candles) > MAX_RANGE_CANDLES:
        raise QualityError("Candle collection is invalid or too large")
    seen = set()
    repeated = set()
    duplicates = []
    for value in candles:
        if not isinstance(value, Candle):
            raise QualityError("Only canonical Candle values can be inspected")
        if value.key in seen and value.key not in repeated:
            duplicates.append(value.key)
            repeated.add(value.key)
        seen.add(value.key)
    return tuple(duplicates)


def _repair_ranges(missing_open_times, duration):
    if not missing_open_times:
        return ()
    ranges = []
    start = previous = missing_open_times[0]
    for open_time in missing_open_times[1:]:
        if open_time != previous + duration:
            ranges.append((start, previous + duration))
            start = open_time
        previous = open_time
    ranges.append((start, previous + duration))
    if len(ranges) > MAX_REPAIR_RANGES:
        raise QualityError("Missing candles require too many repair ranges")
    return tuple(ranges)


def analyze_open_times(source, symbol, interval, start_time_ms, end_time_ms,
                       open_times, server_time_ms):
    """Inspect one half-open range without network calls or automatic repairs."""
    if source != DATA_SOURCE or symbol not in SYMBOLS or interval not in INTERVAL_MILLISECONDS:
        raise QualityError("Unsupported source, symbol or interval")
    duration = INTERVAL_MILLISECONDS[interval]
    if (type(start_time_ms) is not int or type(end_time_ms) is not int
            or type(server_time_ms) is not int or start_time_ms < 0
            or server_time_ms < 0 or start_time_ms >= end_time_ms
            or start_time_ms % duration or end_time_ms % duration):
        raise QualityError("Quality range or server time is invalid")
    expected_rows = (end_time_ms - start_time_ms) // duration
    if expected_rows > MAX_RANGE_CANDLES:
        raise QualityError("Quality range exceeds the candle limit")
    current_open = (server_time_ms // duration) * duration
    if end_time_ms > current_open + duration:
        raise QualityError("Quality range extends beyond the current interval")
    if not isinstance(open_times, (list, tuple)) or len(open_times) > MAX_RANGE_CANDLES:
        raise QualityError("Open-time collection is invalid or too large")

    seen = set()
    repeated = set()
    duplicates = []
    for open_time in open_times:
        if (type(open_time) is not int or open_time < start_time_ms
                or open_time >= end_time_ms or open_time % duration):
            raise QualityError("Observed candle timestamp is outside the exact UTC grid")
        if open_time in seen and open_time not in repeated:
            duplicates.append(open_time)
            repeated.add(open_time)
        seen.add(open_time)

    missing = tuple(
        open_time for open_time in range(start_time_ms, end_time_ms, duration)
        if open_time not in seen
    )
    expected_current = current_open if start_time_ms <= current_open < end_time_ms else None
    current_missing = expected_current is not None and expected_current in missing
    historical_gaps = tuple(value for value in missing if value != expected_current)
    return RangeQualityReport(
        source=source,
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        expected_rows=expected_rows,
        observed_rows=len(open_times),
        observed_unique_rows=len(seen),
        duplicate_open_times=tuple(duplicates),
        historical_gap_open_times=historical_gaps,
        expected_current_open_time_ms=expected_current,
        expected_current_open_missing=current_missing,
        repair_ranges=_repair_ranges(historical_gaps, duration),
    )
