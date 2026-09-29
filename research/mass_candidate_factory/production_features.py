"""Gap-aware production feature cache for MCF-03.

Unlike the accepted MCF-02 engineering cache, this version admits arbitrary
point-in-time USDT Spot members and never fills source gaps.  Every rolling
feature returns None until its exact required cadence window is complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite, sqrt
from statistics import median
from typing import Mapping

from .models import MCFError, digest
from .production import CADENCE_MS, DEVELOPMENT_END_MS

VERSION = "MCF_PRODUCTION_FEATURES/1.0.0"
POPULATION_START_MS = 1577836800000  # 2020-01-01T00:00:00Z


@dataclass(frozen=True)
class ProductionBars:
    dataset_id: str
    symbol: str
    timeframe: str
    times: tuple[int, ...]
    opens: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    closes: tuple[float, ...]
    base_volume: tuple[float, ...]
    quote_volume: tuple[float, ...]
    trade_count: tuple[float, ...]
    evidence_partition: str = "DEVELOPMENT"

    def validate(self) -> None:
        n = len(self.times)
        if (
            self.evidence_partition != "DEVELOPMENT"
            or not self.dataset_id
            or not self.symbol.endswith("USDT")
            or self.timeframe not in CADENCE_MS
            or n < 2
        ):
            raise MCFError("invalid production bars identity")
        fields = ("opens", "highs", "lows", "closes", "base_volume", "quote_volume", "trade_count")
        if any(len(getattr(self, field)) != n for field in fields):
            raise MCFError("production bars length mismatch")
        if any(a >= b for a, b in zip(self.times, self.times[1:])):
            raise MCFError("production bars must be strictly increasing")
        if self.times[0] < POPULATION_START_MS or self.times[-1] >= DEVELOPMENT_END_MS:
            raise MCFError("production bars outside frozen Development population")
        for field in fields:
            values = getattr(self, field)
            if any(not isfinite(float(v)) for v in values):
                raise MCFError("nonfinite production bar")
        if any(v <= 0 for v in self.opens + self.highs + self.lows + self.closes):
            raise MCFError("nonpositive production price")
        if any(v < 0 for v in self.base_volume + self.quote_volume + self.trade_count):
            raise MCFError("negative production activity")
        if any(h < max(o, c) or l > min(o, c) or h < l
               for o, h, l, c in zip(self.opens, self.highs, self.lows, self.closes)):
            raise MCFError("invalid OHLC ordering")


class ProductionFeatureCache:
    def __init__(self, bars: ProductionBars, peers: Mapping[str, ProductionBars] | None = None):
        bars.validate()
        self.bars = bars
        self.peers = dict(peers or {})
        self._index = {t: i for i, t in enumerate(bars.times)}
        if len(self._index) != len(bars.times):
            raise MCFError("duplicate production timestamp")
        for symbol, peer in self.peers.items():
            peer.validate()
            if symbol != peer.symbol or peer.timeframe != bars.timeframe:
                raise MCFError("unaligned production peer identity")
        self._cache: dict[tuple, tuple[float | None, ...]] = {}

    @property
    def cadence(self) -> int:
        return CADENCE_MS[self.bars.timeframe]

    def _field(self, name: str) -> tuple[float, ...]:
        if name not in ("opens", "highs", "lows", "closes", "base_volume", "quote_volume", "trade_count"):
            raise MCFError("unsupported production field")
        return getattr(self.bars, name)

    def _complete_indexes(self, end: int, window: int) -> tuple[int, ...] | None:
        if not isinstance(window, int) or window < 1 or end < 0:
            return None
        start = end - window + 1
        if start < 0:
            return None
        expected = self.bars.times[start]
        for i in range(start, end + 1):
            if self.bars.times[i] != expected:
                return None
            expected += self.cadence
        return tuple(range(start, end + 1))

    def rolling(self, field: str, window: int, *, lag: int = 1, statistic: str = "mean",
                quantile: float | None = None) -> tuple[float | None, ...]:
        if not isinstance(lag, int) or lag < 0:
            raise MCFError("invalid production feature lag")
        if statistic not in {"mean", "std", "min", "max", "median", "sum", "quantile"}:
            raise MCFError("unsupported production rolling statistic")
        if statistic == "quantile" and (quantile is None or not 0.0 <= float(quantile) <= 1.0):
            raise MCFError("invalid production quantile")
        key = ("rolling", field, window, lag, statistic, quantile)
        if key in self._cache:
            return self._cache[key]
        source = self._field(field)
        out: list[float | None] = []
        for i in range(len(source)):
            indexes = self._complete_indexes(i - lag, window)
            if indexes is None:
                out.append(None)
                continue
            values = [float(source[j]) for j in indexes]
            if statistic == "mean":
                value = sum(values) / len(values)
            elif statistic == "std":
                mu = sum(values) / len(values)
                value = sqrt(max(0.0, sum((x - mu) ** 2 for x in values) / len(values)))
            elif statistic == "min":
                value = min(values)
            elif statistic == "max":
                value = max(values)
            elif statistic == "median":
                value = float(median(values))
            elif statistic == "sum":
                value = sum(values)
            else:
                ordered = sorted(values)
                q = float(quantile)
                position = int(q * (len(ordered) - 1))
                value = ordered[position]
            out.append(value)
        result = tuple(out)
        self._cache[key] = result
        return result

    def lagged_return(self, lookback: int) -> tuple[float | None, ...]:
        key = ("lagged_return", lookback)
        if key in self._cache:
            return self._cache[key]
        if not isinstance(lookback, int) or lookback < 1:
            raise MCFError("invalid production return lookback")
        out: list[float | None] = []
        for i, close in enumerate(self.bars.closes):
            indexes = self._complete_indexes(i, lookback + 1)
            if indexes is None:
                out.append(None)
                continue
            prior = float(self.bars.closes[i - lookback])
            out.append(None if prior == 0 else float(close) / prior - 1.0)
        result = tuple(out)
        self._cache[key] = result
        return result

    def zscore_vs_lagged(self, window: int) -> tuple[float | None, ...]:
        key = ("zscore_lagged", window)
        if key in self._cache:
            return self._cache[key]
        means = self.rolling("closes", window, lag=1, statistic="mean")
        stds = self.rolling("closes", window, lag=1, statistic="std")
        out = []
        for close, mu, sd in zip(self.bars.closes, means, stds):
            if mu is None or sd is None or sd <= 0.0:
                out.append(None)
            else:
                out.append((float(close) - mu) / sd)
        result = tuple(out)
        self._cache[key] = result
        return result

    def peer_return(self, peer_symbol: str, lookback: int) -> tuple[float | None, ...]:
        key = ("peer_return", peer_symbol, lookback)
        if key in self._cache:
            return self._cache[key]
        peer = self.peers.get(peer_symbol)
        if peer is None:
            return (None,) * len(self.bars.times)
        peer_index = {t: i for i, t in enumerate(peer.times)}
        cadence = self.cadence
        out = []
        for t in self.bars.times:
            now = peer_index.get(t)
            prior = peer_index.get(t - lookback * cadence)
            if now is None or prior is None:
                out.append(None)
                continue
            # Require every peer bar between prior and now; no gap bridging.
            complete = all((t - k * cadence) in peer_index for k in range(lookback + 1))
            p0 = float(peer.closes[prior])
            out.append(None if not complete or p0 == 0 else float(peer.closes[now]) / p0 - 1.0)
        result = tuple(out)
        self._cache[key] = result
        return result

    def range_fraction(self) -> tuple[float | None, ...]:
        key = ("range_fraction",)
        if key in self._cache:
            return self._cache[key]
        out = tuple(
            None if float(c) <= 0 else (float(h) - float(l)) / float(c)
            for h, l, c in zip(self.bars.highs, self.bars.lows, self.bars.closes)
        )
        self._cache[key] = out
        return out

    def identity(self) -> str:
        return digest({
            "version": VERSION,
            "dataset_id": self.bars.dataset_id,
            "symbol": self.bars.symbol,
            "timeframe": self.bars.timeframe,
            "first_time": self.bars.times[0],
            "last_time": self.bars.times[-1],
            "row_count": len(self.bars.times),
        })


def liquidity_percentiles(caches: Mapping[str, ProductionFeatureCache], window: int) -> dict[str, tuple[float | None, ...]]:
    """Point-in-time percentile from lagged trailing quote volume.

    Each target symbol is aligned on its own observed timestamps. A percentile
    is unavailable when the target or fewer than two peers have a complete
    lagged window at that timestamp.
    """
    if len(caches) < 2:
        raise MCFError("liquidity percentile requires multiple symbols")
    trailing = {
        symbol: cache.rolling("quote_volume", window, lag=1, statistic="sum")
        for symbol, cache in caches.items()
    }
    indexes = {
        symbol: {t: i for i, t in enumerate(cache.bars.times)}
        for symbol, cache in caches.items()
    }
    output: dict[str, tuple[float | None, ...]] = {}
    for symbol, cache in caches.items():
        values = []
        for t in cache.bars.times:
            cross = []
            for peer_symbol in sorted(caches):
                j = indexes[peer_symbol].get(t)
                if j is None:
                    continue
                value = trailing[peer_symbol][j]
                if value is not None:
                    cross.append((peer_symbol, float(value)))
            target = next((v for s, v in cross if s == symbol), None)
            if target is None or len(cross) < 2:
                values.append(None)
                continue
            ordered = sorted(v for _, v in cross)
            below = sum(v < target for v in ordered)
            equal = sum(v == target for v in ordered)
            percentile = (below + 0.5 * (equal - 1)) / (len(ordered) - 1)
            values.append(max(0.0, min(1.0, percentile)))
        output[symbol] = tuple(values)
    return output
