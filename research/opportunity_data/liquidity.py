"""Lagged liquidity from completed admitted candles only."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import AdmittedDataset, CADENCE_MS, OpportunityError, digest


@dataclass(frozen=True)
class Liquidity:
    symbol: str
    venue: str
    interval: str
    dataset_id: str
    ending_ms: int
    window_bars: int
    engine_version: str
    trailing_quote_volume: str
    trailing_base_volume: str
    trailing_trade_count: int
    active_bar_count: int
    gap_rate: str
    turnover_proxy: str | None  # quote/base ratio, explicitly not executable liquidity
    metric_sha256: str

    def payload(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "metric_sha256"}


def compute(dataset: AdmittedDataset, *, ending_ms: int, window_bars: int) -> Liquidity:
    dataset.validate_binding()
    if window_bars <= 0 or ending_ms < 0 or ending_ms > dataset.retrieved_at_ms:
        raise OpportunityError("invalid metric window/end")
    cadence = CADENCE_MS[dataset.interval]
    if ending_ms % cadence:
        raise OpportunityError("ending timestamp not UTC bucket boundary")
    lower = ending_ms - window_bars * cadence
    if lower < 0:
        raise OpportunityError("window precedes epoch")
    # Strictly earlier close than ending_ms: never current or future candle.
    selected = [r for r in dataset.rows if lower <= r.open_time_ms < ending_ms and r.close_time_ms < ending_ms]
    quote = sum((Decimal(r.values[7]) for r in selected), Decimal(0))
    base = sum((Decimal(r.values[5]) for r in selected), Decimal(0))
    count = sum(int(r.values[8]) for r in selected)
    active = sum(Decimal(r.values[5]) > 0 and int(r.values[8]) > 0 for r in selected)
    initial = Liquidity(dataset.symbol, dataset.venue, dataset.interval, dataset.dataset_id,
                        ending_ms, window_bars, "AF-01B-LIQ/1.0.0", str(quote), str(base),
                        count, active, str(Decimal(window_bars - len(selected)) / window_bars),
                        str(quote / base) if base else None, "")
    return Liquidity(**{**initial.payload(), "metric_sha256": digest(initial.payload())})
