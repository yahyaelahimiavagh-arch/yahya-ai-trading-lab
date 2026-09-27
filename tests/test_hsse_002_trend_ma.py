import inspect
import math
import unittest
from pathlib import Path

from research.historical_strategy_search import trend_ma as hsse2


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "docs"
    / "research"
    / "historical-strategy-search"
    / "HSSE-002-TREND-MA-SEARCH-PLAN-v0.1.0.json"
)


class HSSE002TrendMASearchTests(unittest.TestCase):
    def test_plan_binds_ready_candidate_and_full_grid(self):
        plan, _, context = hsse2.load_plan(PLAN)
        self.assertEqual(plan["trial_matrix"]["trials_per_family"], 4950)
        self.assertEqual(plan["trial_matrix"]["total_trials"], 14850)
        self.assertEqual(
            context["candidate"]["status"], "READY_FOR_TRAIN_SEARCH"
        )
        self.assertTrue(context["packet_result"]["ready_for_train_search"])

    def test_trial_grid_is_exact_and_deterministic(self):
        windows = tuple(range(1, 1000, 10))
        pairs = hsse2._trial_pairs(windows)
        self.assertEqual(len(windows), 100)
        self.assertEqual(len(pairs), 4950)
        self.assertEqual(pairs[0], (1, 11))
        self.assertEqual(pairs[-1], (981, 991))
        self.assertEqual(len(set(pairs)), len(pairs))
        self.assertTrue(all(a < b for a, b in pairs))

    def test_sma_resets_after_gap_without_forward_fill(self):
        series = hsse2.SearchSeries(
            symbol="BTCUSDT",
            times=(0, hsse2.HOUR_MS, 3 * hsse2.HOUR_MS, 4 * hsse2.HOUR_MS),
            opens=(1.0, 2.0, 3.0, 4.0),
            closes=(1.0, 2.0, 3.0, 4.0),
        )
        values = hsse2._indicator_series(
            series, "TREND_MA_SMA", 2
        )
        self.assertTrue(math.isnan(values[0]))
        self.assertAlmostEqual(values[1], 1.5)
        self.assertTrue(math.isnan(values[2]))
        self.assertAlmostEqual(values[3], 3.5)

    def test_next_open_long_only_cell_completes_profitable_round_trip(self):
        times = tuple(i * hsse2.HOUR_MS for i in range(6))
        series = hsse2.SearchSeries(
            symbol="BTCUSDT",
            times=times,
            opens=(100.0, 101.0, 102.0, 103.0, 104.0, 105.0),
            closes=(100.0, 101.0, 102.0, 103.0, 104.0, 105.0),
        )
        short = hsse2.array("d", (1.0, 2.0, 3.0, 2.0, 1.0, 1.0))
        long = hsse2.array("d", (2.0, 1.0, 2.0, 2.0, 2.0, 2.0))
        result = hsse2._cell(
            series=series,
            short_values=short,
            long_values=long,
            start_ms=0,
            end_ms=6 * hsse2.HOUR_MS,
            quantity=0.001,
            initial=10000.0,
            base_fee=0.001,
            base_slippage=0.0005,
            stress_fee=0.002,
            stress_slippage=0.001,
        )
        self.assertEqual(result["completed_trades"], 1)
        self.assertEqual(result["wins"], 1)
        self.assertGreater(
            result["base"]["net_pnl_after_costs_quote"], 0.0
        )

    def test_runner_has_no_network_or_execution_authority(self):
        source = inspect.getsource(hsse2)
        for forbidden in (
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "urllib.request",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "API_KEY",
            "API_SECRET",
            "os.environ",
            "os.getenv",
            "RiskAuthorization",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
