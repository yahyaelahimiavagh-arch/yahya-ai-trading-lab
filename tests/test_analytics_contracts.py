import inspect
import unittest
from dataclasses import FrozenInstanceError, replace

from yatl.analytics import (
    ANALYTICS_POLICY_ID,
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


START_TIME = 1_790_000_000_000
END_TIME = START_TIME + 60_000


def sources(symbol="BTCUSDT"):
    return (
        AnalyticsSourceIdentity(
            "SOURCE_P5",
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
            symbol,
            1,
            END_TIME - 1_000,
            "5" * 64,
        ),
        AnalyticsSourceIdentity(
            "SOURCE_P6",
            AnalyticsSourceKind.P6_ANALYST_TRACE,
            symbol,
            1,
            END_TIME - 500,
            "6" * 64,
        ),
    )


def scope(symbol="BTCUSDT"):
    return AnalyticsScope(
        "SCOPE_ONE",
        symbol,
        START_TIME,
        END_TIME,
        sources(symbol),
    )


def events():
    items = sources()
    return (
        AnalyticsJournalEvent(
            "EVENT_P5",
            items[0],
            AnalyticsEventKind.P5_JOURNAL_EVENT,
            START_TIME + 10_000,
            1,
            "7" * 64,
        ),
        AnalyticsJournalEvent(
            "EVENT_P6",
            items[1],
            AnalyticsEventKind.P6_ANALYST_EVENT,
            START_TIME + 20_000,
            2,
            "8" * 64,
        ),
    )


def derived():
    return (
        DerivedAnalyticsField(
            "FIELD_COUNT",
            "event_count",
            ("SOURCE_P5", "SOURCE_P6"),
            "9" * 64,
        ),
    )


class AnalyticsContractTests(unittest.TestCase):
    def test_frozen_policy_is_read_only_descriptive(self):
        policy = AnalyticsPolicy()
        self.assertEqual(policy.policy_id, ANALYTICS_POLICY_ID)
        self.assertEqual(policy.mode, "READ_ONLY_ANALYTICS")
        self.assertTrue(policy.descriptive_only)
        self.assertTrue(policy.paper_only)
        self.assertEqual(policy.live_master_lock, "OFF")
        for name in (
            "allow_short",
            "allow_margin",
            "allow_futures",
            "allow_leverage",
            "allow_withdrawal",
            "allow_external_transport",
            "allow_credentials",
            "allow_upstream_mutation",
            "allow_execution_import",
            "allow_risk_authorization_mutation",
            "allow_quantity_authority",
            "allow_trade_permission",
            "allow_order_endpoint",
            "allow_ai_direct_execution",
            "allow_strategy_evidence_upgrade",
        ):
            with self.subTest(name=name):
                self.assertFalse(getattr(policy, name))

    def test_policy_cannot_be_weakened(self):
        for change in (
            {"allow_upstream_mutation": True},
            {"allow_trade_permission": True},
            {"allow_order_endpoint": True},
            {"allow_execution_import": True},
            {"allow_strategy_evidence_upgrade": True},
            {"live_master_lock": "ON"},
        ):
            with self.subTest(change=change), self.assertRaises(AnalyticsContractError):
                AnalyticsPolicy(**change)

    def test_policy_is_frozen_and_digest_is_deterministic(self):
        first = AnalyticsPolicy()
        second = AnalyticsPolicy()
        self.assertEqual(first, second)
        self.assertEqual(first.policy_sha256, second.policy_sha256)
        self.assertEqual(len(first.policy_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            first.mode = "WRITE"

    def test_source_identity_is_read_only_and_preserves_strategy_label(self):
        item = sources()[0]
        self.assertTrue(item.read_only)
        self.assertEqual(
            item.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(len(item.identity_sha256), 64)

    def test_source_identity_rejects_invalid_material(self):
        item = sources()[0]
        cases = (
            {"source_sha256": "bad"},
            {"symbol": "SOLUSDT"},
            {"schema_version": 0},
            {"read_only": False},
            {"observed_at_ms": -1},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(AnalyticsContractError):
                replace(item, **change)

    def test_strategy_label_has_no_upgrade_member(self):
        self.assertEqual(
            tuple(item.value for item in StrategyEvidenceState),
            ("INSUFFICIENT_EVIDENCE",),
        )

    def test_event_kind_must_match_source_kind(self):
        item = sources()[0]
        with self.assertRaises(AnalyticsContractError):
            AnalyticsJournalEvent(
                "EVENT_BAD",
                item,
                AnalyticsEventKind.P6_ANALYST_EVENT,
                START_TIME + 1,
                0,
                "a" * 64,
            )

    def test_event_is_upstream_only_and_cannot_be_future_of_source(self):
        item = sources()[0]
        valid = AnalyticsJournalEvent(
            "EVENT_OK",
            item,
            AnalyticsEventKind.P5_JOURNAL_EVENT,
            START_TIME + 1,
            0,
            "a" * 64,
        )
        self.assertEqual(valid.origin, AnalyticsOrigin.UPSTREAM)
        with self.assertRaises(AnalyticsContractError):
            replace(valid, origin=AnalyticsOrigin.DERIVED)
        with self.assertRaises(AnalyticsContractError):
            replace(valid, event_time_ms=item.observed_at_ms + 1)

    def test_scope_rejects_duplicate_unordered_future_and_cross_symbol_sources(self):
        items = sources()
        bad_cases = (
            (items[0], items[0]),
            tuple(reversed(items)),
            (
                items[0],
                replace(items[1], observed_at_ms=END_TIME + 1),
            ),
            (
                items[0],
                replace(items[1], symbol="ETHUSDT"),
            ),
        )
        for bad in bad_cases:
            with self.subTest(bad=bad), self.assertRaises(AnalyticsContractError):
                AnalyticsScope(
                    "SCOPE_BAD",
                    "BTCUSDT",
                    START_TIME,
                    END_TIME,
                    bad,
                )

    def test_scope_digest_is_canonical_and_reconstructable(self):
        first = scope()
        second = AnalyticsScope(
            first.scope_id,
            first.symbol,
            first.start_time_ms,
            first.end_time_ms,
            first.sources,
            first.strategy_evidence,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.scope_sha256, second.scope_sha256)

    def test_derived_field_is_explicit_and_source_bound(self):
        item = derived()[0]
        self.assertEqual(item.origin, AnalyticsOrigin.DERIVED)
        self.assertEqual(item.source_ids, ("SOURCE_P5", "SOURCE_P6"))
        with self.assertRaises(AnalyticsContractError):
            replace(item, origin=AnalyticsOrigin.UPSTREAM)
        with self.assertRaises(AnalyticsContractError):
            replace(item, source_ids=("SOURCE_P6", "SOURCE_P5"))

    def test_report_with_events_is_descriptive_only(self):
        report = build_analytics_report(scope(), events(), derived())
        self.assertEqual(report.disposition, AnalyticsDisposition.DESCRIPTIVE_ONLY)
        self.assertEqual(report.reason, AnalyticsReason.ANALYTICS_ONLY)
        self.assertEqual(
            report.scope.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )

    def test_empty_report_is_insufficient_data(self):
        report = build_analytics_report(scope())
        self.assertEqual(report.disposition, AnalyticsDisposition.INSUFFICIENT_DATA)
        self.assertEqual(report.reason, AnalyticsReason.NO_USABLE_EVENTS)
        self.assertEqual(report.events, ())

    def test_event_order_duplicate_unknown_source_and_scope_time_fail_closed(self):
        accepted = scope()
        good = events()
        cases = (
            tuple(reversed(good)),
            (good[0], good[0]),
            (
                good[0],
                replace(
                    good[1],
                    source=replace(good[1].source, source_id="SOURCE_OTHER"),
                ),
            ),
            (
                replace(good[0], event_time_ms=accepted.end_time_ms),
                good[1],
            ),
        )
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(AnalyticsContractError):
                build_analytics_report(accepted, bad)

    def test_unknown_derived_source_fails_closed(self):
        bad = (
            DerivedAnalyticsField(
                "FIELD_BAD",
                "event_count",
                ("SOURCE_UNKNOWN",),
                "b" * 64,
            ),
        )
        with self.assertRaises(AnalyticsContractError):
            build_analytics_report(scope(), events(), bad)

    def test_report_cannot_override_conservative_disposition(self):
        with self.assertRaises(AnalyticsContractError):
            AnalyticsReport(
                scope(),
                events(),
                derived(),
                AnalyticsDisposition.INSUFFICIENT_DATA,
                AnalyticsReason.NO_USABLE_EVENTS,
            )

    def test_report_digest_is_deterministic_and_has_no_authority(self):
        first = build_analytics_report(scope(), events(), derived())
        second = build_analytics_report(scope(), events(), derived())
        self.assertEqual(first, second)
        self.assertEqual(first.report_sha256, second.report_sha256)
        record = first.as_record()
        self.assertEqual(record["safety"]["trade_permission"], False)
        self.assertEqual(record["safety"]["order_endpoints"], False)
        self.assertEqual(record["safety"]["quantity_authority"], False)
        self.assertEqual(record["safety"]["risk_authorization_mutation"], False)
        self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")

    def test_analytics_contract_has_no_execution_account_network_or_provider_import(self):
        import yatl.analytics.contracts as contracts

        source = inspect.getsource(contracts)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "subprocess",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
