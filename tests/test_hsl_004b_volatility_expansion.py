import inspect
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from research.historical_strategy_lab import volatility_expansion as hsl4b


def cell(fold_id, symbol, pnl="2", trades=4):
    return {
        "fold_id": fold_id, "symbol": symbol, "candidate_id": hsl4b.CANDIDATE_ID,
        "completed_trades": trades, "wins": 3, "losses": 1,
        "gross_profit_quote": "8", "gross_loss_quote": "4",
        "net_pnl_after_costs_quote": pnl, "net_return_after_costs": "0.002",
        "realized_closed_trade_pnl_quote": "4", "executed_total_cost_quote": "1",
        "maximum_drawdown_fraction": "0.01", "largest_positive_trade_quote": "1",
    }


class HSL004BTests(unittest.TestCase):
    def test_protocol_is_frozen_and_research_only(self):
        protocol, digest = hsl4b.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertEqual(protocol["checkpoint"], "HSL-004B")
        self.assertEqual(protocol["technique_family"], "VOLATILITY_EXPANSION")
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["p4_p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(protocol["trade_permission"])
        self.assertFalse(protocol["methodology"]["parameter_search"])
        self.assertFalse(protocol["methodology"]["outcome_driven_retuning"])

    def test_true_range_baseline_is_point_in_time(self):
        candles = (
            SimpleNamespace(high="11", low="9", close="10", close_time_ms=10),
            SimpleNamespace(high="13", low="10", close="12", close_time_ms=20),
            SimpleNamespace(high="20", low="1", close="2", close_time_ms=30),
        )
        self.assertEqual(hsl4b._true_ranges(candles, 30), (Decimal("3"),))
        self.assertEqual(hsl4b._atr_baseline(candles, 1, 30), Decimal("3"))

    def test_plain_bounds_repeating_decimal_for_long_setup(self):
        raw = Decimal("99." + "1" * 80)
        normalized = hsl4b._plain(raw)
        self.assertLessEqual(
            len(normalized.partition(".")[2]),
            40,
        )
        setup = hsl4b.LongSetup("100", normalized, "101")
        self.assertEqual(setup.invalidation_price, normalized)

    def test_aggregate_can_qualify_without_live_authority(self):
        protocol, _ = hsl4b.load_protocol()
        cells = [
            cell(f"HSL-F{fold:03d}", symbol)
            for fold in range(1, 6) for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        result = hsl4b._aggregate(protocol, cells)
        self.assertEqual(result["qualification"]["status"], "QUALIFIED_HSL_RESEARCH")
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertTrue(result["p11_locked"])
        self.assertFalse(result["live_authorized"])

    def test_sparse_negative_candidate_fails_closed(self):
        protocol, _ = hsl4b.load_protocol()
        cells = [
            cell(f"HSL-F{fold:03d}", symbol, pnl="-2", trades=1)
            for fold in range(1, 6) for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        for item in cells:
            item.update(wins=0, losses=1, gross_profit_quote="0",
                        gross_loss_quote="2", realized_closed_trade_pnl_quote="-2",
                        largest_positive_trade_quote="0")
        result = hsl4b._aggregate(protocol, cells)
        self.assertEqual(result["qualification"]["status"], "NOT_QUALIFIED_HSL_RESEARCH")

    def test_p10_runtime_is_protected(self):
        with self.assertRaises(hsl4b.HSLVolatilityError):
            hsl4b.run_volatility_expansion(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path="quality/event-quality-" + "0" * 24 + ".json",
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_credentials_orders_or_p4_veto(self):
        source = inspect.getsource(hsl4b)
        for forbidden in (
            "requests", "httpx", "aiohttp", "websockets", "/api/v3/order",
            "/fapi", "/dapi", "api_key", "api_secret", "os.environ", "os.getenv",
            "assess_fixed_quantity_entry", "_RiskTracker",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
