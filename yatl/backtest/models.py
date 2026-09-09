"""Point-in-time market views that make P2 look-ahead fail closed."""

from dataclasses import dataclass

from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS

from .config import CONTEXT_INTERVAL, PRIMARY_INTERVAL, REGIME_INTERVAL


class BacktestContractError(ValueError):
    """A backtest input is incomplete, stale, open or from the future."""


def _validate_history(candles, *, symbol, interval, decision_time_ms):
    if not isinstance(candles, tuple) or not candles:
        raise BacktestContractError(f"{interval} history must be a non-empty tuple")
    duration = INTERVAL_MILLISECONDS[interval]
    expected_last_open = (decision_time_ms // duration) * duration - duration
    previous = None
    for candle in candles:
        if (not isinstance(candle, Candle) or candle.source != DATA_SOURCE
                or candle.symbol != symbol or candle.interval != interval
                or not candle.is_closed):
            raise BacktestContractError(f"{interval} history identity or state is invalid")
        if candle.close_time_ms >= decision_time_ms:
            raise BacktestContractError("Future or still-open candle reached the decision")
        if previous is not None and candle.open_time_ms != previous + duration:
            raise BacktestContractError(f"{interval} history is not contiguous and ordered")
        previous = candle.open_time_ms
    if candles[-1].open_time_ms != expected_last_open:
        raise BacktestContractError(f"{interval} history is stale at the decision time")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Information legally visible at one aligned primary decision boundary."""

    symbol: str
    decision_time_ms: int
    primary: tuple[Candle, ...]
    context: tuple[Candle, ...]
    regime: tuple[Candle, ...]

    def __post_init__(self):
        primary_duration = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
        if (type(self.decision_time_ms) is not int or self.decision_time_ms <= 0
                or self.decision_time_ms % primary_duration):
            raise BacktestContractError("Decision time must be an aligned 1h boundary")
        _validate_history(self.primary, symbol=self.symbol, interval=PRIMARY_INTERVAL,
                          decision_time_ms=self.decision_time_ms)
        _validate_history(self.context, symbol=self.symbol, interval=CONTEXT_INTERVAL,
                          decision_time_ms=self.decision_time_ms)
        _validate_history(self.regime, symbol=self.symbol, interval=REGIME_INTERVAL,
                          decision_time_ms=self.decision_time_ms)

    @property
    def latest_primary(self):
        return self.primary[-1]

    @property
    def latest_context(self):
        return self.context[-1]

    @property
    def latest_regime(self):
        return self.regime[-1]
