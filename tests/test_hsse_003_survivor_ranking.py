import inspect
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from research.historical_strategy_search import survivor_ranking as hsse3


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = (
    ROOT
    / "docs"
    / "research"
    / "historical-strategy-search"
    / "HSSE-003-SURVIVOR-RANKING-PROTOCOL-v0.1.0.json"
)


class HSSE003SurvivorRankingTests(unittest.TestCase):
    def test_protocol_freezes_search_artifacts_before_ranking(self):
        protocol, digest = hsse3.validate_protocol(PROTOCOL)
        self.assertEqual(
            protocol["input_search"]["total_trial_count"], 14850
        )
        self.assertEqual(
            protocol["exact_recompute"]["expected_candidate_count"], 16
        )
        self.assertEqual(
            [x["development_precheck_pass_count"]
             for x in protocol["input_search"]["ledgers"]],
            [1, 8, 7],
        )
        self.assertEqual(len(digest), 64)

    def test_neighbor_contract_is_axial_and_requires_plateau(self):
        protocol, _ = hsse3.validate_protocol(PROTOCOL)
        neighbor = protocol["neighbor_robustness"]
        self.assertEqual(
            neighbor["offsets"],
            [[-10, 0], [10, 0], [0, -10], [0, 10]],
        )
        self.assertEqual(neighbor["minimum_valid_neighbors"], 2)
        self.assertEqual(
            neighbor["minimum_neighbor_pass_fraction"], "0.50"
        )

    def test_pareto_dominance_requires_all_dimensions(self):
        base = {
            "base": {
                "median_development_cell_net_return_after_costs": "0.01",
                "lower_quartile_development_cell_net_return_after_costs": "0.001",
                "profit_factor": "1.2",
                "profit_factor_infinite": False,
                "maximum_drawdown_fraction": "0.02",
                "largest_trade_profit_share": "0.2",
            },
            "stress": {"total_net_pnl_after_costs_quote": "1"},
            "neighbor_robustness": {"neighbor_pass_fraction": "0.75"},
            "family": "TREND_MA_SMA",
            "parameters": {"n1": 1, "n2": 11},
            "trial_id": "A",
        }
        better = json.loads(json.dumps(base))
        better["trial_id"] = "B"
        better["base"][
            "median_development_cell_net_return_after_costs"
        ] = "0.02"
        self.assertTrue(hsse3._dominates(better, base))
        worse_dd = json.loads(json.dumps(better))
        worse_dd["trial_id"] = "C"
        worse_dd["base"]["maximum_drawdown_fraction"] = "0.03"
        self.assertFalse(hsse3._dominates(worse_dd, base))

    def test_decimal_account_uses_adverse_costs(self):
        account = hsse3._new_account(Decimal("10000"))
        hsse3._entry(
            account,
            reference=Decimal("100"),
            quantity=Decimal("0.001"),
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )
        self.assertLess(account.cash, Decimal("10000"))
        hsse3._exit(
            account,
            reference=Decimal("110"),
            quantity=Decimal("0.001"),
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )
        self.assertEqual(len(account.realized), 1)
        self.assertGreater(account.realized[0], Decimal("0"))

    def test_protocol_rejects_holdout_read_permission(self):
        protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        protocol["output"]["blind_oos_read"] = True
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaises(hsse3.HSSESurvivorError):
                hsse3.validate_protocol(path)

    def test_runner_has_no_network_or_execution_authority(self):
        source = inspect.getsource(hsse3)
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
