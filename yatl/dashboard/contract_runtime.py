"""Deterministic offline runtime gate for P8-001 Dashboard contracts."""

from .contracts import (
    DashboardContractError,
    DashboardDiagnostic,
    DashboardMetricValue,
    DashboardOverviewCard,
    DashboardPolicy,
    DashboardSegmentRow,
    DashboardSourceIdentity,
    DashboardTradeRow,
    DiagnosticSeverity,
    MetricState,
    MetricUnit,
    OverviewDisplayKind,
    build_dashboard_view,
    dashboard_view_from_record,
)


OBSERVED_AT_MS = 1_790_000_000_000


def _view():
    source = DashboardSourceIdentity(
        "P7_EXPORT_BTC",
        "BTCUSDT",
        1,
        OBSERVED_AT_MS,
        "7" * 64,
    )
    overview = (
        DashboardOverviewCard(
            "CARD_QUALITY",
            "quality_status",
            "Quality",
            "PASS",
            OverviewDisplayKind.STATUS,
            "1" * 64,
        ),
    )
    trades = (
        DashboardTradeRow(
            "TRADE_ONE",
            "BTCUSDT",
            OBSERVED_AT_MS - 120_000,
            OBSERVED_AT_MS - 60_000,
            "0.01000000",
            "60000.00",
            "60600.00",
            "5.20",
            "0.40",
            "0.40",
            "2" * 64,
        ),
    )
    metrics = (
        DashboardMetricValue(
            "METRIC_NET_PNL",
            "5.20",
            MetricUnit.USD,
            MetricState.VALUE,
            "3" * 64,
        ),
    )
    segments = (
        DashboardSegmentRow(
            "SEGMENT_BTC",
            "symbol",
            "BTCUSDT",
            1,
            "5.20",
            "4" * 64,
        ),
    )
    diagnostics = (
        DashboardDiagnostic(
            "DIAGNOSTIC_OK",
            "QUALITY_PASS",
            DiagnosticSeverity.INFO,
            "Accepted P7 quality state is PASS.",
            "5" * 64,
        ),
    )
    return build_dashboard_view(
        source,
        overview_cards=overview,
        trade_rows=trades,
        metric_values=metrics,
        segment_rows=segments,
        diagnostics=diagnostics,
    )


def main():
    policy = DashboardPolicy()
    first = _view()
    second = _view()
    replay = dashboard_view_from_record(first.as_record())

    smuggled = first.as_record()
    smuggled["trade_permission"] = True
    try:
        dashboard_view_from_record(smuggled)
    except DashboardContractError:
        schema_smuggling_rejected = True
    else:
        schema_smuggling_rejected = False

    if (
        first != second
        or first != replay
        or first.view_sha256 != second.view_sha256
        or first.source.strategy_evidence.value != "INSUFFICIENT_EVIDENCE"
        or schema_smuggling_rejected is not True
    ):
        raise RuntimeError("P8-001 Dashboard contract runtime gate failed")

    print(
        "OK: P8 Dashboard contracts; "
        "source=P7_ACCEPTED_SANITIZED_EXPORT "
        "overview=1 trades=1 metrics=1 segments=1 diagnostics=1 "
        "strategy=INSUFFICIENT_EVIDENCE replay_equal=true "
        "schema_smuggling_rejected=true "
        f"policy_sha256={policy.policy_sha256} "
        f"source_sha256={first.source.identity_sha256} "
        f"view_sha256={first.view_sha256}"
    )
    print(
        "PAPER ONLY | LOCAL_READ_ONLY_DASHBOARD | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | Accepted/sanitized P7 export only | "
        "No credentials | No network/provider | No remote assets | "
        "No direct P5/P6 access | No execution/account/risk import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
