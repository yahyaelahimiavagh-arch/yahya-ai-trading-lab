"""Offline and loopback-only validation for the standalone SML monitor."""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from research.smart_money_lab.live_monitor import build_status, make_handler, _read_json


def sample_report(now=1793466000):
    return {
        "kind": "YATL_SMART_MONEY_PAPER_ONLY",
        "selection_mode": "exploratory_unvetted",
        "start_at": now - 90, "as_of": now,
        "polls": 12, "unique_signals_seen": 288,
        "feed_complete": True,
        "wallets_blind": ["wallet-secret-AAA", "wallet-secret-BBB"],
        "wallets_smart": ["wallet-secret-BBB"],
        "skips": {"unparsed_or_unsupported": 240, "provider_failure": 0},
        "portfolios": [
            {"id": "blind_1s", "cash_usd": "989.50",
             "equity_usd": "1001.24", "open_positions": [{"mint": "sensitive-mint"}],
             "fills": [{"side": "BUY", "wallet": "wallet-secret-AAA",
                        "signature": "private-irrelevant-value",
                        "mint": "A" * 35, "time": now - 10,
                        "usd_price": "0.5"}],
             "rejected": {"illiquid": 2}, "halted": False},
            {"id": "smart_10s", "cash_usd": "1000",
             "equity_usd": None, "open_positions": [],
             "fills": [], "rejected": {}, "halted": False},
        ],
        "key": "this_must_never_be_sent",
    }


class MonitorReportTests(unittest.TestCase):
    def test_whitelist_no_leak_and_preserve_unpriced(self):
        status = build_status(sample_report(), {"calls": 391}, now=1793466005)
        text = json.dumps(status)
        for forbidden in ("wallet-secret", "sensitive-mint", "private-irrelevant",
                          "this_must_never_be_sent"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(status["status"], "running")
        self.assertEqual(status["mode"], "exploratory_unvetted")
        self.assertEqual(status["api_requests_reserved"], 391)
        self.assertEqual(status["paper_fills"], 1)
        self.assertEqual(status["open_positions"], 1)
        self.assertEqual(status["wallets_followed"], 2)
        self.assertEqual(status["portfolios"][0]["pnl_usd"], "1.2400")
        self.assertIsNone(status["portfolios"][1]["equity_usd"])

    def test_monitor_exposes_aggregate_parse_reasons_only(self):
        report = sample_report()
        report["skips"]["parse_ambiguous_legs"] = 7
        report["skips"]["parse_missing_swap_event"] = 11
        report["skips"]["historical_rows_ignored"] = 120
        result = build_status(report, {"calls": 500}, now=1793466005)
        self.assertEqual(result["skips"]["parse_ambiguous_legs"], 7)
        self.assertEqual(result["skips"]["parse_missing_swap_event"], 11)
        self.assertEqual(result["skips"]["historical_rows_ignored"], 120)
        self.assertNotIn("wallet-secret", json.dumps(result))

    def test_feed_health_degrades_live_status_without_wallet_leak(self):
        report = sample_report()
        report["feed_health"] = {
            "state": "collector_stopped", "collector_alive": False,
            "expected_wallets": 6, "recent_wallets": 0,
            "oldest_poll_age_seconds": 600,
            "sensitive_wallet": "wallet-secret-AAA",
            "last_polls": {"wallet-secret-AAA": 1793459999},
        }
        report["feed_complete"] = False
        output = build_status(report, {"calls": 612}, now=1793466005)
        self.assertEqual(output["status"], "degraded")
        self.assertEqual(output["feed_health"]["state"], "collector_stopped")
        self.assertEqual(output["feed_health"]["expected_wallets"], 6)
        self.assertEqual(output["feed_health"]["oldest_poll_age_seconds"], 600)
        self.assertNotIn("wallet-secret", json.dumps(output))
        report["feed_health"]["state"] = "polls_stale"
        self.assertEqual(build_status(report, {}, now=1793466005)["status"],
                         "degraded")

    def test_healthy_heartbeat_and_old_report_backward_compatibility(self):
        report = sample_report()
        output = build_status(report, {}, now=1793466005)
        self.assertEqual(output["status"], "running")
        self.assertEqual(output["feed_health"]["state"], "unknown")
        report["feed_health"] = {
            "state": "healthy", "collector_alive": True,
            "expected_wallets": 6, "recent_wallets": 6,
            "oldest_poll_age_seconds": 176,
        }
        output = build_status(report, {}, now=1793466005)
        self.assertEqual(output["status"], "running")
        self.assertEqual(output["feed_health"]["recent_wallets"], 6)

    def test_staleness_and_initialization(self):
        report = sample_report()
        self.assertEqual(build_status(report, None, now=1793466400)["status"], "stale")
        self.assertEqual(build_status(None, None)["status"], "initializing")
        self.assertEqual(build_status(report, {"calls": "bad"}, now=1793466000)
                         ["api_requests_reserved"], None)

    def test_atomic_report_reader_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "report.json"
            self.assertIsNone(_read_json(file))
            file.write_text("not-json", encoding="utf-8")
            self.assertIsNone(_read_json(file))
            file.write_text(json.dumps(sample_report()), encoding="utf-8")
            self.assertIsNotNone(_read_json(file))
            self.assertTrue(file.exists())

    def test_api_serves_only_filtered_status_no_write_routes(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            (data / "report.json").write_text(json.dumps(sample_report()),
                                              encoding="utf-8")
            (data / "helius_budget.json").write_text('{"calls": 400}',
                                                     encoding="utf-8")
            with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(data)) as srv:
                thread = threading.Thread(target=srv.serve_forever, daemon=True)
                thread.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port,
                                                      timeout=4)
                    conn.request("GET", "/api/status")
                    response = conn.getresponse()
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader("Cache-Control"), "no-store")
                    self.assertEqual(json.loads(body)["api_requests_reserved"], 400)
                    self.assertNotIn("wallet-secret", body)
                    conn.close()

                    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port,
                                                      timeout=4)
                    conn.request("GET", "/")
                    response = conn.getresponse()
                    html = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("YATL", html)
                    self.assertIn("fetch(", html)
                    conn.close()

                    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port,
                                                      timeout=4)
                    conn.request("POST", "/api/status", body="bad")
                    response = conn.getresponse()
                    response.read()
                    self.assertEqual(response.status, 405)
                    conn.close()
                finally:
                    srv.shutdown()
                    thread.join(timeout=4)


if __name__ == "__main__":
    unittest.main()
