import hashlib
import inspect
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.analytics import (
    AnalystTraceDimensionRecord,
    AnalyticsSourceKind,
    SegmentDimension,
    SegmentationError,
    StrategyEvidenceState,
    UNATTRIBUTED_STRATEGY_IDENTITY,
    UpstreamSourceSpec,
    build_segmentation,
)
from yatl.analytics.segmentation import (
    _analyst_segment,
    _group_records,
    _trade_segment,
)
from yatl.analytics.timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from yatl.analytics.trade_runtime import _close_fixture


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SegmentationTests(unittest.TestCase):
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

    def test_replay_is_byte_identical_and_read_only(self):
        before = tuple(file_sha(item.database_path) for item in self.specs)
        first = build_segmentation(SNAPSHOT, self.specs)
        second = build_segmentation(SNAPSHOT, self.specs)
        after = tuple(file_sha(item.database_path) for item in self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.segmentation_sha256, second.segmentation_sha256)
        self.assertEqual(before, after)

    def test_trade_partition_conserves_every_trade_exactly_once_per_family(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        expected = {item.trade_sha256 for item in report.trade_metrics}
        for dimension in (
            SegmentDimension.SYMBOL,
            SegmentDimension.STRATEGY_IDENTITY,
            SegmentDimension.EVIDENCE_LABEL,
        ):
            members = [
                member
                for segment in report.trade_segments
                if segment.dimension is dimension
                for member in segment.member_trade_sha256
            ]
            self.assertEqual(set(members), expected)
            self.assertEqual(len(members), len(set(members)))

    def test_analyst_partition_conserves_every_trace_exactly_once_per_family(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        expected = {item.trace_sha256 for item in report.analyst_traces}
        for dimension in (
            SegmentDimension.ANALYST_DISPOSITION,
            SegmentDimension.GROUNDING_CODE,
            SegmentDimension.TRACE_ACCEPTANCE,
        ):
            members = [
                member
                for segment in report.analyst_segments
                if segment.dimension is dimension
                for member in segment.member_trace_sha256
            ]
            self.assertEqual(set(members), expected)
            self.assertEqual(len(members), len(set(members)))

    def test_strategy_attribution_is_not_invented(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        strategy = next(
            item for item in report.trade_segments
            if item.dimension is SegmentDimension.STRATEGY_IDENTITY
        )
        evidence = next(
            item for item in report.trade_segments
            if item.dimension is SegmentDimension.EVIDENCE_LABEL
        )
        self.assertEqual(strategy.value, UNATTRIBUTED_STRATEGY_IDENTITY)
        self.assertEqual(
            evidence.value,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value,
        )
        record = report.as_record()
        self.assertFalse(
            record["interpretation"]["trade_to_strategy_attribution"]
        )
        self.assertFalse(
            record["interpretation"]["trade_to_analyst_disposition_attribution"]
        )
        self.assertFalse(record["interpretation"]["causality_claim"])

    def test_analyst_disposition_uses_only_sanitized_trace_dimension(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        segment = next(
            item for item in report.analyst_segments
            if item.dimension is SegmentDimension.ANALYST_DISPOSITION
        )
        self.assertEqual(segment.value, "REVIEW")
        self.assertEqual(segment.member_count, 1)

    def test_segment_id_is_stable_for_same_population_dimension_value(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        metric = report.trade_metrics[0]
        one = _trade_segment(
            SegmentDimension.EVIDENCE_LABEL,
            "INSUFFICIENT_EVIDENCE",
            (metric,),
        )
        empty = _trade_segment(
            SegmentDimension.EVIDENCE_LABEL,
            "INSUFFICIENT_EVIDENCE",
            (),
        )
        self.assertEqual(one.segment_id, empty.segment_id)
        self.assertNotEqual(one.segment_sha256, empty.segment_sha256)

    def test_trade_segment_summary_tamper_fails_closed(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        first = report.trade_segments[0]
        tampered = replace(first, realized_pnl_quote="999")
        with self.assertRaises(SegmentationError):
            replace(
                report,
                trade_segments=(tampered, *report.trade_segments[1:]),
            )

    def test_source_metrics_binding_tamper_fails_closed(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        with self.assertRaises(SegmentationError):
            replace(report, metrics_sha256="0" * 64)

    def test_duplicate_trade_member_fails_closed(self):
        report = build_segmentation(SNAPSHOT, self.specs)
        first = report.trade_segments[0]
        member = first.member_trade_sha256[0]
        with self.assertRaises(SegmentationError):
            replace(
                first,
                member_trade_sha256=(member, member),
                member_count=2,
                winning_trades=2 if first.winning_trades else 0,
                losing_trades=2 if first.losing_trades else 0,
                breakeven_trades=2 if first.breakeven_trades else 0,
            )

    def test_synthetic_analyst_partition_is_exact_for_accept_and_reject(self):
        accepted = AnalystTraceDimensionRecord(
            "1" * 64,
            "REVIEW",
            "GROUNDED",
            True,
        )
        rejected = AnalystTraceDimensionRecord(
            "2" * 64,
            "INSUFFICIENT_DATA",
            "CONTRADICTION",
            False,
        )
        segments = _group_records(
            (accepted, rejected),
            SegmentDimension.ANALYST_DISPOSITION,
            lambda item: item.disposition,
            _analyst_segment,
        )
        self.assertEqual(
            tuple(item.value for item in segments),
            ("INSUFFICIENT_DATA", "REVIEW"),
        )
        self.assertEqual(sum(item.member_count for item in segments), 2)

    def test_cross_symbol_source_fails_closed(self):
        bad = replace(self.specs[1], symbol="ETHUSDT")
        with self.assertRaises(SegmentationError):
            build_segmentation(SNAPSHOT, (self.specs[0], bad))

    def test_source_has_no_execution_backtest_account_risk_network_or_provider_import(self):
        import yatl.analytics.segmentation as module

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
