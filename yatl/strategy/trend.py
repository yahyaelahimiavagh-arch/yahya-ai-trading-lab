"""Frozen long-only trend-pullback research candidate; no sizing or execution."""

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.models import BacktestContractError

from .contracts import (DecisionReason, LongSetup, StrategyAction,
                        StrategyContext, StrategyContractError,
                        StrategyDecision, StrategyIdentity)
from .features import FeatureError, atr, rolling_low, sma
from .regime import MarketRegime, RegimeError, RegimeReason, classify_regime
from .registry import (ParameterRule, RegistryError, StrategyDefinition,
                       StrategyRegistry)


class TrendStrategyError(Exception):
    """Trend-pullback input violates its fixed point-in-time contract."""


IDENTITY = StrategyIdentity("TREND_PULLBACK", "1.0.0")
DEFINITION = StrategyDefinition(IDENTITY, (
    ParameterRule("atr_period", "integer", 2, 100),
    ParameterRule("primary_sma_period", "integer", 2, 200),
    ParameterRule("pullback_lookback", "integer", 1, 10),
    ParameterRule("reward_risk", "decimal", "1", "10"),
    ParameterRule("stop_atr_fraction", "decimal", "0", "2"),
))
CONFIGURATION = StrategyRegistry((DEFINITION,)).configure(IDENTITY, {
    "atr_period": 14,
    "primary_sma_period": 20,
    "pullback_lookback": 3,
    "reward_risk": "2",
    "stop_atr_fraction": "0.25",
})
PARAMETERS = dict(CONFIGURATION.values)


def _plain(value):
    if value.as_tuple().exponent < -40:
        value = value.quantize(Decimal("1e-40"), rounding=ROUND_HALF_EVEN)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _validated(context, in_position, active_setup):
    if (type(context) is not StrategyContext or context.identity != IDENTITY
            or type(in_position) is not bool
            or (in_position and type(active_setup) is not LongSetup)
            or (not in_position and active_setup is not None)):
        raise TrendStrategyError("Trend-pullback state or identity is invalid")
    try:
        replace(context.identity)
        replace(context.snapshot)
        replace(context)
        if active_setup is not None:
            replace(active_setup)
    except (BacktestContractError, StrategyContractError, TypeError, ValueError):
        raise TrendStrategyError("Trend-pullback context failed validation") from None


def _no_trade(context, reason):
    return StrategyDecision(context, StrategyAction.NO_TRADE, reason)


def evaluate_trend_pullback(context, *, in_position=False, active_setup=None):
    """Evaluate one legally visible closed-candle snapshot."""
    _validated(context, in_position, active_setup)
    try:
        regime = classify_regime(context)
        average = sma(context.snapshot.primary, PARAMETERS["primary_sma_period"],
                      context.decision_time_ms)
    except (RegimeError, FeatureError, RegistryError):
        raise TrendStrategyError("Trend-pullback feature evaluation failed") from None

    if (regime.reason is RegimeReason.INSUFFICIENT_HISTORY
            or not average.available
            or len(context.snapshot.context) < 2):
        return _no_trade(context, DecisionReason.INSUFFICIENT_HISTORY)

    close = Decimal(context.snapshot.latest_primary.close)
    if in_position:
        invalidation = Decimal(active_setup.invalidation_price)
        if (close <= invalidation or regime.regime is not MarketRegime.TREND_UP
                or close < average.value):
            return StrategyDecision(context, StrategyAction.EXIT_LONG,
                                    DecisionReason.STRATEGY_EXIT)
        return _no_trade(context, DecisionReason.HOLD_POSITION)

    if regime.regime is MarketRegime.UNKNOWN:
        return _no_trade(context, DecisionReason.REGIME_UNKNOWN)
    if regime.regime is not MarketRegime.TREND_UP:
        return _no_trade(context, DecisionReason.REGIME_BLOCKED)

    latest = context.snapshot.latest_primary
    if Decimal(latest.low) > average.value or close <= average.value:
        return _no_trade(context, DecisionReason.SETUP_ABSENT)

    previous_15m, latest_15m = context.snapshot.context[-2:]
    confirmation = (Decimal(latest_15m.close) > Decimal(latest_15m.open)
                    and Decimal(latest_15m.close) > Decimal(previous_15m.close))
    if not confirmation:
        return _no_trade(context, DecisionReason.CONFIRMATION_FAILED)

    try:
        volatility = atr(context.snapshot.primary, PARAMETERS["atr_period"],
                         context.decision_time_ms)
        recent_low = rolling_low(context.snapshot.primary,
                                 PARAMETERS["pullback_lookback"],
                                 context.decision_time_ms)
    except FeatureError:
        raise TrendStrategyError("Trend-pullback level evaluation failed") from None
    if not volatility.available or not recent_low.available:
        return _no_trade(context, DecisionReason.INSUFFICIENT_HISTORY)

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        raw_invalidation = (recent_low.value
                            - volatility.value * Decimal(PARAMETERS["stop_atr_fraction"]))
        invalidation = Decimal(_plain(raw_invalidation))
        risk = close - invalidation
        target = close + risk * Decimal(PARAMETERS["reward_risk"])
    if invalidation <= 0 or risk <= 0:
        return _no_trade(context, DecisionReason.SETUP_ABSENT)
    setup = LongSetup(_plain(close), _plain(invalidation), _plain(target))
    return StrategyDecision(context, StrategyAction.ENTER_LONG,
                            DecisionReason.TREND_PULLBACK_ENTRY, setup)
