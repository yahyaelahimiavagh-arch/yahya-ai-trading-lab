import inspect
import unittest
from dataclasses import FrozenInstanceError, replace

from yatl.dashboard import (
    DASHBOARD_POLICY_ID,
    DashboardContractError,
    DashboardDiagnostic,
    DashboardMetricValue,
    DashboardOverviewCard,
    DashboardPolicy,
    DashboardSafetyBanner,
    DashboardSegmentRow,
    DashboardSourceIdentity,
    DashboardTradeRow,
    DiagnosticSeverity,
    MetricState,
    MetricUnit,
    OverviewDisplayKind,
    StrategyEvidenceState,
    build_dashboard_view,
    dashboard_view_from_record,
)


OBSERVED_AT_MS = 1_790_000_000_000


def source(symbol="BTCUSDT"):
    return DashboardSourceIdentity(
        "P7_EXPORT_BTC" if symbol == "BTCUSDT" else "P7_EXPORT_ETH",
        symbol,
        1,
        OBSERVED_AT_MS,
        "7" * 64,
    )


def overview():
    return (
        DashboardOverviewCard(
            "CARD_QUALITY",
            "quality_status",
            "Quality",
            "PASS",
            OverviewDisplayKind.STATUS,
            "1" * 64,
        ),
    )


def trades(symbol="BTCUSDT"):
    return (
        DashboardTradeRow(
            "TRADE_ONE",
            symbol,
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


def metrics():
    return (
        DashboardMetricValue(
            "METRIC_NET_PNL",
            "5.20",
            MetricUnit.USD,
            MetricState.VALUE,
            "3" * 64,
        ),
    )


def segments():
    return (
        DashboardSegmentRow(
            "SEGMENT_BTC",
            "symbol",
            "BTCUSDT",
            1,
            "5.20",
            "4" * 64,
        ),
    )


def diagnostics():
    return (
        DashboardDiagnostic(
            "DIAGNOSTIC_OK",
            "QUALITY_PASS",
            DiagnosticSeverity.INFO,
            "Accepted P7 quality state is PASS.",
            "5" * 64,
        ),
    )


def view(symbol="BTCUSDT"):
    return build_dashboard_view(
        source(symbol),
        overview_cards=overview(),
        trade_rows=trades(symbol),
        metric_values=metrics(),
        segment_rows=segments(),
        diagnostics=diagnostics(),
    )


class DashboardContractTests(unittest.TestCase):
    def test_policy_is_frozen_local_read_only_and_display_only(self):
        policy = DashboardPolicy()
        self.assertEqual(policy.policy_id, DASHBOARD_POLICY_ID)
        self.assertEqual(policy.mode, "LOCAL_READ_ONLY_DASHBOARD")
        self.assertEqual(policy.source_scope, "ACCEPTED_SANITIZED_P7_EXPORT_ONLY")
        self.assertTrue(policy.display_only)
        self.assertTrue(policy.paper_only)
        self.assertEqual(policy.live_master_lock, "OFF")
        self.assertTrue(policy.spot_only)

    def test_policy_capability_flags_are_all_false(self):
        policy = DashboardPolicy()
        names = (
            "allow_short",
            "allow_margin",
            "allow_futures",
            "allow_leverage",
            "allow_withdrawal",
            "allow_remote_assets",
            "allow_external_scripts",
            "allow_network_transport",
            "allow_provider_transport",
            "allow_credentials",
            "allow_source_write",
            "allow_direct_p5_p6_access",
            "allow_execution_import",
            "allow_account_import",
            "allow_risk_import",
            "allow_risk_authorization_mutation",
            "allow_quantity_authority",
            "allow_trade_permission",
            "allow_order_endpoint",
            "allow_ai_direct_execution",
            "allow_strategy_evidence_upgrade",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(getattr(policy, name))

    def test_policy_cannot_be_weakened(self):
        changes = (
            {"allow_network_transport": True},
            {"allow_credentials": True},
            {"allow_direct_p5_p6_access": True},
            {"allow_execution_import": True},
            {"allow_account_import": True},
            {"allow_risk_import": True},
            {"allow_quantity_authority": True},
            {"allow_trade_permission": True},
            {"allow_order_endpoint": True},
            {"allow_strategy_evidence_upgrade": True},
            {"live_master_lock": "ON"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DashboardContractError):
                DashboardPolicy(**change)

    def test_policy_digest_is_deterministic_and_instance_is_frozen(self):
        first = DashboardPolicy()
        second = DashboardPolicy()
        self.assertEqual(first.policy_sha256, second.policy_sha256)
        self.assertEqual(len(first.policy_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            first.mode = "WRITE"

    def test_source_identity_is_accepted_sanitized_read_only_p7_export(self):
        item = source()
        self.assertEqual(item.source_kind, "P7_ACCEPTED_SANITIZED_EXPORT")
        self.assertEqual(item.quality_status, "PASS")
        self.assertTrue(item.accepted)
        self.assertTrue(item.sanitized)
        self.assertTrue(item.read_only)
        self.assertEqual(
            item.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(len(item.identity_sha256), 64)

    def test_source_identity_rejects_nonaccepted_or_tampered_material(self):
        item = source()
        changes = (
            {"export_sha256": "bad"},
            {"symbol": "SOLUSDT"},
            {"quality_status": "FAIL"},
            {"accepted": False},
            {"sanitized": False},
            {"read_only": False},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DashboardContractError):
                replace(item, **change)

    def test_safety_banner_is_fixed_and_cannot_be_weakened(self):
        banner = DashboardSafetyBanner()
        self.assertEqual(banner.paper_label, "PAPER ONLY")
        self.assertEqual(banner.live_lock_label, "LIVE_MASTER_LOCK=OFF")
        self.assertEqual(banner.evidence_label, "INSUFFICIENT_EVIDENCE")
        with self.assertRaises(DashboardContractError):
            replace(banner, evidence_label="PROFITABLE")

    def test_strategy_evidence_enum_has_no_upgrade_member(self):
        self.assertEqual(
            tuple(item.value for item in StrategyEvidenceState),
            ("INSUFFICIENT_EVIDENCE",),
        )

    def test_overview_card_is_display_only_and_rejects_authority_key(self):
        card = overview()[0]
        self.assertTrue(card.display_only)
        with self.assertRaises(DashboardContractError):
            replace(card, field_key="trade_permission")
        with self.assertRaises(DashboardContractError):
            replace(card, field_key="risk_authorization")

    def test_trade_row_is_completed_paper_long_and_immutable(self):
        row = trades()[0]
        self.assertEqual(row.side, "LONG")
        self.assertEqual(row.status, "COMPLETED")
        self.assertTrue(row.paper)
        self.assertTrue(row.display_only)
        with self.assertRaises(DashboardContractError):
            replace(row, side="SHORT")
        with self.assertRaises(DashboardContractError):
            replace(row, status="OPEN")

    def test_trade_row_rejects_invalid_decimal_and_time_material(self):
        row = trades()[0]
        changes = (
            {"quantity": "0"},
            {"entry_price": "nan"},
            {"fee_total": "-0.01"},
            {"exit_time_ms": row.entry_time_ms},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DashboardContractError):
                replace(row, **change)

    def test_metric_value_requires_exact_value_state_pairing(self):
        available = metrics()[0]
        self.assertEqual(available.state, MetricState.VALUE)
        unavailable = DashboardMetricValue(
            "METRIC_DRAWDOWN",
            None,
            MetricUnit.PERCENT,
            MetricState.UNAVAILABLE,
            "8" * 64,
        )
        self.assertIsNone(unavailable.value)
        with self.assertRaises(DashboardContractError):
            replace(available, state=MetricState.UNAVAILABLE)

    def test_segment_preserves_insufficient_evidence_and_rejects_authority_dimension(self):
        row = segments()[0]
        self.assertEqual(
            row.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        with self.assertRaises(DashboardContractError):
            replace(row, dimension="approved_quantity")

    def test_diagnostic_is_bounded_display_only(self):
        item = diagnostics()[0]
        self.assertTrue(item.display_only)
        with self.assertRaises(DashboardContractError):
            replace(item, message="x" * 257)

    def test_view_is_deterministic_reconstructable_and_has_stable_digest(self):
        first = view()
        second = view()
        replay = dashboard_view_from_record(first.as_record())
        self.assertEqual(first, second)
        self.assertEqual(first, replay)
        self.assertEqual(first.view_sha256, second.view_sha256)
        self.assertEqual(len(first.view_sha256), 64)

    def test_view_rejects_duplicate_or_unordered_display_identities(self):
        first = DashboardOverviewCard(
            "CARD_ALPHA",
            "quality_status",
            "Quality",
            "PASS",
            OverviewDisplayKind.STATUS,
            "a" * 64,
        )
        second = DashboardOverviewCard(
            "CARD_BETA",
            "paper_mode",
            "Mode",
            "PAPER ONLY",
            OverviewDisplayKind.STATUS,
            "b" * 64,
        )
        with self.assertRaises(DashboardContractError):
            build_dashboard_view(source(), overview_cards=(second, first))
        with self.assertRaises(DashboardContractError):
            build_dashboard_view(source(), overview_cards=(first, first))

    def test_view_rejects_cross_symbol_trade_rows(self):
        with self.assertRaises(DashboardContractError):
            build_dashboard_view(source("BTCUSDT"), trade_rows=trades("ETHUSDT"))

    def test_top_level_schema_smuggling_is_rejected(self):
        record = view().as_record()
        record["trade_permission"] = True
        with self.assertRaises(DashboardContractError):
            dashboard_view_from_record(record)

    def test_nested_schema_smuggling_is_rejected(self):
        record = view().as_record()
        record["source"]["credential"] = "secret"
        with self.assertRaises(DashboardContractError):
            dashboard_view_from_record(record)

    def test_canonical_record_contains_no_authority_bearing_fields(self):
        record = view().as_record()
        serialized = str(record)
        for forbidden in (
            "'trade_permission': True",
            "'order_endpoint': True",
            "'quantity_authority': True",
            "'risk_authorization_mutation': True",
            "'allow_credentials': True",
            "'allow_network_transport': True",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_dashboard_contract_source_has_no_execution_account_risk_network_or_provider_import(self):
        import yatl.dashboard.contracts as contracts

        source_text = inspect.getsource(contracts)
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
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
