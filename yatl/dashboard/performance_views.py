"""Deterministic P8-005 performance and segmentation projections."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from .contracts import (
    DashboardSourceIdentity,
    MetricState,
    MetricUnit,
)
from .loader import LoadedP7Export


PERFORMANCE_VIEW_SCHEMA_VERSION = 1
DECIMAL_PRECISION = 256
MAX_SEGMENT_DISPLAY_ROWS = 1024
MAX_TRADE_METRICS = 4096
MAX_LABEL_CHARS = 256
_HEX = frozenset("0123456789abcdef")

_METRIC_SPECS = (
    ("METRIC_COMPLETED_TRADES", MetricUnit.COUNT),
    ("METRIC_WINNING_TRADES", MetricUnit.COUNT),
    ("METRIC_LOSING_TRADES", MetricUnit.COUNT),
    ("METRIC_BREAKEVEN_TRADES", MetricUnit.COUNT),
    ("METRIC_REALIZED_PNL", MetricUnit.USD),
    ("METRIC_GROSS_PNL", MetricUnit.USD),
    ("METRIC_TOTAL_FEES", MetricUnit.USD),
    ("METRIC_TOTAL_SLIPPAGE", MetricUnit.USD),
    ("METRIC_TOTAL_COST", MetricUnit.USD),
    ("METRIC_GROSS_RETURN", MetricUnit.RATIO),
    ("METRIC_NET_RETURN", MetricUnit.RATIO),
    ("METRIC_WIN_RATE", MetricUnit.RATIO),
    ("METRIC_MAX_REALIZED_DRAWDOWN", MetricUnit.USD),
    ("METRIC_TOTAL_HOLDING_TIME", MetricUnit.MILLISECONDS),
    ("METRIC_MIN_HOLDING_TIME", MetricUnit.MILLISECONDS),
    ("METRIC_MAX_HOLDING_TIME", MetricUnit.MILLISECONDS),
    ("METRIC_AVG_HOLDING_TIME", MetricUnit.MILLISECONDS),
    ("METRIC_BEST_TRADE_PNL", MetricUnit.USD),
    ("METRIC_WORST_TRADE_PNL", MetricUnit.USD),
)

_TRADE_METRIC_KEYS = frozenset((
    "trade_index",
    "trade_sha256",
    "realized_pnl_quote",
    "entry_gross_quote",
    "exit_gross_quote",
    "entry_cash_out_quote",
    "gross_return",
    "net_return",
    "total_fee_quote",
    "total_slippage_quote",
    "holding_time_ms",
))
_TRADE_SEGMENT_KEYS = frozenset((
    "segment_id",
    "population",
    "dimension",
    "value",
    "member_trade_sha256",
    "member_count",
    "realized_pnl_quote",
    "total_cost_quote",
    "winning_trades",
    "losing_trades",
    "breakeven_trades",
    "segment_sha256",
))
_ANALYST_TRACE_KEYS = frozenset((
    "trace_sha256",
    "disposition",
    "grounding_code",
    "accepted",
))
_ANALYST_SEGMENT_KEYS = frozenset((
    "segment_id",
    "population",
    "dimension",
    "value",
    "member_trace_sha256",
    "member_count",
    "segment_sha256",
))


class PerformanceViewProjectionError(ValueError):
    """Accepted P7 performance/segment material cannot be projected safely."""


def _valid_exact_decimal_text(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if value != value.strip() or "e" in value.lower():
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite()


@dataclass(frozen=True, slots=True)
class DashboardExactMetricValue:
    """Exact P7 metric string; separate from the frozen 96-char P8-001 metric contract."""

    metric_id: str
    value: str | None
    unit: MetricUnit
    state: MetricState
    source_metric_sha256: str
    display_only: bool = True

    def __post_init__(self):
        expected_ids = tuple(item[0] for item in _METRIC_SPECS)
        valid_value = (
            self.state is MetricState.VALUE
            and _valid_exact_decimal_text(self.value)
        ) or (
            self.state is MetricState.UNAVAILABLE
            and self.value is None
        )
        if (
            self.metric_id not in expected_ids
            or not isinstance(self.unit, MetricUnit)
            or not isinstance(self.state, MetricState)
            or not valid_value
            or not _valid_sha(self.source_metric_sha256)
            or self.display_only is not True
        ):
            raise PerformanceViewProjectionError("Exact performance metric is invalid")

    def as_record(self):
        return {
            "metric_id": self.metric_id,
            "value": self.value,
            "unit": self.unit.value,
            "state": self.state.value,
            "source_metric_sha256": self.source_metric_sha256,
            "display_only": self.display_only,
        }


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    material = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _decimal(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise PerformanceViewProjectionError("Performance decimal is invalid")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise PerformanceViewProjectionError("Performance decimal is invalid") from None
    if not number.is_finite():
        raise PerformanceViewProjectionError("Performance decimal is invalid")
    return number


def _format(value):
    return format(value, "f")


def _bounded_label(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_LABEL_CHARS
        and all(ord(character) >= 32 for character in value)
    )


def _aggregate_trade_metrics(metrics):
    """Reconstruct canonical P7 completed-trade aggregates without extrapolation."""

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        realized_values = [_decimal(item["realized_pnl_quote"]) for item in metrics]
        fee_values = [_decimal(item["total_fee_quote"]) for item in metrics]
        slippage_values = [_decimal(item["total_slippage_quote"]) for item in metrics]

        realized = sum(realized_values, Decimal(0))
        fees = sum(fee_values, Decimal(0))
        slippage = sum(slippage_values, Decimal(0))
        costs = fees + slippage
        wins = sum(value > 0 for value in realized_values)
        losses = sum(value < 0 for value in realized_values)
        breakeven = sum(value == 0 for value in realized_values)
        count = len(metrics)

        gross_return = None
        net_return = None
        win_rate = None
        average_holding = None
        best = None
        worst = None
        gross_pnl = Decimal(0)

        if metrics:
            gross_entry = sum(
                (_decimal(item["entry_gross_quote"]) for item in metrics),
                Decimal(0),
            )
            gross_exit = sum(
                (_decimal(item["exit_gross_quote"]) for item in metrics),
                Decimal(0),
            )
            net_entry_cash = sum(
                (_decimal(item["entry_cash_out_quote"]) for item in metrics),
                Decimal(0),
            )
            if gross_entry <= 0 or net_entry_cash <= 0:
                raise PerformanceViewProjectionError(
                    "Aggregate return denominator is invalid"
                )
            gross_pnl = gross_exit - gross_entry
            gross_return = _format(gross_pnl / gross_entry)
            net_return = _format(realized / net_entry_cash)
            win_rate = _format(Decimal(wins) / Decimal(count))
            total_holding = sum(item["holding_time_ms"] for item in metrics)
            average_holding = _format(Decimal(total_holding) / Decimal(count))
            best = _format(max(realized_values))
            worst = _format(min(realized_values))
        else:
            total_holding = 0

        cumulative = Decimal(0)
        peak = Decimal(0)
        maximum_drawdown = Decimal(0)
        for value in realized_values:
            cumulative += value
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > maximum_drawdown:
                maximum_drawdown = drawdown

    return {
        "completed_trades": str(count),
        "winning_trades": str(wins),
        "losing_trades": str(losses),
        "breakeven_trades": str(breakeven),
        "realized_pnl": _format(realized),
        "gross_pnl": _format(gross_pnl),
        "total_fees": _format(fees),
        "total_slippage": _format(slippage),
        "total_cost": _format(costs),
        "gross_return": gross_return,
        "net_return": net_return,
        "win_rate": win_rate,
        "max_realized_drawdown": _format(maximum_drawdown),
        "total_holding_time": str(total_holding),
        "min_holding_time": (
            str(min(item["holding_time_ms"] for item in metrics))
            if metrics
            else None
        ),
        "max_holding_time": (
            str(max(item["holding_time_ms"] for item in metrics))
            if metrics
            else None
        ),
        "avg_holding_time": average_holding,
        "best_trade_pnl": best,
        "worst_trade_pnl": worst,
    }


_METRIC_KEYS = (
    "completed_trades",
    "winning_trades",
    "losing_trades",
    "breakeven_trades",
    "realized_pnl",
    "gross_pnl",
    "total_fees",
    "total_slippage",
    "total_cost",
    "gross_return",
    "net_return",
    "win_rate",
    "max_realized_drawdown",
    "total_holding_time",
    "min_holding_time",
    "max_holding_time",
    "avg_holding_time",
    "best_trade_pnl",
    "worst_trade_pnl",
)


def _verify_loaded_export(loaded):
    if not isinstance(loaded, LoadedP7Export):
        raise PerformanceViewProjectionError("Performance view requires validated P7 export")
    try:
        record = loaded.record()
        material = {
            "schema_version": record["schema_version"],
            "quality": record["quality"],
            "analytics": record["analytics"],
        }
        quality = record["quality"]
        analytics = record["analytics"]
        chain = quality["accepted_chain"]
        trade_metrics = analytics["trade_metrics"]
        analyst_traces = analytics["analyst_traces"]
        trade_segments = analytics["trade_segments"]
        analyst_segments = analytics["analyst_segments"]
    except (KeyError, TypeError, ValueError):
        raise PerformanceViewProjectionError("Loaded P7 export binding is invalid") from None

    if (
        type(trade_metrics) is not list
        or type(analyst_traces) is not list
        or type(trade_segments) is not list
        or type(analyst_segments) is not list
        or len(trade_metrics) > MAX_TRADE_METRICS
        or len(trade_segments) > MAX_SEGMENT_DISPLAY_ROWS
        or len(analyst_segments) > MAX_SEGMENT_DISPLAY_ROWS
    ):
        raise PerformanceViewProjectionError("Loaded P7 performance collections are invalid")

    quality_safety = quality.get("safety")
    analytics_safety = analytics.get("safety")
    interpretation = analytics.get("interpretation")
    if (
        record.get("export_sha256") != loaded.export_sha256
        or _digest(material) != loaded.export_sha256
        or _digest(quality) != loaded.quality_sha256
        or _digest(analytics) != loaded.segmentation_sha256
        or loaded.source.export_sha256 != loaded.export_sha256
        or loaded.source.symbol != analytics.get("symbol")
        or loaded.source.observed_at_ms != quality.get("snapshot_time_ms")
        or quality.get("status") != "PASS"
        or quality.get("publication_allowed") is not True
        or quality.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or analytics.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or analytics.get("strategy_attribution_status")
        != "UNAVAILABLE_IN_ACCEPTED_DURABLE_P5"
        or not _valid_sha(analytics.get("metrics_sha256"))
        or not isinstance(chain, dict)
        or chain.get("symbol") != loaded.source.symbol
        or chain.get("metrics_sha256") != analytics.get("metrics_sha256")
        or chain.get("segmentation_sha256") != loaded.segmentation_sha256
        or chain.get("completed_trade_count") != len(trade_metrics)
        or chain.get("analyst_trace_count") != len(analyst_traces)
        or not isinstance(quality_safety, dict)
        or quality_safety.get("paper_only") is not True
        or quality_safety.get("read_only") is not True
        or quality_safety.get("live_master_lock") != "OFF"
        or quality_safety.get("strategy_evidence_upgrade") is not False
        or quality_safety.get("trade_permission") is not False
        or quality_safety.get("order_endpoints") is not False
        or quality_safety.get("quantity_authority") is not False
        or quality_safety.get("risk_authorization_mutation") is not False
        or quality_safety.get("ai_direct_execution") is not False
        or not isinstance(analytics_safety, dict)
        or analytics_safety.get("paper_only") is not True
        or analytics_safety.get("read_only") is not True
        or analytics_safety.get("live_master_lock") != "OFF"
        or analytics_safety.get("strategy_evidence_upgrade") is not False
        or analytics_safety.get("trade_permission") is not False
        or analytics_safety.get("order_endpoints") is not False
        or analytics_safety.get("quantity_authority") is not False
        or analytics_safety.get("risk_authorization_mutation") is not False
        or analytics_safety.get("ai_direct_execution") is not False
        or not isinstance(interpretation, dict)
        or interpretation.get("trade_to_strategy_attribution") is not False
        or interpretation.get("trade_to_analyst_disposition_attribution") is not False
        or interpretation.get("causality_claim") is not False
        or interpretation.get("correlation_only") is not True
    ):
        raise PerformanceViewProjectionError("Loaded P7 performance provenance changed")

    indexes = []
    trade_ids = []
    for item in trade_metrics:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _TRADE_METRIC_KEYS
            or type(item["trade_index"]) is not int
            or item["trade_index"] < 0
            or not _valid_sha(item["trade_sha256"])
            or type(item["holding_time_ms"]) is not int
            or item["holding_time_ms"] < 0
        ):
            raise PerformanceViewProjectionError("Accepted P7 trade metric is invalid")
        for name in (
            "realized_pnl_quote",
            "entry_gross_quote",
            "exit_gross_quote",
            "entry_cash_out_quote",
            "gross_return",
            "net_return",
            "total_fee_quote",
            "total_slippage_quote",
        ):
            _decimal(item[name])
        indexes.append(item["trade_index"])
        trade_ids.append(item["trade_sha256"])
    if (
        indexes != sorted(indexes)
        or len(indexes) != len(set(indexes))
        or len(trade_ids) != len(set(trade_ids))
    ):
        raise PerformanceViewProjectionError("Accepted P7 trade metric identity is invalid")

    analyst_trace_ids = []
    for item in analyst_traces:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _ANALYST_TRACE_KEYS
            or not _valid_sha(item["trace_sha256"])
            or item["disposition"] not in ("REVIEW", "INSUFFICIENT_DATA")
            or not isinstance(item["grounding_code"], str)
            or not item["grounding_code"]
            or type(item["accepted"]) is not bool
        ):
            raise PerformanceViewProjectionError("Accepted P7 analyst trace is invalid")
        if item["accepted"]:
            if item["disposition"] != "REVIEW" or item["grounding_code"] != "GROUNDED":
                raise PerformanceViewProjectionError(
                    "Accepted analyst trace semantics are invalid"
                )
        elif (
            item["disposition"] != "INSUFFICIENT_DATA"
            or item["grounding_code"] == "GROUNDED"
        ):
            raise PerformanceViewProjectionError(
                "Rejected analyst trace semantics are invalid"
            )
        analyst_trace_ids.append(item["trace_sha256"])
    if (
        analyst_trace_ids != sorted(analyst_trace_ids)
        or len(analyst_trace_ids) != len(set(analyst_trace_ids))
    ):
        raise PerformanceViewProjectionError("Accepted analyst trace identity is invalid")

    trade_segment_ids = []
    for item in trade_segments:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _TRADE_SEGMENT_KEYS
            or not _valid_sha(item["segment_id"])
            or not _valid_sha(item["segment_sha256"])
            or item["population"] != "COMPLETED_TRADES"
            or item["dimension"]
            not in ("SYMBOL", "STRATEGY_IDENTITY", "EVIDENCE_LABEL")
            or not _bounded_label(item["value"])
            or type(item["member_trade_sha256"]) is not list
            or item["member_trade_sha256"] != sorted(item["member_trade_sha256"])
            or len(set(item["member_trade_sha256"])) != len(item["member_trade_sha256"])
            or any(not _valid_sha(value) for value in item["member_trade_sha256"])
            or type(item["member_count"]) is not int
            or item["member_count"] != len(item["member_trade_sha256"])
            or type(item["winning_trades"]) is not int
            or type(item["losing_trades"]) is not int
            or type(item["breakeven_trades"]) is not int
            or item["winning_trades"] < 0
            or item["losing_trades"] < 0
            or item["breakeven_trades"] < 0
            or item["winning_trades"]
            + item["losing_trades"]
            + item["breakeven_trades"]
            != item["member_count"]
        ):
            raise PerformanceViewProjectionError("Accepted P7 trade segment is invalid")
        _decimal(item["realized_pnl_quote"])
        if _decimal(item["total_cost_quote"]) < 0:
            raise PerformanceViewProjectionError("Accepted P7 trade segment cost is invalid")
        expected_segment_id = _digest({
            "schema_version": 1,
            "population": item["population"],
            "dimension": item["dimension"],
            "value": item["value"],
        })
        base = {key: value for key, value in item.items() if key != "segment_sha256"}
        expected_segment_sha256 = _digest({
            "schema_version": 1,
            "segment": base,
        })
        if (
            item["segment_id"] != expected_segment_id
            or item["segment_sha256"] != expected_segment_sha256
        ):
            raise PerformanceViewProjectionError("Accepted P7 trade segment digest is invalid")
        trade_segment_ids.append(item["segment_id"])
    if len(trade_segment_ids) != len(set(trade_segment_ids)):
        raise PerformanceViewProjectionError("Accepted P7 trade segment identity is duplicate")

    analyst_segment_ids = []
    for item in analyst_segments:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _ANALYST_SEGMENT_KEYS
            or not _valid_sha(item["segment_id"])
            or not _valid_sha(item["segment_sha256"])
            or item["population"] != "ANALYST_TRACES"
            or item["dimension"]
            not in ("ANALYST_DISPOSITION", "GROUNDING_CODE", "TRACE_ACCEPTANCE")
            or not _bounded_label(item["value"])
            or type(item["member_trace_sha256"]) is not list
            or item["member_trace_sha256"] != sorted(item["member_trace_sha256"])
            or len(set(item["member_trace_sha256"])) != len(item["member_trace_sha256"])
            or any(not _valid_sha(value) for value in item["member_trace_sha256"])
            or type(item["member_count"]) is not int
            or item["member_count"] != len(item["member_trace_sha256"])
        ):
            raise PerformanceViewProjectionError("Accepted P7 analyst segment is invalid")
        expected_segment_id = _digest({
            "schema_version": 1,
            "population": item["population"],
            "dimension": item["dimension"],
            "value": item["value"],
        })
        base = {key: value for key, value in item.items() if key != "segment_sha256"}
        expected_segment_sha256 = _digest({
            "schema_version": 1,
            "segment": base,
        })
        if (
            item["segment_id"] != expected_segment_id
            or item["segment_sha256"] != expected_segment_sha256
        ):
            raise PerformanceViewProjectionError(
                "Accepted P7 analyst segment digest is invalid"
            )
        analyst_segment_ids.append(item["segment_id"])
    if len(analyst_segment_ids) != len(set(analyst_segment_ids)):
        raise PerformanceViewProjectionError("Accepted P7 analyst segment identity is duplicate")

    expected_trade_ids = set(trade_ids)
    for dimension in ("SYMBOL", "STRATEGY_IDENTITY", "EVIDENCE_LABEL"):
        seen = [
            member
            for item in trade_segments
            if item["dimension"] == dimension
            for member in item["member_trade_sha256"]
        ]
        if len(seen) != len(set(seen)) or set(seen) != expected_trade_ids:
            raise PerformanceViewProjectionError(
                "Trade segment dimension does not conserve members exactly once"
            )

    expected_trace_ids = set(analyst_trace_ids)
    for dimension in ("ANALYST_DISPOSITION", "GROUNDING_CODE", "TRACE_ACCEPTANCE"):
        seen = [
            member
            for item in analyst_segments
            if item["dimension"] == dimension
            for member in item["member_trace_sha256"]
        ]
        if len(seen) != len(set(seen)) or set(seen) != expected_trace_ids:
            raise PerformanceViewProjectionError(
                "Analyst segment dimension does not conserve members exactly once"
            )

    return (
        analytics,
        tuple(trade_metrics),
        tuple(trade_segments),
        tuple(analyst_segments),
    )


def _reconcile_symbol_segment(symbol, aggregates, trade_segments, trade_ids):
    expected_value = symbol if trade_ids else "NO_COMPLETED_TRADES"
    symbol_segments = [
        item
        for item in trade_segments
        if item["dimension"] == "SYMBOL" and item["value"] == expected_value
    ]
    if len(symbol_segments) != 1:
        raise PerformanceViewProjectionError("Exact symbol segment is missing or duplicate")
    segment = symbol_segments[0]
    if (
        tuple(segment["member_trade_sha256"]) != tuple(sorted(trade_ids))
        or segment["member_count"] != int(aggregates["completed_trades"])
        or segment["realized_pnl_quote"] != aggregates["realized_pnl"]
        or segment["total_cost_quote"] != aggregates["total_cost"]
        or segment["winning_trades"] != int(aggregates["winning_trades"])
        or segment["losing_trades"] != int(aggregates["losing_trades"])
        or segment["breakeven_trades"] != int(aggregates["breakeven_trades"])
    ):
        raise PerformanceViewProjectionError(
            "Completed-trade aggregate does not conserve symbol segment"
        )


def _metric_source_sha(metrics_sha256, metric_key, value, trade_metrics):
    return _digest({
        "source_metrics_sha256": metrics_sha256,
        "projection_formula": "P7_CANONICAL_COMPLETED_TRADE_AGGREGATE_V1",
        "metric_key": metric_key,
        "value": value,
        "source_trade_metrics": trade_metrics,
    })


def _metric_values(metrics_sha256, aggregates, trade_metrics):
    values = []
    for (metric_id, unit), key in zip(_METRIC_SPECS, _METRIC_KEYS):
        value = aggregates[key]
        state = MetricState.VALUE if value is not None else MetricState.UNAVAILABLE
        values.append(
            DashboardExactMetricValue(
                metric_id,
                value,
                unit,
                state,
                _metric_source_sha(metrics_sha256, key, value, trade_metrics),
            )
        )
    return tuple(values)


@dataclass(frozen=True, slots=True)
class DashboardTradeSegmentSummary:
    """Exact accepted P7 trade segment without cross-dimension aggregation."""

    display_id: str
    dimension: str
    label: str
    member_count: int
    realized_pnl: str
    total_cost: str
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    source_segment_id: str
    source_segment_sha256: str
    strategy_evidence: str = "INSUFFICIENT_EVIDENCE"
    display_only: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.display_id, str)
            or not self.display_id.startswith("TRADE_SEGMENT_")
            or self.dimension not in ("symbol", "strategy_identity", "evidence_label")
            or not _bounded_label(self.label)
            or type(self.member_count) is not int
            or self.member_count < 0
            or type(self.winning_trades) is not int
            or type(self.losing_trades) is not int
            or type(self.breakeven_trades) is not int
            or self.winning_trades + self.losing_trades + self.breakeven_trades
            != self.member_count
            or not _valid_sha(self.source_segment_id)
            or not _valid_sha(self.source_segment_sha256)
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or self.display_only is not True
        ):
            raise PerformanceViewProjectionError("Trade segment display row is invalid")
        _decimal(self.realized_pnl)
        if _decimal(self.total_cost) < 0:
            raise PerformanceViewProjectionError("Trade segment display cost is invalid")

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class DashboardAnalystSegmentSummary:
    """Exact accepted P7 analyst segment with trace-count semantics preserved."""

    display_id: str
    dimension: str
    label: str
    trace_count: int
    source_segment_id: str
    source_segment_sha256: str
    strategy_evidence: str = "INSUFFICIENT_EVIDENCE"
    display_only: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.display_id, str)
            or not self.display_id.startswith("ANALYST_SEGMENT_")
            or self.dimension
            not in ("analyst_disposition", "grounding_code", "trace_acceptance")
            or not _bounded_label(self.label)
            or type(self.trace_count) is not int
            or self.trace_count < 0
            or not _valid_sha(self.source_segment_id)
            or not _valid_sha(self.source_segment_sha256)
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or self.display_only is not True
        ):
            raise PerformanceViewProjectionError("Analyst segment display row is invalid")

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class PerformanceSegmentationProjection:
    """Bounded display-only P8-005 projection over accepted P7 analytics."""

    source: DashboardSourceIdentity
    metrics: tuple[DashboardExactMetricValue, ...]
    trade_segments: tuple[DashboardTradeSegmentSummary, ...]
    analyst_segments: tuple[DashboardAnalystSegmentSummary, ...]
    source_metrics_sha256: str
    source_segmentation_sha256: str
    strategy_evidence: str = "INSUFFICIENT_EVIDENCE"
    aggregation_scope: str = "COMPLETED_PAPER_TRADES_ONLY"
    cross_dimension_aggregation: bool = False
    causality_claim: bool = False
    schema_version: int = PERFORMANCE_VIEW_SCHEMA_VERSION

    def __post_init__(self):
        if (
            not isinstance(self.source, DashboardSourceIdentity)
            or type(self.metrics) is not tuple
            or len(self.metrics) != len(_METRIC_SPECS)
            or any(not isinstance(item, DashboardExactMetricValue) for item in self.metrics)
            or tuple(item.metric_id for item in self.metrics)
            != tuple(item[0] for item in _METRIC_SPECS)
            or type(self.trade_segments) is not tuple
            or len(self.trade_segments) > MAX_SEGMENT_DISPLAY_ROWS
            or any(
                not isinstance(item, DashboardTradeSegmentSummary)
                for item in self.trade_segments
            )
            or type(self.analyst_segments) is not tuple
            or len(self.analyst_segments) > MAX_SEGMENT_DISPLAY_ROWS
            or any(
                not isinstance(item, DashboardAnalystSegmentSummary)
                for item in self.analyst_segments
            )
            or not _valid_sha(self.source_metrics_sha256)
            or not _valid_sha(self.source_segmentation_sha256)
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or self.aggregation_scope != "COMPLETED_PAPER_TRADES_ONLY"
            or self.cross_dimension_aggregation is not False
            or self.causality_claim is not False
            or self.schema_version != PERFORMANCE_VIEW_SCHEMA_VERSION
        ):
            raise PerformanceViewProjectionError(
                "Performance/segmentation projection is invalid"
            )
        trade_display_ids = tuple(item.display_id for item in self.trade_segments)
        analyst_display_ids = tuple(item.display_id for item in self.analyst_segments)
        if (
            len(set(trade_display_ids)) != len(trade_display_ids)
            or len(set(analyst_display_ids)) != len(analyst_display_ids)
        ):
            raise PerformanceViewProjectionError("Display segment identity is duplicate")

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "source": self.source.as_record(),
            "metrics": [item.as_record() for item in self.metrics],
            "trade_segments": [item.as_record() for item in self.trade_segments],
            "analyst_segments": [item.as_record() for item in self.analyst_segments],
            "source_metrics_sha256": self.source_metrics_sha256,
            "source_segmentation_sha256": self.source_segmentation_sha256,
            "strategy_evidence": self.strategy_evidence,
            "aggregation_scope": self.aggregation_scope,
            "cross_dimension_aggregation": self.cross_dimension_aggregation,
            "causality_claim": self.causality_claim,
        }

    @property
    def projection_sha256(self):
        return _digest(self.as_record())


def project_performance_segmentation(loaded):
    """Project accepted P7 metrics/segments with exact null and evidence semantics."""

    analytics, trade_metrics, trade_segments, analyst_segments = _verify_loaded_export(loaded)
    aggregates = _aggregate_trade_metrics(trade_metrics)
    _reconcile_symbol_segment(
        analytics["symbol"],
        aggregates,
        trade_segments,
        tuple(item["trade_sha256"] for item in trade_metrics),
    )

    metrics = _metric_values(
        analytics["metrics_sha256"],
        aggregates,
        trade_metrics,
    )

    display_trade_segments = tuple(
        DashboardTradeSegmentSummary(
            display_id=f"TRADE_SEGMENT_{index:04d}",
            dimension=item["dimension"].lower(),
            label=item["value"],
            member_count=item["member_count"],
            realized_pnl=item["realized_pnl_quote"],
            total_cost=item["total_cost_quote"],
            winning_trades=item["winning_trades"],
            losing_trades=item["losing_trades"],
            breakeven_trades=item["breakeven_trades"],
            source_segment_id=item["segment_id"],
            source_segment_sha256=item["segment_sha256"],
        )
        for index, item in enumerate(trade_segments)
    )
    display_analyst_segments = tuple(
        DashboardAnalystSegmentSummary(
            display_id=f"ANALYST_SEGMENT_{index:04d}",
            dimension=item["dimension"].lower(),
            label=item["value"],
            trace_count=item["member_count"],
            source_segment_id=item["segment_id"],
            source_segment_sha256=item["segment_sha256"],
        )
        for index, item in enumerate(analyst_segments)
    )

    return PerformanceSegmentationProjection(
        source=loaded.source,
        metrics=metrics,
        trade_segments=display_trade_segments,
        analyst_segments=display_analyst_segments,
        source_metrics_sha256=analytics["metrics_sha256"],
        source_segmentation_sha256=loaded.segmentation_sha256,
    )
