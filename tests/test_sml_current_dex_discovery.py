"""No-network, deterministic test suite for current DEX public wallet discovery."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from research.smart_money_lab.current_dex_discovery import (
    PublicDex, choose_pools, dec, epoch, extract_pool, normalize_trade,
    analyze, run, save,
)

NOW = 1793520000
W = "5" * 33
ANOTHER = "6" * 33
B1 = "A" * 33
B2 = "D" * 33
Q = "B" * 33
POOL1 = "C" * 33
POOL2 = "E" * 33
SIG1 = "1" * 87
SIG2 = "2" * 87
SIG3 = "3" * 87
SIG4 = "4" * 87


def utc(n):
    return datetime.fromtimestamp(n, timezone.utc).isoformat()


def pool(*, address=POOL1, base=B1, volume="100000", count=200,
         liquid="500000", created=NOW-10*86400):
    return {
        "attributes": {
            "address": address, "reserve_in_usd": liquid,
            "volume_usd": {"h24": volume},
            "transactions": {"h24": {"buys": count//2, "sells": count-count//2}},
            "pool_created_at": utc(created),
            "name": "Test", },
        "relationships": {
            "base_token": {"data": {"id": "solana_"+base}},
            "quote_token": {"data": {"id": "solana_"+Q}},
            "dex": {"data": {"id": "test-dex"}},
        },
    }


def trade(*, side="buy", wallet=W, signature=SIG1, mint=B1, poolbase=B1,
          ts=NOW-400, qty="10", usd="10", anomalous=False):
    # Base "buy" means receive token; base "sell" means spend token.
    return {"attributes": {
        "kind": side, "tx_from_address": wallet,
        "tx_hash": signature, "block_timestamp": utc(ts),
        "from_token_address": Q if side=="buy" else poolbase,
        "to_token_address": poolbase if side=="buy" else Q,
        "from_token_amount": usd if side=="buy" else qty,
        "to_token_amount": qty if side=="buy" else usd,
        "volume_in_usd": usd, "is_anomalous": anomalous
    }}


class FakeApi:
    def __init__(self, *, error=None):
        self.calls = 0
        self.error = error
        self.data = {
            "/networks/solana/trending_pools?page=1": {"data":[pool()]},
            "/networks/solana/pools?page=1": {"data":[pool(address=POOL2, base=B2)]},
            f"/networks/solana/pools/{POOL1}/trades": {"data":[
                trade(side="sell", signature=SIG2, qty="5", usd="6",
                      ts=NOW-300),  # newer than buy
                trade(side="buy", signature=SIG1, ts=NOW-400),
                trade(side="buy", signature=SIG1, ts=NOW-400),  # duplicate
                trade(side="buy", signature="7"*87, ts=NOW+900),
            ]},
            f"/networks/solana/pools/{POOL2}/trades": {"data":[
                trade(side="sell", signature=SIG4, poolbase=B2, qty="5",
                      usd="6",ts=NOW-100),
                trade(side="buy", signature=SIG3, poolbase=B2,
                      ts=NOW-200),
                trade(side="buy", signature="8"*87,
                      poolbase=B2, wallet=ANOTHER,ts=NOW-100),
            ]},
        }

    def get(self, path):
        self.calls += 1
        return self.data[path]


class Tests(unittest.TestCase):
    def test_utc_parser_and_decimal_guard(self):
        self.assertEqual(epoch(utc(NOW)), NOW)
        self.assertIsNone(epoch("2026-11-01 10:00:00"))
        self.assertIsNone(dec("Infinity"))
        self.assertIsNone(dec("NaN"))
        self.assertIsNone(dec("-1"))

    def test_pool_liquidity_age_and_base_relation(self):
        a = extract_pool(pool(), now=NOW)
        self.assertEqual(a["base_mint"], B1)
        self.assertEqual(a["reported_transactions_24h"], 200)
        self.assertIsNone(extract_pool(pool(liquid="100"), now=NOW))
        self.assertIsNone(extract_pool(pool(created=NOW-100), now=NOW))
        self.assertIsNone(extract_pool(pool(count=5), now=NOW))

    def test_deduplicated_diverse_pool_selection(self):
        doc = [{"data":[pool(),pool()]},
               {"data":[pool(address=POOL2,base=B2)]}]
        out = choose_pools(doc, now=NOW,limit=4)
        self.assertEqual(len(out),2)
        self.assertEqual({p["base_mint"] for p in out},{B1,B2})

    def test_normalize_exact_trade_identity_and_no_lookahead(self):
        p = extract_pool(pool(),now=NOW)
        a, error = normalize_trade(trade(), p, now=NOW)
        self.assertIsNone(error)
        self.assertEqual(a["wallet"],W)
        self.assertEqual(a["quantity"],"10")
        self.assertEqual(a["volume_usd"],"10")
        _, err = normalize_trade(trade(ts=NOW+2000),p,now=NOW)
        self.assertEqual(err,"invalid_or_old_or_missing_identity")
        _, err = normalize_trade(trade(anomalous=True),p,now=NOW)
        self.assertEqual(err,"anomalous_indexer_trade")
        _, err = normalize_trade(trade(poolbase=B2),p,now=NOW)
        self.assertEqual(err,"pool_mint_or_side_mismatch")

    def test_realistic_two_pool_sample_cannot_establish_actual_pnl(self):
        api = FakeApi()
        out, raw = run(api,observed_at=NOW,max_pools=2)
        self.assertEqual(out["pool_count"],2)
        self.assertEqual(out["api_requests"],4)
        self.assertEqual(out["deduped_trades"],5)
        self.assertEqual(out["distinct_wallet_addresses"],2)
        self.assertEqual(out["duplicate_trade_rows"],1)
        self.assertEqual(out["candidate_two_sided_multi_token_count"],1)
        self.assertEqual(out["wallets"][0]["wallet"],W)
        self.assertEqual(out["wallets"][0]["distinct_tokens"],2)
        self.assertEqual(out["wallets"][0]["sell_events_with_observed_buy_basis"],2)
        self.assertEqual(out["wallets"][0]["indicative_fifo_gross_spread_usd_unverified"],"2.0000")
        self.assertTrue(out["no_real_orders"])
        self.assertTrue(out["no_helius_calls"])
        self.assertIn("before fees", str(out["limitations"]))

    def test_one_sided_wallet_not_selected_as_skillful(self):
        records = [{
            "wallet":W,"tx_signature":SIG1,"mint":B1,
            "pool":POOL1,"side":"buy","quantity":"10",
            "volume_usd":"10","timestamp":NOW-300},
        ]
        out = analyze(records,[],observed_at=NOW)
        self.assertEqual(out["candidate_two_sided_multi_token_count"],0)
        self.assertEqual(out["wallets"][0]["classification"],
                         "insufficient_two_sided_trade_evidence")

    def test_incomplete_sale_with_no_known_basis_is_flagged(self):
        records = [{
            "wallet":W,"tx_signature":SIG2,"mint":B1,
            "pool":POOL1,"side":"sell","quantity":"8",
            "volume_usd":"9","timestamp":NOW-200},
        ]
        out = analyze(records,[],observed_at=NOW)
        self.assertEqual(out["wallets"][0]["unmatched_sell_events"],1)
        self.assertEqual(out["wallets"][0]["sell_events_with_observed_buy_basis"],0)

    def test_save_all_artifacts_with_digest(self):
        with tempfile.TemporaryDirectory() as d:
            api = FakeApi()
            out, raw = run(api,observed_at=NOW,max_pools=2)
            save(out,raw,Path(d))
            self.assertTrue((Path(d)/"wallet_candidates.json").is_file())
            self.assertTrue((Path(d)/"wallet_candidates.csv").is_file())
            self.assertTrue((Path(d)/"normalized_trades.jsonl").is_file())
            manifest=json.loads((Path(d)/"sha256_manifest.json").read_text())
            self.assertEqual(len(manifest["wallet_candidates.json"]),64)
            self.assertIn(W,(Path(d)/"wallet_candidates.csv").read_text())

    def test_forbidden_endpoint_never_calls_network(self):
        with self.assertRaises(ValueError):
            PublicDex().get("/wallets/balance")
        with self.assertRaises(ValueError):
            PublicDex().get("/sendTransaction")


if __name__ == "__main__":
    unittest.main()
