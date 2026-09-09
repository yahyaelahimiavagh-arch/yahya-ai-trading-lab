"""Deterministic primary-timeframe event clock for P2 simulations."""

from dataclasses import dataclass

from yatl.data import INTERVAL_MILLISECONDS

from .config import PRIMARY_INTERVAL
from .loader import AcceptedBacktestDataset, BacktestLoadError
from .models import MarketSnapshot


class BacktestClockError(Exception):
    """The deterministic event sequence cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    sequence: int
    decision_time_ms: int
    eligible_fill_open_time_ms: int
    snapshot: MarketSnapshot

    def __post_init__(self):
        duration = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
        if (type(self.sequence) is not int or self.sequence < 0
                or type(self.decision_time_ms) is not int
                or self.decision_time_ms <= 0
                or self.decision_time_ms % duration
                or self.eligible_fill_open_time_ms != self.decision_time_ms
                or not isinstance(self.snapshot, MarketSnapshot)
                or self.snapshot.decision_time_ms != self.decision_time_ms):
            raise BacktestClockError("Decision event violates the P2 clock contract")


@dataclass(frozen=True, slots=True)
class BacktestClock:
    dataset: AcceptedBacktestDataset

    def __post_init__(self):
        if not isinstance(self.dataset, AcceptedBacktestDataset):
            raise BacktestClockError("Clock requires an accepted backtest dataset")

    @property
    def event_count(self):
        duration = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
        return ((self.dataset.spec.end_time_ms - self.dataset.spec.start_time_ms)
                // duration)

    def events(self):
        duration = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
        for sequence, decision_time in enumerate(range(
                self.dataset.spec.start_time_ms,
                self.dataset.spec.end_time_ms,
                duration)):
            try:
                snapshot = self.dataset.snapshot_at(decision_time)
            except BacktestLoadError:
                raise BacktestClockError("Clock could not build a legal point-in-time event") from None
            yield DecisionEvent(sequence=sequence,
                                decision_time_ms=decision_time,
                                eligible_fill_open_time_ms=decision_time,
                                snapshot=snapshot)
