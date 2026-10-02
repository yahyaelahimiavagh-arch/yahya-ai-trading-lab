"""Test-only allocation baseline copied from accepted main 890c47ce2c75774ab5f5e4aebcc0cbfddfb7c866.

Only validation and constructor are copied; feature formulas use the production
implementation. Never imported by production code; synthetic bars only.
"""
from __future__ import annotations
from math import isfinite
from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production import CADENCE_MS, DEVELOPMENT_END_MS
from research.mass_candidate_factory.production_features import POPULATION_START_MS, ProductionFeatureCache

def legacy_validate(self) -> None:
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
    cadence = CADENCE_MS[self.timeframe]
    if any(type(t) is not int or t % cadence or t + cadence > DEVELOPMENT_END_MS for t in self.times):
        raise MCFError("production bar cadence/completion boundary mismatch")
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


class LegacyProductionFeatureCache(ProductionFeatureCache):
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
