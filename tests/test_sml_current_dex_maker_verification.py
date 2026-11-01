"""No-network verification tests for current DEX maker/signer checks."""
from __future__ import annotations
import io
import json
import unittest
from unittest.mock import patch
from research.smart_money_lab.current_dex_maker_verification import audit
from research.smart_money_lab.recent_wallet_receipts import PublicRpc, PublicRpcError

A="A"*33
B="B"*33
PAYER="C"*33
SIG1="1"*87
SIG2="2"*87
T=1793520000


def inputs():
    return {"snapshot":"test-public-data","samples":[
        {"wallet":A,"signature":SIG1,"rank":1,"kind":"buy","reported_timestamp":T},
        {"wallet":B,"signature":SIG2,"rank":2,"kind":"sell","reported_timestamp":T+1},
    ]}


def tx(*,wallet=A,signer=True,payer=PAYER,stamp=T):
    return {
        "blockTime":stamp,"slot":234,
        "transaction":{"message":{"accountKeys":[
            {"pubkey":payer,"signer":True},
            {"pubkey":wallet,"signer":signer},
        ],"instructions":[]}},
        "meta":{"err":None,"fee":5000,"preBalances":[10000000,0],
                "postBalances":[9995000,0],
                "preTokenBalances":[],"postTokenBalances":[]},
    }


class FakeRpc:
    def __init__(self,rows,fail_at=None):
        self.rows=rows
        self.fail_at=fail_at
        self.requests=0
    def transaction(self,sig):
        self.requests+=1
        if self.requests==self.fail_at:
            raise PublicRpcError("http_429")
        return self.rows.get(sig)


class Tests(unittest.TestCase):
    def test_two_authorized_signers_may_share_fee_payer(self):
        rpc=FakeRpc({SIG1:tx(wallet=A),SIG2:tx(wallet=B,stamp=T+1)})
        out=audit(inputs(),rpc)
        self.assertEqual(out["rpc_requests"],2)
        self.assertEqual(out["onchain_signer_yes"],2)
        self.assertEqual(out["onchain_signer_no"],0)
        self.assertEqual(len(out["shared_fee_payers"]),1)
        self.assertEqual(len(out["shared_fee_payers"][PAYER]),2)
        self.assertTrue(out["no_verified_profit_or_copyability"])
        self.assertEqual(out["helius_calls"],0)

    def test_indexer_maker_is_not_onchain_signer(self):
        rpc=FakeRpc({SIG1:tx(wallet=A,signer=False),SIG2:tx(wallet=B)})
        out=audit(inputs(),rpc)
        self.assertEqual(out["onchain_signer_no"],1)
        self.assertEqual(out["evidence"][0]["onchain_status"],
                         "indexer_maker_not_onchain_signer")

    def test_bad_timestamp_detected(self):
        rpc=FakeRpc({SIG1:tx(wallet=A,stamp=T+500),SIG2:tx(wallet=B,stamp=T+1)})
        out=audit(inputs(),rpc)
        self.assertEqual(out["evidence"][0]["onchain_status"],
                         "market_chain_time_mismatch")

    def test_rate_limited_is_not_retried(self):
        rpc=FakeRpc({},fail_at=1)
        out=audit(inputs(),rpc)
        self.assertEqual(out["rpc_requests"],1)
        self.assertEqual(out["unknown_signer"],2)
        self.assertEqual(out["rpc_error"],"http_429")
        self.assertEqual(out["evidence"][1]["onchain_status"],
                         "not_checked_rpc_unavailable")

    def test_solana_mainnet_transaction_v1_is_explicitly_supported(self):
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"jsonrpc":"2.0","result":null}')
            result = PublicRpc().transaction(SIG1)
            self.assertIsNone(result)
            payload=json.loads(urlopen.call_args.args[0].data)
            self.assertEqual(payload["method"],"getTransaction")
            self.assertEqual(payload["params"][1]["maxSupportedTransactionVersion"],1)

    def test_invalid_input_prevents_any_network(self):
        source=inputs()
        source["samples"][1]["signature"]=SIG1
        rpc=FakeRpc({})
        with self.assertRaises(ValueError):
            audit(source,rpc)
        self.assertEqual(rpc.requests,0)


if __name__=="__main__":
    unittest.main()
