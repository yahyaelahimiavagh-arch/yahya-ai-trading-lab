"""Offline transaction-fingerprint regression cases; absolutely no RPC."""
from __future__ import annotations
import unittest

from research.smart_money_lab.group_chain_fingerprints import (
    fingerprint, audit, MAX_WALLETS,
)
from research.smart_money_lab.recent_wallet_receipts import (
    WALLETS, JUNE_END,
)

A = WALLETS["behavior_group_1"]
B = WALLETS["behavior_group_2"]
SIG = "1" * 87


def fake_tx(*, owner=A, signer=True, payer=A):
    keys = [
        {"pubkey": payer, "signer": True, "writable": True},
        {"pubkey": owner, "signer": signer, "writable": True},
    ] if payer != owner else [
        {"pubkey": owner, "signer": signer, "writable": True}
    ]
    n = len(keys)
    pre = [10_000_000] * n
    post = [10_000_000] * n
    post[-1] = 9_995_000
    return {
        "slot": 111, "blockTime": JUNE_END + 5,
        "transaction": {"message": {
            "accountKeys": keys,
            "instructions": [{"program": "system",
                              "programId": "11111111111111111111111111111111",
                              "parsed": {"type": "transfer", "info": {}}}],
        }},
        "meta": {"err": None, "fee": 5000,
                 "preBalances": pre, "postBalances": post}
    }


class Mock:
    def __init__(self, tx):
        self.tx = tx
        self.requests = 0
        self.tx_reads = 0

    def signatures(self, wallet):
        self.requests += 1
        return [{"signature": SIG, "blockTime": JUNE_END + 5}]

    def transaction(self, signature):
        self.requests += 1
        self.tx_reads += 1
        return self.tx


class FingerprintTests(unittest.TestCase):
    def test_signer_and_native_delta_are_NOT_pnl(self):
        f = fingerprint(fake_tx(), A, SIG)
        self.assertTrue(f["wallet_listed"])
        self.assertTrue(f["wallet_is_signer"])
        self.assertTrue(f["wallet_is_fee_payer"])
        self.assertEqual(f["wallet_native_lamports_change"], -5000)
        self.assertIn("transfer", f["top_level_instruction_types"])
        self.assertNotIn("pnl", f)

    def test_recipient_may_appear_on_chain_without_signing(self):
        f = fingerprint(fake_tx(owner=B, signer=False, payer=A), B, SIG)
        self.assertTrue(f["wallet_listed"])
        self.assertFalse(f["wallet_is_signer"])
        self.assertFalse(f["wallet_is_fee_payer"])
        self.assertEqual(f["wallet_native_lamports_change"], -5000)

    def test_same_signature_reuses_one_transaction_request(self):
        rpc = Mock(fake_tx())
        out = audit({"one": A, "two": B}, rpc)
        self.assertEqual(rpc.requests, 3)
        self.assertEqual(rpc.tx_reads, 1)
        self.assertEqual(len(out["shared_latest_signatures"]), 1)
        self.assertIsNone(out["realized_pnl"])

    def test_safety_cap_and_missing_tx(self):
        with self.assertRaises(ValueError):
            audit({f"w{i}": A for i in range(MAX_WALLETS+1)}, Mock(fake_tx()))
        f = fingerprint(None, A, SIG)
        self.assertEqual(f["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
