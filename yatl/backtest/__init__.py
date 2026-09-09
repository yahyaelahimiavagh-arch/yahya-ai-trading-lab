"""Deterministic, paper-only P2 backtesting contracts."""

from .config import (
    BacktestConfigError,
    BacktestSpec,
    CONTEXT_INTERVAL,
    EXECUTION_PRICE_POLICY,
    PRIMARY_INTERVAL,
    REGIME_INTERVAL,
)
from .models import BacktestContractError, MarketSnapshot
from .loader import (AcceptedBacktestDataset, BacktestLoadError,
                     latest_spec_from_manifest, load_accepted_dataset)
from .clock import BacktestClock, BacktestClockError, DecisionEvent
from .fills import (FillModelError, FillReason, FillReference, IntentAction,
                    PaperFillEngine, PaperIntent)

__all__ = [
    "BacktestConfigError",
    "BacktestClock",
    "BacktestClockError",
    "BacktestContractError",
    "BacktestSpec",
    "BacktestLoadError",
    "AcceptedBacktestDataset",
    "CONTEXT_INTERVAL",
    "DecisionEvent",
    "EXECUTION_PRICE_POLICY",
    "FillModelError",
    "FillReason",
    "FillReference",
    "IntentAction",
    "MarketSnapshot",
    "PRIMARY_INTERVAL",
    "PaperFillEngine",
    "PaperIntent",
    "REGIME_INTERVAL",
    "latest_spec_from_manifest",
    "load_accepted_dataset",
]
