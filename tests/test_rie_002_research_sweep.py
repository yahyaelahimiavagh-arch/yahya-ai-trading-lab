import unittest
from pathlib import Path

from research.research_intake import registry as rie


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "docs"
    / "research"
    / "research-intake"
    / "CANDIDATE-REGISTRY-v0.1.0.json"
)


class RIE002ResearchSweepTests(unittest.TestCase):
    def test_first_sweep_is_bounded_diverse_and_not_promoted(self):
        result = rie.validate_registry(REGISTRY)
        self.assertGreaterEqual(result["candidate_count"], 20)
        self.assertLessEqual(result["candidate_count"], 50)
        self.assertEqual(result["candidate_count"], 24)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(result["unique_hypothesis_count"], 24)
        self.assertEqual(result["status_counts"]["NEW"], 24)
        self.assertGreaterEqual(result["source_tier_counts"]["A"], 1)
        self.assertGreaterEqual(result["source_tier_counts"]["C"], 1)
        self.assertEqual(result["strategy_evidence_effect"], "NONE")
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertFalse(result["p10_write_allowed"])
        self.assertTrue(result["p11_locked"])


if __name__ == "__main__":
    unittest.main()
