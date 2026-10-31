"""Offline tests for Hostinger static export; no network or orders."""
from __future__ import annotations
import json
import tempfile
import time
import unittest
from pathlib import Path
from research.smart_money_lab.hostinger_export import export, make_static_html


class HostingerStaticExportTests(unittest.TestCase):
    def test_static_template_replaces_only_status_fetch(self):
        src = 'const x = fetch("/api/status", {cache:"no-store"});'
        result = make_static_html(src)
        self.assertIn('fetch("./status.json"', result)
        with self.assertRaisesRegex(ValueError, "marker"):
            make_static_html("no fetch")

    def test_export_redacts_and_never_edits_originals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp, out = root / "in", root / "out"
            inp.mkdir()
            report = {
                "kind": "YATL_SMART_MONEY_PAPER_ONLY",
                "selection_mode": "exploratory_unvetted",
                "start_at": 1793465154, "as_of": 1793465500,
                "polls": 12, "unique_signals_seen": 288,
                "wallets_blind": ["private-wallet-AAA"],
                "wallets_smart": ["private-wallet-AAA"],
                "portfolios": [{"id": "blind_1s", "cash_usd": "1000",
                                "equity_usd": "1000", "fills": [],
                                "open_positions": [], "rejected": {}}],
                "sensitive_value": "HELIUS_SECRET_SHOULD_NOT_LEAK"
            }
            raw = json.dumps(report)
            (inp / "report.json").write_text(raw)
            (inp / "helius_budget.json").write_text('{"calls":391}')
            result = export(data_dir=inp, output_dir=out, include_html=True)
            sanitized = (out / "status.json").read_text()
            self.assertEqual(result["api_requests_reserved"], 391)
            self.assertNotIn("HELIUS_SECRET", sanitized)
            self.assertNotIn("private-wallet-AAA", sanitized)
            self.assertEqual(json.loads(sanitized)["mode"], "exploratory_unvetted")
            self.assertIn('fetch("./status.json"', (out / "index.html").read_text())
            self.assertEqual((inp / "report.json").read_text(), raw)
            self.assertFalse((inp / "index.html").exists())
            export(data_dir=inp, output_dir=out)
            self.assertTrue((out / "index.html").exists())
            with self.assertRaisesRegex(ValueError, "source data"):
                export(data_dir=inp, output_dir=inp)

    def test_v2_can_read_shared_helius_budget_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, out = root / "v2", root / "public"
            source.mkdir()
            (source / "report.json").write_text(json.dumps({
                "kind": "YATL_SMART_MONEY_PAPER_ONLY",
                "selection_mode": "exploratory_unvetted",
                "start_at": 1793465154, "as_of": 1793465500,
                "polls": 6, "portfolios": [], "wallets_blind": [],
                "wallets_smart": [],
            }))
            budget = root / "old-v1-budget.json"
            raw = '{"calls":611,"max_calls":5000}'
            budget.write_text(raw)
            result = export(data_dir=source, output_dir=out, budget_file=budget)
            self.assertEqual(result["api_requests_reserved"], 611)
            self.assertEqual(budget.read_text(), raw)
            self.assertFalse((source / "helius_budget.json").exists())

    def test_old_running_v2_uses_state_polls_to_detect_a_stalled_feed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, dst = root / "private", root / "public"
            src.mkdir()
            now = int(time.time())
            report = {
                "kind": "YATL_SMART_MONEY_PAPER_ONLY",
                "selection_mode": "exploratory_unvetted",
                "start_at": now - 3600, "as_of": now,
                "feed_complete": True, "portfolios": [],
                "wallets_blind": ["secret-wallet-a", "secret-wallet-b"],
                "wallets_smart": ["secret-wallet-b"]
            }
            (src / "report.json").write_text(json.dumps(report))
            (src / "state.json").write_text(json.dumps({
                "last_polls": {"secret-wallet-a": now - 800,
                               "secret-wallet-b": now - 10},
                "seen": ["private-signature"],
            }))
            result = export(data_dir=src, output_dir=dst)
            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["feed_health"]["state"], "polls_stale")
            self.assertIsNone(result["feed_health"]["collector_alive"])
            self.assertEqual(result["feed_health"]["recent_wallets"], 1)
            published = (dst / "status.json").read_text()
            for secret in ("secret-wallet", "private-signature", "last_polls"):
                self.assertNotIn(secret, published)
            self.assertTrue(report["feed_complete"])
            self.assertTrue(json.loads((src / "report.json").read_text())["feed_complete"])

            (src / "state.json").write_text(json.dumps({
                "last_polls": {"secret-wallet-a": now - 30,
                               "secret-wallet-b": now - 10},
            }))
            fresh = export(data_dir=src, output_dir=dst)
            self.assertEqual(fresh["status"], "running")
            self.assertEqual(fresh["feed_health"]["state"], "polls_recent")
            self.assertEqual(fresh["feed_health"]["recent_wallets"], 2)

    def test_new_observer_heartbeat_overrides_derived_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp, out = root / "source", root / "public"
            inp.mkdir()
            now = int(time.time())
            report = {
                "kind": "YATL_SMART_MONEY_PAPER_ONLY",
                "selection_mode": "exploratory_unvetted",
                "start_at": now - 1800, "as_of": now,
                "portfolios": [], "wallets_blind": ["secret-wallet-a"],
                "feed_health": {
                    "state": "collector_stopped", "collector_alive": False,
                    "recent_wallets": 0, "expected_wallets": 1,
                }
            }
            (inp / "report.json").write_text(json.dumps(report))
            (inp / "state.json").write_text(json.dumps({
                "last_polls": {"secret-wallet-a": now - 1}
            }))
            status = export(data_dir=inp, output_dir=out)
            self.assertEqual(status["status"], "degraded")
            self.assertEqual(status["feed_health"]["state"], "collector_stopped")

    def test_sftp_publisher_keeps_remote_html_and_json_web_readable(self):
        script = (Path(__file__).resolve().parents[1] /
                  "ops/publish-sml-hostinger.sh").read_text(encoding="utf-8")
        self.assertIn('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/index.html"', script)
        self.assertEqual(
            script.count('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json"'), 2
        )
        self.assertEqual(
            script.count('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"'), 2
        )
        self.assertLess(
            script.index('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"'),
            script.index('rename "$HOSTINGER_SFTP_REMOTE_DIR/status.json.tmp"')
        )
        self.assertIn('budget_args=(--budget-file "$YATL_HELIUS_BUDGET_FILE")', script)
        self.assertIn("StrictHostKeyChecking=yes", script)
        self.assertNotIn("0.0.0.0", script)

    def test_invalid_source_is_not_published_raw(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp, out = root / "data", root / "public"
            inp.mkdir()
            (inp / "report.json").write_text('not-json private-api-key', encoding="utf-8")
            result = export(data_dir=inp, output_dir=out)
            self.assertEqual(result["status"], "initializing")
            self.assertNotIn("private-api-key", (out / "status.json").read_text())


if __name__ == "__main__":
    unittest.main()
