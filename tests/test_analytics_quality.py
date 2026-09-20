import hashlib
import inspect
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.analytics import (
    AnalyticsSourceKind,
    QualityCheck,
    QualityCode,
    QualityStatus,
    UpstreamSourceSpec,
    run_quality_gate,
)
from yatl.analytics.timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from yatl.analytics.trade_runtime import _close_fixture


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AnalyticsQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p5 = self.root / "p5.sqlite3"
        self.p6 = self.root / "p6.sqlite3"
        _create_p5(self.p5)
        _close_fixture(self.p5)
        _create_p6(self.p6)
        self.specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                START + 90,
                self.p5,
                file_sha(self.p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                P6_OBSERVED,
                self.p6,
                file_sha(self.p6),
            ),
        )

    def tearDown(self):
        self.temp.cleanup()

    def codes(self, result):
        return tuple(item.code for item in result.report.diagnostics)

    def test_healthy_fixture_passes_entire_quality_chain(self):
        before = tuple(file_sha(item.database_path) for item in self.specs)
        first = run_quality_gate(SNAPSHOT, self.specs)
        second = run_quality_gate(SNAPSHOT, self.specs)
        after = tuple(file_sha(item.database_path) for item in self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.report.status, QualityStatus.PASS)
        self.assertIsNotNone(first.accepted_segmentation)
        self.assertIsNotNone(first.report.accepted_chain)
        self.assertEqual(first.report.diagnostics, ())
        self.assertEqual(first.report.canonical_json, second.report.canonical_json)
        self.assertEqual(first.report.quality_sha256, second.report.quality_sha256)
        self.assertEqual(before, after)

    def test_pass_report_covers_arithmetic_relationship_and_partition_checks(self):
        result = run_quality_gate(SNAPSHOT, self.specs)
        expected = {
            QualityCheck.SOURCE_COVERAGE,
            QualityCheck.SOURCE_DIGESTS,
            QualityCheck.SOURCE_POINT_IN_TIME,
            QualityCheck.SOURCE_NO_WRITE,
            QualityCheck.TIMELINE_SEQUENCE,
            QualityCheck.TIMELINE_RELATIONSHIPS,
            QualityCheck.TIMELINE_IDENTITIES,
            QualityCheck.TRADE_RECONCILIATION,
            QualityCheck.METRICS_ARITHMETIC,
            QualityCheck.SEGMENT_PARTITIONS,
            QualityCheck.SEGMENT_TOTALS,
            QualityCheck.REPORT_BINDINGS,
        }
        self.assertEqual(set(result.report.passed_checks), expected)

    def test_missing_source_fails_without_partial_publication(self):
        self.p6.unlink()
        result = run_quality_gate(SNAPSHOT, self.specs)
        self.assertEqual(result.report.status, QualityStatus.FAIL)
        self.assertIn(QualityCode.MISSING_SOURCE, self.codes(result))
        self.assertIsNone(result.report.accepted_chain)
        self.assertIsNone(result.accepted_segmentation)
        self.assertFalse(result.report.as_record()["publication_allowed"])

    def test_changed_upstream_digest_fails_closed(self):
        with self.p5.open("ab") as stream:
            stream.write(b"changed")
        result = run_quality_gate(SNAPSHOT, self.specs)
        self.assertEqual(
            self.codes(result),
            (QualityCode.UPSTREAM_DIGEST_CHANGED,),
        )
        self.assertIsNone(result.accepted_segmentation)

    def test_future_source_timestamp_fails_closed(self):
        result = run_quality_gate(
            SNAPSHOT,
            (self.specs[0], replace(self.specs[1], observed_at_ms=SNAPSHOT + 1)),
        )
        self.assertEqual(self.codes(result), (QualityCode.FUTURE_TIMESTAMP,))
        self.assertIsNone(result.accepted_segmentation)

    def test_duplicate_source_identity_fails_closed(self):
        result = run_quality_gate(
            SNAPSHOT,
            (
                self.specs[0],
                replace(self.specs[1], source_id=self.specs[0].source_id),
            ),
        )
        self.assertEqual(self.codes(result), (QualityCode.DUPLICATE_IDENTITY,))
        self.assertIsNone(result.accepted_segmentation)

    def test_orphan_order_intent_fails_closed(self):
        connection = sqlite3.connect(str(self.p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET intent_sha256=? "
                "WHERE sequence=0 LIMIT 1",
                ("0" * 64,),
            )
        connection.close()
        specs = (
            replace(self.specs[0], expected_database_sha256=file_sha(self.p5)),
            self.specs[1],
        )
        result = run_quality_gate(SNAPSHOT, specs)
        self.assertEqual(self.codes(result), (QualityCode.ORPHAN_RELATIONSHIP,))
        self.assertIsNone(result.accepted_segmentation)

    def test_timeline_gap_fails_closed(self):
        connection = sqlite3.connect(str(self.p5))
        authorization = connection.execute(
            "SELECT authorization_sha256 FROM local_paper_order_events "
            "ORDER BY event_time_ms LIMIT 1"
        ).fetchone()[0]
        with connection:
            connection.execute(
                "DELETE FROM local_paper_order_events "
                "WHERE authorization_sha256=? AND sequence=0",
                (authorization,),
            )
        connection.close()
        specs = (
            replace(self.specs[0], expected_database_sha256=file_sha(self.p5)),
            self.specs[1],
        )
        result = run_quality_gate(SNAPSHOT, specs)
        self.assertEqual(self.codes(result), (QualityCode.TIMELINE_GAP,))
        self.assertIsNone(result.accepted_segmentation)

    def test_cross_symbol_sources_fail_without_analytics_payload(self):
        result = run_quality_gate(
            SNAPSHOT,
            (self.specs[0], replace(self.specs[1], symbol="ETHUSDT")),
        )
        self.assertEqual(result.report.status, QualityStatus.FAIL)
        self.assertIn(QualityCode.SOURCE_IDENTITY_INVALID, self.codes(result))
        self.assertIsNone(result.report.accepted_chain)
        self.assertIsNone(result.accepted_segmentation)

    def test_diagnostics_are_sanitized_bounded_and_path_free(self):
        self.p6.unlink()
        result = run_quality_gate(SNAPSHOT, self.specs)
        record = result.report.as_record()
        self.assertLessEqual(len(record["diagnostics"]), 8)
        encoded = result.report.canonical_json
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(".sqlite3", encoded)
        self.assertNotIn("Traceback", encoded)
        self.assertNotIn("SELECT ", encoded)

    def test_failure_is_deterministic(self):
        with self.p5.open("ab") as stream:
            stream.write(b"changed")
        first = run_quality_gate(SNAPSHOT, self.specs)
        second = run_quality_gate(SNAPSHOT, self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.report.quality_sha256, second.report.quality_sha256)

    def test_source_has_no_execution_backtest_account_risk_network_or_provider_import(self):
        import yatl.analytics.quality as module

        source = inspect.getsource(module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.backtest",
            "import yatl.backtest",
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
