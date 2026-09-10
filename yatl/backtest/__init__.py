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
from .costs import CostedFill, CostModelError, apply_costs
from .portfolio import PortfolioError, PortfolioLedger, PortfolioSnapshot
from .metrics import (EquityPoint, MetricsError, PerformanceReport,
                      calculate_metrics)
from .artifacts import (ArtifactError, build_run_manifest, artifact_json,
                        write_run_manifest)

__all__ = [
    "BacktestConfigError",
    "BacktestClock",
    "BacktestClockError",
    "BacktestContractError",
    "BacktestSpec",
    "BacktestLoadError",
    "AcceptedBacktestDataset",
    "ArtifactError",
    "CONTEXT_INTERVAL",
    "CostedFill",
    "CostModelError",
    "DecisionEvent",
    "EquityPoint",
    "EXECUTION_PRICE_POLICY",
    "FillModelError",
    "FillReason",
    "FillReference",
    "IntentAction",
    "MarketSnapshot",
    "MetricsError",
    "PRIMARY_INTERVAL",
    "PaperFillEngine",
    "PaperIntent",
    "PortfolioError",
    "PortfolioLedger",
    "PortfolioSnapshot",
    "PerformanceReport",
    "REGIME_INTERVAL",
    "latest_spec_from_manifest",
    "load_accepted_dataset",
    "apply_costs",
    "artifact_json",
    "build_run_manifest",
    "calculate_metrics",
    "write_run_manifest",
]
