import copy
import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.metrics import TradePerformanceMetric, _aggregate
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.contracts import MetricState
from yatl.dashboard.loader import load_p7_export
from yatl.dashboard.performance_views import (
    DashboardAnalystSegmentSummary,
    DashboardTradeSegmentSummary,
    PerformanceViewProjectionError,
    _aggregate_trade_metrics,
    project_performance_segmentation,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    material = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def resign_loaded(loaded, record):
    record = copy.deepcopy(record)
    analytics = record["analytics"]
    quality = record["quality"]
    segmentation_sha256 = digest(analytics)
    quality["accepted_chain"]["segmentation_sha256"] = segmentation_sha256
    quality["accepted_chain"]["metrics_sha256"] = analytics["metrics_sha256"]
    quality["accepted_chain"]["completed_trade_count"] = len(analytics["trade_metrics"])
    quality["accepted_chain"]["analyst_trace_count"] = len(analytics["analyst_traces"])
    quality_sha256 = digest(quality)
    export_sha256 = digest({
        "schema_version": record["schema_version"],
        "quality": quality,
        "analytics": analytics,
    })
    record["export_sha256"] = export_sha256
    encoded = canonical(record) + "\n"
    source = replace(
        loaded.source,
        source_id="P7_EXPORT_" + export_sha256[:16].upper(),
        export_sha256=export_sha256,
    )
    return replace(
        loaded,
        source=source,
        quality_sha256=quality_sha256,
        segmentation_sha256=segmentation_sha256,
        export_sha256=export_sha256,
        raw_file_sha256=digest(encoded),
        byte_length=len(encoded.encode("utf-8")),
        canonical_json=encoded,
    )


def p7_aggregate_from_record(record):
    metrics = tuple(
        TradePerformanceMetric(
            item["trade_index"],
            item["trade_sha256"],
            item["realized_pnl_quote"],
            item["entry_gross_quote"],
            item["exit_gross_quote"],
            item["entry_cash_out_quote"],
            item["gross_return"],
            item["net_return"],
            item["total_fee_quote"],
            item["total_slippage_quote"],
            item["holding_time_ms"],
        )
        for item in record["analytics"]["trade_metrics"]
    )
    return _aggregate(metrics)


class PerformanceSegmentationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_root = self.root / "source"
        source_root.mkdir()
        _, _, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        self.record, encoded = _export_payload(gate)
        self.path = self.root / "accepted.json"
        self.path.write_text(encoded, encoding="utf-8")
        self.loaded = load_p7_export(self.path, self.record["export_sha256"])
        self.view = project_performance_segmentation(self.loaded)
        self.metrics = {item.metric_id: item for item in self.view.metrics}

    def tearDown(self):
        self.temp.cleanup()

    def test_projection_is_deterministic_and_digest_stable(self):
        replay = project_performance_segmentation(self.loaded)
        self.assertEqual(self.view, replay)
        self.assertEqual(self.view.projection_sha256, replay.projection_sha256)
        self.assertEqual(len(self.view.projection_sha256), 64)

    def test_projection_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.view.strategy_evidence = "OTHER"

    def test_metric_order_is_frozen_and_complete(self):
        self.assertEqual(
            tuple(item.metric_id for item in self.view.metrics),
            (
                "METRIC_COMPLETED_TRADES",
                "METRIC_WINNING_TRADES",
                "METRIC_LOSING_TRADES",
                "METRIC_BREAKEVEN_TRADES",
                "METRIC_REALIZED_PNL",
                "METRIC_GROSS_PNL",
                "METRIC_TOTAL_FEES",
                "METRIC_TOTAL_SLIPPAGE",
                "METRIC_TOTAL_COST",
                "METRIC_GROSS_RETURN",
                "METRIC_NET_RETURN",
                "METRIC_WIN_RATE",
                "METRIC_MAX_REALIZED_DRAWDOWN",
                "METRIC_TOTAL_HOLDING_TIME",
                "METRIC_MIN_HOLDING_TIME",
                "METRIC_MAX_HOLDING_TIME",
                "METRIC_AVG_HOLDING_TIME",
                "METRIC_BEST_TRADE_PNL",
                "METRIC_WORST_TRADE_PNL",
            ),
        )

    def test_aggregate_values_match_authoritative_p7_metric_formula(self):
        expected = p7_aggregate_from_record(self.record)
        mapping = {
            "METRIC_COMPLETED_TRADES": str(expected.completed_trade_count),
            "METRIC_WINNING_TRADES": str(expected.winning_trades),
            "METRIC_LOSING_TRADES": str(expected.losing_trades),
            "METRIC_BREAKEVEN_TRADES": str(expected.breakeven_trades),
            "METRIC_REALIZED_PNL": expected.realized_pnl_quote,
            "METRIC_GROSS_PNL": expected.gross_pnl_quote,
            "METRIC_TOTAL_FEES": expected.total_fee_quote,
            "METRIC_TOTAL_SLIPPAGE": expected.total_slippage_quote,
            "METRIC_TOTAL_COST": expected.total_cost_quote,
            "METRIC_GROSS_RETURN": expected.gross_return,
            "METRIC_NET_RETURN": expected.net_return,
            "METRIC_WIN_RATE": expected.win_rate,
            "METRIC_MAX_REALIZED_DRAWDOWN": expected.maximum_realized_drawdown_quote,
            "METRIC_TOTAL_HOLDING_TIME": str(expected.total_holding_time_ms),
            "METRIC_MIN_HOLDING_TIME": (
                str(expected.minimum_holding_time_ms)
                if expected.minimum_holding_time_ms is not None else None
            ),
            "METRIC_MAX_HOLDING_TIME": (
                str(expected.maximum_holding_time_ms)
                if expected.maximum_holding_time_ms is not None else None
            ),
            "METRIC_AVG_HOLDING_TIME": expected.average_holding_time_ms,
            "METRIC_BEST_TRADE_PNL": expected.best_trade_pnl_quote,
            "METRIC_WORST_TRADE_PNL": expected.worst_trade_pnl_quote,
        }
        for metric_id, expected_value in mapping.items():
            with self.subTest(metric_id=metric_id):
                self.assertEqual(self.metrics[metric_id].value, expected_value)

    def test_symbol_segment_reconciles_counts_pnl_and_cost(self):
        segment = next(
            item
            for item in self.record["analytics"]["trade_segments"]
            if item["dimension"] == "SYMBOL"
            and item["value"] == self.record["analytics"]["symbol"]
        )
        self.assertEqual(self.metrics["METRIC_COMPLETED_TRADES"].value, str(segment["member_count"]))
        self.assertEqual(self.metrics["METRIC_REALIZED_PNL"].value, segment["realized_pnl_quote"])
        self.assertEqual(self.metrics["METRIC_TOTAL_COST"].value, segment["total_cost_quote"])
        self.assertEqual(self.metrics["METRIC_WINNING_TRADES"].value, str(segment["winning_trades"]))
        self.assertEqual(self.metrics["METRIC_LOSING_TRADES"].value, str(segment["losing_trades"]))
        self.assertEqual(self.metrics["METRIC_BREAKEVEN_TRADES"].value, str(segment["breakeven_trades"]))

    def test_metric_source_hashes_bind_metrics_identity_formula_and_source_rows(self):
        for item in self.view.metrics:
            with self.subTest(metric_id=item.metric_id):
                self.assertEqual(len(item.source_metric_sha256), 64)
                self.assertNotEqual(item.source_metric_sha256, self.view.source_metrics_sha256)

    def test_empty_aggregate_preserves_exact_unavailable_semantics(self):
        aggregate = _aggregate_trade_metrics(())
        self.assertEqual(aggregate["completed_trades"], "0")
        self.assertEqual(aggregate["realized_pnl"], "0")
        self.assertEqual(aggregate["gross_pnl"], "0")
        self.assertEqual(aggregate["total_fees"], "0")
        self.assertEqual(aggregate["total_slippage"], "0")
        self.assertEqual(aggregate["total_cost"], "0")
        self.assertEqual(aggregate["max_realized_drawdown"], "0")
        self.assertEqual(aggregate["total_holding_time"], "0")
        for key in (
            "gross_return",
            "net_return",
            "win_rate",
            "min_holding_time",
            "max_holding_time",
            "avg_holding_time",
            "best_trade_pnl",
            "worst_trade_pnl",
        ):
            with self.subTest(key=key):
                self.assertIsNone(aggregate[key])

    def test_available_metrics_use_value_state(self):
        for metric_id in (
            "METRIC_COMPLETED_TRADES",
            "METRIC_REALIZED_PNL",
            "METRIC_TOTAL_FEES",
            "METRIC_MAX_REALIZED_DRAWDOWN",
        ):
            self.assertIs(self.metrics[metric_id].state, MetricState.VALUE)

    def test_trade_segments_preserve_exact_source_rows(self):
        source = self.record["analytics"]["trade_segments"]
        self.assertEqual(len(self.view.trade_segments), len(source))
        for index, (display, original) in enumerate(zip(self.view.trade_segments, source)):
            self.assertIsInstance(display, DashboardTradeSegmentSummary)
            self.assertEqual(display.display_id, f"TRADE_SEGMENT_{index:04d}")
            self.assertEqual(display.dimension, original["dimension"].lower())
            self.assertEqual(display.label, original["value"])
            self.assertEqual(display.member_count, original["member_count"])
            self.assertEqual(display.realized_pnl, original["realized_pnl_quote"])
            self.assertEqual(display.total_cost, original["total_cost_quote"])
            self.assertEqual(display.winning_trades, original["winning_trades"])
            self.assertEqual(display.losing_trades, original["losing_trades"])
            self.assertEqual(display.breakeven_trades, original["breakeven_trades"])
            self.assertEqual(display.source_segment_id, original["segment_id"])
            self.assertEqual(display.source_segment_sha256, original["segment_sha256"])

    def test_analyst_segments_preserve_trace_count_semantics(self):
        source = self.record["analytics"]["analyst_segments"]
        self.assertEqual(len(self.view.analyst_segments), len(source))
        for index, (display, original) in enumerate(zip(self.view.analyst_segments, source)):
            self.assertIsInstance(display, DashboardAnalystSegmentSummary)
            self.assertEqual(display.display_id, f"ANALYST_SEGMENT_{index:04d}")
            self.assertEqual(display.dimension, original["dimension"].lower())
            self.assertEqual(display.label, original["value"])
            self.assertEqual(display.trace_count, original["member_count"])
            self.assertEqual(display.source_segment_id, original["segment_id"])
            self.assertEqual(display.source_segment_sha256, original["segment_sha256"])

    def test_strategy_evidence_is_never_upgraded(self):
        self.assertEqual(self.view.strategy_evidence, "INSUFFICIENT_EVIDENCE")
        for item in self.view.trade_segments:
            self.assertEqual(item.strategy_evidence, "INSUFFICIENT_EVIDENCE")
        for item in self.view.analyst_segments:
            self.assertEqual(item.strategy_evidence, "INSUFFICIENT_EVIDENCE")

    def test_no_cross_dimension_aggregation_or_causality_claim(self):
        self.assertIs(self.view.cross_dimension_aggregation, False)
        self.assertIs(self.view.causality_claim, False)
        self.assertEqual(self.view.aggregation_scope, "COMPLETED_PAPER_TRADES_ONLY")

    def test_each_trade_dimension_partitions_members_exactly_once(self):
        expected = {item["trade_sha256"] for item in self.record["analytics"]["trade_metrics"]}
        for dimension in ("SYMBOL", "STRATEGY_IDENTITY", "EVIDENCE_LABEL"):
            seen = [
                member
                for item in self.record["analytics"]["trade_segments"]
                if item["dimension"] == dimension
                for member in item["member_trade_sha256"]
            ]
            with self.subTest(dimension=dimension):
                self.assertEqual(len(seen), len(set(seen)))
                self.assertEqual(set(seen), expected)

    def test_each_analyst_dimension_partitions_members_exactly_once(self):
        expected = {item["trace_sha256"] for item in self.record["analytics"]["analyst_traces"]}
        for dimension in ("ANALYST_DISPOSITION", "GROUNDING_CODE", "TRACE_ACCEPTANCE"):
            seen = [
                member
                for item in self.record["analytics"]["analyst_segments"]
                if item["dimension"] == dimension
                for member in item["member_trace_sha256"]
            ]
            with self.subTest(dimension=dimension):
                self.assertEqual(len(seen), len(set(seen)))
                self.assertEqual(set(seen), expected)

    def test_projection_rejects_non_loaded_input(self):
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(object())

    def test_projection_rejects_simple_payload_tamper(self):
        record = self.loaded.record()
        record["analytics"]["trade_metrics"][0]["realized_pnl_quote"] = "999"
        forged = replace(self.loaded, canonical_json=canonical(record) + "\n")
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_re_signed_segment_digest_tamper(self):
        record = self.loaded.record()
        segment = record["analytics"]["trade_segments"][0]
        segment["realized_pnl_quote"] = "999"
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_cross_dimension_double_count_even_if_re_signed(self):
        record = self.loaded.record()
        source = next(
            item for item in record["analytics"]["trade_segments"]
            if item["dimension"] == "EVIDENCE_LABEL"
        )
        duplicate = copy.deepcopy(source)
        duplicate["value"] = "OTHER"
        duplicate["segment_id"] = digest({
            "schema_version": 1,
            "population": duplicate["population"],
            "dimension": duplicate["dimension"],
            "value": duplicate["value"],
        })
        base = {key: value for key, value in duplicate.items() if key != "segment_sha256"}
        duplicate["segment_sha256"] = digest({"schema_version": 1, "segment": base})
        record["analytics"]["trade_segments"].append(duplicate)
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_missing_trade_partition_even_if_re_signed(self):
        record = self.loaded.record()
        record["analytics"]["trade_segments"] = [
            item for item in record["analytics"]["trade_segments"]
            if item["dimension"] != "EVIDENCE_LABEL"
        ]
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_missing_analyst_partition_even_if_re_signed(self):
        record = self.loaded.record()
        record["analytics"]["analyst_segments"] = [
            item for item in record["analytics"]["analyst_segments"]
            if item["dimension"] != "TRACE_ACCEPTANCE"
        ]
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_strategy_evidence_upgrade_even_if_re_signed(self):
        record = self.loaded.record()
        record["analytics"]["strategy_evidence"] = "PROVEN"
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_symbol_segment_aggregate_drift_even_if_re_signed(self):
        record = self.loaded.record()
        segment = next(
            item for item in record["analytics"]["trade_segments"]
            if item["dimension"] == "SYMBOL"
        )
        segment["realized_pnl_quote"] = "999"
        base = {key: value for key, value in segment.items() if key != "segment_sha256"}
        segment["segment_sha256"] = digest({"schema_version": 1, "segment": base})
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_rejects_invalid_analyst_trace_semantics_even_if_re_signed(self):
        record = self.loaded.record()
        if not record["analytics"]["analyst_traces"]:
            self.skipTest("fixture has no analyst traces")
        trace = record["analytics"]["analyst_traces"][0]
        trace["accepted"] = True
        trace["disposition"] = "INSUFFICIENT_DATA"
        forged = resign_loaded(self.loaded, record)
        with self.assertRaises(PerformanceViewProjectionError):
            project_performance_segmentation(forged)

    def test_projection_source_identities_are_exact(self):
        self.assertEqual(
            self.view.source_metrics_sha256,
            self.record["analytics"]["metrics_sha256"],
        )
        self.assertEqual(
            self.view.source_segmentation_sha256,
            self.loaded.segmentation_sha256,
        )

    def test_projection_record_has_no_caller_path_or_private_material(self):
        encoded = canonical(self.view.as_record())
        self.assertNotIn(str(self.path), encoded)
        for forbidden in (
            "database_path",
            "api_key",
            "api_secret",
            "account_id",
            "raw_response",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_performance_source_has_no_analytics_runtime_database_or_network_import(self):
        import yatl.dashboard.performance_views as performance_views

        source_text = inspect.getsource(performance_views)
        for forbidden in (
            "from yatl.analytics",
            "import yatl.analytics",
            "sqlite3",
            "database_path",
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
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
