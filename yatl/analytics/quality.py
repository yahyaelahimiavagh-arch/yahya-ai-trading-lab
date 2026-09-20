"""Fail-closed deterministic quality gate for accepted P7 analytics."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from pathlib import Path

from .contracts import AnalyticsSourceKind, StrategyEvidenceState
from .ingestion import (
    AnalyticsIngestionError,
    ReadOnlyIngestionManifest,
    UpstreamSourceSpec,
    _safe_stat,
    _sha256_file,
    ingest_readonly_sources,
)
from .metrics import (
    DECIMAL_PRECISION,
    PerformanceMetricsError,
    PerformanceMetricsReport,
    calculate_performance_metrics,
)
from .segmentation import (
    ANALYST_DIMENSIONS,
    TRADE_DIMENSIONS,
    SegmentDimension,
    SegmentationError,
    SegmentationReport,
    build_segmentation,
)
from .timeline import (
    RelationshipKind,
    TimelineError,
    TimelineKind,
    UnifiedTimeline,
    build_unified_timeline,
)
from .trades import (
    PaperTradeReconstruction,
    TradeReconstructionError,
    reconstruct_paper_trades,
)


QUALITY_SCHEMA_VERSION = 1
MAX_DIAGNOSTICS = 8
MAX_PASSED_CHECKS = 16


class QualityStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class QualityCode(str, Enum):
    MISSING_SOURCE = "MISSING_SOURCE"
    SOURCE_IDENTITY_INVALID = "SOURCE_IDENTITY_INVALID"
    UPSTREAM_DIGEST_CHANGED = "UPSTREAM_DIGEST_CHANGED"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    ORPHAN_RELATIONSHIP = "ORPHAN_RELATIONSHIP"
    TIMELINE_GAP = "TIMELINE_GAP"
    INCONSISTENT_TOTALS = "INCONSISTENT_TOTALS"
    REPORT_ARITHMETIC = "REPORT_ARITHMETIC"
    ANALYTICS_CHAIN_INVALID = "ANALYTICS_CHAIN_INVALID"
    UPSTREAM_MUTATION = "UPSTREAM_MUTATION"


class QualityComponent(str, Enum):
    SOURCE = "SOURCE"
    TIMELINE = "TIMELINE"
    TRADES = "TRADES"
    METRICS = "METRICS"
    SEGMENTATION = "SEGMENTATION"
    GATE = "GATE"


class QualityCheck(str, Enum):
    SOURCE_COVERAGE = "SOURCE_COVERAGE"
    SOURCE_DIGESTS = "SOURCE_DIGESTS"
    SOURCE_POINT_IN_TIME = "SOURCE_POINT_IN_TIME"
    SOURCE_NO_WRITE = "SOURCE_NO_WRITE"
    TIMELINE_SEQUENCE = "TIMELINE_SEQUENCE"
    TIMELINE_RELATIONSHIPS = "TIMELINE_RELATIONSHIPS"
    TIMELINE_IDENTITIES = "TIMELINE_IDENTITIES"
    TRADE_RECONCILIATION = "TRADE_RECONCILIATION"
    METRICS_ARITHMETIC = "METRICS_ARITHMETIC"
    SEGMENT_PARTITIONS = "SEGMENT_PARTITIONS"
    SEGMENT_TOTALS = "SEGMENT_TOTALS"
    REPORT_BINDINGS = "REPORT_BINDINGS"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _decimal(value):
    if not isinstance(value, str) or not value:
        raise ValueError("decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("decimal") from None
    if not number.is_finite():
        raise ValueError("decimal")
    return number


@dataclass(frozen=True, slots=True)
class QualityDiagnostic:
    code: QualityCode
    component: QualityComponent

    def __post_init__(self):
        if not isinstance(self.code, QualityCode) or not isinstance(
            self.component, QualityComponent
        ):
            raise ValueError("Quality diagnostic is invalid")

    def as_record(self):
        return {
            "code": self.code.value,
            "component": self.component.value,
        }


@dataclass(frozen=True, slots=True)
class QualityChainIdentity:
    symbol: str
    ingestion_manifest_sha256: str
    timeline_sha256: str
    reconstruction_sha256: str
    metrics_sha256: str
    segmentation_sha256: str
    completed_trade_count: int
    analyst_trace_count: int

    def __post_init__(self):
        if (
            self.symbol not in ("BTCUSDT", "ETHUSDT")
            or any(
                not _valid_sha(value)
                for value in (
                    self.ingestion_manifest_sha256,
                    self.timeline_sha256,
                    self.reconstruction_sha256,
                    self.metrics_sha256,
                    self.segmentation_sha256,
                )
            )
            or type(self.completed_trade_count) is not int
            or self.completed_trade_count < 0
            or type(self.analyst_trace_count) is not int
            or self.analyst_trace_count < 0
        ):
            raise ValueError("Quality chain identity is invalid")

    def as_record(self):
        return {
            "symbol": self.symbol,
            "ingestion_manifest_sha256": self.ingestion_manifest_sha256,
            "timeline_sha256": self.timeline_sha256,
            "reconstruction_sha256": self.reconstruction_sha256,
            "metrics_sha256": self.metrics_sha256,
            "segmentation_sha256": self.segmentation_sha256,
            "completed_trade_count": self.completed_trade_count,
            "analyst_trace_count": self.analyst_trace_count,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsQualityReport:
    snapshot_time_ms: int
    status: QualityStatus
    diagnostics: tuple[QualityDiagnostic, ...]
    passed_checks: tuple[QualityCheck, ...]
    accepted_chain: QualityChainIdentity | None
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = QUALITY_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != QUALITY_SCHEMA_VERSION
            or type(self.snapshot_time_ms) is not int
            or self.snapshot_time_ms < 0
            or not isinstance(self.status, QualityStatus)
            or type(self.diagnostics) is not tuple
            or len(self.diagnostics) > MAX_DIAGNOSTICS
            or any(not isinstance(item, QualityDiagnostic) for item in self.diagnostics)
            or tuple(
                sorted(
                    set(self.diagnostics),
                    key=lambda item: (item.code.value, item.component.value),
                )
            )
            != self.diagnostics
            or type(self.passed_checks) is not tuple
            or len(self.passed_checks) > MAX_PASSED_CHECKS
            or any(not isinstance(item, QualityCheck) for item in self.passed_checks)
            or tuple(sorted(set(self.passed_checks), key=lambda item: item.value))
            != self.passed_checks
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError("Analytics quality report identity is invalid")
        if self.status is QualityStatus.PASS:
            if self.diagnostics or not isinstance(
                self.accepted_chain, QualityChainIdentity
            ):
                raise ValueError("PASS quality report is incomplete")
        else:
            if not self.diagnostics or self.accepted_chain is not None:
                raise ValueError(
                    "FAIL quality report cannot publish partial analytics identity"
                )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "snapshot_time_ms": self.snapshot_time_ms,
            "status": self.status.value,
            "publication_allowed": self.status is QualityStatus.PASS,
            "diagnostics": [item.as_record() for item in self.diagnostics],
            "passed_checks": [item.value for item in self.passed_checks],
            "accepted_chain": (
                None
                if self.accepted_chain is None
                else self.accepted_chain.as_record()
            ),
            "strategy_evidence": self.strategy_evidence.value,
            "safety": {
                "descriptive_only": True,
                "read_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "partial_publication_on_failure": False,
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
    def quality_sha256(self):
        return _digest(self.as_record())

    @property
    def canonical_json(self):
        return _json(self.as_record()) + "\n"


@dataclass(frozen=True, slots=True)
class AnalyticsQualityGate:
    report: AnalyticsQualityReport
    accepted_segmentation: SegmentationReport | None

    def __post_init__(self):
        if not isinstance(self.report, AnalyticsQualityReport):
            raise ValueError("Quality gate report is invalid")
        if self.report.status is QualityStatus.PASS:
            if not isinstance(self.accepted_segmentation, SegmentationReport):
                raise ValueError("PASS quality gate is missing accepted analytics")
            if (
                self.report.accepted_chain.segmentation_sha256
                != self.accepted_segmentation.segmentation_sha256
            ):
                raise ValueError("Quality gate accepted payload identity changed")
        elif self.accepted_segmentation is not None:
            raise ValueError("FAIL quality gate exposed partial analytics payload")


def _diagnostics(*items):
    unique = tuple(
        sorted(
            set(items),
            key=lambda item: (item.code.value, item.component.value),
        )
    )
    return unique[:MAX_DIAGNOSTICS]


def _fail(snapshot_time_ms, *items, passed_checks=()):
    return AnalyticsQualityGate(
        AnalyticsQualityReport(
            snapshot_time_ms,
            QualityStatus.FAIL,
            _diagnostics(*items),
            tuple(sorted(set(passed_checks), key=lambda item: item.value)),
            None,
        ),
        None,
    )


def _preflight(snapshot_time_ms, specs):
    diagnostics = []
    checks = []
    raw_before = {}

    if type(snapshot_time_ms) is not int or snapshot_time_ms < 0:
        return (
            _diagnostics(
                QualityDiagnostic(
                    QualityCode.SOURCE_IDENTITY_INVALID,
                    QualityComponent.GATE,
                )
            ),
            (),
            raw_before,
        )
    if type(specs) is not tuple or len(specs) != 2:
        return (
            _diagnostics(
                QualityDiagnostic(
                    QualityCode.MISSING_SOURCE,
                    QualityComponent.SOURCE,
                )
            ),
            (),
            raw_before,
        )
    if any(not isinstance(item, UpstreamSourceSpec) for item in specs):
        return (
            _diagnostics(
                QualityDiagnostic(
                    QualityCode.SOURCE_IDENTITY_INVALID,
                    QualityComponent.SOURCE,
                )
            ),
            (),
            raw_before,
        )

    kinds = tuple(item.source_kind for item in specs)
    source_ids = tuple(item.source_id for item in specs)
    symbols = {item.symbol for item in specs}
    if set(kinds) != {
        AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
        AnalyticsSourceKind.P6_ANALYST_TRACE,
    }:
        diagnostics.append(
            QualityDiagnostic(QualityCode.MISSING_SOURCE, QualityComponent.SOURCE)
        )
    if len(set(source_ids)) != len(source_ids):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.DUPLICATE_IDENTITY,
                QualityComponent.SOURCE,
            )
        )
    if len(symbols) != 1:
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.SOURCE_IDENTITY_INVALID,
                QualityComponent.SOURCE,
            )
        )
    if any(item.observed_at_ms > snapshot_time_ms for item in specs):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.FUTURE_TIMESTAMP,
                QualityComponent.SOURCE,
            )
        )

    resolved = []
    for item in specs:
        try:
            path = item.database_path
            if not isinstance(path, Path):
                raise TypeError
            resolved.append(path.resolve())
            before_stat = _safe_stat(path)
            before_sha = _sha256_file(path)
        except (AnalyticsIngestionError, OSError, TypeError, ValueError):
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.MISSING_SOURCE,
                    QualityComponent.SOURCE,
                )
            )
            continue
        if before_sha != item.expected_database_sha256:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.UPSTREAM_DIGEST_CHANGED,
                    QualityComponent.SOURCE,
                )
            )
        raw_before[item.source_id] = (before_stat, before_sha)

    if len(resolved) == 2 and len(set(resolved)) != 2:
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.DUPLICATE_IDENTITY,
                QualityComponent.SOURCE,
            )
        )
    if not diagnostics:
        checks.extend(
            (
                QualityCheck.SOURCE_COVERAGE,
                QualityCheck.SOURCE_DIGESTS,
                QualityCheck.SOURCE_POINT_IN_TIME,
            )
        )
    return _diagnostics(*diagnostics), tuple(checks), raw_before


def _classify_timeline_error(error):
    text = str(error).casefold()
    if "future" in text:
        return QualityDiagnostic(
            QualityCode.FUTURE_TIMESTAMP,
            QualityComponent.TIMELINE,
        )
    if "duplicate" in text:
        return QualityDiagnostic(
            QualityCode.DUPLICATE_IDENTITY,
            QualityComponent.TIMELINE,
        )
    if (
        "out of order" in text
        or "skipped" in text
        or "sequence" in text
        or "predecessor" in text
        or "chain" in text
    ):
        return QualityDiagnostic(
            QualityCode.TIMELINE_GAP,
            QualityComponent.TIMELINE,
        )
    if (
        "orphan" in text
        or "no accepted intent" in text
        or "relationship" in text
        or "order state" in text
    ):
        return QualityDiagnostic(
            QualityCode.ORPHAN_RELATIONSHIP,
            QualityComponent.TIMELINE,
        )
    return QualityDiagnostic(
        QualityCode.ANALYTICS_CHAIN_INVALID,
        QualityComponent.TIMELINE,
    )


def _quality_checks(
    manifest,
    timeline,
    reconstruction,
    metrics,
    segmentation,
):
    diagnostics = []
    passed = []
    if not isinstance(manifest, ReadOnlyIngestionManifest):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.SOURCE,
            )
        )
        return _diagnostics(*diagnostics), ()

    source_by_kind = {
        item.identity.source_kind: item
        for item in manifest.sources
    }
    if (
        len(source_by_kind) != 2
        or set(source_by_kind) != {
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
            AnalyticsSourceKind.P6_ANALYST_TRACE,
        }
    ):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.MISSING_SOURCE,
                QualityComponent.SOURCE,
            )
        )
    else:
        passed.append(QualityCheck.SOURCE_COVERAGE)

    if not isinstance(timeline, UnifiedTimeline):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.TIMELINE,
            )
        )
    else:
        sequence = tuple(item.sequence for item in timeline.entries)
        if sequence != tuple(range(len(timeline.entries))):
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.TIMELINE_GAP,
                    QualityComponent.TIMELINE,
                )
            )
        else:
            passed.append(QualityCheck.TIMELINE_SEQUENCE)

        identities = tuple(
            (item.kind.value, item.primary_sha256)
            for item in timeline.entries
        )
        if len(set(identities)) != len(identities):
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.DUPLICATE_IDENTITY,
                    QualityComponent.TIMELINE,
                )
            )
        else:
            passed.append(QualityCheck.TIMELINE_IDENTITIES)

        if source_by_kind:
            p5_source = source_by_kind[
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE
            ].identity.source_id
            p6_source = source_by_kind[
                AnalyticsSourceKind.P6_ANALYST_TRACE
            ].identity.source_id
            if any(
                (
                    item.source_id != p6_source
                    if item.kind is TimelineKind.P6_ANALYST_TRACE
                    else item.source_id != p5_source
                )
                or item.time_ms > timeline.snapshot_time_ms
                for item in timeline.entries
            ):
                diagnostics.append(
                    QualityDiagnostic(
                        QualityCode.FUTURE_TIMESTAMP,
                        QualityComponent.TIMELINE,
                    )
                )

        intents = {
            item.primary_sha256
            for item in timeline.entries
            if item.kind is TimelineKind.P5_INTENT_BINDING
        }
        orders = {
            item.primary_sha256
            for item in timeline.entries
            if item.kind is TimelineKind.P5_ORDER_EVENT
        }
        fills = {
            item.primary_sha256
            for item in timeline.entries
            if item.kind is TimelineKind.P5_FILL_EVENT
        }
        relationship_error = False
        earlier_orders = set()
        for item in timeline.entries:
            relations = {
                relation.kind: relation.sha256
                for relation in item.relationships
            }
            if item.kind is TimelineKind.P5_ORDER_EVENT:
                if relations.get(RelationshipKind.INTENT) not in intents:
                    relationship_error = True
                previous = relations.get(RelationshipKind.PREVIOUS_EVENT)
                if previous is not None and previous not in earlier_orders:
                    relationship_error = True
                earlier_orders.add(item.primary_sha256)
            elif item.kind is TimelineKind.P5_FILL_EVENT:
                if relations.get(RelationshipKind.INTENT) not in intents:
                    relationship_error = True
            elif item.kind is TimelineKind.P5_PORTFOLIO_PROJECTION:
                if relations.get(RelationshipKind.LAST_FILL) not in fills:
                    relationship_error = True
        if relationship_error:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.ORPHAN_RELATIONSHIP,
                    QualityComponent.TIMELINE,
                )
            )
        else:
            passed.append(QualityCheck.TIMELINE_RELATIONSHIPS)

    if not isinstance(reconstruction, PaperTradeReconstruction):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.TRADES,
            )
        )
    elif isinstance(timeline, UnifiedTimeline):
        timeline_fills = {
            item.primary_sha256
            for item in timeline.entries
            if item.kind is TimelineKind.P5_FILL_EVENT
        }
        timeline_portfolios = {
            item.primary_sha256
            for item in timeline.entries
            if item.kind is TimelineKind.P5_PORTFOLIO_PROJECTION
        }
        trade_bad = reconstruction.timeline_sha256 != timeline.timeline_sha256
        for trade in reconstruction.completed:
            if (
                trade.entry.fill_event_sha256 not in timeline_fills
                or trade.exit.fill_event_sha256 not in timeline_fills
            ):
                trade_bad = True
        if (
            reconstruction.open_trade is not None
            and reconstruction.open_trade.entry.fill_event_sha256
            not in timeline_fills
        ):
            trade_bad = True
        if (
            reconstruction.final_portfolio is not None
            and reconstruction.final_portfolio.projection_sha256
            not in timeline_portfolios
        ):
            trade_bad = True
        if trade_bad:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.ORPHAN_RELATIONSHIP,
                    QualityComponent.TRADES,
                )
            )
        else:
            passed.append(QualityCheck.TRADE_RECONCILIATION)

    if not isinstance(metrics, PerformanceMetricsReport):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.METRICS,
            )
        )
    elif isinstance(reconstruction, PaperTradeReconstruction):
        try:
            replay_metrics = calculate_performance_metrics(reconstruction)
        except PerformanceMetricsError:
            replay_metrics = None
        if replay_metrics != metrics:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.REPORT_ARITHMETIC,
                    QualityComponent.METRICS,
                )
            )
        else:
            passed.append(QualityCheck.METRICS_ARITHMETIC)

    if not isinstance(segmentation, SegmentationReport):
        diagnostics.append(
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.SEGMENTATION,
            )
        )
    elif isinstance(metrics, PerformanceMetricsReport):
        binding_bad = (
            segmentation.metrics_sha256 != metrics.metrics_sha256
            or segmentation.reconstruction_sha256
            != metrics.reconstruction_sha256
            or segmentation.timeline_sha256 != metrics.timeline_sha256
            or segmentation.source_metrics != metrics
            or tuple(segmentation.trade_metrics) != tuple(metrics.trades)
        )
        p6_source = source_by_kind.get(
            AnalyticsSourceKind.P6_ANALYST_TRACE
        )
        if (
            p6_source is None
            or segmentation.analyst_source_sha256
            != p6_source.canonical_sha256
        ):
            binding_bad = True
        if binding_bad:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.ORPHAN_RELATIONSHIP,
                    QualityComponent.SEGMENTATION,
                )
            )
        else:
            passed.append(QualityCheck.REPORT_BINDINGS)

        totals_bad = False
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            for dimension in TRADE_DIMENSIONS:
                segments = tuple(
                    item
                    for item in segmentation.trade_segments
                    if item.dimension is dimension
                )
                if (
                    sum(item.member_count for item in segments)
                    != metrics.completed_trade_count
                    or sum(item.winning_trades for item in segments)
                    != metrics.winning_trades
                    or sum(item.losing_trades for item in segments)
                    != metrics.losing_trades
                    or sum(item.breakeven_trades for item in segments)
                    != metrics.breakeven_trades
                ):
                    totals_bad = True
                    continue
                try:
                    realized = sum(
                        (_decimal(item.realized_pnl_quote) for item in segments),
                        Decimal(0),
                    )
                    costs = sum(
                        (_decimal(item.total_cost_quote) for item in segments),
                        Decimal(0),
                    )
                    if (
                        realized != _decimal(metrics.realized_pnl_quote)
                        or costs != _decimal(metrics.total_cost_quote)
                    ):
                        totals_bad = True
                except ValueError:
                    totals_bad = True

            for dimension in ANALYST_DIMENSIONS:
                segments = tuple(
                    item
                    for item in segmentation.analyst_segments
                    if item.dimension is dimension
                )
                if sum(item.member_count for item in segments) != len(
                    segmentation.analyst_traces
                ):
                    totals_bad = True

        if totals_bad:
            diagnostics.append(
                QualityDiagnostic(
                    QualityCode.INCONSISTENT_TOTALS,
                    QualityComponent.SEGMENTATION,
                )
            )
        else:
            passed.extend(
                (
                    QualityCheck.SEGMENT_PARTITIONS,
                    QualityCheck.SEGMENT_TOTALS,
                )
            )

    return (
        _diagnostics(*diagnostics),
        tuple(sorted(set(passed), key=lambda item: item.value)),
    )


def run_quality_gate(snapshot_time_ms, specs):
    """Return PASS analytics only when the entire accepted chain reconciles."""

    preflight, passed, raw_before = _preflight(snapshot_time_ms, specs)
    if preflight:
        return _fail(snapshot_time_ms, *preflight, passed_checks=passed)

    try:
        manifest = ingest_readonly_sources(snapshot_time_ms, specs)
    except AnalyticsIngestionError:
        return _fail(
            snapshot_time_ms,
            QualityDiagnostic(
                QualityCode.ANALYTICS_CHAIN_INVALID,
                QualityComponent.SOURCE,
            ),
            passed_checks=passed,
        )

    try:
        timeline = build_unified_timeline(snapshot_time_ms, specs)
    except TimelineError as error:
        return _fail(
            snapshot_time_ms,
            _classify_timeline_error(error),
            passed_checks=passed,
        )

    try:
        reconstruction = reconstruct_paper_trades(snapshot_time_ms, specs)
    except TradeReconstructionError:
        return _fail(
            snapshot_time_ms,
            QualityDiagnostic(
                QualityCode.INCONSISTENT_TOTALS,
                QualityComponent.TRADES,
            ),
            passed_checks=passed,
        )

    try:
        metrics = calculate_performance_metrics(reconstruction)
    except PerformanceMetricsError:
        return _fail(
            snapshot_time_ms,
            QualityDiagnostic(
                QualityCode.REPORT_ARITHMETIC,
                QualityComponent.METRICS,
            ),
            passed_checks=passed,
        )

    try:
        segmentation = build_segmentation(snapshot_time_ms, specs)
    except SegmentationError:
        return _fail(
            snapshot_time_ms,
            QualityDiagnostic(
                QualityCode.INCONSISTENT_TOTALS,
                QualityComponent.SEGMENTATION,
            ),
            passed_checks=passed,
        )

    diagnostics, artifact_checks = _quality_checks(
        manifest,
        timeline,
        reconstruction,
        metrics,
        segmentation,
    )
    passed = tuple(sorted(set((*passed, *artifact_checks)), key=lambda item: item.value))
    if diagnostics:
        return _fail(
            snapshot_time_ms,
            *diagnostics,
            passed_checks=passed,
        )

    for spec in specs:
        try:
            after_stat = _safe_stat(spec.database_path)
            after_sha = _sha256_file(spec.database_path)
        except AnalyticsIngestionError:
            return _fail(
                snapshot_time_ms,
                QualityDiagnostic(
                    QualityCode.UPSTREAM_MUTATION,
                    QualityComponent.SOURCE,
                ),
                passed_checks=passed,
            )
        before = raw_before.get(spec.source_id)
        if before is None or before != (after_stat, after_sha):
            return _fail(
                snapshot_time_ms,
                QualityDiagnostic(
                    QualityCode.UPSTREAM_MUTATION,
                    QualityComponent.SOURCE,
                ),
                passed_checks=passed,
            )
    passed = tuple(
        sorted(
            set((*passed, QualityCheck.SOURCE_NO_WRITE)),
            key=lambda item: item.value,
        )
    )

    chain = QualityChainIdentity(
        segmentation.symbol,
        manifest.manifest_sha256,
        timeline.timeline_sha256,
        reconstruction.reconstruction_sha256,
        metrics.metrics_sha256,
        segmentation.segmentation_sha256,
        metrics.completed_trade_count,
        len(segmentation.analyst_traces),
    )
    report = AnalyticsQualityReport(
        snapshot_time_ms,
        QualityStatus.PASS,
        (),
        passed,
        chain,
    )
    return AnalyticsQualityGate(report, segmentation)
