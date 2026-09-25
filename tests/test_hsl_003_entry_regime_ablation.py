import inspect
import unittest
from pathlib import Path

from research.historical_strategy_lab import entry_regime_ablation as hsl3


def summary(
    experiment_id,
    *,
    net="20",
    expectancy="1",
    trades=40,
    drawdown="0.05",
    qualified=True,
):
    return {
        "experiment_id": experiment_id,
        "completed_trades": trades,
        "total_net_pnl_after_costs_quote": net,
        "expectancy_quote": expectancy,
        "profit_factor": "1.2",
        "profit_factor_infinite": False,
        "maximum_drawdown_fraction": drawdown,
        "entry_signal_count": 50,
        "qualification": {
            "status": (
                "QUALIFIED_HSL_RESEARCH"
                if qualified
                else "NOT_QUALIFIED_HSL_RESEARCH"
            ),
            "failure_reasons": (
                [] if qualified else ["SYNTHETIC_FAILURE"]
            ),
        },
    }


class HSL003EntryRegimeAblationTests(unittest.TestCase):
    def test_protocol_is_single_filter_preregistered(self):
        protocol, digest = hsl3.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["paper_only"])
        self.assertTrue(protocol["p4_p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(protocol["trade_permission"])
        self.assertEqual(protocol["live_master_lock"], "OFF")

        experiments = protocol["experiments"]
        self.assertEqual(len(experiments), 7)
        for experiment in experiments:
            self.assertLessEqual(
                len(experiment["entry_changes"]), 1
            )
        self.assertFalse(
            protocol["methodology"]["parameter_search"]
        )
        self.assertFalse(
            protocol["methodology"]["post_hoc_combination"]
        )
        self.assertFalse(
            protocol["methodology"]["p4_risk_veto_applied"]
        )
        self.assertTrue(
            protocol["methodology"]["exit_logic_frozen"]
        )
        self.assertTrue(
            protocol["methodology"][
                "protective_level_logic_frozen"
            ]
        )

    def test_trend_has_no_invented_volatility_ablation(self):
        protocol, _ = hsl3.load_protocol()
        trend = [
            item
            for item in protocol["experiments"]
            if item["strategy_id"] == "TREND_PULLBACK"
        ]
        self.assertEqual(len(trend), 3)
        self.assertFalse(
            any(
                hsl3.REMOVE_VOLATILITY_EXTENSION
                in item["entry_changes"]
                for item in trend
            )
        )
        self.assertTrue(
            protocol["non_experiments"][
                "trend_volatility_filter_ablation"
            ].startswith("NOT_APPLICABLE")
        )

    def test_breakout_volatility_ablation_is_single_gate_only(self):
        protocol, _ = hsl3.load_protocol()
        item = next(
            experiment
            for experiment in protocol["experiments"]
            if experiment["experiment_id"]
            == "HSL003-BREAKOUT-NO-VOLATILITY-EXTENSION"
        )
        self.assertEqual(
            item["entry_changes"],
            [hsl3.REMOVE_VOLATILITY_EXTENSION],
        )

    def test_beneficial_ablation_only_supports_future_challenger(self):
        protocol, _ = hsl3.load_protocol()
        experiment = next(
            item
            for item in protocol["experiments"]
            if item["experiment_id"]
            == "HSL003-TREND-NO-CONFIRMATION"
        )
        control = summary(
            "HSL003-TREND-CONTROL",
            net="10",
            expectancy="0.5",
        )
        ablation = summary(
            experiment["experiment_id"],
            net="20",
            expectancy="0.8",
        )
        result = hsl3._comparison(
            experiment=experiment,
            summary=ablation,
            control=control,
            gate=protocol["comparison_gate"],
        )
        self.assertEqual(
            result["status"],
            "ABLATION_SUPPORTS_FUTURE_CHALLENGER",
        )
        self.assertFalse(
            result["automatic_strategy_mutation"]
        )
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertTrue(result["p11_locked"])
        self.assertFalse(result["live_authorized"])

    def test_ablation_that_does_not_beat_control_fails_closed(self):
        protocol, _ = hsl3.load_protocol()
        experiment = next(
            item
            for item in protocol["experiments"]
            if item["experiment_id"]
            == "HSL003-BREAKOUT-NO-REGIME-ENTRY"
        )
        control = summary(
            "HSL003-BREAKOUT-CONTROL",
            net="20",
            expectancy="1",
        )
        ablation = summary(
            experiment["experiment_id"],
            net="15",
            expectancy="0.8",
        )
        result = hsl3._comparison(
            experiment=experiment,
            summary=ablation,
            control=control,
            gate=protocol["comparison_gate"],
        )
        self.assertEqual(
            result["status"],
            "ABLATION_NOT_SUPPORTED",
        )
        self.assertIn(
            "NET_PNL_DID_NOT_BEAT_CONTROL",
            result["failure_reasons"],
        )
        self.assertIn(
            "EXPECTANCY_BELOW_CONTROL",
            result["failure_reasons"],
        )

    def test_p10_runtime_is_protected(self):
        with self.assertRaises(hsl3.HSLAblationError):
            hsl3.run_entry_regime_ablation(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_credentials_risk_veto_or_orders(self):
        source = inspect.getsource(hsl3)
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
