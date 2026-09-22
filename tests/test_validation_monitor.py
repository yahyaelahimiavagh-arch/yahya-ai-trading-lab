import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yatl.notifications.runner import load_notification_source
from yatl.validation import monitor


OBSERVED_AT_MS = 1_800_000_000_000


def not_ready():
    return {
        "schema_version": 1,
        "command": "summary",
        "ok": False,
        "code": "NOT_READY",
        "reason": "FORWARD_WARMUP_NOT_COMPLETE",
        "ingestion_snapshot_sha256": "1" * 64,
        "generated_at_ms": OBSERVED_AT_MS,
        "database_snapshot_sha256": "2" * 64,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
    }


def ready():
    return {
        "schema_version": 1,
        "command": "summary",
        "ok": True,
        "code": "SUMMARY_READY",
        "ingestion_snapshot_sha256": "3" * 64,
        "database_snapshot_sha256": "4" * 64,
        "paper_run_sha256": "5" * 64,
        "economics_sha256": "6" * 64,
        "gate_sha256": "7" * 64,
        "sample_status": "INSUFFICIENT_DATA",
        "disposition": "INSUFFICIENT_DATA",
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
        "observed_days": "10",
        "observation_start_ms": OBSERVED_AT_MS - 86_400_000,
        "observation_end_ms": OBSERVED_AT_MS,
        "completed_trades": 3,
        "net_pnl_after_costs_quote": "-5.25",
        "net_return_after_costs": "-0.0002625",
        "profit_factor_after_costs": "0.90",
        "maximum_validation_drawdown_fraction": "0.012",
        "criteria": {
            "NET_PNL_AFTER_COSTS": "INSUFFICIENT_DATA",
            "MAX_DRAWDOWN": "PASS",
            "SAMPLE_SIZE": "INSUFFICIENT_DATA",
            "CONSISTENCY": "INSUFFICIENT_DATA",
            "REGIME_STABILITY": "INSUFFICIENT_DATA",
            "FAILURE_RECOVERY": "PASS",
            "RISK_CONTROLS": "PASS",
        },
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "completed_trades": 2,
                "net_pnl_after_costs_quote": "-3.00",
                "net_return_after_costs": "-0.0003",
                "open_positions": 0,
            },
            {
                "symbol": "ETHUSDT",
                "completed_trades": 1,
                "net_pnl_after_costs_quote": "-2.25",
                "net_return_after_costs": "-0.000225",
                "open_positions": 0,
            },
        ],
    }


class P10MonitorTests(unittest.TestCase):
    def test_warmup_dashboard_is_locked_network_free_and_deterministic(self):
        first = monitor.render_dashboard(not_ready())
        second = monitor.render_dashboard(not_ready())
        self.assertEqual(first, second)
        self.assertIn("P10 warm-up in progress", first)
        self.assertIn("P11 LOCKED", first)
        self.assertNotIn("http://", first)
        self.assertNotIn("https://", first)
        self.assertNotIn("<script", first.casefold())

    def test_ready_dashboard_uses_exact_summary_values(self):
        document = monitor.render_dashboard(ready())
        self.assertIn("INSUFFICIENT_DATA", document)
        self.assertIn("-0.0002625", document)
        self.assertIn("BTCUSDT", document)
        self.assertIn("ETHUSDT", document)
        self.assertIn("MAX_DRAWDOWN", document)

    def test_monitor_record_never_upgrades_safety(self):
        record = monitor.build_monitor_record(not_ready())
        self.assertTrue(record["paper_only"])
        self.assertEqual(record["live_master_lock"], "OFF")
        self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(record["p11_unlocked"])
        self.assertEqual(record["state"], "WARMUP")

    def test_notification_file_is_canonical_and_runner_compatible(self):
        batch, encoded = monitor.notification_json(not_ready(), "BTCUSDT")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notification.json"
            source.write_text(encoded, encoding="utf-8", newline="")
            loaded, raw = load_notification_source(
                source,
                batch.batch_sha256,
                "BTCUSDT",
            )
            self.assertEqual(loaded, batch)
            self.assertEqual(raw, encoded.encode("utf-8"))

    def test_dashboard_atomic_replace_and_no_source_path_in_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "index.html"
            output.write_text("old", encoding="utf-8")
            with mock.patch.object(monitor, "validation_summary", return_value=not_ready()):
                result = monitor.build_dashboard(
                    "PRIVATE_DB",
                    "PRIVATE_SNAPSHOT",
                    output,
                )
            self.assertEqual(result["code"], "DASHBOARD_UPDATED")
            self.assertIn("P10 warm-up in progress", output.read_text(encoding="utf-8"))
            encoded = json.dumps(result)
            self.assertNotIn("PRIVATE_DB", encoded)
            self.assertNotIn("PRIVATE_SNAPSHOT", encoded)
            self.assertFalse(any(item.name.endswith(".tmp") for item in root.iterdir()))

    def test_notification_atomic_replace_and_provenance_changes_with_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "btc.json"
            with mock.patch.object(monitor, "validation_summary", return_value=not_ready()):
                first = monitor.build_notification("db", "snapshot", "BTCUSDT", output)
            before = output.read_bytes()
            changed = not_ready()
            changed["generated_at_ms"] += 1
            with mock.patch.object(monitor, "validation_summary", return_value=changed):
                second = monitor.build_notification("db", "snapshot", "BTCUSDT", output)
            self.assertNotEqual(first["batch_sha256"], second["batch_sha256"])
            self.assertNotEqual(before, output.read_bytes())

    def test_smuggled_or_unlocked_summary_is_rejected(self):
        item = not_ready()
        item["p11_unlocked"] = True
        with self.assertRaises(monitor.P10MonitorError):
            monitor.render_dashboard(item)
        item = not_ready()
        item["secret"] = "x"
        with self.assertRaises(monitor.P10MonitorError):
            monitor.notification_json(item, "ETHUSDT")

    def test_monitor_source_has_no_network_credential_or_execution_capability(self):
        source = inspect.getsource(monitor)
        for forbidden in (
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "os.getenv",
            "os.environ",
            "api.telegram",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
