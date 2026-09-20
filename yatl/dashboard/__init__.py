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
