try:
    import fcntl
except ImportError:
    fcntl = None
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from yatl.data import BINANCE_PUBLIC_BASE_URL, INTERVAL_MILLISECONDS, BinancePublicRestClient
from yatl.validation.cli import snapshot_json
from yatl.validation.collector_cli import (
    CollectorCode,
    CollectorError,
    EXIT_NOT_READY,
    collect_once,
    main,
)
from yatl.validation.forward_store import ForwardCandleStore
from yatl.validation.ingestion import snapshot_from_record
from yatl.validation.window import ForwardWindowSeal


class MockPublicClient(BinancePublicRestClient):
    def __init__(self, server_time_ms):
        super().__init__(base_url=BINANCE_PUBLIC_BASE_URL)
        self._server_time_ms = server_time_ms
        self.server_time_calls = 0
        self.kline_calls = 0

    def server_time(self):
        self.server_time_calls += 1
        return self._server_time_ms

    def klines(self, symbol, interval, *, limit=1000, start_time=None, end_time=None):
        self.kline_calls += 1
        duration = INTERVAL_MILLISECONDS[interval]
        rows = []
        cursor = start_time
        while cursor is not None and end_time is not None and cursor <= end_time:
            rows.append([
                cursor,
                "100",
                "101",
                "99",
                "100",
                "1",
                cursor + duration - 1,
                "100",
                10,
                "0",
                "0",
                "0",
            ])
            cursor += duration
            if len(rows) >= limit:
                break
        return rows


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "p10-forward.sqlite3"
        self.snapshot = self.root / "snapshot.json"
        self.window = ForwardWindowSeal()

    def tearDown(self):
        self.temp.cleanup()

    def client_after_hours(self, hours):
        return MockPublicClient(
            self.window.forward_window_start_ms + hours * 3_600_000 + 1_234
        )

    def test_collect_once_creates_canonical_snapshot_and_store(self):
        record = collect_once(
            self.database,
            self.snapshot,
            client=self.client_after_hours(8),
        )
        self.assertEqual(record["code"], CollectorCode.COLLECTED.value)
        self.assertTrue(record["quality_pass"])
        self.assertTrue(record["paper_only"])
        self.assertEqual(record["live_master_lock"], "OFF")
        self.assertFalse(record["trade_permission"])
        self.assertFalse(record["order_endpoint"])
        self.assertFalse(record["ai_direct_execution"])
        self.assertEqual(record["dataset_count"], 6)
        self.assertEqual(record["store_count"], 84)
        restored = snapshot_from_record(
            json.loads(self.snapshot.read_text(encoding="utf-8"))
        )
        self.assertEqual(self.snapshot.read_text(encoding="utf-8"), snapshot_json(restored))
        self.assertEqual(restored.snapshot_sha256, record["snapshot_sha256"])
        with ForwardCandleStore(self.database) as store:
            self.assertEqual(store.count(), 84)

    def test_repeated_same_cutoff_is_idempotent(self):
        client = self.client_after_hours(8)
        first = collect_once(self.database, self.snapshot, client=client)
        bytes_before = self.snapshot.read_bytes()
        second = collect_once(
            self.database,
            self.snapshot,
            client=self.client_after_hours(8),
        )
        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertEqual(bytes_before, self.snapshot.read_bytes())
        self.assertEqual(second["store_count"], 84)

    def test_later_collection_backfills_and_advances_snapshot(self):
        first = collect_once(
            self.database,
            self.snapshot,
            client=self.client_after_hours(8),
        )
        second = collect_once(
            self.database,
            self.snapshot,
            client=self.client_after_hours(12),
        )
        self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertGreater(second["generated_at_ms"], first["generated_at_ms"])
        self.assertEqual(second["store_count"], 126)
        with ForwardCandleStore(self.database) as store:
            self.assertEqual(store.count(), 126)

    def test_snapshot_rollback_is_rejected_and_existing_snapshot_remains(self):
        collect_once(
            self.database,
            self.snapshot,
            client=self.client_after_hours(12),
        )
        before = self.snapshot.read_bytes()
        with self.assertRaises(CollectorError) as caught:
            collect_once(
                self.database,
                self.snapshot,
                client=self.client_after_hours(8),
            )
        self.assertIs(caught.exception.code, CollectorCode.SOURCE_REJECTED)
        self.assertEqual(before, self.snapshot.read_bytes())

    def test_corrupted_existing_snapshot_rejects_before_network(self):
        self.snapshot.write_text("{}\n", encoding="utf-8")
        client = self.client_after_hours(8)
        with self.assertRaises(CollectorError) as caught:
            collect_once(self.database, self.snapshot, client=client)
        self.assertIs(caught.exception.code, CollectorCode.SOURCE_REJECTED)
        self.assertEqual(client.server_time_calls, 0)
        self.assertEqual(client.kline_calls, 0)

    def test_snapshot_symlink_is_rejected(self):
        victim = self.root / "victim.json"
        victim.write_text("{}\n", encoding="utf-8")
        self.snapshot.symlink_to(victim)
        with self.assertRaises(CollectorError) as caught:
            collect_once(
                self.database,
                self.snapshot,
                client=self.client_after_hours(8),
            )
        self.assertIs(caught.exception.code, CollectorCode.SOURCE_REJECTED)

    def test_database_symlink_is_rejected(self):
        victim = self.root / "victim.sqlite3"
        victim.write_bytes(b"x")
        self.database.symlink_to(victim)
        with self.assertRaises(CollectorError) as caught:
            collect_once(
                self.database,
                self.snapshot,
                client=self.client_after_hours(8),
            )
        self.assertIs(caught.exception.code, CollectorCode.SOURCE_REJECTED)

    @unittest.skipIf(fcntl is None, "collector advisory lock is Linux-only")
    def test_lock_blocks_overlapping_collector(self):
        lock_path = self.root / ".snapshot.json.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(CollectorError) as caught:
                collect_once(
                    self.database,
                    self.snapshot,
                    client=self.client_after_hours(8),
                )
            self.assertIs(caught.exception.code, CollectorCode.ALREADY_RUNNING)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_before_first_closed_four_hour_bar_is_not_ready(self):
        client = self.client_after_hours(1)
        with self.assertRaises(CollectorError) as caught:
            collect_once(self.database, self.snapshot, client=client)
        self.assertIs(caught.exception.code, CollectorCode.NOT_READY)
        self.assertEqual(client.kline_calls, 0)

    def test_cli_not_ready_uses_stable_exit_and_redacted_output(self):
        client = self.client_after_hours(1)
        with patch(
            "yatl.validation.collector_cli.BinancePublicRestClient",
            return_value=client,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([
                    "--database",
                    str(self.database),
                    "--snapshot",
                    str(self.snapshot),
                ])
        self.assertEqual(code, EXIT_NOT_READY)
        record = json.loads(output.getvalue())
        self.assertEqual(record["code"], CollectorCode.NOT_READY.value)
        self.assertNotIn(str(self.root), output.getvalue())

    def test_cli_success_output_contains_no_local_paths(self):
        client = self.client_after_hours(8)
        with patch(
            "yatl.validation.collector_cli.BinancePublicRestClient",
            return_value=client,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([
                    "--database",
                    str(self.database),
                    "--snapshot",
                    str(self.snapshot),
                ])
        self.assertEqual(code, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["code"], CollectorCode.COLLECTED.value)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertNotIn("api_key", output.getvalue().casefold())
        self.assertNotIn("api_secret", output.getvalue().casefold())

    def test_collector_source_has_no_execution_account_risk_or_secret_capability(self):
        import inspect
        import yatl.validation.collector_cli as collector

        source = inspect.getsource(collector)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "os.environ",
            "os.getenv",
            "dotenv",
            "API_KEY",
            "API_SECRET",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "input(",
            "eval(",
            "exec(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
