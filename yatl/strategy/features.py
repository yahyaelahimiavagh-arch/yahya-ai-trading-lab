"""Point-in-time Decimal feature primitives over canonical closed candles."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import Candle, INTERVAL_MILLISECONDS


MAX_FEATURE_CANDLES = 100_000
MAX_FEATURE_PERIOD = 10_000


class FeatureError(Exception):
    """Feature input or arithmetic violates the deterministic P3 contract."""


class FeatureState(str, Enum):
    READY = "READY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


@dataclass(frozen=True, slots=True)
class FeatureResult:
    name: str
    period: int
    decision_time_ms: int
    observed: int
    warmup_required: int
    state: FeatureState
    value: Decimal | None

    def __post_init__(self):
        if (not isinstance(self.name, str) or not self.name
                or type(self.period) is not int or self.period <= 0
                or type(self.decision_time_ms) is not int or self.decision_time_ms <= 0
                or type(self.observed) is not int or self.observed < 0
                or type(self.warmup_required) is not int or self.warmup_required <= 0
                or not isinstance(self.state, FeatureState)
                or (self.state is FeatureState.READY
                    and (type(self.value) is not Decimal or not self.value.is_finite()
                         or self.observed < self.warmup_required))
                or (self.state is FeatureState.INSUFFICIENT_HISTORY
                    and (self.value is not None or self.observed >= self.warmup_required))):
            raise FeatureError("Feature result is inconsistent")

    @property
    def available(self):
        return self.state is FeatureState.READY


def _period(value):
    if type(value) is not int or not 1 <= value <= MAX_FEATURE_PERIOD:
        raise FeatureError("Feature period is invalid")
    return value


def _visible(candles, decision_time_ms):
    if (not isinstance(candles, tuple) or len(candles) > MAX_FEATURE_CANDLES
            or type(decision_time_ms) is not int or decision_time_ms <= 0):
        raise FeatureError("Feature input identity is invalid")
    if not candles:
        return ()
    if any(not isinstance(item, Candle) for item in candles):
        raise FeatureError("Feature input contains an invalid candle")
    visible = tuple(item for item in candles if item.close_time_ms < decision_time_ms)
    if not visible:
        return ()
    first = visible[0]
    duration = INTERVAL_MILLISECONDS[first.interval]
    previous = None
    for candle in visible:
        if (not isinstance(candle, Candle) or candle.symbol != first.symbol
                or candle.interval != first.interval or not candle.is_closed
                or (previous is not None
                    and candle.open_time_ms != previous.open_time_ms + duration)):
            raise FeatureError("Feature candle series is inconsistent")
        previous = candle
    return visible


def _result(name, period, decision_time_ms, visible, required, value=None):
    if len(visible) < required:
        return FeatureResult(name, period, decision_time_ms, len(visible), required,
                             FeatureState.INSUFFICIENT_HISTORY, None)
    return FeatureResult(name, period, decision_time_ms, len(visible), required,
                         FeatureState.READY, value)


def simple_return(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    required = period + 1
    if len(visible) < required:
        return _result("SIMPLE_RETURN", period, decision_time_ms, visible, required)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        value = Decimal(visible[-1].close) / Decimal(visible[-required].close) - Decimal(1)
    return _result("SIMPLE_RETURN", period, decision_time_ms, visible, required, value)


def rolling_high(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    if len(visible) < period:
        return _result("ROLLING_HIGH", period, decision_time_ms, visible, period)
    value = max(Decimal(item.high) for item in visible[-period:])
    return _result("ROLLING_HIGH", period, decision_time_ms, visible, period, value)


def rolling_low(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    if len(visible) < period:
        return _result("ROLLING_LOW", period, decision_time_ms, visible, period)
    value = min(Decimal(item.low) for item in visible[-period:])
    return _result("ROLLING_LOW", period, decision_time_ms, visible, period, value)


def sma(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    if len(visible) < period:
        return _result("SMA", period, decision_time_ms, visible, period)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        value = sum((Decimal(item.close) for item in visible[-period:]), Decimal(0)) \
            / Decimal(period)
    return _result("SMA", period, decision_time_ms, visible, period, value)


def ema(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    if len(visible) < period:
        return _result("EMA", period, decision_time_ms, visible, period)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        values = [Decimal(item.close) for item in visible]
        current = sum(values[:period], Decimal(0)) / Decimal(period)
        alpha = Decimal(2) / Decimal(period + 1)
        for value in values[period:]:
            current = alpha * value + (Decimal(1) - alpha) * current
    return _result("EMA", period, decision_time_ms, visible, period, current)


def atr(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    required = period + 1
    if len(visible) < required:
        return _result("ATR", period, decision_time_ms, visible, required)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        ranges = []
        for previous, current in zip(visible, visible[1:]):
            high = Decimal(current.high)
            low = Decimal(current.low)
            prior_close = Decimal(previous.close)
            ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
        current_atr = sum(ranges[:period], Decimal(0)) / Decimal(period)
        for value in ranges[period:]:
            current_atr = ((current_atr * Decimal(period - 1)) + value) / Decimal(period)
    return _result("ATR", period, decision_time_ms, visible, required, current_atr)


def rsi(candles, period, decision_time_ms):
    period = _period(period)
    visible = _visible(candles, decision_time_ms)
    required = period + 1
    if len(visible) < required:
        return _result("RSI", period, decision_time_ms, visible, required)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        closes = [Decimal(item.close) for item in visible]
        changes = [current - previous for previous, current in zip(closes, closes[1:])]
        gains = [max(value, Decimal(0)) for value in changes]
        losses = [max(-value, Decimal(0)) for value in changes]
        average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
        average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
        for gain, loss in zip(gains[period:], losses[period:]):
            average_gain = ((average_gain * Decimal(period - 1)) + gain) / Decimal(period)
            average_loss = ((average_loss * Decimal(period - 1)) + loss) / Decimal(period)
        if average_gain == 0 and average_loss == 0:
            value = Decimal(50)
        elif average_loss == 0:
            value = Decimal(100)
        elif average_gain == 0:
            value = Decimal(0)
        else:
            relative_strength = average_gain / average_loss
            value = Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)
    return _result("RSI", period, decision_time_ms, visible, required, value)
