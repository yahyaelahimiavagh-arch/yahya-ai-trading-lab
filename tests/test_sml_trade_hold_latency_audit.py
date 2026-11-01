"""Entirely offline tests of sample FIFO and no-future-price replay guards."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from research.smart_money_lab.trade_hold_latency_audit import (
    _median_pct, analyze, asof_print, evaluate, print_index,
    read_snapshot, reconstruct,
)

W="5"*33
M="A"*33
P="C"*33


def trade(side, timestamp, qty, usd, sig):
    return {
        "wallet":W,"mint":M,"pool":P,"side":side,
        "timestamp":timestamp,"qty":Decimal(str(qty)),
        "usd":Decimal(str(usd)),"quantity":str(qty),
        "volume_usd":str(usd),"tx_signature":sig,
    }


class FifoTests(unittest.TestCase):
    def test_partial_sells_are_fragments_not_independent_trades(self):
        rows=[trade("buy",100,10,20,"buy"),
              trade("sell",500,4,12,"sell_1"),
              trade("sell",600,3,9,"sell_2")]
        matched,coverage=reconstruct(rows)
        self.assertEqual(len(matched),2)
        self.assertEqual(len({x["buy_sig"] for x in matched}),1)
        self.assertEqual(sum((x["source_gross_spread_usd"] for x in matched),
                             Decimal(0)),Decimal(7))
        self.assertEqual(coverage["unmatched_sell_events"],0)

    def test_same_second_sell_does_not_borrow_future_buy(self):
        matches,issues=reconstruct([
            trade("buy",100,10,10,"sig_buy"),
            trade("sell",100,5,7,"sig_sell")])
        self.assertEqual(matches,[])
        self.assertEqual(issues["unmatched_sell_events"],1)

    def test_missing_open_inventory_never_generates_closed_pnl(self):
        matches,issues=reconstruct([trade("sell",500,10,30,"sell")])
        self.assertEqual(matches,[])
        self.assertEqual(issues["unmatched_sell_events"],1)

    def test_asof_print_is_always_at_or_before_decision(self):
        index=print_index([trade("buy",100,10,10,"a"),
                           trade("sell",218,10,30,"b")])
        self.assertIsNone(asof_print(index,P,217,30))
        self.assertEqual(asof_print(index,P,218,0),Decimal(3))

    def test_117_second_copy_enters_only_if_leader_still_holding(self):
        rows=[trade("buy",100,10,10,"b"),
              trade("sell",150,10,11,"s")]
        matched,_=reconstruct(rows)
        counts,covered,_=evaluate(matched,print_index(rows),delay=117,
                                   age_limit=30)
        self.assertEqual(counts["leader_exited_before_copy_entry"],1)
        self.assertFalse(covered)

    def test_cost_sensitivity_cannot_create_alpha(self):
        example=[{"buy_asof_print":Decimal(1),
                  "sell_asof_print":Decimal("1.001")}]
        self.assertEqual(_median_pct(example,0),0.1)
        self.assertLess(_median_pct(example,150),0)
        self.assertIsNone(_median_pct([],150))

    def test_complete_synthetic_summary_no_trader_is_verified(self):
        rows=[trade("buy",100,10,10,"b"),trade("sell",600,10,12,"s")]
        summary={
            "data_retrieved_at_utc":"2026-11-01T09:30:00Z",
            "api_failure":None,"pool_count":1,
            "distinct_wallet_addresses":1,
            "wallets":[{"wallet":W,
                        "classification":"candidate_two_sided_multi_token_sample"}],
        }
        result=analyze(summary,rows)
        self.assertEqual(result["matching_quality"]["fifo_matched_fragments"],1)
        self.assertEqual(result["selected_top_10"][0]["wallet"],W)
        self.assertTrue(result["selected_top_10"][0]["not_proven_profitable"])
        self.assertIsNone(result["realized_pnl"])
        self.assertTrue(result["no_api_calls"])

    def test_modified_archive_rejected_before_scoring(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"sample.zip"
            blobs={"wallet_candidates.json":b"{}",
                   "normalized_trades.jsonl":b"{}\n"}
            manifest={k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()}
            with ZipFile(path,"w") as z:
                for k,v in blobs.items():
                    z.writestr(k,v)
                z.writestr("sha256_manifest.json",json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"kind"):
                read_snapshot(path)
            with ZipFile(path,"w") as z:
                z.writestr("wallet_candidates.json",b"tampered")
                z.writestr("normalized_trades.jsonl",b"{}\n")
                z.writestr("sha256_manifest.json",json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
                read_snapshot(path)


if __name__=="__main__":
    unittest.main()
