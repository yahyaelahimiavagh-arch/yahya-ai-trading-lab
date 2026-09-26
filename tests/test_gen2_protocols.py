import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"docs"/"research"/"generation-2"
MASTER=BASE/"GEN2-MASTER-PROTOCOL-v0.1.0.json"
STOP=BASE/"GEN2-001-STOP-OVERLAY-PROTOCOL-v0.1.0.json"

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

if __name__=="__main__":
    unittest.main()
