import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"docs"/"research"/"research-intake"/"gen2-method-extractions"

class RIE005Gen2MethodExtractionTests(unittest.TestCase):
    def load(self,cid):
        return json.loads((BASE/f"{cid}-v0.1.0.json").read_text(encoding="utf-8"))

    def test_blocked_candidates_cannot_run(self):
        for cid in ("RIE-CAND-0011","RIE-CAND-0022","RIE-CAND-0027"):
            r=self.load(cid)
            self.assertTrue(r["status"].startswith("NOT_READY"))
            self.assertFalse(r["performance_run_allowed"])
            self.assertTrue(r["blockers"])

    def test_stop_overlay_is_method_ready_but_not_runnable(self):
        r=self.load("RIE-CAND-0030")
        self.assertEqual(r["status"],"METHOD_READY_PROTOCOL_NOT_FROZEN")
        self.assertEqual(r["extracted_method"]["source_primary_threshold_percent"],30)
        self.assertEqual(r["extracted_method"]["robustness_thresholds_percent"],[10,20,30,40,50])
        self.assertFalse(r["performance_run_allowed"])
        self.assertTrue(r["yatl_adaptation_draft"]["no_short"])
        self.assertTrue(r["yatl_adaptation_draft"]["no_leverage"])

    def test_all_extractions_preserve_safety(self):
        for path in BASE.glob("RIE-CAND-*.json"):
            r=json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(r["research_only"])
            self.assertFalse(r["p10_read"])
            self.assertFalse(r["p10_write_allowed"])
            self.assertTrue(r["p11_locked"])

if __name__=="__main__":
    unittest.main()
