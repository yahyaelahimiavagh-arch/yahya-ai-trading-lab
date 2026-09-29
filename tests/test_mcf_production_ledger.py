import unittest

from research.mass_candidate_factory.models import digest
from research.mass_candidate_factory.production_ledger import SAFETY, make_record, reconcile


def candidate(ordinal, cid, state="PRE_OUTCOME_REGISTERED"):
    return {
        "ordinal": ordinal,
        "candidate_id": cid,
        "candidate_spec_sha256": (str(ordinal + 1) * 64)[:64],
        "family": "FAM",
        "family_id": "FAM-ID",
        "state": state,
        "failure_reasons": ("STRUCTURAL_CONSTRAINT",) if state == "STRUCTURALLY_INVALID" else (),
    }


def canonical_result(c):
    body = {
        "candidate_id": c["candidate_id"],
        "candidate_spec_sha256": c["candidate_spec_sha256"],
        "evidence_partition": "DEVELOPMENT",
        "f0_f3_state": "DEVELOPMENT_FAIL",
        "failure_reasons": ("F1_COMPLETED_TRADES_LT_250",),
        "daily_return_series": {"calendar_days": (1, 2), "returns": ("0", "0"), "valid_mask": (True, True)},
        "per_symbol_daily_return_series": (),
        "safety": dict(SAFETY),
    }
    return {**body, "result_sha256": digest(body)}


class ProductionLedgerTest(unittest.TestCase):
    def test_complete_batch_requires_all_preoutcome_identities(self):
        structural = candidate(0, "C0", "STRUCTURALLY_INVALID")
        blocked = candidate(1, "C1")
        executable = candidate(2, "C2")
        raw = (structural, blocked, executable)
        freeze = {
            "registered_candidates": ((executable["candidate_id"], executable["candidate_spec_sha256"]),),
            "blocked": (blocked,),
        }
        records = (
            make_record(structural, state="STRUCTURALLY_INVALID"),
            make_record(blocked, state="BLOCKED_IMPLEMENTATION", blocker_reason="frozen rule underspecified"),
            make_record(executable, state="DEVELOPMENT_FAIL", result=canonical_result(executable)),
        )
        outcome = reconcile(raw, freeze, records)
        self.assertEqual(outcome["status"], "BATCH_COMPLETE")
        self.assertEqual(outcome["raw_candidate_count"], 3)
        self.assertEqual(outcome["state_counts"]["STRUCTURALLY_INVALID"], 1)
        self.assertEqual(outcome["state_counts"]["BLOCKED_IMPLEMENTATION"], 1)
        self.assertEqual(outcome["state_counts"]["DEVELOPMENT_FAIL"], 1)

    def test_missing_candidate_invalidates_batch(self):
        structural = candidate(0, "C0", "STRUCTURALLY_INVALID")
        executable = candidate(1, "C1")
        freeze = {
            "registered_candidates": ((executable["candidate_id"], executable["candidate_spec_sha256"]),),
            "blocked": (),
        }
        records = (make_record(structural, state="STRUCTURALLY_INVALID"),)
        outcome = reconcile((structural, executable), freeze, records)
        self.assertEqual(outcome["status"], "BATCH_INVALID")
        self.assertIn("incomplete", outcome["reason"])


if __name__ == "__main__":
    unittest.main()
