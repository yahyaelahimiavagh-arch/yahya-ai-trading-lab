"""Frozen 4h research regime rules; no signal or execution capability."""

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from enum import Enum

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.models import BacktestContractError
from .contracts import StrategyContext, StrategyContractError


REGIME_VERSION = "SMA_4H_V1"
FAST_PERIOD = 20
SLOW_PERIOD = 50
WARMUP = 51
SPREAD_BOUNDARY = Decimal("0.002")
RANGE_SLOPE_BOUNDARY = Decimal("0.0005")


class RegimeError(Exception):
    """Invalid regime input or inconsistent result."""


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class RegimeReason(str, Enum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UP_ALIGNED = "UP_ALIGNED"
    DOWN_ALIGNED = "DOWN_ALIGNED"
    AVERAGES_CONVERGED = "AVERAGES_CONVERGED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


def _classify(price, fast, slow, spread, slope):
    if spread > SPREAD_BOUNDARY and slope > 0 and price > fast:
        return MarketRegime.TREND_UP, RegimeReason.UP_ALIGNED
    if spread < -SPREAD_BOUNDARY and slope < 0 and price < fast:
        return MarketRegime.TREND_DOWN, RegimeReason.DOWN_ALIGNED
    if abs(spread) <= SPREAD_BOUNDARY and abs(slope) <= RANGE_SLOPE_BOUNDARY:
        return MarketRegime.RANGE, RegimeReason.AVERAGES_CONVERGED
    return MarketRegime.UNKNOWN, RegimeReason.CONFLICTING_EVIDENCE


def _measure(context):
    if type(context) is not StrategyContext:
        raise RegimeError("Regime requires a valid strategy context")
    try:
        # Reconstruct validated immutable contracts to reject corrupted nested state.
        replace(context.identity)
        replace(context.snapshot)
        replace(context)
    except (ValueError, TypeError, StrategyContractError, BacktestContractError):
        raise RegimeError("Regime context failed point-in-time validation") from None
    candles = context.snapshot.regime
    if len(candles) < WARMUP:
        return (MarketRegime.UNKNOWN, RegimeReason.INSUFFICIENT_HISTORY,
                None, None, None, None)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        closes = [Decimal(item.close) for item in candles[-WARMUP:]]
        fast = sum(closes[-FAST_PERIOD:], Decimal(0)) / FAST_PERIOD
        slow = sum(closes[-SLOW_PERIOD:], Decimal(0)) / SLOW_PERIOD
        previous_slow = sum(closes[:-1], Decimal(0)) / SLOW_PERIOD
        spread = (fast - slow) / slow
        slope = (slow - previous_slow) / previous_slow
        regime, reason = _classify(closes[-1], fast, slow, spread, slope)
    return regime, reason, fast, slow, spread, slope


@dataclass(frozen=True, slots=True)
class RegimeResult:
    context: StrategyContext
    regime: MarketRegime
    reason: RegimeReason
    fast_sma: Decimal | None
    slow_sma: Decimal | None
    relative_spread: Decimal | None
    relative_slope: Decimal | None
    version: str = REGIME_VERSION

    def __post_init__(self):
        values = (self.fast_sma, self.slow_sma, self.relative_spread, self.relative_slope)
        if (self.version != REGIME_VERSION or type(self.regime) is not MarketRegime
                or type(self.reason) is not RegimeReason
                or any(value is not None and
                       (type(value) is not Decimal or not value.is_finite())
                       for value in values)
                or (self.regime, self.reason, *values) != _measure(self.context)):
            raise RegimeError("Regime result is inconsistent")


def classify_regime(context):
    """Classify only the validated closed 4h prefix; 51 bars required."""
    return RegimeResult(context, *_measure(context))
