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

__all__ = [
    "BacktestConfigError",
    "BacktestContractError",
    "BacktestSpec",
    "BacktestLoadError",
    "AcceptedBacktestDataset",
    "CONTEXT_INTERVAL",
    "EXECUTION_PRICE_POLICY",
    "MarketSnapshot",
    "PRIMARY_INTERVAL",
    "REGIME_INTERVAL",
    "latest_spec_from_manifest",
    "load_accepted_dataset",
]
