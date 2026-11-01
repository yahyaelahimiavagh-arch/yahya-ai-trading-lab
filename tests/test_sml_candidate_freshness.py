"""No-network unit tests for candidate status snapshots, not trading skill."""
from __future__ import annotations
import unittest

from research.smart_money_lab.candidate_freshness_scan import assess
from research.smart_money_lab.recent_wallet_receipts import JUNE_END, PublicRpcError, WALLETS

A = WALLETS["behavior_group_1"]
B = WALLETS["behavior_group_2"]
C = WALLETS["behavior_group_3"]


class MockRpc:
    def __init__(self, histories, *, fail_wallet=None):
        self.histories = histories
        self.fail_wallet = fail_wallet
        self.requests = 0

    def signatures(self, wallet):
        self.requests += 1
        if wallet == self.fail_wallet:
            raise PublicRpcError("http_429")
        return self.histories.get(wallet, [])


def input_rows():
    return {"source": "frozen June 2026",
            "candidates": [{"rank": 1, "group": 1, "address": A},
                           {"rank": 10, "group": 2, "address": B},
                           {"rank": 20, "group": 3, "address": C}]}


class StatusTests(unittest.TestCase):
    def test_recent_activity_and_no_trade_claim(self):
        now = JUNE_END + 120*86400
        rpc = MockRpc({
            A: [{"blockTime": now-5*86400}],
            B: [{"blockTime": now-20*86400}],
            C: [{"blockTime": JUNE_END-100}],
        })
        result = assess(input_rows(), rpc, now=now)
        self.assertEqual(result["rpc_requests"], 3)
        self.assertEqual(result["status_counts"]["tx_within_7d_not_necessarily_trade"], 1)
        self.assertEqual(result["status_counts"]["tx_within_30d_not_necessarily_trade"], 1)
        self.assertEqual(result["status_counts"]["latest_observed_before_july"], 1)
        self.assertEqual(result["latest_7d_activity_only"][0]["wallet"], A)
        self.assertIsNone(result["realized_pnl"])
        self.assertEqual(result["helius_requests"], 0)

    def test_rpc_429_stops_remaining_wallets(self):
        rpc = MockRpc({A:[{"blockTime": JUNE_END+100}]}, fail_wallet=B)
        result = assess(input_rows(), rpc, now=JUNE_END+100*86400)
        self.assertEqual(result["rpc_error"], "http_429")
        self.assertEqual(result["rpc_requests"], 2)
        self.assertEqual(result["status_counts"]["not_checked_rpc_unavailable"], 1)
        self.assertEqual(result["status_counts"]["rpc_unavailable"], 1)

    def test_no_timestamps_is_not_marked_dead_or_unprofitable(self):
        rpc = MockRpc({})
        result = assess(input_rows(), rpc, now=JUNE_END+100*86400)
        self.assertEqual(result["status_counts"]["no_timestamped_transaction_in_latest_12"], 3)

    def test_invalid_candidates_rejected(self):
        with self.assertRaises(ValueError):
            assess({"candidates": [{"rank": 1, "group": 1, "address": "not-key"}]},
                   MockRpc({}), now=JUNE_END+100)
        with self.assertRaises(ValueError):
            assess({"candidates": [input_rows()["candidates"][0]] * 2},
                   MockRpc({}), now=JUNE_END+100)
        with self.assertRaises(ValueError):
            assess({"candidates": []}, MockRpc({}), now=JUNE_END+100)


if __name__ == "__main__":
    unittest.main()
