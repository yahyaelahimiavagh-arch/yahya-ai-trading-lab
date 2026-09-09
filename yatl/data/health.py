"""Deterministic data-health reports for canonical bounded candle ranges."""

import json
from dataclasses import asdict, dataclass

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from .history import MAX_RANGE_CANDLES
from .models import Candle
from .quality import QualityError, analyze_open_times, duplicate_candle_keys


class HealthError(ValueError):
    """Health inputs cannot produce a trustworthy report."""


@dataclass(frozen=True, slots=True)
class DataHealthReport:
    source: str
    symbol: str
    interval: str
    requested_start_time_ms: int
    requested_end_time_ms: int
    stored_first_open_time_ms: int | None
    stored_last_open_time_ms: int | None
    total_rows: int
    unique_rows: int
    closed_rows: int
    open_rows: int
    duplicate_open_times: tuple
    historical_gap_open_times: tuple
    repair_ranges: tuple
    expected_current_open_time_ms: int | None
    expected_current_open_missing: bool
    unexpected_open_times: tuple
    malformed_rows: int
    conflicting_rows: int
    freshness_ms: int | None
    fresh: bool
    backtest_ready: bool
    failure_reasons: tuple

    def to_json(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def to_text(self):
        state = "PASS" if self.backtest_ready else "FAIL"
        first = "none" if self.stored_first_open_time_ms is None else self.stored_first_open_time_ms
        last = "none" if self.stored_last_open_time_ms is None else self.stored_last_open_time_ms
        reasons = "none" if not self.failure_reasons else ",".join(self.failure_reasons)
        return "\n".join((
            f"{state}: {self.source} {self.symbol} {self.interval}",
            f"requested=[{self.requested_start_time_ms},{self.requested_end_time_ms}) "
            f"stored=[{first},{last}] rows={self.total_rows} unique={self.unique_rows}",
            f"closed={self.closed_rows} open={self.open_rows} "
            f"duplicates={len(self.duplicate_open_times)} gaps={len(self.historical_gap_open_times)}",
            f"malformed={self.malformed_rows} conflicts={self.conflicting_rows} "
            f"fresh={str(self.fresh).lower()} backtest_ready={str(self.backtest_ready).lower()}",
            f"reasons={reasons}",
        ))


def build_health_report(source, symbol, interval, start_time_ms, end_time_ms,
                        candles, server_time_ms, *, malformed_rows=0,
                        conflicting_rows=0):
    if source != DATA_SOURCE or symbol not in SYMBOLS or interval not in INTERVAL_MILLISECONDS:
        raise HealthError("Unsupported health-report identity")
    if (not isinstance(candles, (list, tuple)) or len(candles) > MAX_RANGE_CANDLES
            or type(malformed_rows) is not int or malformed_rows < 0
            or type(conflicting_rows) is not int or conflicting_rows < 0):
        raise HealthError("Health-report rows or diagnostics are invalid")
    for value in candles:
        if (not isinstance(value, Candle) or value.source != source
                or value.symbol != symbol or value.interval != interval):
            raise HealthError("Candle identity does not match the health report")
    try:
        quality = analyze_open_times(
            source, symbol, interval, start_time_ms, end_time_ms,
            [value.open_time_ms for value in candles], server_time_ms,
        )
        duplicate_candle_keys(candles)
    except QualityError:
        raise HealthError("Health range failed quality validation") from None

    ordered = sorted(candles, key=lambda value: value.open_time_ms)
    unique_by_time = {}
    for value in ordered:
        unique_by_time.setdefault(value.open_time_ms, value)
    closed_times = {value.open_time_ms for value in unique_by_time.values() if value.is_closed}
    open_times = tuple(value.open_time_ms for value in unique_by_time.values()
                       if not value.is_closed)
    unexpected_open = tuple(value for value in open_times
                            if value != quality.expected_current_open_time_ms)
    duration = INTERVAL_MILLISECONDS[interval]
    current_open = (server_time_ms // duration) * duration
    closed_boundary = min(end_time_ms, current_open)
    latest_required_closed = closed_boundary - duration if closed_boundary > start_time_ms else None
    fresh = latest_required_closed is None or latest_required_closed in closed_times
    latest_closed = max((value for value in unique_by_time.values() if value.is_closed),
                        key=lambda value: value.open_time_ms, default=None)
    freshness = (None if latest_closed is None else
                 max(0, server_time_ms - (latest_closed.close_time_ms + 1)))

    reasons = []
    if quality.duplicate_open_times:
        reasons.append("duplicates")
    if quality.historical_gap_open_times:
        reasons.append("historical_gaps")
    if unexpected_open:
        reasons.append("unexpected_open_candles")
    if malformed_rows:
        reasons.append("malformed_rows")
    if conflicting_rows:
        reasons.append("conflicting_rows")
    if not fresh:
        reasons.append("stale_closed_data")
    ready = not reasons
    return DataHealthReport(
        source=source, symbol=symbol, interval=interval,
        requested_start_time_ms=start_time_ms, requested_end_time_ms=end_time_ms,
        stored_first_open_time_ms=ordered[0].open_time_ms if ordered else None,
        stored_last_open_time_ms=ordered[-1].open_time_ms if ordered else None,
        total_rows=len(candles), unique_rows=len(unique_by_time),
        closed_rows=sum(value.is_closed for value in unique_by_time.values()),
        open_rows=sum(not value.is_closed for value in unique_by_time.values()),
        duplicate_open_times=quality.duplicate_open_times,
        historical_gap_open_times=quality.historical_gap_open_times,
        repair_ranges=quality.repair_ranges,
        expected_current_open_time_ms=quality.expected_current_open_time_ms,
        expected_current_open_missing=quality.expected_current_open_missing,
        unexpected_open_times=unexpected_open,
        malformed_rows=malformed_rows, conflicting_rows=conflicting_rows,
        freshness_ms=freshness, fresh=fresh, backtest_ready=ready,
        failure_reasons=tuple(reasons),
    )
