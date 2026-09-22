import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yatl.notifications.runner import NotifierRunnerCode, NotifierRunnerError
from yatl.validation import monitor_notify


OBSERVED_AT_MS = 1_800_000_000_000


def summary():
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


def delivered(symbol):
    return {
        "schema_version": 1,
        "runner_id": "P9_NOTIFIER_RUNNER_V1",
        "ok": True,
        "code": "DELIVERED",
        "symbol": symbol,
        "source_file_sha256": "a" * 64,
        "batch_sha256": "b" * 64,
        "notification_sha256": "c" * 64,
        "formatted_sha256": "d" * 64,
        "delivery_id": "e" * 64,
        "delivery_state_sha256": "f" * 64,
        "receipt_sha256": "1" * 64,
        "telegram_message_id": 10,
        "attempts": 1,
        "wait_seconds": [],
        "duplicate_suppressed": False,
        "source_unchanged": True,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }


class P10MonitorNotifyTests(unittest.TestCase):
    def test_reuses_p9_runner_once_per_symbol_with_separate_state(self):
        calls = []

        def fake_runner(source, batch_sha, state, symbol):
            self.assertTrue(Path(source).is_file())
            calls.append((batch_sha, Path(state).name, symbol))
            return delivered(symbol)

        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(
                    monitor_notify,
                    "validation_summary",
                    return_value=summary(),
                ),
                mock.patch.object(
                    monitor_notify,
                    "notifier_run",
                    side_effect=fake_runner,
                ),
            ):
                result = monitor_notify.send_monitor_notifications(
                    "db",
                    "snapshot",
                    directory,
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["code"], "DELIVERY_COMPLETE")
            self.assertEqual([item[2] for item in calls], ["BTCUSDT", "ETHUSDT"])
            self.assertEqual(
                [item[1] for item in calls],
                [
                    "telegram-btcusdt-state.json",
                    "telegram-ethusdt-state.json",
                ],
            )
            leftovers = [
                item.name
                for item in Path(directory).iterdir()
                if item.name.startswith(".p10-")
            ]
            self.assertEqual(leftovers, [])

    def test_delivery_rejection_is_bounded_and_other_symbol_still_runs(self):
        calls = []

        def fake_runner(source, batch_sha, state, symbol):
            calls.append(symbol)
            if symbol == "BTCUSDT":
                raise NotifierRunnerError(NotifierRunnerCode.CONFIG_REJECTED)
            return delivered(symbol)

        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(
                    monitor_notify,
                    "validation_summary",
                    return_value=summary(),
                ),
                mock.patch.object(
                    monitor_notify,
                    "notifier_run",
                    side_effect=fake_runner,
                ),
            ):
                result = monitor_notify.send_monitor_notifications(
                    "db",
                    "snapshot",
                    directory,
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "DELIVERY_REJECTED")
            self.assertEqual(calls, ["BTCUSDT", "ETHUSDT"])
            self.assertEqual(result["results"][0]["code"], "CONFIG_REJECTED")
            self.assertTrue(result["results"][1]["ok"])

    def test_state_directory_must_exist_and_not_be_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing"
            with self.assertRaises(monitor_notify.P10MonitorNotifyError):
                monitor_notify.send_monitor_notifications("db", "snapshot", missing)

            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(monitor_notify.P10MonitorNotifyError):
                monitor_notify.send_monitor_notifications("db", "snapshot", link)

    def test_wrapper_has_no_direct_telegram_or_execution_transport(self):
        source = inspect.getsource(monitor_notify)
        for forbidden in (
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "api.telegram.org",
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
