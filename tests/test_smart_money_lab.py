"""Offline, deterministic safety and behavior gates for Smart Money Lab."""
import unittest
from unittest.mock import patch
from decimal import Decimal as D

from research.smart_money_lab.engine import (
    PaperLab, Trade, Portfolio, score_wallet, rank_wallets,
)
from research.smart_money_lab.providers import (
    USDC, SOL, Market, parse_swap, _token_amount,
)
from research.smart_money_lab.__main__ import snapshot, restore


W1 = "A" * 35
W2 = "B" * 35
MINT = "C" * 35


def trade(wallet=W1, side="BUY", signature="sig1", t=110, qty="20", usd="20",
          mint=MINT, quote="USDC"):
    return Trade(wallet, mint, side, signature, t, t + 1, D(qty), D(usd), quote)


def quote(price="1", now=113, liquidity="100000"):
    return {MINT: {"price_usd": price, "liquidity_usd": liquidity, "ts": now}}


class SelectionTests(unittest.TestCase):
    def test_realized_profit_uses_cost_basis_and_excludes_open_positions(self):
        series = [
            trade(t=100, qty="20", usd="20"),
            trade(side="SELL", signature="sig2", t=150, qty="10", usd="25"),
        ]
        r = score_wallet(W1, series, cutoff=200, min_closed=1, min_days=1)
        self.assertEqual(r["closed"], 1)
        self.assertGreater(D(r["net_realized_usd"]), D("14"))
        self.assertFalse(r["eligible"])  # external provenance required

    def test_no_pre_cutoff_leakage(self):
        rows = [
            trade(t=100),
            trade(side="SELL", signature="sig2", t=300, usd="200"),
        ]
        r = score_wallet(W1, rows, cutoff=200, min_closed=1, min_days=1)
        self.assertEqual(r["closed"], 0)

    def test_incomplete_history_never_ranks(self):
        base = dict(wallet=W1, net_realized_usd="999999",
                    preliminary_score="60", copyability_score="25",
                    min_liquidity_usd="900000", copyable=True,
                    meets_activity_thresholds=True, unmatched_sells=0,
                    history_complete=False)
        self.assertEqual(rank_wallets([base]), ([], []))
        base["history_complete"] = True
        a, b = rank_wallets([base])
        self.assertEqual(a, [W1])
        self.assertEqual(b, [W1])


class ProviderTests(unittest.TestCase):
    def test_parse_usdc_buy(self):
        raw = {
            "type": "SWAP", "feePayer": W1, "signature": "chain-sig", "timestamp": 100,
            "events": {"swap": {"tokenInputs": [
                {"mint": USDC, "tokenAmount": 20}
            ], "tokenOutputs": [{"mint": MINT, "tokenAmount": 1000}]}}
        }
        t = parse_swap(raw, wallet=W1, observed_at=105)
        self.assertIsNotNone(t)
        self.assertEqual(t.side, "BUY")
        self.assertEqual(t.usd_notional, D("20"))
        self.assertIsNone(parse_swap(raw, wallet=W2, observed_at=105))

    def test_parse_sol_requires_asof_usd_price(self):
        raw = {
            "type": "SWAP", "feePayer": W1, "signature": "chain-sig", "timestamp": 100,
            "events": {"swap": {"tokenInputs": [
                {"mint": SOL, "tokenAmount": "1.5"}
            ], "tokenOutputs": [{"mint": MINT, "tokenAmount": "1000"}]}}
        }
        self.assertIsNone(parse_swap(raw, wallet=W1, observed_at=105))
        t = parse_swap(raw, wallet=W1, observed_at=105, historical_sol_usd=D("100"))
        self.assertEqual(t.usd_notional, D("150"))

    def test_raw_token_decimals(self):
        self.assertEqual(_token_amount({"rawTokenAmount":
            {"tokenAmount": "1000000", "decimals": 6}}), D("1"))

    def test_market_never_uses_quote_token_base_price(self):
        pairs = [
            {"chainId": "solana", "baseToken": {"address": MINT},
             "quoteToken": {"address": SOL}, "priceUsd": "0.01",
             "liquidity": {"usd": 1000000}},
            {"chainId": "solana", "baseToken": {"address": SOL},
             "quoteToken": {"address": USDC}, "priceUsd": "250",
             "liquidity": {"usd": 100000}},
        ]
        with patch("research.smart_money_lab.providers.get_json", return_value=pairs):
            q = Market().token(SOL, now=100)
            self.assertEqual(q["price_usd"], "250")
            batch = Market().tokens({MINT, SOL}, now=100)
            self.assertEqual(batch[SOL]["price_usd"], "250")
            self.assertEqual(batch[MINT]["price_usd"], "0.01")


class LedgerTests(unittest.TestCase):
    def test_separate_paper_ledgers_and_no_lookback_execution(self):
        lab = PaperLab(100, [W1], [W1, W2])
        self.assertEqual(len(lab.portfolios), 9)
        lab.ingest(trade(t=90, signature="old"))
        self.assertEqual(len(lab.pending), 0)
        lab.ingest(trade(t=110))
        lab.ingest(trade(t=110))  # same signature is idempotent
        self.assertEqual(len(lab.pending), 6)
        lab.process(113, quote(now=113))
        self.assertEqual(len(lab.portfolios["blind_1s"].fills), 1)
        self.assertEqual(len(lab.portfolios["smart_1s"].fills), 1)
        self.assertEqual(len(lab.portfolios["consensus_1s"].fills), 0)
        self.assertLess(lab.portfolios["smart_1s"].cash, D("1000"))
        self.assertEqual(lab.portfolios["smart_1s"].cash, D("970"))

    def test_two_distinct_voters_required(self):
        lab = PaperLab(100, [], [W1, W2])
        lab.ingest(trade(W1, signature="one"))
        lab.ingest(trade(W1, signature="another", t=111))
        self.assertFalse(any(x[1].startswith("consensus") for x in lab.pending))
        lab.ingest(trade(W2, signature="three", t=112))
        self.assertEqual(
            sum(x[1].startswith("consensus") for x in lab.pending), 3)

    def test_costs_and_early_exit(self):
        p = Portfolio("blind", 1)
        t = trade()
        self.assertTrue(p.apply(t, price=D("1"), liquidity_usd=D("100000"),
                                quote_ts=112, now=112))
        self.assertEqual(p.cash, D("970"))
        self.assertTrue(p.apply(trade(side="SELL", signature="2", t=112),
                                price=D("1"), liquidity_usd=D("100000"),
                                quote_ts=114, now=114))
        self.assertFalse(p.holdings)
        self.assertLess(p.cash, D("1000"))  # cost drag after flat round-trip

    def test_stale_quote_or_illiquidity_cannot_buy(self):
        p = Portfolio("blind", 1)
        self.assertFalse(p.apply(trade(), price=D("1"), liquidity_usd=D("100000"),
                                 quote_ts=60, now=113))
        self.assertFalse(p.apply(trade(), price=D("1"), liquidity_usd=D("2"),
                                 quote_ts=113, now=113))
        self.assertEqual(p.cash, D("1000"))

    def test_stop_loss_closes_and_prevents_new_buys(self):
        p = Portfolio("blind", 1)
        p.apply(trade(), price=D("1"), liquidity_usd=D("100000"),
                quote_ts=112, now=112)
        p.peak_equity = D("1100")  # synthetic prior high-water mark
        p.mark(quote(price="0.001", now=113), 113)
        self.assertTrue(p.halted)
        self.assertFalse(p.holdings)
        self.assertEqual(p.fills[-1]["side"], "RISK_EXIT")
        self.assertFalse(p.apply(trade(signature="new", t=114), price=D("1"),
                                 liquidity_usd=D("100000"), quote_ts=115, now=115))

    def test_snapshot_restore(self):
        lab = PaperLab(100, [W1], [W1, W2])
        lab.ingest(trade())
        lab.process(113, quote(now=113))
        doc = snapshot(lab, quote(now=113), 113, 1, {})
        restored = restore(doc)
        self.assertEqual(
            restored.portfolios["blind_1s"].cash,
            lab.portfolios["blind_1s"].cash)
        self.assertEqual(restored.seen, lab.seen)
        self.assertEqual(restored.report(quote(now=113), 113)["kind"],
                         "YATL_SMART_MONEY_PAPER_ONLY")


if __name__ == "__main__":
    unittest.main()
