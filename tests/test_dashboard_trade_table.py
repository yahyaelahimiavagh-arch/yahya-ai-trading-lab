import hashlib
import inspect
import json
import tempfile
import unittest
from decimal import Decimal
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.loader import load_p7_export
from yatl.dashboard.trade_table import (
    MAX_PAGE_SIZE,
    DashboardCompletedTradeMetricRow,
    TradeOutcomeFilter,
    TradeSortDirection,
    TradeSortKey,
    TradeTableProjectionError,
    TradeTableQuery,
    apply_trade_table_query,
    project_completed_trade_table,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def metric_sha(metric):
    return hashlib.sha256(
        canonical({"schema_version": 1, "trade_metric": metric}).encode("utf-8")
    ).hexdigest()


def synthetic_row(index, pnl, holding, sha_char):
    metric = {
        "trade_index": index,
        "trade_sha256": sha_char * 64,
        "realized_pnl_quote": pnl,
        "entry_gross_quote": "100",
        "exit_gross_quote": "101",
        "entry_cash_out_quote": "100.1",
        "gross_return": "0.01",
        "net_return": pnl,
        "total_fee_quote": "0.1",
        "total_slippage_quote": "0.2",
        "holding_time_ms": holding,
    }
    value = Decimal(pnl)
    outcome = "WIN" if value > 0 else "LOSS" if value < 0 else "BREAKEVEN"
    return DashboardCompletedTradeMetricRow(
        row_id=f"TRADE_{index:08d}",
        trade_index=index,
        symbol="BTCUSDT",
        net_pnl=pnl,
        entry_gross_quote=metric["entry_gross_quote"],
        exit_gross_quote=metric["exit_gross_quote"],
        entry_cash_out_quote=metric["entry_cash_out_quote"],
        gross_return=metric["gross_return"],
        net_return=metric["net_return"],
        fee_total=metric["total_fee_quote"],
        slippage_total=metric["total_slippage_quote"],
        holding_time_ms=holding,
        outcome=outcome,
        source_trade_sha256=metric["trade_sha256"],
        source_metric_sha256=metric_sha(metric),
    )


class CompletedTradeTableProjectionTests(unittest.TestCase):
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
        self.table = project_completed_trade_table(self.loaded)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_projection_is_deterministic_and_digest_stable(self):
        replay = project_completed_trade_table(self.loaded)
        self.assertEqual(self.table, replay)
        self.assertEqual(self.table.table_sha256, replay.table_sha256)
        self.assertEqual(len(self.table.table_sha256), 64)

    def test_projection_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.table.total_completed = 99

    def test_default_query_is_bounded(self):
        self.assertEqual(self.table.query, TradeTableQuery())
        self.assertLessEqual(self.table.returned_count, self.table.query.page_size)
        self.assertLessEqual(self.table.query.page_size, MAX_PAGE_SIZE)

    def test_query_rejects_invalid_page_size(self):
        for value in (0, MAX_PAGE_SIZE + 1):
            with self.subTest(value=value), self.assertRaises(TradeTableProjectionError):
                TradeTableQuery(page_size=value)

    def test_query_rejects_invalid_offset(self):
        with self.assertRaises(TradeTableProjectionError):
            TradeTableQuery(offset=-1)

    def test_every_source_metric_becomes_exact_completed_long_paper_row(self):
        metrics = self.record["analytics"]["trade_metrics"]
        self.assertEqual(self.table.total_completed, len(metrics))
        self.assertEqual(self.table.returned_count, len(metrics))
        for row, metric in zip(self.table.rows, metrics):
            self.assertEqual(row.trade_index, metric["trade_index"])
            self.assertEqual(row.source_trade_sha256, metric["trade_sha256"])
            self.assertEqual(row.net_pnl, metric["realized_pnl_quote"])
            self.assertEqual(row.entry_gross_quote, metric["entry_gross_quote"])
            self.assertEqual(row.exit_gross_quote, metric["exit_gross_quote"])
            self.assertEqual(row.entry_cash_out_quote, metric["entry_cash_out_quote"])
            self.assertEqual(row.gross_return, metric["gross_return"])
            self.assertEqual(row.net_return, metric["net_return"])
            self.assertEqual(row.fee_total, metric["total_fee_quote"])
            self.assertEqual(row.slippage_total, metric["total_slippage_quote"])
            self.assertEqual(row.holding_time_ms, metric["holding_time_ms"])
            self.assertEqual(row.side, "LONG")
            self.assertEqual(row.status, "COMPLETED")
            self.assertTrue(row.paper)
            self.assertTrue(row.display_only)
            self.assertEqual(row.strategy_evidence, "INSUFFICIENT_EVIDENCE")

    def test_source_metric_digest_binds_exact_metric_record(self):
        metric = self.record["analytics"]["trade_metrics"][0]
        self.assertEqual(self.table.rows[0].source_metric_sha256, metric_sha(metric))

    def test_row_id_maps_exactly_to_trade_index(self):
        row = self.table.rows[0]
        self.assertEqual(row.row_id, f"TRADE_{row.trade_index:08d}")

    def test_noncompleted_policy_is_explicit_and_fixed(self):
        self.assertEqual(
            self.table.noncompleted_policy,
            "SEPARATE_NOT_PROJECTED_FROM_P7_TRADE_METRICS",
        )

    def test_no_absent_execution_fields_are_invented(self):
        encoded = canonical(self.table.as_record())
        for forbidden in (
            "entry_time_ms",
            "exit_time_ms",
            "quantity",
            "entry_price",
            "exit_price",
            "open_trade",
            "incomplete_trade",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_win_filter_is_exact(self):
        rows = (
            synthetic_row(0, "1.5", 30, "a"),
            synthetic_row(1, "-2", 20, "b"),
            synthetic_row(2, "0", 10, "c"),
        )
        page, count = apply_trade_table_query(
            rows,
            TradeTableQuery(outcome=TradeOutcomeFilter.WIN),
        )
        self.assertEqual(count, 1)
        self.assertEqual(tuple(item.outcome for item in page), ("WIN",))

    def test_loss_filter_is_exact(self):
        rows = (
            synthetic_row(0, "1.5", 30, "a"),
            synthetic_row(1, "-2", 20, "b"),
            synthetic_row(2, "0", 10, "c"),
        )
        page, count = apply_trade_table_query(
            rows,
            TradeTableQuery(outcome=TradeOutcomeFilter.LOSS),
        )
        self.assertEqual(count, 1)
        self.assertEqual(tuple(item.outcome for item in page), ("LOSS",))

    def test_breakeven_filter_is_exact(self):
        rows = (
            synthetic_row(0, "1.5", 30, "a"),
            synthetic_row(1, "-2", 20, "b"),
            synthetic_row(2, "0", 10, "c"),
        )
        page, count = apply_trade_table_query(
            rows,
            TradeTableQuery(outcome=TradeOutcomeFilter.BREAKEVEN),
        )
        self.assertEqual(count, 1)
        self.assertEqual(tuple(item.outcome for item in page), ("BREAKEVEN",))

    def test_trade_index_sort_asc_and_desc_is_deterministic(self):
        rows = (
            synthetic_row(2, "0", 10, "c"),
            synthetic_row(0, "1.5", 30, "a"),
            synthetic_row(1, "-2", 20, "b"),
        )
        asc, _ = apply_trade_table_query(rows, TradeTableQuery())
        desc, _ = apply_trade_table_query(
            rows,
            TradeTableQuery(direction=TradeSortDirection.DESC),
        )
        self.assertEqual(tuple(item.trade_index for item in asc), (0, 1, 2))
        self.assertEqual(tuple(item.trade_index for item in desc), (2, 1, 0))

    def test_net_pnl_sort_is_numeric_not_lexicographic(self):
        rows = (
            synthetic_row(0, "2", 30, "a"),
            synthetic_row(1, "10", 20, "b"),
            synthetic_row(2, "-3", 10, "c"),
        )
        page, _ = apply_trade_table_query(
            rows,
            TradeTableQuery(sort_key=TradeSortKey.NET_PNL),
        )
        self.assertEqual(tuple(item.net_pnl for item in page), ("-3", "2", "10"))

    def test_holding_time_sort_is_numeric(self):
        rows = (
            synthetic_row(0, "1", 300, "a"),
            synthetic_row(1, "1", 100, "b"),
            synthetic_row(2, "1", 200, "c"),
        )
        page, _ = apply_trade_table_query(
            rows,
            TradeTableQuery(sort_key=TradeSortKey.HOLDING_TIME),
        )
        self.assertEqual(tuple(item.holding_time_ms for item in page), (100, 200, 300))

    def test_sort_ties_use_stable_trade_identity_order(self):
        rows = (
            synthetic_row(2, "1", 100, "c"),
            synthetic_row(0, "1", 100, "a"),
            synthetic_row(1, "1", 100, "b"),
        )
        page, _ = apply_trade_table_query(
            rows,
            TradeTableQuery(sort_key=TradeSortKey.NET_PNL),
        )
        self.assertEqual(tuple(item.trade_index for item in page), (0, 1, 2))

    def test_pagination_is_bounded_and_has_no_overlap(self):
        rows = tuple(synthetic_row(i, "1", i + 1, "abcdef"[i]) for i in range(6))
        first, count = apply_trade_table_query(rows, TradeTableQuery(offset=0, page_size=2))
        second, count2 = apply_trade_table_query(rows, TradeTableQuery(offset=2, page_size=2))
        self.assertEqual(count, 6)
        self.assertEqual(count2, 6)
        self.assertEqual(tuple(item.trade_index for item in first), (0, 1))
        self.assertEqual(tuple(item.trade_index for item in second), (2, 3))
        self.assertTrue(set(first).isdisjoint(set(second)))

    def test_offset_beyond_filtered_population_returns_empty_page(self):
        rows = (synthetic_row(0, "1", 10, "a"),)
        page, count = apply_trade_table_query(
            rows,
            TradeTableQuery(offset=5, page_size=2),
        )
        self.assertEqual(page, ())
        self.assertEqual(count, 1)

    def test_duplicate_row_id_is_rejected(self):
        row = synthetic_row(0, "1", 10, "a")
        with self.assertRaises(TradeTableProjectionError):
            apply_trade_table_query((row, row), TradeTableQuery())

    def test_duplicate_trade_identity_is_rejected(self):
        first = synthetic_row(0, "1", 10, "a")
        original = synthetic_row(1, "1", 20, "b")
        duplicate_metric = {
            "trade_index": original.trade_index,
            "trade_sha256": first.source_trade_sha256,
            "realized_pnl_quote": original.net_pnl,
            "entry_gross_quote": original.entry_gross_quote,
            "exit_gross_quote": original.exit_gross_quote,
            "entry_cash_out_quote": original.entry_cash_out_quote,
            "gross_return": original.gross_return,
            "net_return": original.net_return,
            "total_fee_quote": original.fee_total,
            "total_slippage_quote": original.slippage_total,
            "holding_time_ms": original.holding_time_ms,
        }
        second = replace(
            original,
            source_trade_sha256=first.source_trade_sha256,
            source_metric_sha256=metric_sha(duplicate_metric),
        )
        with self.assertRaises(TradeTableProjectionError):
            apply_trade_table_query((first, second), TradeTableQuery())

    def test_projection_rejects_non_loaded_input(self):
        with self.assertRaises(TradeTableProjectionError):
            project_completed_trade_table(object())

    def test_projection_rejects_forged_missing_trade_id(self):
        forged_record = self.loaded.record()
        del forged_record["analytics"]["trade_metrics"][0]["trade_sha256"]
        forged = replace(
            self.loaded,
            canonical_json=canonical(forged_record) + "\n",
        )
        with self.assertRaises(TradeTableProjectionError):
            project_completed_trade_table(forged)

    def test_projection_rejects_forged_duplicate_trade_identity(self):
        forged_record = self.loaded.record()
        metric = dict(forged_record["analytics"]["trade_metrics"][0])
        metric["trade_index"] += 1
        forged_record["analytics"]["trade_metrics"].append(metric)
        forged_record["quality"]["accepted_chain"]["completed_trade_count"] += 1
        forged = replace(
            self.loaded,
            canonical_json=canonical(forged_record) + "\n",
        )
        with self.assertRaises(TradeTableProjectionError):
            project_completed_trade_table(forged)

    def test_projection_record_has_no_caller_path_or_private_material(self):
        encoded = canonical(self.table.as_record())
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

    def test_trade_table_source_has_no_analytics_runtime_database_or_network_import(self):
        import yatl.dashboard.trade_table as trade_table

        source_text = inspect.getsource(trade_table)
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
