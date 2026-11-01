"""Offline tests for one-shot probe; never access Helius or external networks."""
import json
import tempfile
import unittest
from pathlib import Path

from research.smart_money_lab.history_gap_probe import (
    CappedHelius, MAX_REQUEST_ATTEMPTS, probe,
)


class FakeHelius:
    def __init__(self):
        self.calls = []

    def transactions(self, wallet, *, before="", limit=100):
        self.calls.append((wallet, before, limit))
        return [{"timestamp": 999, "signature": f"sig-{wallet}"}]


class HistoryGapProbeTests(unittest.TestCase):
    def test_anonymous_six_wallets_and_no_second_page(self):
        wallets = [f"PRIVATE_WALLET_{n}" for n in range(1, 7)]
        state = {
            "state_status": "halted_history_gap", "started_at": 1000,
            "wallets": wallets,
            "last_seen_chain": {w: 1100 for w in wallets},
        }
        h = FakeHelius()
        results = probe(state, h)
        self.assertEqual(len(results), 6)
        self.assertEqual(len(h.calls), 6)
        self.assertEqual(results[0]["wallet_index"], 1)
        self.assertEqual(results[0]["outcome"], "overlap_verified")
        encoded = json.dumps(results)
        self.assertNotIn("PRIVATE_WALLET_", encoded)
        self.assertNotIn("sig-PRIVATE", encoded)

    def test_rejects_non_halted_experiment(self):
        state = {"state_status": "running", "wallets": [f"wallet_{i}" for i in range(6)],
                 "last_seen_chain": {}, "started_at": 1000}
        with self.assertRaises(ValueError):
            probe(state, FakeHelius())

    def test_strict_global_request_attempt_cap(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "helius_budget.json"
            ledger.write_text(json.dumps({"calls": 10, "max_calls": 5000}))
            h = CappedHelius("fake_key_abcd", limit=2)
            h._budget_file = ledger
            h._reserve_request()
            h._reserve_request()
            with self.assertRaisesRegex(RuntimeError, "PROBE_ATTEMPT_CAP_REACHED"):
                h._reserve_request()
            self.assertEqual(h.request_attempts, 2)
            self.assertEqual(json.loads(ledger.read_text())["calls"], 12)

    def test_maximum_probe_attempts_bounded(self):
        self.assertEqual(MAX_REQUEST_ATTEMPTS, 18)


if __name__ == "__main__":
    unittest.main()
