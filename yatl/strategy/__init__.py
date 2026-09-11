"""Deterministic, research-only P3 strategy contracts."""

from .contracts import (DecisionReason, LongSetup, StrategyAction,
                        StrategyContext, StrategyContractError,
                        StrategyDecision, StrategyIdentity)
from .features import (FeatureError, FeatureResult, FeatureState, atr, ema,
                       rolling_high, rolling_low, rsi, simple_return, sma)
from .regime import (MarketRegime, RegimeError, RegimeReason, RegimeResult,
                     classify_regime)
from .registry import (ParameterRule, RegistryError, StrategyConfiguration,
                       StrategyDefinition, StrategyRegistry)
from .trend import (CONFIGURATION as TREND_PULLBACK_CONFIGURATION,
                    IDENTITY as TREND_PULLBACK_IDENTITY, TrendStrategyError,
                    evaluate_trend_pullback)
from .breakout import (CONFIGURATION as BREAKOUT_CONFIGURATION,
                       IDENTITY as BREAKOUT_IDENTITY, BreakoutStrategyError,
                       evaluate_breakout)
from .adapter import (FIXED_RESEARCH_QUANTITY, AdapterStep,
                      ResearchSignalAdapter, SignalAdapterError)
from .evaluate import (MIN_EVALUATION_DAYS, MIN_TOTAL_TRADES,
                       MIN_TRADES_PER_SYMBOL, EvaluationError,
                       EvaluationPlan, EvaluationReport, EvidenceLabel,
                       EvidenceReason, SymbolEvidence, assess_evidence,
                       evaluation_input_sha256)

__all__ = [
    "ParameterRule", "RegistryError", "StrategyConfiguration",
    "StrategyDefinition", "StrategyRegistry",
    "TREND_PULLBACK_CONFIGURATION", "TREND_PULLBACK_IDENTITY",
    "TrendStrategyError", "evaluate_trend_pullback",
    "BREAKOUT_CONFIGURATION", "BREAKOUT_IDENTITY",
    "BreakoutStrategyError", "evaluate_breakout",
    "FIXED_RESEARCH_QUANTITY", "AdapterStep",
    "ResearchSignalAdapter", "SignalAdapterError",
    "MIN_EVALUATION_DAYS", "MIN_TOTAL_TRADES", "MIN_TRADES_PER_SYMBOL",
    "EvaluationError", "EvaluationPlan", "EvaluationReport",
    "EvidenceLabel", "EvidenceReason", "SymbolEvidence", "assess_evidence",
    "evaluation_input_sha256",
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
