"""Deterministic no-network checks for bounded public Solana wallet receipt audit."""
from __future__ import annotations

import unittest

from research.smart_money_lab.recent_wallet_receipts import (
    BASE58, JUNE_END, PublicRpc, audit, interpret_transaction, owned_token_deltas,
    USDC, WALLETS,
)

MINT = "TokenMintTesting111111111111111111111111111"
WALLET1 = WALLETS["behavior_group_1"]
WALLET2 = WALLETS["behavior_group_2"]
SIG = "1" * 87
SIG2 = "2" * 87


def row(owner, mint, amount, *, ix=1, decimals=6):
    return {"accountIndex": ix, "mint": mint, "owner": owner,
            "uiTokenAmount": {"amount": str(amount), "decimals": decimals}}


def tx(wallet, *, failed=False):
    return {
        "slot": 234, "blockTime": JUNE_END + 3600,
        "meta": {
            "err": {"Custom": 1} if failed else None,
            "fee": 5000,
            "preTokenBalances": [
                row(wallet, MINT, 10_000_000),
                row(wallet, USDC, 200_000_000, ix=2),
            ],
            "postTokenBalances": [
                row(wallet, MINT, 35_000_000),
                row(wallet, USDC, 170_000_000, ix=2),
            ],
        },
    }


class DummyRpc:
    def __init__(self, signatures=None, transactions=None):
        self.requests = 0
        self._sigs = signatures or {}
        self._transactions = transactions or {}
        self.tx_calls = []

    def signatures(self, wallet):
        self.requests += 1
        return self._sigs.get(wallet, [])

    def transaction(self, signature):
        self.requests += 1
        self.tx_calls.append(signature)
        return self._transactions.get(signature)


class TokenDeltaTests(unittest.TestCase):
    def test_simple_candidate_stablecoin_buy_not_confused_with_profit(self):
        got = interpret_transaction(tx(WALLET1), WALLET1, SIG)
        self.assertEqual(got["status"],
                         "simple_opposite_stablecoin_token_flow_unverified_swap_intent")
        self.assertEqual(got["direction"], "BUY_CANDIDATE")
        self.assertEqual(got["token_amount"], "25")
        self.assertEqual(got["nominal_stablecoin_amount"], "30")
        self.assertEqual(got["price_per_token_stablecoin"], "1.2")
        self.assertEqual(got["network_fee_lamports"], 5000)
        self.assertNotIn("pnl_usd", got)

    def test_sell_candidate_from_owned_exact_integer_amount(self):
        data = tx(WALLET1)
        data["meta"]["preTokenBalances"][0]["uiTokenAmount"]["amount"] = "35000000"
        data["meta"]["postTokenBalances"][0]["uiTokenAmount"]["amount"] = "10000000"
        data["meta"]["preTokenBalances"][1]["uiTokenAmount"]["amount"] = "170000000"
        data["meta"]["postTokenBalances"][1]["uiTokenAmount"]["amount"] = "200000000"
        got = interpret_transaction(data, WALLET1, SIG)
        self.assertEqual(got["direction"], "SELL_CANDIDATE")
        self.assertEqual(got["token_amount"], "25")

    def test_foreign_owner_and_missing_balance_never_create_fake_buy(self):
        data = tx(WALLET1)
        got = interpret_transaction(data, WALLET2, SIG)
        self.assertEqual(got["status"], "no_verifiable_owned_spl_change")
        data["meta"]["preTokenBalances"] = None
        out = interpret_transaction(data, WALLET1, SIG)
        self.assertEqual(out["status"], "no_verifiable_owned_spl_change")
        self.assertTrue(out["balance_metadata_warnings"]["token_balance_metadata_missing"])

    def test_multileg_and_failed_tx_not_verified(self):
        data = tx(WALLET1)
        data["meta"]["postTokenBalances"].append(
            row(WALLET1, "MoreToken111111111111111111111111111111111", 5_000_000, ix=3))
        got = interpret_transaction(data, WALLET1, SIG)
        self.assertEqual(got["status"], "multileg_or_nonstable_flow_no_pnl")
        self.assertEqual(interpret_transaction(tx(WALLET1, failed=True),
                                               WALLET1, SIG)["status"],
                         "transaction_failed")

    def test_missing_account_in_pre_is_new_token_account(self):
        meta = {
            "preTokenBalances": [row(WALLET1, USDC, 100_000_000, ix=2)],
            "postTokenBalances": [
                row(WALLET1, USDC, 70_000_000, ix=2),
                row(WALLET1, MINT, 25_000_000),
            ],
        }
        d, warnings = owned_token_deltas(meta, WALLET1)
        self.assertEqual(d[MINT]["token_delta"], "25")
        self.assertEqual(d[USDC]["token_delta"], "-30")
        self.assertFalse(warnings)

    def test_owner_conflict_is_not_treated_as_trade(self):
        data = tx(WALLET1)
        data["meta"]["postTokenBalances"][0]["owner"] = WALLET2
        got = interpret_transaction(data, WALLET1, SIG)
        self.assertEqual(got["status"], "no_verifiable_owned_spl_change")
        self.assertEqual(got["balance_metadata_warnings"]["ownership_conflict"], 1)


class AuditTests(unittest.TestCase):
    def test_respects_cutoff_dedups_cross_wallet_signatures(self):
        now = JUNE_END + 3600
        rpc = DummyRpc(
            signatures={
                WALLET1: [{"signature": SIG, "blockTime": now},
                          {"signature": SIG2, "blockTime": JUNE_END-10}],
                WALLET2: [{"signature": SIG, "blockTime": now},
                          {"signature": SIG2, "blockTime": JUNE_END-10}],
            },
            transactions={SIG: tx(WALLET1)})
        a = audit({"one": WALLET1, "two": WALLET2}, rpc)
        self.assertEqual(a["rpc_request_count"], 3)
        self.assertEqual(a["distinct_tx_signatures_retrieved"], 1)
        self.assertEqual(len(a["reused_signatures_across_groups"]), 1)
        self.assertEqual(a["wallet_groups"]["one"]["recent_signatures_after_cutoff"], 1)
        self.assertEqual(a["wallet_groups"]["one"]["outcome"], "sampled_until_cutoff")
        self.assertTrue(a["no_realized_pnl"])
        self.assertEqual(a["helius_requests"], 0)

    def test_latest_12_signatures_are_marked_truncated(self):
        rpc = DummyRpc(signatures={
            WALLET1: [{"signature": SIG, "blockTime": JUNE_END+10}] * 12
        }, transactions={SIG: tx(WALLET1)})
        a = audit({"one": WALLET1}, rpc)
        self.assertEqual(a["wallet_groups"]["one"]["outcome"], "sample_truncated")
        self.assertEqual(a["wallet_groups"]["one"]["latest_signature_count"], 12)

    def test_public_rpc_forbids_transaction_submission(self):
        with self.assertRaises(ValueError):
            PublicRpc().call("sendTransaction", ["deadbeef"])

    def test_wallet_identifier_and_signature_patterns_are_distinct(self):
        self.assertTrue(BASE58.fullmatch(WALLET1))
        with self.assertRaises(ValueError):
            PublicRpc().transaction(WALLET1)
        with self.assertRaises(ValueError):
            PublicRpc().signatures(SIG)


if __name__ == "__main__":
    unittest.main()
