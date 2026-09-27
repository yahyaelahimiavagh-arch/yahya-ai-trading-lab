import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"docs"/"research"/"generation-2"
MASTER=BASE/"GEN2-MASTER-PROTOCOL-v0.1.0.json"
STOP=BASE/"GEN2-001-STOP-OVERLAY-PROTOCOL-v0.1.0.json"
VOL=BASE/"GEN2-002-VOL-SCALING-PROTOCOL-v0.1.0.json"

class Gen2ProtocolsTests(unittest.TestCase):
    def test_master_has_two_terminal_states_and_sealed_oos(self):
        r=json.loads(MASTER.read_text(encoding="utf-8"))
        self.assertEqual(set(r["completion_states"]),{"GEN2_FORWARD_CANDIDATE","GEN2_NO_ROBUST_EDGE_FOUND"})
        self.assertEqual(r["evidence_map"]["fresh_oos"]["status"],"SEALED_UNTIL_GEN2_SURVIVOR_FREEZE")
        self.assertEqual(r["evidence_map"]["recent_reserve"]["status"],"SEALED")
        self.assertTrue(r["p10_independent"])
        self.assertTrue(r["p11_locked"])

    def test_stop_protocol_has_exact_bounded_matrix(self):
        r=json.loads(STOP.read_text(encoding="utf-8"))
        self.assertEqual(r["trial_matrix"]["stop_thresholds_percent"],[10,20,30,40,50])
        self.assertEqual(r["trial_matrix"]["reference_strategy_count"],6)
        self.assertEqual(r["trial_matrix"]["conditions_per_strategy"],6)
        self.assertEqual(r["trial_matrix"]["total_conditions"],36)
        self.assertTrue(r["trial_matrix"]["hidden_trials_forbidden"])

    def test_stop_search_cannot_read_known_blind_or_fresh_oos(self):
        r=json.loads(STOP.read_text(encoding="utf-8"))
        scope=r["development_scope"]
        self.assertFalse(scope["hsse_004b_2023_2024_read_allowed"])
        self.assertFalse(scope["hsse_005_outcomes_used_for_selection"])
        self.assertFalse(scope["fresh_oos_read_allowed"])
        self.assertFalse(scope["recent_reserve_read_allowed"])

    def test_stop_semantics_are_long_only_next_open_and_no_tuning(self):
        r=json.loads(STOP.read_text(encoding="utf-8"))
        self.assertEqual(r["execution"]["mode"],"LONG_ONLY_SPOT_RESEARCH")
        self.assertIn("next contiguous 1h open",r["execution"]["stop_fill"])
        self.assertTrue(r["no_rerank_after_outcomes"])
        self.assertTrue(r["no_retune_after_outcomes"])
        self.assertFalse(r["p10_write_allowed"])
        self.assertTrue(r["p11_locked"])

    def test_vol_scaler_has_one_exact_no_leverage_trial_per_reference(self):
        r=json.loads(VOL.read_text(encoding="utf-8"))
        self.assertEqual(r["source_candidate_id"],"RIE-CAND-0025")
        self.assertEqual(r["tested_object_type"],"YATL_INTERNAL_ADAPTATION")
        self.assertEqual(r["source_basis"]["source_risk_window_trading_days"],126)
        self.assertEqual(r["scaling_rule"]["target_annualized_volatility"],"0.12")
        self.assertEqual(r["volatility_estimator"]["window_completed_utc_days"],183)
        self.assertEqual(r["volatility_estimator"]["annualization_days"],365)
        self.assertEqual(r["scaling_rule"]["scale_cap"],"1.0")
        self.assertTrue(r["scaling_rule"]["leverage_forbidden"])
        self.assertTrue(r["scaling_rule"]["short_forbidden"])
        self.assertEqual(r["trial_matrix"]["reference_strategy_count"],6)
        self.assertEqual(r["trial_matrix"]["conditions_per_strategy"],2)
        self.assertEqual(r["trial_matrix"]["total_conditions"],12)
        self.assertEqual(r["generation_budget"]["primary_hypothesis_ordinal"],2)
        self.assertEqual(r["generation_budget"]["primary_hypotheses_max"],8)
        self.assertFalse(r["generation_budget"]["combination_architecture"])
        self.assertTrue(r["trial_matrix"]["hidden_trials_forbidden"])
        self.assertTrue(r["trial_matrix"]["post_outcome_trial_budget_expansion_forbidden"])

    def test_vol_scaler_is_point_in_time_and_preserves_seals(self):
        r=json.loads(VOL.read_text(encoding="utf-8"))
        scope=r["development_scope"]
        self.assertEqual(scope["estimator_warmup_start_utc"],"2020-01-01T00:00:00Z")
        self.assertEqual(scope["scored_analysis_start_utc"],"2020-08-01T00:00:00Z")
        self.assertEqual(scope["analysis_end_exclusive_utc"],"2023-01-01T00:00:00Z")
        self.assertIn("ending before that boundary",r["volatility_estimator"]["decision_lag"])
        self.assertFalse(scope["hsse_004b_2023_2024_read_allowed"])
        self.assertFalse(scope["hsse_005_outcomes_used_for_selection"])
        self.assertFalse(scope["fresh_oos_read_allowed"])
        self.assertFalse(scope["recent_reserve_read_allowed"])
        self.assertFalse(r["p10_read"])
        self.assertFalse(r["p10_write_allowed"])
        self.assertTrue(r["p11_locked"])
        self.assertFalse(r["safety_boundary"]["futures"])
        self.assertFalse(r["safety_boundary"]["short"])
        self.assertFalse(r["safety_boundary"]["leverage"])
        self.assertFalse(r["safety_boundary"]["live_execution"])
        self.assertFalse(r["safety_boundary"]["order_endpoint"])
        self.assertFalse(r["safety_boundary"]["ai_direct_execution"])

    def test_vol_scaler_preserves_opportunity_and_forbids_rescue_tuning(self):
        r=json.loads(VOL.read_text(encoding="utf-8"))
        o=r["opportunity_preservation"]
        self.assertTrue(o["directional_entry_signal_count_must_equal_control"])
        self.assertTrue(o["completed_directional_trade_count_must_equal_control"])
        self.assertEqual(o["active_exposure_hours_fraction_vs_control_minimum"],"1.0")
        self.assertEqual(o["notional_exposure_ratio_vs_control_minimum"],"0.25")
        self.assertTrue(r["scaling_rule"]["alternate_targets_forbidden"])
        self.assertTrue(r["scaling_rule"]["alternate_windows_forbidden"])
        self.assertTrue(r["scaling_rule"]["ewma_variants_forbidden"])
        self.assertTrue(r["no_rerank_after_outcomes"])
        self.assertTrue(r["no_retune_after_outcomes"])
        self.assertEqual(r["implementation_gate"]["status_at_registration"],"PENDING_IMPLEMENTATION")
        self.assertTrue(r["implementation_gate"]["protocol_mutation_to_unlock_run_forbidden"])

if __name__=="__main__":
    unittest.main()
