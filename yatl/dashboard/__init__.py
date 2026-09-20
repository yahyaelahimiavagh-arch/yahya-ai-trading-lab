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
