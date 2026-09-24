import json
import unittest
from pathlib import Path


REGISTRY = Path(
    "docs/research/crisis-lab/SYNTHETIC-SHOCK-REGISTRY-v0.1.0.json"
)


class CrisisLabSyntheticShockRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_registry_is_research_only_and_p10_isolated(self):
        record = self.registry
        self.assertEqual(
            record["schema"], "YATL_CRL_SYNTHETIC_SHOCK_REGISTRY"
        )
        self.assertEqual(record["schema_version"], "0.1.0")
        self.assertEqual(
            record["status"],
            "PREREGISTERED_BEFORE_SYNTHETIC_OUTCOMES",
        )
        self.assertTrue(record["research_only"])
        self.assertFalse(record["p10_write_allowed"])
        self.assertTrue(record["p11_locked"])
        safety = record["safety"]
        self.assertTrue(safety["research_only"])
        self.assertFalse(safety["p10_read"])
        self.assertFalse(safety["p10_write_allowed"])
        self.assertEqual(safety["p10_evidence_effect"], "NONE")
        self.assertFalse(safety["trade_permission"])
        self.assertFalse(safety["order_endpoint"])
        self.assertFalse(safety["quantity_authority"])
        self.assertFalse(safety["risk_authorization_mutation"])
        self.assertFalse(safety["ai_direct_execution"])
        self.assertTrue(safety["p11_locked"])

    def test_source_state_is_confirmed_open_and_no_lookahead(self):
        source = self.registry["source_state"]
        self.assertEqual(
            source["source"],
            "CRL-005_STRATEGY_ACTIVE_SELECTED_EPISODE",
        )
        self.assertTrue(source["confirmed_open_position_required"])
        self.assertFalse(source["outcome_selected"])
        self.assertFalse(
            source["future_next_candle_used_to_construct_shock"]
        )
        self.assertEqual(
            source["shock_anchor_policy"],
            "ENTRY_CANDLE_CLOSE_AFTER_SAME_CANDLE_PROTECTIVE_PROCESSING",
        )
        for field in (
            "active_setup",
            "portfolio_after_entry",
            "entry_fill",
            "entry_candle",
            "source_state_confirmed_at_ms",
        ):
            self.assertIn(field, source["required_fields"])

    def test_initial_matrix_is_exact_cartesian_nine(self):
        matrix = self.registry["matrix"]
        self.assertEqual(matrix["adverse_gap_bps"], [500, 1000, 2000])
        self.assertEqual(matrix["slippage_multipliers"], [1, 2, 5])
        self.assertEqual(matrix["scenario_count"], 9)
        expected = {
            (gap, mult)
            for gap in (500, 1000, 2000)
            for mult in (1, 2, 5)
        }
        actual = {
            (
                item["adverse_gap_bps"],
                item["slippage_multiplier"],
            )
            for item in matrix["scenarios"]
        }
        self.assertEqual(actual, expected)
        ids = [item["scenario_id"] for item in matrix["scenarios"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 9)
        self.assertTrue(
            all(item["fee_multiplier"] == 1
                for item in matrix["scenarios"])
        )

    def test_immediate_shock_isolated_from_future_real_path(self):
        phase = self.registry["phase_006a_immediate_shock"]
        self.assertEqual(
            phase["decision_time_policy"],
            "NEXT_PRIMARY_DECISION_AFTER_ENTRY_CANDLE",
        )
        self.assertEqual(
            phase["strategy_snapshot_policy"],
            "SOURCE_CORPUS_ONLY_THROUGH_ENTRY_CANDLE",
        )
        self.assertFalse(phase["strategy_receives_scenario_label"])
        self.assertTrue(phase["active_setup_preserved"])
        self.assertEqual(
            phase["shock_bar_ohlc_policy"],
            "open=high=low=close=synthetic_open",
        )
        self.assertIn(
            "entry_candle.close",
            phase["synthetic_open_formula"],
        )
        self.assertEqual(
            phase["kill_switch_interpretation"],
            "DEFER_POST_SHOCK_OBSERVATION_TO_CRL-006B",
        )

    def test_synthetic_evidence_never_pools_with_historical_or_p10(self):
        policy = self.registry["evidence_policy"]
        self.assertEqual(policy["label"], "SYNTHETIC")
        self.assertFalse(policy["pool_with_historical_returns"])
        self.assertFalse(policy["pool_with_p10_forward_evidence"])
        self.assertTrue(policy["negative_results_retained"])
        self.assertTrue(
            policy["deterministic_two_run_equality_required"]
        )


if __name__ == "__main__":
    unittest.main()
