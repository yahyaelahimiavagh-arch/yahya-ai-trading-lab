"""No-network tests for YATL V3 evidence quality and selection controls."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research.smart_money_lab.wallet_intelligence import (
    audit_screening, audit_v2_report, quote_coverage, run, main,
)


def eligible(wallet: str, *, screened_at=1000, history_end_at=990):
    return {
        "wallet": wallet, "eligible": True,
        "history_complete": True, "meets_activity_thresholds": True,
        "copyable": True, "closed": 60, "active_days": 20,
        "unmatched_sells": 0, "total_swaps_observed": 100,
        "unparsed_swaps": 10, "min_liquidity_usd": "45000",
        "net_realized_usd": "230", "preliminary_score": "42",
        "screened_at": screened_at, "history_end_at": history_end_at,
    }


def event(*, wallet="WALLET_PRIVATE_A", signature="TX_PRIVATE_1",
          chain=1100, observed=1200, mint="MINT_PRIVATE_X",
          side="BUY"):
    return {
        "source": "live_observed", "wallet": wallet, "mint": mint,
        "signature": signature, "side": side,
        "chain_time": chain, "observed_at": observed,
    }


def quote(*, mint="MINT_PRIVATE_X", captured=1234, liquidity="45000",
          price="1.5", source="live_recorded"):
    return {
        "source": source, "mint": mint, "captured_at": captured,
        "price_usd": price, "liquidity_usd": liquidity,
    }


class V3ScreeningTests(unittest.TestCase):
    def test_v2_old_screened_rows_blocked_until_timestamps_are_proven(self):
        row = eligible("WALLET_PRIVATE_A")
        row.pop("screened_at")
        row.pop("history_end_at")
        output = audit_screening([row], selection_at=1500)
        self.assertEqual(output["training_candidates_with_point_in_time_proof"], 0)
        self.assertIn("missing_or_leaky_training_timestamps",
                      output["overlapping_rejection_reasons"])
        self.assertNotIn("WALLET_PRIVATE", json.dumps(output))

    def test_no_selection_cutoff_is_no_eligible_training_snapshot(self):
        output = audit_screening([eligible("WALLET_PRIVATE_A")])
        self.assertEqual(output["training_candidates_with_point_in_time_proof"], 0)
        self.assertEqual(output["cohort_design"]["status"], "blocked_insufficient_evidence")

    def test_four_pre_cutoff_candidates_form_two_disjoint_research_arms(self):
        rows = [eligible("WALLET_PRIVATE_" + x) for x in ("A", "B", "C", "D")]
        result = audit_screening(rows, selection_at=1500)
        self.assertEqual(result["training_candidates_with_point_in_time_proof"], 4)
        self.assertEqual(result["cohort_design"]["smart_candidates"], 2)
        self.assertEqual(result["cohort_design"]["control_candidates"], 2)
        self.assertTrue(result["cohort_design"]["disjoint_by_construction"])
        self.assertFalse(result["cohort_design"]["balanced_or_randomized"])
        self.assertFalse(result["cohort_design"]["independent_forward_validation"])
        self.assertNotIn("WALLET_PRIVATE_", json.dumps(result))

    def test_incomplete_history_unknown_cost_and_low_parse_rate_block(self):
        a = eligible("WALLET_PRIVATE_A")
        a.update(history_complete=False, unmatched_sells=3,
                 unparsed_swaps=30, total_swaps_observed=100)
        result = audit_screening([a], selection_at=1500)
        reasons = result["overlapping_rejection_reasons"]
        for reason in ("incomplete_history", "unknown_cost_basis",
                       "poor_parse_coverage"):
            self.assertEqual(reasons[reason], 1)

    def test_duplicate_and_future_leaking_training_rejected(self):
        a = eligible("WALLET_PRIVATE_A", screened_at=2000, history_end_at=1990)
        result = audit_screening([a, a], selection_at=1500)
        self.assertEqual(result["duplicate_wallet_rows"], 1)
        self.assertEqual(result["training_candidates_with_point_in_time_proof"], 0)

    def test_zero_activity_does_not_count_as_proven_profit(self):
        a = eligible("WALLET_PRIVATE_A")
        a["closed"] = 0
        a["active_days"] = 0
        a["net_realized_usd"] = "-10"
        output = audit_screening([a], selection_at=1500)
        self.assertIn("positive_training_pnl_not_established",
                      output["overlapping_rejection_reasons"])
        self.assertIn("insufficient_closed_trades",
                      output["overlapping_rejection_reasons"])


class V3AsOfQuoteTests(unittest.TestCase):
    def test_quote_after_decision_never_looks_ahead(self):
        # obs 1200; end-to-end target chain 1100+134 => 1234.
        result = quote_coverage([event()], [quote(captured=1235)], cutoff=1000)
        self.assertEqual(result["indicative_quotes_available"], 0)
        self.assertEqual(result["rejection_reasons"]["no_asof_quote"], 1)
        self.assertIsNone(result["realized_or_copy_pnl"])

    def test_quote_asof_exact_decision_is_covered_not_realized_pnl(self):
        result = quote_coverage([event()], [quote(captured=1234)], cutoff=1000)
        self.assertEqual(result["indicative_quotes_available"], 1)
        self.assertEqual(result["median_chain_to_decision_seconds_for_covered"], 134)
        self.assertEqual(result["coverage_fraction"], "1")
        self.assertIsNone(result["realized_or_copy_pnl"])
        self.assertNotIn("MINT_PRIVATE", json.dumps(result))

    def test_stale_illiquid_duplicate_and_pre_cutoff_are_explained(self):
        events = [
            event(signature="stale", mint="STALE", chain=1100, observed=1200),
            event(signature="poor", mint="LOW_LIQ", chain=1100, observed=1200),
            event(signature="poor", mint="LOW_LIQ", chain=1100, observed=1200),
            event(signature="old", chain=800, observed=900),
            event(signature="late", chain=1100, observed=1410),
        ]
        quotes = [
            quote(mint="STALE", captured=1190),
            quote(mint="LOW_LIQ", captured=1234, liquidity="100"),
            quote(mint="MINT_PRIVATE_X", captured=1400),
        ]
        result = quote_coverage(events, quotes, cutoff=1000)
        reasons = result["rejection_reasons"]
        self.assertEqual(reasons["stale_asof_quote"], 1)
        self.assertEqual(reasons["illiquid_at_decision"], 1)
        self.assertEqual(reasons["duplicate_event"], 1)
        self.assertEqual(reasons["before_holdout_cutoff"], 1)
        self.assertEqual(reasons["signal_too_old"], 1)

    def test_unverified_future_price_and_bad_event_not_copied(self):
        result = quote_coverage([event(), {**event(signature="bad"), "source": "unverified"}],
                                [quote(source="scraped_history")], cutoff=1000)
        self.assertEqual(result["indicative_quotes_available"], 0)
        self.assertEqual(result["rejection_reasons"]["invalid_or_unverified_event"], 1)

    def test_observed_later_than_assumed_latency_cannot_backdate_execution(self):
        result = quote_coverage([event(observed=1260)],
                                [quote(captured=1250)], cutoff=1000)
        self.assertEqual(result["indicative_quotes_available"], 1)
        self.assertEqual(result["median_chain_to_decision_seconds_for_covered"], 160)

    def test_invalid_cutoff_is_rejected(self):
        with self.assertRaises(ValueError):
            quote_coverage([], [], cutoff=0)


class V3BaselineTests(unittest.TestCase):
    def test_v2_overlap_and_cloned_delays_are_exposed(self):
        fill = {
            "side": "BUY", "signature": "TX_PRIVATE_1",
            "wallet": "WALLET_PRIVATE_A", "mint": "MINT_PRIVATE_X",
            "signal_to_fill_seconds": 134,
        }
        base = {
            "kind": "YATL_SMART_MONEY_PAPER_ONLY", "polls": 210,
            "unique_signals_seen": 25,
            "wallets_blind": ["WALLET_PRIVATE_A", "WALLET_PRIVATE_B"],
            "wallets_smart": ["WALLET_PRIVATE_B", "WALLET_PRIVATE_C"],
            "portfolios": [
                {"id": f"blind_{d}s", "equity_usd": "953.25",
                 "halted": True, "fills": [fill]} for d in (1, 3, 10)
            ],
        }
        r = audit_v2_report(base)
        self.assertEqual(r["cohort_wallet_overlap_count"], 1)
        self.assertEqual(r["paper_fill_rows_including_clones_and_risk_exits"], 3)
        self.assertEqual(r["unique_underlying_buy_sell_signals_with_fill"], 1)
        self.assertEqual(r["median_observed_signal_to_fill_seconds"], 134)
        self.assertTrue(r["identical_1_3_10s_outcomes"]["blind"])
        self.assertNotIn("WALLET_PRIVATE", json.dumps(r))

    def test_cli_offline_output_redacted_and_refuses_source_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            screened = root / "screened.json"
            report = root / "report.json"
            outfile = root / "v3_summary.json"
            screened.write_text(json.dumps([eligible("WALLET_PRIVATE_A")]))
            report.write_text(json.dumps({
                "kind": "YATL_SMART_MONEY_PAPER_ONLY", "polls": 1,
                "wallets_blind": ["WALLET_PRIVATE_A"],
                "wallets_smart": [], "portfolios": [],
            }))
            result = run(screened=screened, report=report, cutoff=1500)
            self.assertEqual(result["forward_quote_coverage"]["status"], "not_evaluated")
            self.assertNotIn("WALLET_PRIVATE", json.dumps(result))
            main(["--screened", str(screened), "--report", str(report),
                  "--cutoff", "1500", "--output", str(outfile)])
            self.assertTrue(outfile.exists())
            self.assertNotIn("WALLET_PRIVATE", outfile.read_text())
            with self.assertRaises(ValueError):
                main(["--screened", str(screened), "--output", str(report)])
            with self.assertRaises(ValueError):
                main(["--screened", str(screened), "--output", str(screened)])


if __name__ == "__main__":
    unittest.main()
