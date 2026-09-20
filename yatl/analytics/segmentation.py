"""Deterministic conservative segmentation of accepted P7 analytics populations."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from .contracts import AnalyticsSourceKind, StrategyEvidenceState
from .ingestion import (
    AnalyticsIngestionError,
    UpstreamSourceSpec,
    _connect_readonly,
    _p6_canonical,
    _safe_stat,
    _sha256_file,
)
from .metrics import (
    DECIMAL_PRECISION,
    PerformanceMetricsError,
    TradePerformanceMetric,
    calculate_performance_metrics,
)
from .trades import TradeReconstructionError, reconstruct_paper_trades


SEGMENTATION_SCHEMA_VERSION = 1
MAX_SEGMENT_MEMBERS = 4096
UNATTRIBUTED_STRATEGY_IDENTITY = "UNATTRIBUTED_DURABLE_P5"
STRATEGY_ATTRIBUTION_STATUS = "UNAVAILABLE_IN_ACCEPTED_DURABLE_P5"


class SegmentationError(TradeReconstructionError):
    """Accepted analytics cannot be partitioned without ambiguity or double counting."""


class SegmentPopulation(str, Enum):
    COMPLETED_TRADES = "COMPLETED_TRADES"
    ANALYST_TRACES = "ANALYST_TRACES"


class SegmentDimension(str, Enum):
    SYMBOL = "SYMBOL"
    STRATEGY_IDENTITY = "STRATEGY_IDENTITY"
    EVIDENCE_LABEL = "EVIDENCE_LABEL"
    ANALYST_DISPOSITION = "ANALYST_DISPOSITION"
    GROUNDING_CODE = "GROUNDING_CODE"
    TRACE_ACCEPTANCE = "TRACE_ACCEPTANCE"


TRADE_DIMENSIONS = (
    SegmentDimension.SYMBOL,
    SegmentDimension.STRATEGY_IDENTITY,
    SegmentDimension.EVIDENCE_LABEL,
)
ANALYST_DIMENSIONS = (
    SegmentDimension.ANALYST_DISPOSITION,
    SegmentDimension.GROUNDING_CODE,
    SegmentDimension.TRACE_ACCEPTANCE,
)
ALLOWED_DISPOSITIONS = frozenset(("REVIEW", "INSUFFICIENT_DATA"))
ALLOWED_GROUNDING_CODES = frozenset((
    "GROUNDED",
    "UPSTREAM_REJECTED",
    "INPUT_BINDING_MISMATCH",
    "UNSUPPORTED_CLAIM",
    "CLAIM_SHAPE_MISMATCH",
    "EVIDENCE_REFERENCE_MISMATCH",
    "EVIDENCE_STATE_INVALID",
    "CONTRADICTION",
))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha(value, label):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SegmentationError(f"{label} digest is invalid")
    return value


def _decimal(value, label):
    if not isinstance(value, str) or not value:
        raise SegmentationError(f"{label} is invalid")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise SegmentationError(f"{label} is invalid") from None
    if not number.is_finite():
        raise SegmentationError(f"{label} is not finite")
    return number


def _format(value):
    return format(value, "f")


def _segment_id(population, dimension, value):
    return _digest({
        "schema_version": SEGMENTATION_SCHEMA_VERSION,
        "population": population.value,
        "dimension": dimension.value,
        "value": value,
    })


@dataclass(frozen=True, slots=True)
class AnalystTraceDimensionRecord:
    """Sanitized immutable P6 fields usable for trace-only segmentation."""

    trace_sha256: str
    disposition: str
    grounding_code: str
    accepted: bool

    def __post_init__(self):
        _sha(self.trace_sha256, "Analyst trace")
        if (
            self.disposition not in ALLOWED_DISPOSITIONS
            or self.grounding_code not in ALLOWED_GROUNDING_CODES
            or type(self.accepted) is not bool
        ):
            raise SegmentationError("Analyst trace dimension is invalid")
        if self.accepted:
            if (
                self.disposition != "REVIEW"
                or self.grounding_code != "GROUNDED"
            ):
                raise SegmentationError(
                    "Accepted analyst trace dimensions are inconsistent"
                )
        elif (
            self.disposition != "INSUFFICIENT_DATA"
            or self.grounding_code == "GROUNDED"
        ):
            raise SegmentationError(
                "Rejected analyst trace dimensions are inconsistent"
            )

    def as_record(self):
        return {
            "trace_sha256": self.trace_sha256,
            "disposition": self.disposition,
            "grounding_code": self.grounding_code,
            "accepted": self.accepted,
        }


@dataclass(frozen=True, slots=True)
class TradeSegment:
    population: SegmentPopulation
    dimension: SegmentDimension
    value: str
    member_trade_sha256: tuple[str, ...]
    member_count: int
    realized_pnl_quote: str
    total_cost_quote: str
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    def __post_init__(self):
        if (
            self.population is not SegmentPopulation.COMPLETED_TRADES
            or self.dimension not in TRADE_DIMENSIONS
            or not isinstance(self.value, str)
            or not self.value
            or type(self.member_trade_sha256) is not tuple
            or len(self.member_trade_sha256) > MAX_SEGMENT_MEMBERS
            or any(not isinstance(item, str) for item in self.member_trade_sha256)
            or tuple(sorted(self.member_trade_sha256)) != self.member_trade_sha256
            or len(set(self.member_trade_sha256)) != len(self.member_trade_sha256)
            or type(self.member_count) is not int
            or self.member_count != len(self.member_trade_sha256)
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.winning_trades,
                    self.losing_trades,
                    self.breakeven_trades,
                )
            )
        ):
            raise SegmentationError("Trade segment identity is invalid")
        for item in self.member_trade_sha256:
            _sha(item, "Trade segment member")
        _decimal(self.realized_pnl_quote, "Segment realized PnL")
        if _decimal(self.total_cost_quote, "Segment total cost") < 0:
            raise SegmentationError("Trade segment cost is negative")
        if (
            self.winning_trades
            + self.losing_trades
            + self.breakeven_trades
            != self.member_count
        ):
            raise SegmentationError("Trade segment outcome counts do not conserve")

    @property
    def segment_id(self):
        return _segment_id(self.population, self.dimension, self.value)

    def as_record(self):
        return {
            "segment_id": self.segment_id,
            "population": self.population.value,
            "dimension": self.dimension.value,
            "value": self.value,
            "member_trade_sha256": list(self.member_trade_sha256),
            "member_count": self.member_count,
            "realized_pnl_quote": self.realized_pnl_quote,
            "total_cost_quote": self.total_cost_quote,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
        }

    @property
    def segment_sha256(self):
        return _digest({
            "schema_version": SEGMENTATION_SCHEMA_VERSION,
            "segment": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class AnalystSegment:
    population: SegmentPopulation
    dimension: SegmentDimension
    value: str
    member_trace_sha256: tuple[str, ...]

    def __post_init__(self):
        if (
            self.population is not SegmentPopulation.ANALYST_TRACES
            or self.dimension not in ANALYST_DIMENSIONS
            or not isinstance(self.value, str)
            or not self.value
            or type(self.member_trace_sha256) is not tuple
            or len(self.member_trace_sha256) > MAX_SEGMENT_MEMBERS
            or tuple(sorted(self.member_trace_sha256)) != self.member_trace_sha256
            or len(set(self.member_trace_sha256)) != len(self.member_trace_sha256)
        ):
            raise SegmentationError("Analyst segment identity is invalid")
        for item in self.member_trace_sha256:
            _sha(item, "Analyst segment member")

    @property
    def segment_id(self):
        return _segment_id(self.population, self.dimension, self.value)

    @property
    def member_count(self):
        return len(self.member_trace_sha256)

    def as_record(self):
        return {
            "segment_id": self.segment_id,
            "population": self.population.value,
            "dimension": self.dimension.value,
            "value": self.value,
            "member_trace_sha256": list(self.member_trace_sha256),
            "member_count": self.member_count,
        }

    @property
    def segment_sha256(self):
        return _digest({
            "schema_version": SEGMENTATION_SCHEMA_VERSION,
            "segment": self.as_record(),
        })


def _trade_segment(dimension, value, members):
    if type(members) is not tuple or any(
        not isinstance(item, TradePerformanceMetric) for item in members
    ):
        raise SegmentationError("Trade segment members are invalid")
    ordered = tuple(sorted(members, key=lambda item: item.trade_sha256))
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        realized_values = [
            _decimal(item.realized_pnl_quote, "Trade realized PnL")
            for item in ordered
        ]
        costs = [
            _decimal(item.total_fee_quote, "Trade fee")
            + _decimal(item.total_slippage_quote, "Trade slippage")
            for item in ordered
        ]
        realized = sum(realized_values, Decimal(0))
        total_cost = sum(costs, Decimal(0))
    return TradeSegment(
        SegmentPopulation.COMPLETED_TRADES,
        dimension,
        value,
        tuple(item.trade_sha256 for item in ordered),
        len(ordered),
        _format(realized),
        _format(total_cost),
        sum(value > 0 for value in realized_values),
        sum(value < 0 for value in realized_values),
        sum(value == 0 for value in realized_values),
    )


def _analyst_segment(dimension, value, members):
    if type(members) is not tuple or any(
        not isinstance(item, AnalystTraceDimensionRecord) for item in members
    ):
        raise SegmentationError("Analyst segment members are invalid")
    return AnalystSegment(
        SegmentPopulation.ANALYST_TRACES,
        dimension,
        value,
        tuple(sorted(item.trace_sha256 for item in members)),
    )


def _group_records(records, dimension, value_fn, segment_builder):
    buckets = {}
    for item in records:
        value = value_fn(item)
        if not isinstance(value, str) or not value:
            raise SegmentationError("Segment dimension value is invalid")
        buckets.setdefault(value, []).append(item)
    if not buckets:
        return (segment_builder(dimension, _empty_value(dimension), ()),)
    return tuple(
        segment_builder(dimension, value, tuple(buckets[value]))
        for value in sorted(buckets)
    )


def _empty_value(dimension):
    if dimension is SegmentDimension.SYMBOL:
        return "NO_COMPLETED_TRADES"
    if dimension is SegmentDimension.STRATEGY_IDENTITY:
        return UNATTRIBUTED_STRATEGY_IDENTITY
    if dimension is SegmentDimension.EVIDENCE_LABEL:
        return StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value
    if dimension is SegmentDimension.ANALYST_DISPOSITION:
        return "NO_ANALYST_TRACES"
    if dimension is SegmentDimension.GROUNDING_CODE:
        return "NO_ANALYST_TRACES"
    if dimension is SegmentDimension.TRACE_ACCEPTANCE:
        return "NO_ANALYST_TRACES"
    raise SegmentationError("Unsupported empty segment dimension")


def _read_analyst_dimensions(spec):
    before_stat = _safe_stat(spec.database_path)
    before_sha = _sha256_file(spec.database_path)
    if before_sha != spec.expected_database_sha256:
        raise SegmentationError("P6 database identity changed before segmentation")
    connection = _connect_readonly(spec.database_path)
    try:
        encoded, _ = _p6_canonical(connection)
    except AnalyticsIngestionError:
        raise SegmentationError("P6 trace segmentation failed closed") from None
    finally:
        connection.close()
    after_stat = _safe_stat(spec.database_path)
    after_sha = _sha256_file(spec.database_path)
    if before_stat != after_stat or before_sha != after_sha:
        raise SegmentationError("P6 database changed during segmentation")

    payload = json.loads(encoded)
    traces = tuple(
        AnalystTraceDimensionRecord(
            item["trace_sha256"],
            item["disposition"],
            item["grounding_code"],
            bool(item["accepted"]),
        )
        for item in payload["traces"]
    )
    identities = tuple(item.trace_sha256 for item in traces)
    if len(set(identities)) != len(identities):
        raise SegmentationError("P6 trace identities are duplicate")
    return tuple(sorted(traces, key=lambda item: item.trace_sha256))


def _trade_members_for_segment(segment, metric_by_sha):
    try:
        return tuple(metric_by_sha[item] for item in segment.member_trade_sha256)
    except KeyError:
        raise SegmentationError("Trade segment references an unknown metric") from None


def _analyst_members_for_segment(segment, trace_by_sha):
    try:
        return tuple(trace_by_sha[item] for item in segment.member_trace_sha256)
    except KeyError:
        raise SegmentationError("Analyst segment references an unknown trace") from None


@dataclass(frozen=True, slots=True)
class SegmentationReport:
    metrics_sha256: str
    reconstruction_sha256: str
    timeline_sha256: str
    symbol: str
    trade_metrics: tuple[TradePerformanceMetric, ...]
    analyst_traces: tuple[AnalystTraceDimensionRecord, ...]
    trade_segments: tuple[TradeSegment, ...]
    analyst_segments: tuple[AnalystSegment, ...]
    strategy_attribution_status: str = STRATEGY_ATTRIBUTION_STATUS
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = SEGMENTATION_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != SEGMENTATION_SCHEMA_VERSION
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or self.strategy_attribution_status != STRATEGY_ATTRIBUTION_STATUS
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
            or type(self.trade_metrics) is not tuple
            or type(self.analyst_traces) is not tuple
            or type(self.trade_segments) is not tuple
            or type(self.analyst_segments) is not tuple
            or any(not isinstance(item, TradePerformanceMetric) for item in self.trade_metrics)
            or any(
                not isinstance(item, AnalystTraceDimensionRecord)
                for item in self.analyst_traces
            )
            or any(not isinstance(item, TradeSegment) for item in self.trade_segments)
            or any(not isinstance(item, AnalystSegment) for item in self.analyst_segments)
        ):
            raise SegmentationError("Segmentation report identity is invalid")
        for value, label in (
            (self.metrics_sha256, "Metrics"),
            (self.reconstruction_sha256, "Reconstruction"),
            (self.timeline_sha256, "Timeline"),
        ):
            _sha(value, label)

        metric_by_sha = {item.trade_sha256: item for item in self.trade_metrics}
        trace_by_sha = {item.trace_sha256: item for item in self.analyst_traces}
        if len(metric_by_sha) != len(self.trade_metrics):
            raise SegmentationError("Trade metric identities are duplicate")
        if len(trace_by_sha) != len(self.analyst_traces):
            raise SegmentationError("Analyst trace identities are duplicate")

        self._validate_trade_partitions(metric_by_sha)
        self._validate_analyst_partitions(trace_by_sha)

    def _validate_trade_partitions(self, metric_by_sha):
        dimensions = tuple(item.dimension for item in self.trade_segments)
        if set(dimensions) != set(TRADE_DIMENSIONS):
            raise SegmentationError("Trade segment dimension coverage is incomplete")
        expected_ids = set(metric_by_sha)
        for dimension in TRADE_DIMENSIONS:
            segments = tuple(
                item for item in self.trade_segments
                if item.dimension is dimension
            )
            seen = []
            for segment in segments:
                members = _trade_members_for_segment(segment, metric_by_sha)
                expected = _trade_segment(segment.dimension, segment.value, members)
                if expected != segment:
                    raise SegmentationError("Trade segment arithmetic is inconsistent")
                seen.extend(segment.member_trade_sha256)

                if dimension is SegmentDimension.SYMBOL:
                    expected_value = self.symbol if members else "NO_COMPLETED_TRADES"
                    if segment.value != expected_value:
                        raise SegmentationError("Symbol segment value is invalid")
                elif dimension is SegmentDimension.STRATEGY_IDENTITY:
                    if segment.value != UNATTRIBUTED_STRATEGY_IDENTITY:
                        raise SegmentationError(
                            "Durable P5 evidence cannot assert strategy identity"
                        )
                elif (
                    dimension is SegmentDimension.EVIDENCE_LABEL
                    and segment.value
                    != StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value
                ):
                    raise SegmentationError("Evidence label segment was upgraded")

            if (
                len(seen) != len(set(seen))
                or set(seen) != expected_ids
            ):
                raise SegmentationError(
                    "Trade partition does not conserve members exactly once"
                )

    def _validate_analyst_partitions(self, trace_by_sha):
        dimensions = tuple(item.dimension for item in self.analyst_segments)
        if set(dimensions) != set(ANALYST_DIMENSIONS):
            raise SegmentationError("Analyst segment dimension coverage is incomplete")
        expected_ids = set(trace_by_sha)
        for dimension in ANALYST_DIMENSIONS:
            segments = tuple(
                item for item in self.analyst_segments
                if item.dimension is dimension
            )
            seen = []
            for segment in segments:
                members = _analyst_members_for_segment(segment, trace_by_sha)
                expected = _analyst_segment(segment.dimension, segment.value, members)
                if expected != segment:
                    raise SegmentationError("Analyst segment membership is inconsistent")
                seen.extend(segment.member_trace_sha256)
                if members:
                    if dimension is SegmentDimension.ANALYST_DISPOSITION:
                        if any(item.disposition != segment.value for item in members):
                            raise SegmentationError("Disposition segment is ambiguous")
                    elif dimension is SegmentDimension.GROUNDING_CODE:
                        if any(item.grounding_code != segment.value for item in members):
                            raise SegmentationError("Grounding segment is ambiguous")
                    elif dimension is SegmentDimension.TRACE_ACCEPTANCE:
                        expected_value = (
                            "ACCEPTED" if all(item.accepted for item in members)
                            else "REJECTED"
                        )
                        if any(item.accepted != members[0].accepted for item in members):
                            raise SegmentationError("Acceptance segment is ambiguous")
                        if segment.value != expected_value:
                            raise SegmentationError("Acceptance segment value is invalid")
                elif segment.value != "NO_ANALYST_TRACES":
                    raise SegmentationError("Empty analyst segment value is invalid")

            if len(seen) != len(set(seen)) or set(seen) != expected_ids:
                raise SegmentationError(
                    "Analyst partition does not conserve members exactly once"
                )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "metrics_sha256": self.metrics_sha256,
            "reconstruction_sha256": self.reconstruction_sha256,
            "timeline_sha256": self.timeline_sha256,
            "symbol": self.symbol,
            "strategy_evidence": self.strategy_evidence.value,
            "strategy_attribution_status": self.strategy_attribution_status,
            "trade_metrics": [item.as_record() for item in self.trade_metrics],
            "analyst_traces": [item.as_record() for item in self.analyst_traces],
            "trade_segments": [
                {**item.as_record(), "segment_sha256": item.segment_sha256}
                for item in self.trade_segments
            ],
            "analyst_segments": [
                {**item.as_record(), "segment_sha256": item.segment_sha256}
                for item in self.analyst_segments
            ],
            "interpretation": {
                "trade_to_strategy_attribution": False,
                "trade_to_analyst_disposition_attribution": False,
                "causality_claim": False,
                "correlation_only": True,
                "reason": (
                    "Accepted durable P5 execution evidence does not persist a "
                    "strategy identifier or a cryptographic trade-to-P6-trace link."
                ),
            },
            "safety": {
                "descriptive_only": True,
                "read_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "strategy_evidence_upgrade": False,
                "upstream_mutation": False,
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
        }

    @property
    def segmentation_sha256(self):
        return _digest(self.as_record())

    @property
    def canonical_json(self):
        return _json(self.as_record()) + "\n"


def build_segmentation(snapshot_time_ms, specs):
    """Build exact per-population partitions without inventing cross-population links."""

    if type(specs) is not tuple or len(specs) != 2:
        raise SegmentationError("Segmentation requires exactly two upstream source specs")
    if any(not isinstance(item, UpstreamSourceSpec) for item in specs):
        raise SegmentationError("Segmentation source specification is invalid")

    try:
        reconstruction = reconstruct_paper_trades(snapshot_time_ms, specs)
        metrics = calculate_performance_metrics(reconstruction)
    except (TradeReconstructionError, PerformanceMetricsError):
        raise SegmentationError("Segmentation upstream analytics failed closed") from None

    p6 = tuple(
        item
        for item in specs
        if item.source_kind is AnalyticsSourceKind.P6_ANALYST_TRACE
    )
    if len(p6) != 1:
        raise SegmentationError("Segmentation requires exactly one P6 trace source")
    if p6[0].symbol != metrics.symbol:
        raise SegmentationError("Segmentation P5/P6 symbols differ")
    analyst_traces = _read_analyst_dimensions(p6[0])

    trade_metrics = tuple(metrics.trades)
    trade_segments = (
        *_group_records(
            trade_metrics,
            SegmentDimension.SYMBOL,
            lambda _: metrics.symbol,
            _trade_segment,
        ),
        *_group_records(
            trade_metrics,
            SegmentDimension.STRATEGY_IDENTITY,
            lambda _: UNATTRIBUTED_STRATEGY_IDENTITY,
            _trade_segment,
        ),
        *_group_records(
            trade_metrics,
            SegmentDimension.EVIDENCE_LABEL,
            lambda _: StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value,
            _trade_segment,
        ),
    )
    analyst_segments = (
        *_group_records(
            analyst_traces,
            SegmentDimension.ANALYST_DISPOSITION,
            lambda item: item.disposition,
            _analyst_segment,
        ),
        *_group_records(
            analyst_traces,
            SegmentDimension.GROUNDING_CODE,
            lambda item: item.grounding_code,
            _analyst_segment,
        ),
        *_group_records(
            analyst_traces,
            SegmentDimension.TRACE_ACCEPTANCE,
            lambda item: "ACCEPTED" if item.accepted else "REJECTED",
            _analyst_segment,
        ),
    )

    return SegmentationReport(
        metrics.metrics_sha256,
        reconstruction.reconstruction_sha256,
        reconstruction.timeline_sha256,
        metrics.symbol,
        trade_metrics,
        analyst_traces,
        trade_segments,
        analyst_segments,
    )
