import inspect
import unittest
from decimal import Decimal
from pathlib import Path

from research.historical_strategy_lab import walk_forward as hsl


def cell(fold_id, symbol, *, pnl="2", trades=4):
    return {
        "fold_id": fold_id,
        "symbol": symbol,
        "candidate_id": "HSL-CHALLENGER-RANGE-BREAKOUT-1",
        "completed_trades": trades,
        "wins": 3,
        "losses": 1,
        "gross_profit_quote": "8",
        "gross_loss_quote": "4",
        "net_pnl_after_costs_quote": pnl,
        "realized_closed_trade_pnl_quote": "4",
        "executed_total_cost_quote": "1",
        "maximum_drawdown_fraction": "0.01",
        "largest_positive_trade_quote": "1",
    }


class HSL001WalkForwardTests(unittest.TestCase):
    def test_protocol_is_preregistered_and_bounded(self):
        protocol, digest = hsl.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["paper_only"])
        self.assertTrue(protocol["p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(protocol["trade_permission"])
        self.assertEqual(protocol["live_master_lock"], "OFF")
        self.assertEqual(len(protocol["folds"]), 5)
        self.assertEqual(
            [item["fold_id"] for item in protocol["folds"]],
            [f"HSL-F{i:03d}" for i in range(1, 6)],
        )
        self.assertEqual(
            {
                item["strategy_id"]
                for item in protocol["candidates"]
            },
            {"TREND_PULLBACK", "RANGE_BREAKOUT"},
        )
        methodology = protocol["methodology"]
        self.assertFalse(methodology["p4_risk_veto_applied"])
        self.assertTrue(
            methodology["state_reset_at_each_evaluation_fold"]
        )
        self.assertTrue(
            methodology["market_history_available_point_in_time"]
        )
        self.assertEqual(methodology["fixed_quantity"], "0.001")
        self.assertEqual(methodology["fee_bps"], "10")
        self.assertEqual(methodology["slippage_bps"], "5")

    def test_good_candidate_passes_frozen_hsl_research_gate(self):
        protocol, _ = hsl.load_protocol()
        candidate = protocol["candidates"][1]
        cells = [
            cell(f"HSL-F{fold:03d}", symbol)
            for fold in range(1, 6)
            for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        result = hsl._aggregate_candidate(
            candidate_record=candidate,
            cells=cells,
            gate=protocol["qualification_gate"],
        )
        self.assertEqual(result["completed_trades"], 40)
        self.assertEqual(result["profit_factor"], "2")
        self.assertEqual(
            result["qualification"]["status"],
            "QUALIFIED_HSL_RESEARCH",
        )
        self.assertEqual(
            result["qualification"]["failure_reasons"], []
        )

    def test_unprofitable_sparse_candidate_fails_closed(self):
        protocol, _ = hsl.load_protocol()
        candidate = protocol["candidates"][0]
        cells = [
            cell(
                f"HSL-F{fold:03d}",
                symbol,
                pnl="-2",
                trades=1,
            )
            for fold in range(1, 6)
            for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        for item in cells:
            item["wins"] = 0
            item["losses"] = 1
            item["gross_profit_quote"] = "0"
            item["gross_loss_quote"] = "2"
            item["realized_closed_trade_pnl_quote"] = "-2"
            item["largest_positive_trade_quote"] = "0"
        result = hsl._aggregate_candidate(
            candidate_record=candidate,
            cells=cells,
            gate=protocol["qualification_gate"],
        )
        self.assertEqual(
            result["qualification"]["status"],
            "NOT_QUALIFIED_HSL_RESEARCH",
        )
        reasons = set(
            result["qualification"]["failure_reasons"]
        )
        self.assertIn(
            "MINIMUM_COMPLETED_TRADES_TOTAL_NOT_MET", reasons
        )
        self.assertIn("TOTAL_NET_PNL_NOT_POSITIVE", reasons)
        self.assertIn("EXPECTANCY_NOT_POSITIVE", reasons)
        self.assertIn("PROFIT_FACTOR_GATE_FAILED", reasons)

    def test_profit_factor_handles_no_loss_without_nonfinite_json(self):
        value, infinite = hsl._profit_factor(
            Decimal("5"), Decimal("0")
        )
        self.assertIsNone(value)
        self.assertTrue(infinite)

    def test_p10_runtime_is_protected(self):
        with self.assertRaises(hsl.HSLImplementationError):
            hsl.run_walk_forward(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_credentials_or_p4_veto(self):
        source = inspect.getsource(hsl)
        for forbidden in (
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
            "assess_fixed_quantity_entry",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
