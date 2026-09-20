"""Deterministic offline runtime gate for P7-001 analytics contracts."""

from .contracts import (
    AnalyticsEventKind,
    AnalyticsJournalEvent,
    AnalyticsPolicy,
    AnalyticsScope,
    AnalyticsSourceIdentity,
    AnalyticsSourceKind,
    DerivedAnalyticsField,
    build_analytics_report,
)


START_TIME = 1_790_000_000_000
END_TIME = START_TIME + 60_000


def _sources():
    return (
        AnalyticsSourceIdentity(
            "SOURCE_P5",
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
            "BTCUSDT",
            1,
            END_TIME - 1_000,
            "5" * 64,
        ),
        AnalyticsSourceIdentity(
            "SOURCE_P6",
            AnalyticsSourceKind.P6_ANALYST_TRACE,
            "BTCUSDT",
            1,
            END_TIME - 500,
            "6" * 64,
        ),
    )


def main():
    sources = _sources()
    scope = AnalyticsScope(
        "SCOPE_BTC",
        "BTCUSDT",
        START_TIME,
        END_TIME,
        sources,
    )
    events = (
        AnalyticsJournalEvent(
            "EVENT_P5",
            sources[0],
            AnalyticsEventKind.P5_JOURNAL_EVENT,
            START_TIME + 10_000,
            1,
            "7" * 64,
        ),
        AnalyticsJournalEvent(
            "EVENT_P6",
            sources[1],
            AnalyticsEventKind.P6_ANALYST_EVENT,
            START_TIME + 20_000,
            2,
            "8" * 64,
        ),
    )
    derived = (
        DerivedAnalyticsField(
            "FIELD_EVENT_COUNT",
            "event_count",
            ("SOURCE_P5", "SOURCE_P6"),
            "9" * 64,
        ),
    )
    policy = AnalyticsPolicy()
    report = build_analytics_report(scope, events, derived, policy)
    empty = build_analytics_report(scope, (), (), policy)
    replay = build_analytics_report(scope, events, derived, policy)

    if (
        report.disposition.value != "DESCRIPTIVE_ONLY"
        or empty.disposition.value != "INSUFFICIENT_DATA"
        or report != replay
        or report.scope.strategy_evidence.value != "INSUFFICIENT_EVIDENCE"
    ):
        raise RuntimeError("P7-001 analytics contract runtime gate failed")

    print(
        "OK: P7 analytics contracts; "
        "sources=2 events=2 derived=1 "
        "disposition=DESCRIPTIVE_ONLY empty=INSUFFICIENT_DATA "
        "strategy=INSUFFICIENT_EVIDENCE replay_equal=true "
        f"policy_sha256={policy.policy_sha256} "
        f"scope_sha256={scope.scope_sha256} "
        f"report_sha256={report.report_sha256}"
    )
    print(
        "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | Upstream/derived origin explicit | "
        "No credentials | No network/provider | No upstream mutation | "
        "No executor import | No RiskAuthorization mutation | "
        "No quantity authority | No trade permission | No order endpoint | "
        "No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
