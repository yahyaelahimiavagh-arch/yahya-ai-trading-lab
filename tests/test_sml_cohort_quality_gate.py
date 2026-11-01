"""Offline no-network checks for frozen six-wallet quality gate."""
import copy
import json
import unittest

from research.smart_money_lab.cohort_quality_gate import (
    WATCH, EVIDENCE, audit, git_blob_sha1,
)


class CohortQualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = WATCH.read_bytes()
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_frozen_watchlist_identity_matches(self):
        self.assertEqual(git_blob_sha1(self.raw),
                         self.evidence["watchlist_git_blob_sha1"])

    def test_all_six_unqualified_and_no_source_addresses_exported(self):
        outcome = audit(self.raw, self.evidence)
        self.assertEqual(outcome["wallet_count"], 6)
        self.assertEqual(outcome["qualified_wallet_count"], 0)
        self.assertEqual(outcome["new_helius_requests"], 0)
        self.assertEqual(outcome["new_orders"], 0)
        self.assertEqual(outcome["decision"],
                         "NO_GO_NEW_PAPER_COHORT_OR_LIVE_TRADING")
        self.assertEqual(len(outcome["wallets"]), 6)
        text = json.dumps(outcome)
        frozen = json.loads(self.raw)
        for w in frozen["wallets"]:
            self.assertNotIn(w["wallet"], text)

    def test_known_history_failures_are_never_marked_qualified(self):
        rows = audit(self.raw, self.evidence)["wallets"]
        self.assertEqual(rows[0]["recent_probe_outcome"], "page_cap")
        self.assertEqual(rows[1]["recent_probe_outcome"], "repeated_signature")
        self.assertEqual(rows[2]["collector_category"], "BORDERLINE_COLLECTION")
        for row in rows:
            self.assertIs(row["candidate_for_live_copy"], False)
            self.assertIs(row["candidate_for_new_six_hour_paper"], False)

    def test_modified_watchlist_refused(self):
        raw = self.raw + b" "
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            audit(raw, self.evidence)

    def test_missing_or_reordered_evidence_refused(self):
        doc = copy.deepcopy(self.evidence)
        doc["wallets"][0]["index"] = 6
        with self.assertRaisesRegex(ValueError, "six fixed"):
            audit(self.raw, doc)

    def test_evidence_cannot_grant_real_trading_authorization(self):
        doc = copy.deepcopy(self.evidence)
        doc["authorize_live_trading"] = True
        with self.assertRaisesRegex(ValueError, "disallow live trading"):
            audit(self.raw, doc)

    def test_invalid_sample_count_refused(self):
        doc = copy.deepcopy(self.evidence)
        doc["wallets"][3]["sampled_fifo_fragments"] = -1
        with self.assertRaisesRegex(ValueError, "invalid wallet evidence"):
            audit(self.raw, doc)


if __name__ == "__main__":
    unittest.main()
