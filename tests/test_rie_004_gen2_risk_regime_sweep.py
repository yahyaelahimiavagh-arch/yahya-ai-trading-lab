import json
import unittest
from pathlib import Path

from research.research_intake import registry as rie

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "research" / "research-intake" / "CANDIDATE-REGISTRY-v0.1.0.json"
SWEEP = ROOT / "docs" / "research" / "research-intake" / "RIE-004-GEN2-RISK-REGIME-SWEEP.md"

class RIE004Gen2SweepTests(unittest.TestCase):
    def test_gen2_registry_append_is_bounded_and_not_promoted(self):
        result = rie.validate_registry(REGISTRY)
        self.assertEqual(result["candidate_count"], 31)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(result["unique_hypothesis_count"], 31)
        self.assertEqual(result["status_counts"]["NEW"], 30)
        self.assertEqual(result["status_counts"]["READY_FOR_TRAIN_SEARCH"], 1)
        self.assertEqual(result["strategy_evidence_effect"], "NONE")
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertFalse(result["p10_write_allowed"])
        self.assertTrue(result["p11_locked"])

    def test_gen2_ids_are_exact_and_all_new(self):
        record=json.loads(REGISTRY.read_text(encoding="utf-8"))
        rows={x["candidate_id"]:x for x in record["candidates"]}
        expected={f"RIE-CAND-{i:04d}" for i in range(25,32)}
        self.assertTrue(expected.issubset(rows))
        self.assertTrue(all(rows[x]["status"]=="NEW" for x in expected))

    def test_sweep_preserves_holdout_boundary(self):
        text=SWEEP.read_text(encoding="utf-8")
        self.assertIn("2025-2026 Audit Holdout",text)
        self.assertIn("remain sealed",text)
        self.assertIn("No retuning of the failed Generation-1 six",text)
        self.assertIn("No combinations",text)

if __name__ == "__main__":
    unittest.main()
