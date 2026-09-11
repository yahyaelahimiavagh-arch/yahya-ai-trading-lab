"""Deterministic, research-only P3 strategy contracts."""

from .contracts import (DecisionReason, LongSetup, StrategyAction,
                        StrategyContext, StrategyContractError,
                        StrategyDecision, StrategyIdentity)
from .features import (FeatureError, FeatureResult, FeatureState, atr, ema,
                       rolling_high, rolling_low, rsi, simple_return, sma)
from .regime import (MarketRegime, RegimeError, RegimeReason, RegimeResult,
                     classify_regime)

__all__ = [
    "MarketRegime", "RegimeError", "RegimeReason", "RegimeResult", "classify_regime",
    "DecisionReason",
    "FeatureError",
    "FeatureResult",
    "FeatureState",
    "LongSetup",
    "StrategyAction",
    "StrategyContext",
    "StrategyContractError",
    "StrategyDecision",
    "StrategyIdentity",
    "atr",
    "ema",
    "rolling_high",
    "rolling_low",
    "rsi",
    "simple_return",
    "sma",
]
