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
