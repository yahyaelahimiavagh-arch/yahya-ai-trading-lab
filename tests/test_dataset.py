import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from yatl.__main__ import main
from yatl.data import CandleStore, DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from yatl.data.dataset import DatasetError, build_datasets, manifest_json, write_manifest
from yatl.data.history import HistoricalBatch


SERVER_TIME = 1_700_000_123_456
DAY = 86_400_000


def row(open_time, duration):
    return [open_time, "26000.0", "26250.0", "25900.0", "26100.0", "123.0",
            open_time + duration - 1, "3210000.0", 100, "60.0", "1560000.0", "0"]


def batch_for_call(client, symbol, interval, start, end, **kwargs):
    duration = INTERVAL_MILLISECONDS[interval]
    known = set(kwargs["known_open_times"])
    rows = tuple(tuple(row(value, duration)) for value in range(start, end, duration)
                 if value not in known)
    return HistoricalBatch(symbol=symbol, interval=interval, start_time_ms=start,
                           end_time_ms=end, pages=1 if rows else 0, rows=rows,
                           skipped_known_rows=len(known))


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.server_time.return_value = SERVER_TIME

    @patch("yatl.data.dataset.download_range", side_effect=batch_for_call)
    def test_builds_six_complete_closed_public_datasets(self, download):
        with CandleStore(":memory:") as store:
            manifest = build_datasets(store, client=self.client, days=1)
            expected_total = sum(DAY // duration for duration in INTERVAL_MILLISECONDS.values()) * 2
            self.assertEqual(store.count(), expected_total)
        self.assertEqual(len(manifest["datasets"]), 6)
        self.assertEqual(download.call_count, 6)
        self.assertTrue(all(item["backtest_ready"] for item in manifest["datasets"]))
        self.assertTrue(all(item["open_rows"] == 0 for item in manifest["datasets"]))
        self.assertEqual({item["symbol"] for item in manifest["datasets"]}, set(SYMBOLS))

    @patch("yatl.data.dataset.download_range", side_effect=batch_for_call)
    def test_repeated_build_is_idempotent(self, download):
        with CandleStore(":memory:") as store:
            first = build_datasets(store, client=self.client, days=1)
            count = store.count()
            second = build_datasets(store, client=self.client, days=1)
            self.assertEqual(store.count(), count)
        self.assertEqual(first, second)
        second_calls = download.call_args_list[6:]
        self.assertTrue(all(call.kwargs["known_open_times"] for call in second_calls))

    def test_invalid_store_and_day_bounds_fail_closed(self):
        for days in (0, 366, True):
            with self.subTest(days=days), self.assertRaises(DatasetError):
                build_datasets(MagicMock(spec=CandleStore), client=self.client, days=days)
        with self.assertRaises(DatasetError):
            build_datasets(object(), client=self.client, days=1)

    @patch("yatl.data.dataset.build_health_report")
    @patch("yatl.data.dataset.download_range", side_effect=batch_for_call)
    def test_unhealthy_dataset_aborts(self, download, health):
        health.return_value = MagicMock(backtest_ready=False, open_rows=0)
        with CandleStore(":memory:") as store:
            with self.assertRaisesRegex(DatasetError, "health gate"):
                build_datasets(store, client=self.client, days=1)

    def test_manifest_json_is_stable_and_path_is_atomic(self):
        manifest = {"schema_version": 1, "datasets": [], "generated_at_ms": SERVER_TIME}
        encoded = manifest_json(manifest)
        self.assertEqual(encoded, manifest_json(manifest))
        self.assertTrue(encoded.endswith("\n"))
        root = Path(os.environ.get("YATL_TEST_TEMP_DIR", os.environ.get("TEMP", ".")))
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"manifest-{uuid4().hex}.json"
        try:
            self.assertEqual(write_manifest(manifest, path), path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), manifest)
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_manifest_fails_without_output(self):
        with self.assertRaises(DatasetError):
            manifest_json({})
        with self.assertRaises(DatasetError):
            write_manifest({}, "ignored.json")

    @patch("yatl.__main__.write_manifest", return_value=Path("manifest.json"))
    @patch("yatl.__main__.build_datasets")
    @patch("yatl.__main__.CandleStore")
    @patch("sys.argv", ["yatl", "dataset-build", "--days", "30"])
    def test_cli_prints_only_safe_dataset_summary(self, store_type, build, write):
        store_type.return_value.__enter__.return_value = MagicMock()
        build.return_value = {
            "datasets": [{"symbol": symbol, "interval": interval, "total_rows": 10,
                          "backtest_ready": True}
                         for symbol in SYMBOLS for interval in INTERVAL_MILLISECONDS],
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("6 public-real closed datasets", text)
        self.assertIn("No credentials", text)
        self.assertIn("No execution", text)
        build.assert_called_once()
        write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
