"""Local read-only P8 Dashboard contracts. No execution capability is exposed."""

from .contracts import (
    DASHBOARD_POLICY_ID,
    DASHBOARD_SCHEMA_VERSION,
    DashboardContractError,
    DashboardDiagnostic,
    DashboardMetricValue,
    DashboardOverviewCard,
    DashboardPolicy,
    DashboardSafetyBanner,
    DashboardSegmentRow,
    DashboardSourceIdentity,
    DashboardTradeRow,
    DashboardView,
    DiagnosticSeverity,
    MetricState,
    MetricUnit,
    OverviewDisplayKind,
    StrategyEvidenceState,
    build_dashboard_view,
    dashboard_view_from_record,
)

__all__ = [
    "DASHBOARD_POLICY_ID",
    "DASHBOARD_SCHEMA_VERSION",
    "DashboardContractError",
    "DashboardDiagnostic",
    "DashboardMetricValue",
    "DashboardOverviewCard",
    "DashboardPolicy",
    "DashboardSafetyBanner",
    "DashboardSegmentRow",
    "DashboardSourceIdentity",
    "DashboardTradeRow",
    "DashboardView",
    "DiagnosticSeverity",
    "MetricState",
    "MetricUnit",
    "OverviewDisplayKind",
    "StrategyEvidenceState",
    "build_dashboard_view",
    "dashboard_view_from_record",
]

from .loader import (
    MAX_P7_EXPORT_BYTES,
    P7_EXPORT_SCHEMA_VERSION,
    LoadedP7Export,
    P7ExportLoadCode,
    P7ExportLoadError,
    load_p7_export,
)

__all__ += [
    "MAX_P7_EXPORT_BYTES",
    "P7_EXPORT_SCHEMA_VERSION",
    "LoadedP7Export",
    "P7ExportLoadCode",
    "P7ExportLoadError",
    "load_p7_export",
]

from .overview import (
    EXPECTED_CARD_IDS,
    EXPECTED_FIELD_KEYS,
    OVERVIEW_SCHEMA_VERSION,
    UNKNOWN_FIELDS,
    UNKNOWN_VALUE,
    DashboardOverviewProjection,
    OverviewProjectionError,
    project_overview,
)

__all__ += [
    "EXPECTED_CARD_IDS",
    "EXPECTED_FIELD_KEYS",
    "OVERVIEW_SCHEMA_VERSION",
    "UNKNOWN_FIELDS",
    "UNKNOWN_VALUE",
    "DashboardOverviewProjection",
    "OverviewProjectionError",
    "project_overview",
]

from .trade_table import (
    MAX_PAGE_SIZE,
    TRADE_TABLE_SCHEMA_VERSION,
    CompletedTradeTableProjection,
    DashboardCompletedTradeMetricRow,
    TradeOutcomeFilter,
    TradeSortDirection,
    TradeSortKey,
    TradeTableProjectionError,
    TradeTableQuery,
    apply_trade_table_query,
    project_completed_trade_table,
)

__all__ += [
    "MAX_PAGE_SIZE",
    "TRADE_TABLE_SCHEMA_VERSION",
    "CompletedTradeTableProjection",
    "DashboardCompletedTradeMetricRow",
    "TradeOutcomeFilter",
    "TradeSortDirection",
    "TradeSortKey",
    "TradeTableProjectionError",
    "TradeTableQuery",
    "apply_trade_table_query",
    "project_completed_trade_table",
]

from .performance_views import (
    PERFORMANCE_VIEW_SCHEMA_VERSION,
    DashboardAnalystSegmentSummary,
    DashboardExactMetricValue,
    DashboardTradeSegmentSummary,
    PerformanceSegmentationProjection,
    PerformanceViewProjectionError,
    project_performance_segmentation,
)

__all__ += [
    "PERFORMANCE_VIEW_SCHEMA_VERSION",
    "DashboardAnalystSegmentSummary",
    "DashboardExactMetricValue",
    "DashboardTradeSegmentSummary",
    "PerformanceSegmentationProjection",
    "PerformanceViewProjectionError",
    "project_performance_segmentation",
]

from .quality_view import (
    QUALITY_CHECKS,
    QUALITY_CODES,
    QUALITY_COMPONENTS,
    QUALITY_VIEW_SCHEMA_VERSION,
    QualityDiagnosticProjection,
    QualityDiagnosticProjectionError,
    project_quality_diagnostics,
)

__all__ += [
    "QUALITY_CHECKS",
    "QUALITY_CODES",
    "QUALITY_COMPONENTS",
    "QUALITY_VIEW_SCHEMA_VERSION",
    "QualityDiagnosticProjection",
    "QualityDiagnosticProjectionError",
    "project_quality_diagnostics",
]

from .renderer import (
    MAX_DASHBOARD_BYTES,
    RENDERER_SCHEMA_VERSION,
    DashboardRenderError,
    RenderedDashboardArtifact,
    render_dashboard,
)

__all__ += [
    "MAX_DASHBOARD_BYTES",
    "RENDERER_SCHEMA_VERSION",
    "DashboardRenderError",
    "RenderedDashboardArtifact",
    "render_dashboard",
]

from .cli import (
    DASHBOARD_CLI_SCHEMA_VERSION,
    DashboardCliCode,
    DashboardCliError,
    dashboard_build,
    dashboard_summary,
    dashboard_validate,
)

__all__ += [
    "DASHBOARD_CLI_SCHEMA_VERSION",
    "DashboardCliCode",
    "DashboardCliError",
    "dashboard_build",
    "dashboard_summary",
    "dashboard_validate",
]

from .scenarios import (
    ARTIFACT_KIND as DASHBOARD_SCENARIO_ARTIFACT_KIND,
    MATRIX_KIND as DASHBOARD_SCENARIO_MATRIX_KIND,
    SCENARIOS as DASHBOARD_SCENARIOS,
    DashboardAcceptedFixture,
    DashboardScenarioError,
    DashboardScenarioMatrixResult,
    DashboardScenarioResult,
    dashboard_matrix_sha256,
    run_adversarial_dashboard_matrix,
    scenario_artifact_json as dashboard_scenario_artifact_json,
    write_adversarial_dashboard_matrix,
)

__all__ += [
    "DASHBOARD_SCENARIO_ARTIFACT_KIND",
    "DASHBOARD_SCENARIO_MATRIX_KIND",
    "DASHBOARD_SCENARIOS",
    "DashboardAcceptedFixture",
    "DashboardScenarioError",
    "DashboardScenarioMatrixResult",
    "DashboardScenarioResult",
    "dashboard_matrix_sha256",
    "run_adversarial_dashboard_matrix",
    "dashboard_scenario_artifact_json",
    "write_adversarial_dashboard_matrix",
]

from .audit import (
    EXPECTED_EXPORT_SET_SHA256 as P8_EXPECTED_EXPORT_SET_SHA256,
    EXPECTED_INDEX_SHA256 as P8_EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256 as P8_EXPECTED_POLICY_SHA256,
    P8AuditError,
    P8AuditResult,
    audit_p8,
)

__all__ += [
    "P8_EXPECTED_EXPORT_SET_SHA256",
    "P8_EXPECTED_INDEX_SHA256",
    "P8_EXPECTED_POLICY_SHA256",
    "P8AuditError",
    "P8AuditResult",
    "audit_p8",
]
