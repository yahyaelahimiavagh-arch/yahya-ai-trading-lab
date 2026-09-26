import json
import tempfile
import unittest
from pathlib import Path

from research.research_intake import reproduction as rp


ROOT = Path(__file__).resolve().parents[1]
PACKET = (
    ROOT
    / "docs"
    / "research"
    / "research-intake"
    / "reproduction-packets"
    / "RIE-CAND-0020-v0.1.0.json"
)


class RIE003ReproductionPacketTests(unittest.TestCase):
    def test_bound_packet_is_valid_but_not_prematurely_promoted(self):
        result = rp.validate_packet(PACKET)
        self.assertEqual(result["candidate_id"], "RIE-CAND-0020")
        self.assertEqual(result["source_freeze_status"], "PENDING_BYTES")
        self.assertEqual(
            result["implementation_commit_sha"],
            "d2e66e405183349f52556a18d387bb1dfc900db5",
        )
        self.assertEqual(result["implementation_file_count"], 4)
        self.assertEqual(result["candidate_status"], "NEW")
        self.assertFalse(result["ready_for_train_search"])
        self.assertFalse(result["p10_write_allowed"])
        self.assertEqual(result["strategy_evidence_effect"], "NONE")
        self.assertTrue(result["p11_locked"])

    def test_pending_source_bytes_cannot_claim_ready_status(self):
        record = json.loads(PACKET.read_text(encoding="utf-8"))
        record["readiness"]["ready_for_train_search"] = True
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "packet.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(rp.ReproductionPacketError):
                rp.validate_packet(path)

    def test_pending_source_bytes_cannot_claim_sha(self):
        record = json.loads(PACKET.read_text(encoding="utf-8"))
        record["source_binding"]["content_sha256"] = "a" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "packet.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(rp.ReproductionPacketError):
                rp.validate_packet(path)

    def test_oos_cannot_be_used_for_train_selection(self):
        record = json.loads(PACKET.read_text(encoding="utf-8"))
        record["train_search"]["oos_used_for_selection"] = True
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "packet.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(rp.ReproductionPacketError):
                rp.validate_packet(path)


if __name__ == "__main__":
    unittest.main()
