"""No-network safety regressions for selected-wallet paper-copy replacement."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from research.smart_money_lab.engine import Portfolio, Trade
from research.smart_money_lab.paper_copy_next import (
    _apply_cycle, _budget, _ensure_new_budget, _load_watchlist,
    _parse_batch, _report, _restore, _snapshot, start, _atomic
)

W=["AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51",
   "FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT",
   "BXEHNbKPGeUHaqpaiHR6hc9mQkTZ2WFCXh6kkHkhFnCY",
   "7KyEvScKGoBPdroVYAy6v47XWjuuQFtPLjpWgZgMWEi",
   "SHARKdrwEJCe5hLNNLMNkkxn7aV8sTnURUV4TWtNUZS",
   "Jd97uyw9wb6PxV2jawAjS7aU6XUMHbcfn4En8xRP7Mg"]
M="So11111111111111111111111111111111111111112"
N="EpJFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW=1793520000


def trade(side,ts=None,mint=M,sig="sig-a",wallet=W[0]):
    stamp=NOW-10 if ts is None else ts
    return Trade(wallet=wallet,mint=mint,side=side,
                 signature=sig,chain_time=stamp,
                 observed_at=NOW,amount=Decimal("20"),
                 usd_notional=Decimal("30"),quote_mint="SOL")


def quote(mint=M,ts=NOW,price="1",liquidity="100000"):
    return {mint:{"ts":ts,"price_usd":price,
                  "liquidity_usd":liquidity}}


def watched():
    return {"schema":"YATL_FORWARD_PAPER_COPY_WATCHLIST_V1",
            "wallets":[{"wallet":x} for x in W],
            "allow_real_orders":False}


class GuardTests(unittest.TestCase):
    def test_six_unique_frozen_watchlist_only(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"watchlist.json"
            p.write_text(json.dumps(watched()))
            wallets,sha=_load_watchlist(p)
            self.assertEqual(wallets,W)
            self.assertEqual(len(sha),64)
            bad=watched()
            bad["wallets"][1]["wallet"]=W[0]
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"duplicate"):
                _load_watchlist(p)
            bad["wallets"][1]["wallet"]=W[1]
            bad["allow_real_orders"]=True
            p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"paper-only"):
                _load_watchlist(p)

    def test_budget_requires_existing_cumulative_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"old_shared.json"
            with self.assertRaisesRegex(ValueError,"existing absolute"):
                _budget(p)
            p.write_text('{"calls":4380,"max_calls":5000}')
            self.assertEqual(_budget(p),(4380,620))
            self.assertEqual(
                _ensure_new_budget(300,6,6,620)["estimated_calls"],432)
            with self.assertRaisesRegex(ValueError,"insufficient EXISTING"):
                _ensure_new_budget(300,6,6,400)
            self.assertEqual(json.loads(p.read_text())["calls"],4380)

    def test_no_real_order_code_and_single_account(self):
        p=Portfolio("forward_copy",0)
        self.assertEqual(len(p.holdings),0)
        self.assertEqual(p.cash,Decimal("1000"))

    def test_preflight_does_not_call_helius_or_create_state(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            wl=folder/"watchlist.json"
            wl.write_text(json.dumps(watched()))
            b=folder/"helius_budget.json"
            b.write_text('{"calls":40}')
            out=folder/"output"
            args=types.SimpleNamespace(watchlist=str(wl),existing_budget_file=str(b),
                                      output_dir=str(out),hours=6,poll_seconds=300,
                                      resume=False,start_paper=False)
            with patch("research.smart_money_lab.paper_copy_next.Helius") as h:
                with patch("research.smart_money_lab.paper_copy_next._old_observer_running",
                           return_value=False):
                    start(args)
                h.assert_not_called()
            self.assertFalse((out/"paper_copy_state.json").exists())

    def test_older_observer_running_is_hard_block(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            wl=folder/"w.json"
            wl.write_text(json.dumps(watched()))
            budget=folder/"budget.json"
            budget.write_text('{"calls":0}')
            args=types.SimpleNamespace(watchlist=str(wl),
                 existing_budget_file=str(budget),output_dir=str(folder/"out"),
                 hours=6,poll_seconds=300,resume=False,start_paper=True)
            with patch("research.smart_money_lab.paper_copy_next._old_observer_running",
                       return_value=True):
                with self.assertRaisesRegex(RuntimeError,"V2 observer is still running"):
                    start(args)
            self.assertEqual(json.loads(budget.read_text())["calls"],0)

    def test_snapshot_resume_guards_always_match_frozen_wallets(self):
        p=Portfolio("forward_copy",0)
        state=_snapshot(p,started_at=NOW,finish_at=NOW+6*3600,
                        watchlist_sha="f"*64,wallets=W,quotes={},seen=set(),
                        latest_poll={},last_seen_chain={},latest_source_sell={},
                        skips=Counter(),source_signals=0,cycles=0,
                        status="running",halt_reason=None)
        copy=_restore(state,expected_hash="f"*64,expected_wallets=W)
        self.assertEqual(copy.cash,Decimal("1000"))
        with self.assertRaisesRegex(ValueError,"different experiment"):
            _restore(state,expected_hash="0"*64,expected_wallets=W)
        report=_report(state,NOW)
        self.assertEqual(report["real_orders_submitted"],0)
        self.assertEqual(report["watched_wallet_count"],6)
        self.assertEqual(report["paper_account"]["cash_usd"],"1000")

    def test_atomic_state_is_json(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"state.json"
            _atomic(p,{"kind":"test"})
            self.assertEqual(json.loads(p.read_text()),{"kind":"test"})


class PaperEventTests(unittest.TestCase):
    def test_first_buy_then_leader_sell_creates_paper_positions_and_exit(self):
        p=Portfolio("forward_copy",0)
        seen=set()
        skips=Counter()
        buys,sells=0,0
        with patch("research.smart_money_lab.paper_copy_next.time.time",
                   return_value=NOW):
            buy=trade("BUY",sig="buy1")
            a,b=_apply_cycle(p,[buy],quote(),now=NOW,seen=seen,
                             latest_source_sell={},skips=skips)
            self.assertEqual((a,b),(1,1))
            self.assertEqual(len(p.holdings),1)
            sell=trade("SELL",sig="sell1")
            a,b=_apply_cycle(p,[sell],quote(),now=NOW,seen=seen,
                             latest_source_sell={},skips=skips)
            self.assertEqual((a,b),(1,1))
            self.assertEqual(len(p.holdings),0)
            self.assertEqual([r["side"] for r in p.fills],["BUY","SELL"])
            self.assertLess(p.cash,Decimal("1000"))

    def test_unknown_holding_valuation_blocks_new_paper_buy(self):
        p=Portfolio("forward_copy",0)
        seen=set()
        skips=Counter()
        _apply_cycle(p,[trade("BUY",mint=M)],quote(M),
                     now=NOW,seen=seen,latest_source_sell={},skips=skips)
        self.assertEqual(len(p.holdings),1)
        a,b=_apply_cycle(p,[trade("BUY",mint=N,sig="other")],
                         quote(N),now=NOW,seen=seen,
                         latest_source_sell={},skips=skips)
        self.assertEqual((a,b),(1,0))
        self.assertTrue(p.halted)
        self.assertEqual(len(p.holdings),1)
        self.assertGreater(skips["risk_locked_unpriced_holding"],0)

    def test_already_sold_leader_buy_suppressed_in_same_observed_batch(self):
        a=trade("BUY",NOW-110,sig="b")
        b=trade("SELL",NOW-10,sig="s")
        mock={"b":a,"s":b}
        raw=[{"signature":"b","timestamp":NOW-110},
             {"signature":"s","timestamp":NOW-10}]
        with patch("research.smart_money_lab.paper_copy_next.classify_swap",
                   side_effect=lambda item,**kw:(mock[item["signature"]],"ok")):
            events,counts,sells=_parse_batch(raw,W[0],started_at=NOW-200,
                                               observed_at=NOW,sol_price=Decimal(100))
        self.assertEqual([x.side for x in events],["SELL"])
        self.assertEqual(counts["leader_already_sold_before_observation"],1)
        p=Portfolio("forward_copy",0)
        seen=set()
        skips=Counter()
        a,b=_apply_cycle(p,[trade("BUY",NOW-110,sig="b")],quote(),
                         now=NOW,seen=seen,latest_source_sell=sells,skips=skips)
        self.assertEqual((a,b),(1,0))
        self.assertEqual(len(p.holdings),0)

    def test_missing_quote_and_stale_signal_are_never_paper_filled(self):
        p=Portfolio("forward_copy",0)
        seen=set()
        skips=Counter()
        a,b=_apply_cycle(p,[trade("BUY")],{},now=NOW,
                         seen=seen,latest_source_sell={},skips=skips)
        self.assertEqual(b,0)
        self.assertEqual(skips["missing_market_quote"],1)
        a,b=_apply_cycle(p,[trade("BUY",NOW-301,sig="late")],
                         quote(),now=NOW,seen=seen,
                         latest_source_sell={},skips=skips)
        self.assertEqual(b,0)
        self.assertEqual(skips["stale_before_paper_fill"],1)


if __name__=="__main__":
    unittest.main()
