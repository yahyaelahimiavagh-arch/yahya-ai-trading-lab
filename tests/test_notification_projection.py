import inspect
import unittest
from dataclasses import replace

from yatl.dashboard import (
    DashboardDiagnostic,
    DashboardOverviewCard,
    DashboardOverviewProjection,
    DashboardSourceIdentity,
    DiagnosticSeverity,
    OverviewDisplayKind,
    QualityDiagnosticProjection,
)
from yatl.notifications import (
    NotificationCategory,
    NotificationSeverity,
    NotificationSourcePhase,
)
from yatl.notifications.formatter import (
    FORMAT_MODE,
    MAX_FORMATTED_CHARS,
    NotificationFormatError,
    format_notification,
)
from yatl.notifications.projection import (
    NotificationProjectionError,
    project_data_quality_alert,
    project_p10_validation_status,
    project_system_status,
)


OBSERVED_AT_MS = 1_800_000_000_000


def _field_sha(char):
    return char * 64


def overview():
    source = DashboardSourceIdentity(
        "P7_EXPORT_BTC",
        "BTCUSDT",
        1,
        OBSERVED_AT_MS,
        "f" * 64,
    )
    values = (
        ("CARD_01_SYMBOL", "symbol", "Symbol", "BTCUSDT", OverviewDisplayKind.TEXT, "1"),
        ("CARD_02_EXPORT_SHA256", "export_sha256", "Export", "f" * 64, OverviewDisplayKind.HASH, "2"),
        ("CARD_03_SNAPSHOT_TIME_MS", "snapshot_time_ms", "Snapshot", str(OBSERVED_AT_MS), OverviewDisplayKind.TEXT, "3"),
        ("CARD_04_PAPER_STATE", "paper_state", "Mode", "PAPER ONLY", OverviewDisplayKind.STATUS, "4"),
        ("CARD_05_LIVE_MASTER_LOCK", "live_master_lock", "Live Lock", "OFF", OverviewDisplayKind.STATUS, "5"),
        ("CARD_06_STRATEGY_EVIDENCE", "strategy_evidence", "Evidence", "INSUFFICIENT_EVIDENCE", OverviewDisplayKind.STATUS, "6"),
        ("CARD_07_QUALITY_STATUS", "quality_status", "Quality", "PASS", OverviewDisplayKind.STATUS, "7"),
        ("CARD_08_COMPLETED_TRADE_COUNT", "completed_trade_count", "Completed", "3", OverviewDisplayKind.COUNT, "8"),
        ("CARD_09_OPEN_TRADE_COUNT", "open_trade_count", "Open", "UNKNOWN", OverviewDisplayKind.STATUS, "9"),
        ("CARD_10_SNAPSHOT_FRESHNESS", "snapshot_freshness", "Freshness", "UNKNOWN", OverviewDisplayKind.STATUS, "a"),
        ("CARD_11_INGESTION_MANIFEST_SHA256", "ingestion_manifest_sha256", "Manifest", "b" * 64, OverviewDisplayKind.HASH, "b"),
        ("CARD_12_TIMELINE_SHA256", "timeline_sha256", "Timeline", "c" * 64, OverviewDisplayKind.HASH, "c"),
        ("CARD_13_RECONSTRUCTION_SHA256", "reconstruction_sha256", "Reconstruction", "d" * 64, OverviewDisplayKind.HASH, "d"),
        ("CARD_14_METRICS_SHA256", "metrics_sha256", "Metrics", "e" * 64, OverviewDisplayKind.HASH, "e"),
        ("CARD_15_SEGMENTATION_SHA256", "segmentation_sha256", "Segmentation", "1" * 64, OverviewDisplayKind.HASH, "f"),
    )
    cards = tuple(
        DashboardOverviewCard(
            card_id,
            field_key,
            label,
            value,
            kind,
            _field_sha(sha_char),
        )
        for card_id, field_key, label, value, kind, sha_char in values
    )
    return DashboardOverviewProjection(source, cards)


def pass_quality():
    return QualityDiagnosticProjection(
        quality_status="PASS",
        status_severity=DiagnosticSeverity.INFO,
        status_message="Accepted P7 quality state is PASS.",
        publication_allowed=True,
        analytics_presentation_allowed=True,
        partial_analytics_visible=False,
        diagnostics=(),
        passed_checks=(
            "METRICS_ARITHMETIC",
            "REPORT_BINDINGS",
            "SEGMENT_PARTITIONS",
            "SEGMENT_TOTALS",
            "SOURCE_COVERAGE",
            "SOURCE_DIGESTS",
            "SOURCE_NO_WRITE",
            "SOURCE_POINT_IN_TIME",
            "TIMELINE_IDENTITIES",
            "TIMELINE_RELATIONSHIPS",
            "TIMELINE_SEQUENCE",
            "TRADE_RECONCILIATION",
        ),
        source_quality_sha256="4" * 64,
        source_export_sha256="5" * 64,
        snapshot_time_ms=OBSERVED_AT_MS,
        source_mode="ACCEPTED_P7_EXPORT",
    )


def failed_quality():
    diagnostic = DashboardDiagnostic(
        "DIAGNOSTIC_000_MISSING_SOURCE_SOURCE",
        "MISSING_SOURCE",
        DiagnosticSeverity.ERROR,
        "A required P7 source is unavailable. Component: SOURCE.",
        "2" * 64,
    )
    return QualityDiagnosticProjection(
        quality_status="FAIL",
        status_severity=DiagnosticSeverity.ERROR,
        status_message="P7 quality state is FAIL; analytics presentation is blocked.",
        publication_allowed=False,
        analytics_presentation_allowed=False,
        partial_analytics_visible=False,
        diagnostics=(diagnostic,),
        passed_checks=(),
        source_quality_sha256="3" * 64,
        source_export_sha256=None,
        snapshot_time_ms=OBSERVED_AT_MS,
        source_mode="SANITIZED_P7_QUALITY_REPORT",
    )


def p10_not_ready():
    return {
        "schema_version": 1,
        "command": "summary",
        "ok": False,
        "code": "NOT_READY",
        "reason": "FORWARD_WARMUP_NOT_COMPLETE",
        "ingestion_snapshot_sha256": "1" * 64,
        "generated_at_ms": OBSERVED_AT_MS,
        "database_snapshot_sha256": "2" * 64,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
    }


def p10_ready(disposition="INSUFFICIENT_DATA"):
    criteria = {
        "NET_PNL_AFTER_COSTS": "INSUFFICIENT_DATA",
        "MAX_DRAWDOWN": "PASS",
        "SAMPLE_SIZE": "INSUFFICIENT_DATA",
        "CONSISTENCY": "INSUFFICIENT_DATA",
        "REGIME_STABILITY": "INSUFFICIENT_DATA",
        "FAILURE_RECOVERY": "PASS",
        "RISK_CONTROLS": "PASS",
    }
    return {
        "schema_version": 1,
        "command": "summary",
        "ok": True,
        "code": "SUMMARY_READY",
        "ingestion_snapshot_sha256": "3" * 64,
        "database_snapshot_sha256": "4" * 64,
        "paper_run_sha256": "5" * 64,
        "economics_sha256": "6" * 64,
        "gate_sha256": "7" * 64,
        "sample_status": "INSUFFICIENT_DATA",
        "disposition": disposition,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
        "observed_days": "12.5",
        "observation_start_ms": OBSERVED_AT_MS - 1_000_000,
        "observation_end_ms": OBSERVED_AT_MS,
        "completed_trades": 4,
        "net_pnl_after_costs_quote": "12.34",
        "net_return_after_costs": "0.000617",
        "profit_factor_after_costs": "1.12",
        "maximum_validation_drawdown_fraction": "0.01",
        "criteria": criteria,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "completed_trades": 2,
                "net_pnl_after_costs_quote": "8.00",
                "net_return_after_costs": "0.0008",
                "open_positions": 0,
            },
            {
                "symbol": "ETHUSDT",
                "completed_trades": 2,
                "net_pnl_after_costs_quote": "4.34",
                "net_return_after_costs": "0.000434",
                "open_positions": 1,
            },
        ],
    }


class NotificationProjectionFormatterTests(unittest.TestCase):
    def test_system_status_preserves_p8_provenance_and_unknowns(self):
        item = project_system_status(overview())
        self.assertEqual(item.category, NotificationCategory.SYSTEM_STATUS)
        self.assertEqual(item.severity, NotificationSeverity.INFO)
        self.assertEqual(item.source.payload_sha256, overview().overview_sha256)
        self.assertEqual(item.event_time_ms, OBSERVED_AT_MS)
        self.assertEqual(item.symbol, "BTCUSDT")
        self.assertIn("open trade count UNKNOWN", item.body)
        self.assertIn("snapshot freshness UNKNOWN", item.body)
        self.assertEqual(item.evidence_label, "INSUFFICIENT_EVIDENCE")

    def test_system_status_is_deterministic(self):
        first = project_system_status(overview())
        second = project_system_status(overview())
        self.assertEqual(first, second)
        self.assertEqual(first.message_sha256, second.message_sha256)

    def test_system_status_rejects_invented_freshness(self):
        item = overview()
        cards = list(item.cards)
        cards[9] = replace(cards[9], value="FRESH")
        object.__setattr__(item, "cards", tuple(cards))
        with self.assertRaises(NotificationProjectionError):
            project_system_status(item)

    def test_system_status_rejects_invented_open_trade_count(self):
        item = overview()
        cards = list(item.cards)
        cards[8] = replace(cards[8], value="1")
        object.__setattr__(item, "cards", tuple(cards))
        with self.assertRaises(NotificationProjectionError):
            project_system_status(item)

    def test_system_status_rejects_weakened_evidence_or_live_lock(self):
        item = overview()
        cards = list(item.cards)
        cards[5] = replace(cards[5], value="PROFITABLE")
        object.__setattr__(item, "cards", tuple(cards))
        with self.assertRaises(NotificationProjectionError):
            project_system_status(item)

        item = overview()
        cards = list(item.cards)
        cards[4] = replace(cards[4], value="ON")
        object.__setattr__(item, "cards", tuple(cards))
        with self.assertRaises(NotificationProjectionError):
            project_system_status(item)

    def test_quality_alert_accepts_only_sanitized_fail_projection(self):
        item = project_data_quality_alert(failed_quality())
        self.assertEqual(item.category, NotificationCategory.DATA_QUALITY_ALERT)
        self.assertEqual(item.severity, NotificationSeverity.ERROR)
        self.assertIsNone(item.symbol)
        self.assertIn("analytics presentation blocked", item.body)
        self.assertIn("MISSING_SOURCE", item.body)
        self.assertEqual(
            item.source.payload_sha256,
            failed_quality().projection_sha256,
        )

    def test_quality_alert_rejects_absent_or_pass_like_state(self):
        with self.assertRaises(NotificationProjectionError):
            project_data_quality_alert(pass_quality())
        with self.assertRaises(NotificationProjectionError):
            project_data_quality_alert(object())

    def test_quality_alert_rejects_partial_analytics(self):
        fail = failed_quality()
        object.__setattr__(fail, "partial_analytics_visible", True)
        with self.assertRaises(NotificationProjectionError):
            project_data_quality_alert(fail)

    def test_quality_alert_is_deterministic(self):
        first = project_data_quality_alert(failed_quality())
        second = project_data_quality_alert(failed_quality())
        self.assertEqual(first, second)
        self.assertEqual(first.message_sha256, second.message_sha256)


    def test_p10_warmup_projection_is_information_only_and_provenance_bound(self):
        item = project_p10_validation_status(p10_not_ready(), "BTCUSDT")
        self.assertEqual(item.category, NotificationCategory.P10_VALIDATION_STATUS)
        self.assertEqual(item.severity, NotificationSeverity.INFO)
        self.assertEqual(
            item.source.source_phase,
            NotificationSourcePhase.P10_FORWARD_VALIDATION,
        )
        self.assertEqual(item.event_time_ms, OBSERVED_AT_MS)
        self.assertEqual(item.symbol, "BTCUSDT")
        self.assertIn("warm-up is not complete", item.body)
        self.assertIn("P11 remains locked", item.body)

    def test_p10_ready_projection_preserves_summary_and_fail_severity(self):
        normal = project_p10_validation_status(p10_ready(), "ETHUSDT")
        failed = project_p10_validation_status(p10_ready("FAIL"), "ETHUSDT")
        self.assertIn("completed Paper trades 2", normal.body)
        self.assertIn("net return after costs 0.000434", normal.body)
        self.assertEqual(normal.severity, NotificationSeverity.INFO)
        self.assertEqual(failed.severity, NotificationSeverity.ERROR)
        self.assertEqual(
            normal.message_sha256,
            project_p10_validation_status(p10_ready(), "ETHUSDT").message_sha256,
        )

    def test_p10_projection_rejects_unlock_schema_smuggling_and_cross_symbol(self):
        unlocked = p10_not_ready()
        unlocked["p11_unlocked"] = True
        with self.assertRaises(NotificationProjectionError):
            project_p10_validation_status(unlocked, "BTCUSDT")

        smuggled = p10_not_ready()
        smuggled["extra"] = "field"
        with self.assertRaises(NotificationProjectionError):
            project_p10_validation_status(smuggled, "BTCUSDT")

        with self.assertRaises(NotificationProjectionError):
            project_p10_validation_status(p10_not_ready(), "BNBUSDT")

    def test_formatter_is_deterministic_bounded_and_plain_text(self):
        message = project_system_status(overview())
        first = format_notification(message)
        second = format_notification(message)
        self.assertEqual(first, second)
        self.assertEqual(first.format_mode, FORMAT_MODE)
        self.assertLessEqual(first.char_count, MAX_FORMATTED_CHARS)
        self.assertEqual(first.notification_sha256, message.message_sha256)
        self.assertIn("Actionability: INFORMATION_ONLY", first.text)
        self.assertIn("Evidence: INSUFFICIENT_EVIDENCE", first.text)

    def test_formatter_preserves_source_hash_and_event_time(self):
        message = project_data_quality_alert(failed_quality())
        rendered = format_notification(message)
        self.assertIn(message.source.payload_sha256, rendered.text)
        self.assertIn(str(message.event_time_ms), rendered.text)

    def test_formatter_escapes_backslash_quote_and_controls(self):
        message = project_system_status(overview())
        modified = replace(message, title='Status "quoted" \\ path')
        rendered = format_notification(modified)
        self.assertIn('Status \\"quoted\\" \\\\ path', rendered.text)

    def test_formatter_rejects_non_notification(self):
        with self.assertRaises(NotificationFormatError):
            format_notification(object())

    def test_projection_source_has_no_execution_account_risk_or_transport_import(self):
        import yatl.notifications.projection as projection

        source_text = inspect.getsource(projection)
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
            "os.getenv",
            "os.environ",
            "api.telegram",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)

    def test_formatter_source_has_no_network_credential_or_execution_capability(self):
        import yatl.notifications.formatter as formatter

        source_text = inspect.getsource(formatter)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "os.getenv",
            "os.environ",
            "api.telegram",
            "from yatl.execution",
            "from yatl.account",
            "from yatl.risk",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
