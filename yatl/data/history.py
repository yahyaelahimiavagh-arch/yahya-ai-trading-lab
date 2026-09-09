"""Bounded, deterministic pagination for public historical Spot klines."""

from dataclasses import dataclass

from .config import INTERVAL_MILLISECONDS, SYMBOLS
from .rest import BinancePublicRestClient, PublicRestError


MAX_RANGE_CANDLES = 100_000


class HistoricalDownloadError(Exception):
    """Historical range or page validation failed."""


@dataclass(frozen=True, slots=True)
class HistoricalBatch:
    symbol: str
    interval: str
    start_time_ms: int
    end_time_ms: int
    pages: int
    rows: tuple
    skipped_known_rows: int


def _timestamp(value, name):
    if type(value) is not int or value <= 0:
        raise HistoricalDownloadError(f"{name} must be a positive integer timestamp")
    return value


def download_range(client, symbol, interval, start_time_ms, end_time_ms, *,
                   page_limit=1000, known_open_times=()):
    """Download `[start_time_ms, end_time_ms)` and exclude already-known rows.

    No files or database records are written. Passing stored open timestamps makes
    a resumed/repeated collection idempotent for its caller.
    """
    if not isinstance(client, BinancePublicRestClient):
        raise HistoricalDownloadError("A Binance public REST client is required")
    if symbol not in SYMBOLS:
        raise HistoricalDownloadError("Unsupported historical symbol")
    if interval not in INTERVAL_MILLISECONDS:
        raise HistoricalDownloadError("Unsupported historical interval")
    start = _timestamp(start_time_ms, "start_time_ms")
    end = _timestamp(end_time_ms, "end_time_ms")
    duration = INTERVAL_MILLISECONDS[interval]
    if start >= end or start % duration or end % duration:
        raise HistoricalDownloadError("Historical range must be ordered and interval-aligned")
    requested_count = (end - start) // duration
    if requested_count > MAX_RANGE_CANDLES:
        raise HistoricalDownloadError("Historical range exceeds the candle limit")
    if type(page_limit) is not int or not 1 <= page_limit <= 1000:
        raise HistoricalDownloadError("page_limit must be between 1 and 1000")
    try:
        known = set(known_open_times)
    except TypeError:
        raise HistoricalDownloadError("known_open_times must be an iterable of timestamps") from None
    if any(type(value) is not int or value < start or value >= end or value % duration for value in known):
        raise HistoricalDownloadError("Known candle timestamps are invalid for the range")

    cursor = start
    pages = 0
    skipped = 0
    seen_remote = set()
    collected = []
    while cursor < end:
        remaining = (end - cursor) // duration
        limit = min(page_limit, remaining)
        try:
            page = client.klines(symbol, interval, limit=limit,
                                 start_time=cursor, end_time=end - 1)
        except PublicRestError as error:
            raise HistoricalDownloadError("Historical page request failed") from error
        pages += 1
        if not page:
            break
        previous = None
        for row in page:
            if not isinstance(row, list) or len(row) != 12:
                raise HistoricalDownloadError("Historical page contains an invalid row")
            open_time = row[0]
            close_time = row[6]
            if (type(open_time) is not int or type(close_time) is not int
                    or open_time < cursor or open_time >= end or open_time % duration
                    or close_time != open_time + duration - 1):
                raise HistoricalDownloadError("Historical candle timestamps are invalid")
            if (previous is not None and open_time <= previous) or open_time in seen_remote:
                raise HistoricalDownloadError("Historical page is duplicated or out of order")
            previous = open_time
            seen_remote.add(open_time)
            if open_time in known:
                skipped += 1
            else:
                collected.append(tuple(row))
        next_cursor = page[-1][0] + duration
        if next_cursor <= cursor:
            raise HistoricalDownloadError("Historical pagination made no progress")
        cursor = next_cursor

    return HistoricalBatch(
        symbol=symbol,
        interval=interval,
        start_time_ms=start,
        end_time_ms=end,
        pages=pages,
        rows=tuple(collected),
        skipped_known_rows=skipped,
    )
