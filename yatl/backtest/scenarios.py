"""Deterministic no-strategy scenarios over accepted public-real P1 data."""

from dataclasses import dataclass, replace
from decimal import Decimal

from .artifacts import ArtifactError, artifact_json, build_run_manifest
from .clock import BacktestClock, BacktestClockError
from .config import BacktestSpec
from .costs import CostedFill, CostModelError, apply_costs
from .fills import FillModelError, FillReason, FillReference, IntentAction
from .loader import (AcceptedBacktestDataset, BacktestLoadError,
                     latest_spec_from_manifest, load_accepted_dataset)
from .metrics import EquityPoint, MetricsError, PerformanceReport, calculate_metrics
from .portfolio import PortfolioError, PortfolioLedger


SCENARIOS = ("NO_TRADE", "SINGLE_ROUND_TRIP", "CONTROLLED_MULTI_TRADE")
QUANTITIES = {"BTCUSDT": "0.01", "ETHUSDT": "0.1"}


class ScenarioError(Exception):
    """A P2 real-data scripted scenario failed a deterministic safety gate."""


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    symbol: str
    report: PerformanceReport
    manifest_json: str
    zero_cost_net_pnl_quote: Decimal

    def __post_init__(self):
        if (self.name not in SCENARIOS or self.symbol not in QUANTITIES
                or not isinstance(self.report, PerformanceReport)
                or not isinstance(self.manifest_json, str)
                or type(self.zero_cost_net_pnl_quote) is not Decimal
                or not self.zero_cost_net_pnl_quote.is_finite()):
            raise ScenarioError("Scenario result is invalid")


def _schedule(name, event_count):
    if name not in SCENARIOS or type(event_count) is not int:
        raise ScenarioError("Scenario name or event count is invalid")
    if name == "NO_TRADE":
        return {}
    if event_count < 20:
        raise ScenarioError("Scripted trading scenarios require at least 20 events")
    if name == "SINGLE_ROUND_TRIP":
        pairs = ((1, event_count - 2),)
    else:
        pairs = ((1, 4), (7, 10), (13, event_count - 2))
    schedule = {}
    for entry, exit_time in pairs:
        if entry >= exit_time or exit_time >= event_count:
            raise ScenarioError("Scripted trade schedule is invalid")
        schedule[entry] = IntentAction.ENTER_LONG
        schedule[exit_time] = IntentAction.EXIT_LONG
    return schedule


def _execute(dataset, name):
    if (not isinstance(dataset, AcceptedBacktestDataset)
            or dataset.spec.symbol not in QUANTITIES):
        raise ScenarioError("Scenario requires an accepted BTC or ETH dataset")
    try:
        events = tuple(BacktestClock(dataset).events())
    except BacktestClockError:
        raise ScenarioError("Scenario event clock failed safely") from None
    schedule = _schedule(name, len(events))
    if not events:
        raise ScenarioError("Scenario event sequence is empty")
    primary_by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(primary_by_open) != len(dataset.primary):
        raise ScenarioError("Scenario primary candles are duplicated")

    ledger = PortfolioLedger(dataset.spec)
    fills: list[CostedFill] = []
    initial_mark = events[0].snapshot.latest_primary.close
    points = [EquityPoint(events[0].decision_time_ms, ledger.snapshot(initial_mark))]
    for index, event in enumerate(events[1:], start=1):
        candle = primary_by_open.get(event.eligible_fill_open_time_ms)
        if candle is None or not candle.is_closed:
            raise ScenarioError("Scenario fill candle is unavailable")
        action = schedule.get(index)
        if action is not None:
            reason = (FillReason.NEXT_PRIMARY_OPEN
                      if action is IntentAction.ENTER_LONG else FillReason.SCRIPTED_EXIT)
            reference = FillReference(
                action, dataset.spec.symbol, event.decision_time_ms,
                event.eligible_fill_open_time_ms, QUANTITIES[dataset.spec.symbol],
                candle.open, reason,
            )
            fill = apply_costs(reference, dataset.spec)
            ledger.apply(fill)
            fills.append(fill)
        points.append(EquityPoint(event.decision_time_ms, ledger.snapshot(candle.open)))
    if ledger.has_position:
        raise ScenarioError("Scenario ended with an open position")
    report = calculate_metrics(tuple(points))
    manifest = build_run_manifest(dataset, tuple(fills), report)
    return tuple(fills), report, artifact_json(manifest)


def run_scripted_scenario(dataset, name):
    try:
        fills, report, encoded = _execute(dataset, name)
        zero_spec = replace(dataset.spec, fee_bps="0", slippage_bps="0")
        zero_dataset = replace(dataset, spec=zero_spec)
        _, zero_report, _ = _execute(zero_dataset, name)
        if (name == "NO_TRADE" and report.net_pnl_quote != zero_report.net_pnl_quote
                or name != "NO_TRADE"
                and not report.net_pnl_quote < zero_report.net_pnl_quote
                or name != "NO_TRADE" and report.total_cost_quote <= 0):
            raise ScenarioError("Explicit costs did not reduce the scripted result")
        repeated_fills, repeated_report, repeated = _execute(dataset, name)
        if fills != repeated_fills or report != repeated_report or encoded != repeated:
            raise ScenarioError("Scripted scenario replay is not byte-identical")
        return ScenarioResult(name, dataset.spec.symbol, report, encoded,
                              zero_report.net_pnl_quote)
    except ScenarioError:
        raise
    except (ArtifactError, BacktestClockError, CostModelError, FillModelError,
            MetricsError, PortfolioError, TypeError, ValueError):
        raise ScenarioError("Scripted scenario failed safely") from None


def run_real_scenario_matrix(database_path, manifest_path, *, hours=24):
    if type(hours) is not int or hours < 20:
        raise ScenarioError("Scenario matrix requires at least 20 hours")
    results = []
    try:
        for symbol in QUANTITIES:
            spec = latest_spec_from_manifest(manifest_path, symbol, hours=hours)
            dataset = load_accepted_dataset(database_path, manifest_path, spec)
            for name in SCENARIOS:
                results.append(run_scripted_scenario(dataset, name))
    except (BacktestLoadError, ScenarioError, TypeError, ValueError):
        raise ScenarioError("Real-data scenario matrix failed safely") from None
    return tuple(results)
