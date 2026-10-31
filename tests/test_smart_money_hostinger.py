"""Offline tests for Hostinger static export; no network or orders."""
from __future__ import annotations
import json
import tempfile
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

    def test_sftp_publisher_keeps_remote_html_and_json_web_readable(self):
        script = (Path(__file__).resolve().parents[1] /
                  "ops/publish-sml-hostinger.sh").read_text(encoding="utf-8")
        self.assertIn('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/index.html"', script)
        self.assertEqual(
            script.count('chmod 644 "$HOSTINGER_SFTP_REMOTE_DIR/status.json"'), 2
        )
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
