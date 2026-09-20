"""Read-only P7 Journal / Analytics contracts. No execution capability is exposed."""

from .contracts import (
    ANALYTICS_POLICY_ID,
    ANALYTICS_SCHEMA_VERSION,
    AnalyticsContractError,
    AnalyticsDisposition,
    AnalyticsEventKind,
    AnalyticsJournalEvent,
    AnalyticsOrigin,
    AnalyticsPolicy,
    AnalyticsReason,
    AnalyticsReport,
    AnalyticsScope,
    AnalyticsSourceIdentity,
    AnalyticsSourceKind,
    DerivedAnalyticsField,
    StrategyEvidenceState,
    build_analytics_report,
)

__all__ = [
    "ANALYTICS_POLICY_ID",
    "ANALYTICS_SCHEMA_VERSION",
    "AnalyticsContractError",
    "AnalyticsDisposition",
    "AnalyticsEventKind",
    "AnalyticsJournalEvent",
    "AnalyticsOrigin",
    "AnalyticsPolicy",
    "AnalyticsReason",
    "AnalyticsReport",
    "AnalyticsScope",
    "AnalyticsSourceIdentity",
    "AnalyticsSourceKind",
    "DerivedAnalyticsField",
    "StrategyEvidenceState",
    "build_analytics_report",
]

from .ingestion import (
    INGESTION_SCHEMA_VERSION,
    AnalyticsIngestionError,
    IngestedSource,
    ReadOnlyIngestionManifest,
    UpstreamSourceSpec,
    ingest_readonly_sources,
    ingest_source,
)

__all__ += [
    "INGESTION_SCHEMA_VERSION",
    "AnalyticsIngestionError",
    "IngestedSource",
    "ReadOnlyIngestionManifest",
    "UpstreamSourceSpec",
    "ingest_readonly_sources",
    "ingest_source",
]

from .timeline import (
    TIMELINE_SCHEMA_VERSION,
    RelationshipKind,
    TimelineEntry,
    TimelineError,
    TimelineKind,
    TimelineRelationship,
    TimelineTimeBasis,
    UnifiedTimeline,
    build_unified_timeline,
)

__all__ += [
    "TIMELINE_SCHEMA_VERSION",
    "RelationshipKind",
    "TimelineEntry",
    "TimelineError",
    "TimelineKind",
    "TimelineRelationship",
    "TimelineTimeBasis",
    "UnifiedTimeline",
    "build_unified_timeline",
]

from .trades import (
    TRADE_SCHEMA_VERSION,
    AcceptedTradeFill,
    CompletedPaperTrade,
    FinalPortfolioEvidence,
    OpenPaperTrade,
    PaperTradeReconstruction,
    TradeBookStatus,
    TradeReconstructionError,
    reconstruct_paper_trades,
)

__all__ += [
    "TRADE_SCHEMA_VERSION",
    "AcceptedTradeFill",
    "CompletedPaperTrade",
    "FinalPortfolioEvidence",
    "OpenPaperTrade",
    "PaperTradeReconstruction",
    "TradeBookStatus",
    "TradeReconstructionError",
    "reconstruct_paper_trades",
]

from .metrics import (
    METRICS_SCHEMA_VERSION,
    MAX_COMPLETED_TRADES,
    PerformanceMetricsError,
    PerformanceMetricsReport,
    PerformanceMetricsStatus,
    TradePerformanceMetric,
    calculate_performance_metrics,
)

__all__ += [
    "METRICS_SCHEMA_VERSION",
    "MAX_COMPLETED_TRADES",
    "PerformanceMetricsError",
    "PerformanceMetricsReport",
    "PerformanceMetricsStatus",
    "TradePerformanceMetric",
    "calculate_performance_metrics",
]

from .segmentation import (
    SEGMENTATION_SCHEMA_VERSION,
    STRATEGY_ATTRIBUTION_STATUS,
    UNATTRIBUTED_STRATEGY_IDENTITY,
    AnalystSegment,
    AnalystTraceDimensionRecord,
    SegmentDimension,
    SegmentPopulation,
    SegmentationError,
    SegmentationReport,
    TradeSegment,
    build_segmentation,
)

__all__ += [
    "SEGMENTATION_SCHEMA_VERSION",
    "STRATEGY_ATTRIBUTION_STATUS",
    "UNATTRIBUTED_STRATEGY_IDENTITY",
    "AnalystSegment",
    "AnalystTraceDimensionRecord",
    "SegmentDimension",
    "SegmentPopulation",
    "SegmentationError",
    "SegmentationReport",
    "TradeSegment",
    "build_segmentation",
]

from .quality import (
    QUALITY_SCHEMA_VERSION,
    AnalyticsQualityGate,
    AnalyticsQualityReport,
    QualityChainIdentity,
    QualityCheck,
    QualityCode,
    QualityComponent,
    QualityDiagnostic,
    QualityStatus,
    run_quality_gate,
)

__all__ += [
    "QUALITY_SCHEMA_VERSION",
    "AnalyticsQualityGate",
    "AnalyticsQualityReport",
    "QualityChainIdentity",
    "QualityCheck",
    "QualityCode",
    "QualityComponent",
    "QualityDiagnostic",
    "QualityStatus",
    "run_quality_gate",
]

from .cli import (
    ANALYTICS_CLI_SCHEMA_VERSION,
    ANALYTICS_EXPORT_SCHEMA_VERSION,
    MAX_CLI_OUTPUT_BYTES,
    AnalyticsCliCode,
    AnalyticsCliError,
    analytics_export,
    analytics_summary,
    analytics_trades,
    analytics_validate,
    load_analytics_spec,
)

__all__ += [
    "ANALYTICS_CLI_SCHEMA_VERSION",
    "ANALYTICS_EXPORT_SCHEMA_VERSION",
    "MAX_CLI_OUTPUT_BYTES",
    "AnalyticsCliCode",
    "AnalyticsCliError",
    "analytics_export",
    "analytics_summary",
    "analytics_trades",
    "analytics_validate",
    "load_analytics_spec",
]

from .scenarios import (
    ACCEPTED_UPSTREAM_IDENTITIES,
    SCENARIOS as ANALYTICS_ADVERSARIAL_SCENARIOS,
    AnalyticsScenarioError,
    AnalyticsScenarioMatrixResult,
    AnalyticsScenarioResult,
    analytics_matrix_sha256,
    run_adversarial_analytics_matrix,
    run_and_write_adversarial_analytics_matrix,
    scenario_artifact_json,
    write_adversarial_analytics_matrix,
)

__all__ += [
    "ACCEPTED_UPSTREAM_IDENTITIES",
    "ANALYTICS_ADVERSARIAL_SCENARIOS",
    "AnalyticsScenarioError",
    "AnalyticsScenarioMatrixResult",
    "AnalyticsScenarioResult",
    "analytics_matrix_sha256",
    "run_adversarial_analytics_matrix",
    "run_and_write_adversarial_analytics_matrix",
    "scenario_artifact_json",
    "write_adversarial_analytics_matrix",
]

from .audit import (
    EXPECTED_BTC_CHAIN,
    EXPECTED_CHAIN_SET_SHA256,
    EXPECTED_INDEX_SHA256 as P7_EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256 as P7_EXPECTED_POLICY_SHA256,
    P7AuditError,
    P7AuditResult,
    audit_p7,
)

__all__ += [
    "EXPECTED_BTC_CHAIN",
    "EXPECTED_CHAIN_SET_SHA256",
    "P7_EXPECTED_INDEX_SHA256",
    "P7_EXPECTED_POLICY_SHA256",
    "P7AuditError",
    "P7AuditResult",
    "audit_p7",
]
