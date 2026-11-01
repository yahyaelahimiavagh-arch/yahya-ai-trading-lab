"""Offline regression tests for the six-wallet Hostinger read-only adapter."""
import json
import unittest

from research.smart_money_lab.paper_copy_hostinger_status import build_paper_copy_status


class PaperCopyHostingerStatusTests(unittest.TestCase):
    def fixture(self):
        return {
            "kind": "YATL_FORWARD_COPY_PAPER_REPORT",
            "started_at": 10000, "finish_at": 31600, "as_of": 10300,
            "experiment_status": "running", "watched_wallet_count": 6,
            "last_polls_recent_count": 6, "cycles": 1, "source_signals": 1,
            "wallets": ["SENSITIVE_WALLET_NEVER_EXPORTED"],
            "paper_account": {
                "cash_usd": "970", "equity_usd": "999.1", "halted": False,
                "open_positions": [{"wallet": "SENSITIVE_WALLET_NEVER_EXPORTED"}],
                "rejected": {"illiquid": 2},
                "fills": [{"side": "BUY", "time": 10300, "usd_price": "2.5",
                           "wallet": "SENSITIVE_WALLET_NEVER_EXPORTED",
                           "mint": "ABCDEFGHIJKLMN1234567890PQRSTUVWXYZ",
                           "signature": "SENSITIVE_SIGNATURE_NEVER_EXPORTED"}],
            },
            "skips": {"historical_ignored": 595, "parse_ambiguous_legs": 4},
        }

    def test_new_report_to_existing_hostinger_schema(self):
        result = build_paper_copy_status(self.fixture(), {"calls": 2821}, now=10301)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["wallets_followed"], 6)
        self.assertEqual(result["polls"], 1)
        self.assertEqual(result["paper_fills"], 1)
        self.assertEqual(result["portfolios"][0]["id"], "paper_copy")
        self.assertEqual(result["portfolios"][0]["pnl_usd"], "-0.9000")
        self.assertEqual(result["api_requests_reserved"], 2821)
        self.assertEqual(result["skips"]["historical_rows_ignored"], 595)
        encoded = json.dumps(result)
        self.assertNotIn("SENSITIVE_WALLET", encoded)
        self.assertNotIn("SENSITIVE_SIGNATURE", encoded)

    def test_five_minute_polling_does_not_instantly_look_stale(self):
        r = self.fixture()
        self.assertEqual(build_paper_copy_status(r, None, now=10800)["status"], "running")
        self.assertEqual(build_paper_copy_status(r, None, now=11000)["status"], "stale")

    def test_completed_or_unpriced_is_never_falsely_profitable(self):
        r = self.fixture()
        r["experiment_status"] = "completed"
        r["paper_account"]["equity_usd"] = None
        status = build_paper_copy_status(r, None, now=50000)
        self.assertEqual(status["status"], "completed")
        self.assertIsNone(status["portfolios"][0]["pnl_usd"])
        self.assertIsNone(status["portfolios"][0]["equity_usd"])

    def test_invalid_report_remains_initializing(self):
        r = self.fixture()
        r["kind"] = "UNKNOWN"
        status = build_paper_copy_status(r, None, now=10301)
        self.assertEqual(status["status"], "initializing")
        self.assertEqual(status["portfolios"], [])


if __name__ == "__main__":
    unittest.main()
