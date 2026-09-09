import contextlib
import io
import os
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from yatl.__main__ import main
from yatl.data import Candle, CandleStore, ClosedCandleConflict, DATA_SOURCE, StorageError
from yatl.data.storage import MAX_BATCH_SIZE, SCHEMA_VERSION


OPEN_TIME = 1_699_999_200_000


def candle(*, symbol="BTCUSDT", open_time=OPEN_TIME, closed=False):
    return Candle(
        source=DATA_SOURCE,
        symbol=symbol,
        interval="1h",
        open_time_ms=open_time,
        close_time_ms=open_time + 3_600_000 - 1,
        open="26000.10000000",
        high="26250.00000000",
        low="25900.00000000",
        close="26100.25000000",
        base_volume="123.45000000",
        quote_volume="3210000.12345678",
        trade_count=1234,
        is_closed=closed,
    )


class CandleStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_root = os.environ.get("YATL_TEST_TEMP_DIR")
        if cls.temp_root is not None:
            Path(cls.temp_root).mkdir(parents=True, exist_ok=True)

    def database_path(self):
        root = Path(self.temp_root) if self.temp_root else Path(os.environ.get("TEMP", "."))
        return root / f"test-storage-{uuid4().hex}.sqlite3"

    def remove_database(self, path):
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
            candidate.unlink(missing_ok=True)

    def test_fresh_schema_insert_and_lossless_round_trip(self):
        value = candle(closed=True)
        with CandleStore(":memory:") as store:
            self.assertEqual(store.schema_version(), SCHEMA_VERSION)
            self.assertEqual(store.write(value), "inserted")
            self.assertEqual(store.count(), 1)
            self.assertEqual(store.get(value.key), value)
            self.assertIsNone(store.get((DATA_SOURCE, "ETHUSDT", "1h", OPEN_TIME)))

    def test_identical_write_is_idempotent(self):
        value = candle(closed=True)
        with CandleStore(":memory:") as store:
            self.assertEqual(store.write(value), "inserted")
            self.assertEqual(store.write(value), "unchanged")
            self.assertEqual(store.count(), 1)

    def test_open_candle_can_update_once_and_finalize(self):
        initial = candle()
        updated = replace(initial, close="26150.25000000", trade_count=1240)
        finalized = replace(updated, is_closed=True)
        with CandleStore(":memory:") as store:
            self.assertEqual(store.write(initial), "inserted")
            self.assertEqual(store.write(updated), "updated")
            self.assertEqual(store.write(finalized), "finalized")
            self.assertEqual(store.get(initial.key), finalized)

    def test_closed_candle_rewrite_and_downgrade_fail_closed(self):
        final = candle(closed=True)
        conflicting = replace(final, close="26150.25000000")
        downgraded = replace(final, is_closed=False)
        with CandleStore(":memory:") as store:
            store.write(final)
            for value in (conflicting, downgraded):
                with self.subTest(value=value), self.assertRaises(ClosedCandleConflict):
                    store.write(value)
            self.assertEqual(store.get(final.key), final)

    def test_batch_rolls_back_all_rows_on_conflict(self):
        final = candle(closed=True)
        next_value = candle(symbol="ETHUSDT")
        conflict = replace(final, close="26150.25000000")
        with CandleStore(":memory:") as store:
            store.write(final)
            with self.assertRaises(ClosedCandleConflict):
                store.write_many([next_value, conflict])
            self.assertEqual(store.count(), 1)
            self.assertIsNone(store.get(next_value.key))

    def test_file_database_reopens_with_data_and_schema(self):
        path = self.database_path()
        try:
            value = candle(closed=True)
            with CandleStore(path) as store:
                store.write(value)
            with CandleStore(path) as store:
                self.assertEqual(store.schema_version(), SCHEMA_VERSION)
                self.assertEqual(store.get(value.key), value)
        finally:
            self.remove_database(path)

    def test_known_open_times_are_filtered_and_ordered(self):
        first = candle()
        second = candle(open_time=OPEN_TIME + 3_600_000)
        other = candle(symbol="ETHUSDT")
        with CandleStore(":memory:") as store:
            store.write_many([second, other, first])
            self.assertEqual(store.known_open_times(
                DATA_SOURCE, "BTCUSDT", "1h", OPEN_TIME, OPEN_TIME + 7_200_000,
            ), (OPEN_TIME, OPEN_TIME + 3_600_000))

    def test_invalid_values_and_batch_sizes_fail_closed(self):
        with CandleStore(":memory:") as store:
            for value in (None, {}, "candle"):
                with self.subTest(value=value), self.assertRaises(StorageError):
                    store.write(value)
            for batch in (None, [], (), [candle()] * (MAX_BATCH_SIZE + 1)):
                with self.subTest(length=getattr(batch, "__len__", lambda: None)()):
                    with self.assertRaises(StorageError):
                        store.write_many(batch)
            for key in (None, (), (1, 2, 3), [DATA_SOURCE, "BTCUSDT", "1h", OPEN_TIME]):
                with self.subTest(key=key), self.assertRaises(StorageError):
                    store.get(key)

    def test_newer_schema_is_rejected(self):
        path = self.database_path()
        try:
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (?)",
                               (SCHEMA_VERSION + 1,))
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(StorageError, "newer"):
                CandleStore(path)
        finally:
            self.remove_database(path)

    @patch("yatl.__main__._storage_runtime_check")
    @patch("sys.argv", ["yatl", "storage-check"])
    def test_runtime_cli_reports_safe_lifecycle(self, check):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        check.assert_called_once_with()
        text = output.getvalue()
        self.assertIn("migration, idempotency, finalization, reopen", text)
        self.assertIn("No credentials", text)
        self.assertIn("No execution endpoints", text)


if __name__ == "__main__":
    unittest.main()
