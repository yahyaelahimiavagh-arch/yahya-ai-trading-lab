import json
import copy
import unittest
from pathlib import Path

from research.research_intake import registry as rie

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "research" / "research-intake" / "CANDIDATE-REGISTRY-GEN2-v0.1.0.json"
SWEEP = ROOT / "docs" / "research" / "research-intake" / "RIE-004-GEN2-RISK-REGIME-SWEEP.md"
HISTORICAL_REGISTRY = ROOT / "docs" / "research" / "research-intake" / "CANDIDATE-REGISTRY-v0.1.0.json"

class RIE004Gen2SweepTests(unittest.TestCase):
    def test_gen2_registry_append_is_bounded_and_not_promoted(self):
        result = rie.validate_registry(REGISTRY)
        self.assertEqual(result["candidate_count"], 31)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(result["unique_hypothesis_count"], 31)
        self.assertEqual(result["status_counts"]["NEW"], 27)
        self.assertEqual(result["status_counts"]["READY_FOR_TRAIN_SEARCH"], 1)
        self.assertEqual(result["status_counts"]["BLOCKED_REPRODUCIBILITY"], 1)
        self.assertEqual(result["status_counts"]["BLOCKED_SOURCE"], 1)
        self.assertEqual(result["status_counts"]["PREREGISTERED"], 1)
        self.assertEqual(result["reproduction_packet_count"], 1)
        self.assertEqual(result["strategy_evidence_effect"], "NONE")
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertFalse(result["p10_write_allowed"])
        self.assertTrue(result["p11_locked"])

    def test_gen2_ids_have_exact_post_af03a_states(self):
        record=json.loads(REGISTRY.read_text(encoding="utf-8"))
        rows={x["candidate_id"]:x for x in record["candidates"]}
        self.assertEqual(set(rows), {f"RIE-CAND-{i:04d}" for i in range(1,32)})
        expected={f"RIE-CAND-{i:04d}":"NEW" for i in range(1,32)}
        expected.update({
            "RIE-CAND-0011":"BLOCKED_REPRODUCIBILITY",
            "RIE-CAND-0020":"READY_FOR_TRAIN_SEARCH",
            "RIE-CAND-0022":"BLOCKED_SOURCE",
            "RIE-CAND-0027":"PREREGISTERED",
        })
        self.assertEqual({cid:row["status"] for cid,row in rows.items()},expected)
        self.assertEqual(rows["RIE-CAND-0027"]["reproduction_packet"]["state"],"METHOD_SPECIFIED")
        self.assertIs(rows["RIE-CAND-0027"]["reproduction_packet"]["performance_authorized"],False)
        self.assertIs(rows["RIE-CAND-0027"]["reproduction_packet"]["protocol"]["implementation_required"],True)

    def test_historical_registry_remains_24_candidate_snapshot(self):
        result = rie.validate_registry(HISTORICAL_REGISTRY)
        self.assertEqual(result["candidate_count"], 24)
        self.assertEqual(result["unique_hypothesis_count"], 24)

    def test_af03a_packets_reject_unsafe_or_unrecognized_transitions(self):
        rows={x["candidate_id"]:x for x in json.loads(REGISTRY.read_text(encoding="utf-8"))["candidates"]}
        mutations=(
            ("RIE-CAND-0011",lambda x:x["reproduction_packet"].update(missing_details=[])),
            ("RIE-CAND-0022",lambda x:x["reproduction_packet"].update(closeout_ref="../unsafe.md")),
            ("RIE-CAND-0027",lambda x:x["reproduction_packet"].update(performance_authorized=True)),
            ("RIE-CAND-0027",lambda x:x["reproduction_packet"]["protocol"].update(implementation_required=False)),
            ("RIE-CAND-0027",lambda x:x["reproduction_packet"]["protocol"].update(relative_path="../unsafe.json")),
            ("RIE-CAND-0027",lambda x:x["reproduction_packet"].update(unrecognized_field="bypass")),
            ("RIE-CAND-0027",lambda x:x.update(reproduction_packet=None)),
            ("RIE-CAND-0028",lambda x:x.update(status="PREREGISTERED")),
        )
        for cid,mutate in mutations:
            with self.subTest(candidate=cid,mutation=mutate):
                item=copy.deepcopy(rows[cid])
                mutate(item)
                with self.assertRaises(rie.ResearchIntakeError):
                    rie._validate_candidate(item)

    def test_sweep_preserves_holdout_boundary(self):
        text=SWEEP.read_text(encoding="utf-8")
        self.assertIn("2025-2026 Audit Holdout",text)
        self.assertIn("remain sealed",text)
        self.assertIn("No retuning of the failed Generation-1 six",text)
        self.assertIn("No combinations",text)

if __name__ == "__main__":
    unittest.main()
