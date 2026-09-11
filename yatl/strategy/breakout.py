"""Frozen long-only range-breakout research candidate; no sizing or execution."""

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.models import BacktestContractError

from .contracts import (DecisionReason, LongSetup, StrategyAction,
                        StrategyContext, StrategyContractError,
                        StrategyDecision, StrategyIdentity)
from .features import FeatureError, atr, rolling_high
from .regime import MarketRegime, RegimeError, RegimeReason, classify_regime
from .registry import ParameterRule, StrategyDefinition, StrategyRegistry


class BreakoutStrategyError(Exception):
    """Breakout input violates its fixed point-in-time contract."""


IDENTITY = StrategyIdentity("RANGE_BREAKOUT", "1.0.0")
DEFINITION = StrategyDefinition(IDENTITY, (
    ParameterRule("atr_period", "integer", 2, 100),
    ParameterRule("breakout_lookback", "integer", 2, 200),
    ParameterRule("maximum_extension_atr", "decimal", "0", "10"),
    ParameterRule("minimum_close_location", "decimal", "0", "1"),
    ParameterRule("reward_risk", "decimal", "1", "10"),
    ParameterRule("stop_atr_fraction", "decimal", "0", "2"),
))
CONFIGURATION = StrategyRegistry((DEFINITION,)).configure(IDENTITY, {
    "atr_period": 14,
    "breakout_lookback": 20,
    "maximum_extension_atr": "1",
    "minimum_close_location": "0.75",
    "reward_risk": "2",
    "stop_atr_fraction": "0.25",
})
PARAMETERS = dict(CONFIGURATION.values)


def _plain(value):
    if value.as_tuple().exponent < -40:
        value = value.quantize(Decimal("1e-40"), rounding=ROUND_HALF_EVEN)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _validated(context, in_position, active_setup):
    if (type(context) is not StrategyContext or context.identity != IDENTITY
            or type(in_position) is not bool
            or (in_position and type(active_setup) is not LongSetup)
            or (not in_position and active_setup is not None)):
        raise BreakoutStrategyError("Breakout state or identity is invalid")
    try:
        replace(context.identity)
        replace(context.snapshot)
        replace(context)
        if active_setup is not None:
            replace(active_setup)
    except (BacktestContractError, StrategyContractError, TypeError, ValueError):
        raise BreakoutStrategyError("Breakout context failed validation") from None


def _no_trade(context, reason):
    return StrategyDecision(context, StrategyAction.NO_TRADE, reason)


def evaluate_breakout(context, *, in_position=False, active_setup=None):
    """Evaluate a confirmed breakout using only legally visible closed candles."""
    _validated(context, in_position, active_setup)
    primary = context.snapshot.primary
    lookback = PARAMETERS["breakout_lookback"]
    try:
        regime = classify_regime(context)
        boundary = rolling_high(primary[:-1], lookback, context.decision_time_ms)
        volatility = atr(primary[:-1], PARAMETERS["atr_period"],
                         context.decision_time_ms)
    except (RegimeError, FeatureError):
        raise BreakoutStrategyError("Breakout feature evaluation failed") from None

    if (regime.reason is RegimeReason.INSUFFICIENT_HISTORY
            or not boundary.available or not volatility.available
            or len(context.snapshot.context) < 2):
        return _no_trade(context, DecisionReason.INSUFFICIENT_HISTORY)

    latest = context.snapshot.latest_primary
    close = Decimal(latest.close)
    if in_position:
        if (close <= Decimal(active_setup.invalidation_price)
                or regime.regime is not MarketRegime.TREND_UP
                or close <= boundary.value):
            return StrategyDecision(context, StrategyAction.EXIT_LONG,
                                    DecisionReason.STRATEGY_EXIT)
        return _no_trade(context, DecisionReason.HOLD_POSITION)

    if regime.regime is MarketRegime.UNKNOWN:
        return _no_trade(context, DecisionReason.REGIME_UNKNOWN)
    if regime.regime is not MarketRegime.TREND_UP:
        return _no_trade(context, DecisionReason.REGIME_BLOCKED)
    if close <= boundary.value:
        return _no_trade(context, DecisionReason.SETUP_ABSENT)

    high, low = Decimal(latest.high), Decimal(latest.low)
    candle_range = high - low
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        close_location = ((close - low) / candle_range
                          if candle_range > 0 else Decimal(0))
        extension_atr = ((close - boundary.value) / volatility.value
                         if volatility.value > 0 else Decimal("Infinity"))
    if (close_location < Decimal(PARAMETERS["minimum_close_location"])
            or extension_atr > Decimal(PARAMETERS["maximum_extension_atr"])):
        return _no_trade(context, DecisionReason.SETUP_ABSENT)

    previous_15m, latest_15m = context.snapshot.context[-2:]
    if not (Decimal(latest_15m.close) > Decimal(latest_15m.open)
            and Decimal(latest_15m.close) > Decimal(previous_15m.close)):
        return _no_trade(context, DecisionReason.CONFIRMATION_FAILED)

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        raw_invalidation = (low
                            - volatility.value * Decimal(PARAMETERS["stop_atr_fraction"]))
        invalidation = Decimal(_plain(raw_invalidation))
        risk = close - invalidation
        target = close + risk * Decimal(PARAMETERS["reward_risk"])
    if invalidation <= 0 or risk <= 0:
        return _no_trade(context, DecisionReason.SETUP_ABSENT)
    setup = LongSetup(_plain(close), _plain(invalidation), _plain(target))
    return StrategyDecision(context, StrategyAction.ENTER_LONG,
                            DecisionReason.BREAKOUT_ENTRY, setup)
