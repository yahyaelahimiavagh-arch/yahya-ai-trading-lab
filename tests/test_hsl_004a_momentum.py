import inspect
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from research.historical_strategy_lab import momentum as hsl4


def cell(fold_id, symbol, *, pnl="2", trades=4, buy_hold="0.01"):
    return {
        "fold_id": fold_id,
        "symbol": symbol,
        "candidate_id": hsl4.CANDIDATE_ID,
        "completed_trades": trades,
        "wins": 3,
        "losses": 1,
        "gross_profit_quote": "8",
        "gross_loss_quote": "4",
        "net_pnl_after_costs_quote": pnl,
        "net_return_after_costs": "0.002",
        "realized_closed_trade_pnl_quote": "4",
        "executed_total_cost_quote": "1",
        "maximum_drawdown_fraction": "0.01",
        "largest_positive_trade_quote": "1",
        "buy_and_hold_return_fraction": buy_hold,
        "excess_return_vs_buy_and_hold_fraction": "-0.008",
    }


class HSL004AMomentumTests(unittest.TestCase):
    def test_protocol_is_preregistered_and_bounded(self):
        protocol, digest = hsl4.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertEqual(protocol["checkpoint"], "HSL-004A")
        self.assertEqual(protocol["technique_family"], "MOMENTUM")
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["paper_only"])
        self.assertTrue(protocol["p4_p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(protocol["trade_permission"])
        self.assertEqual(protocol["live_master_lock"], "OFF")

        candidate = protocol["candidate"]
        self.assertEqual(candidate["candidate_id"], hsl4.CANDIDATE_ID)
        self.assertEqual(candidate["strategy_id"], hsl4.STRATEGY_ID)
        self.assertEqual(
            candidate["parameters"],
            {
                "entry_return_lookback_hours": 24,
                "minimum_entry_return_fraction": "0.03",
                "ema_period_hours": 24,
                "rsi_period_hours": 14,
                "minimum_rsi": "55",
                "maximum_rsi": "75",
                "atr_period_hours": 14,
                "stop_atr_multiple": "1.5",
                "reward_risk": "2",
                "exit_return_lookback_hours": 12,
                "exit_return_threshold_fraction": "0",
            },
        )
        self.assertFalse(
            protocol["methodology"]["parameter_search"]
        )
        self.assertFalse(
            protocol["methodology"]["outcome_driven_retuning"]
        )
        self.assertFalse(
            protocol["benchmarks"][
                "buy_and_hold_is_parameter_selector"
            ]
        )

    def test_buy_hold_is_reported_but_not_required_for_qualification(self):
        protocol, _ = hsl4.load_protocol()
        cells = [
            cell(
                f"HSL-F{fold:03d}",
                symbol,
                buy_hold="0.50",
            )
            for fold in range(1, 6)
            for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        summary = hsl4._aggregate(
            protocol=protocol,
            cells=cells,
        )
        self.assertEqual(
            summary["qualification"]["status"],
            "QUALIFIED_HSL_RESEARCH",
        )
        self.assertFalse(
            summary["buy_and_hold_outperformance_required"]
        )
        self.assertFalse(summary["automatic_promotion"])
        self.assertEqual(summary["p10_evidence_effect"], "NONE")
        self.assertTrue(summary["p11_locked"])
        self.assertFalse(summary["live_authorized"])

    def test_sparse_unprofitable_candidate_fails_closed(self):
        protocol, _ = hsl4.load_protocol()
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
        summary = hsl4._aggregate(
            protocol=protocol,
            cells=cells,
        )
        self.assertEqual(
            summary["qualification"]["status"],
            "NOT_QUALIFIED_HSL_RESEARCH",
        )
        reasons = set(
            summary["qualification"]["failure_reasons"]
        )
        self.assertIn(
            "MINIMUM_COMPLETED_TRADES_TOTAL_NOT_MET",
            reasons,
        )
        self.assertIn("TOTAL_NET_PNL_NOT_POSITIVE", reasons)
        self.assertIn("EXPECTANCY_NOT_POSITIVE", reasons)

    def test_plain_bounds_repeating_decimal_for_long_setup(self):
        raw = Decimal("99." + "1" * 80)
        normalized = hsl4._setup_plain(raw)
        self.assertLessEqual(
            len(normalized.partition(".")[2]),
            40,
        )
        setup = hsl4.LongSetup("100", normalized, "101")
        self.assertEqual(setup.invalidation_price, normalized)

    def test_trade_accounting_uses_shared_ledger_precision_sum(self):
        source = inspect.getsource(hsl4._run_cell)
        self.assertIn("hsl1._sum_decimals(trade_pnls)", source)
        self.assertIn("hsl1._sum_decimals(wins)", source)
        self.assertIn("hsl1._sum_decimals(losses)", source)
        self.assertEqual(
            hsl4.IMPLEMENTATION_ID,
            "HSL-004A-MOMENTUM/0.1.2",
        )

    def test_buy_hold_return_is_deterministic(self):
        candles = (
            SimpleNamespace(open="100", close="110"),
            SimpleNamespace(open="110", close="120"),
        )
        value = hsl4._buy_hold_return(candles)
        self.assertEqual(value, Decimal("0.2"))

    def test_decision_contract_rejects_entry_without_setup(self):
        from yatl.strategy import StrategyAction

        with self.assertRaises(hsl4.HSLMomentumError):
            hsl4.MomentumDecision(
                StrategyAction.ENTER_LONG,
                "MOMENTUM_ENTRY",
                None,
                None,
                None,
                None,
                None,
                None,
            )

    def test_p10_runtime_is_protected(self):
        with self.assertRaises(hsl4.HSLMomentumError):
            hsl4.run_momentum(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_credentials_orders_or_p4_veto(self):
        source = inspect.getsource(hsl4)
        for forbidden in (
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
            "assess_fixed_quantity_entry",
            "_RiskTracker",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
