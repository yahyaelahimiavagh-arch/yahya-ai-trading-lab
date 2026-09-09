import contextlib
import io
import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from yatl.__main__ import main
from yatl.backtest import (BacktestLoadError, BacktestSpec,
                           latest_spec_from_manifest, load_accepted_dataset)
from yatl.data import Candle, CandleStore, DATA_SOURCE, INTERVAL_MILLISECONDS


START = 1_699_977_600_000
END = START + 8 * 3_600_000


def make_candle(symbol, interval, opened, *, closed=True):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
                  "100", "110", "90", "105", "10", "1000", 20, closed)


class BacktestLoaderTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("YATL_TEST_TEMP_DIR", os.environ.get("TEMP", ".")))
        root.mkdir(parents=True, exist_ok=True)
        tag = uuid4().hex
        self.database = root / f"loader-{tag}.sqlite3"
        self.manifest_path = root / f"loader-{tag}.json"
        self.manifest = {
            "database_schema_version": 1,
            "generated_at_ms": END + 1,
            "datasets": [],
        }
        with CandleStore(self.database) as store:
            for symbol in ("BTCUSDT", "ETHUSDT"):
                for interval, duration in INTERVAL_MILLISECONDS.items():
                    rows = tuple(make_candle(symbol, interval, opened)
                                 for opened in range(START, END, duration))
                    store.write_many(rows)
                    self.manifest["datasets"].append({
                        "symbol": symbol, "interval": interval,
                        "requested_start_time_ms": START,
                        "requested_end_time_ms": END,
                        "total_rows": len(rows),
                    })
        self.write_manifest()
        self.spec = BacktestSpec("BTCUSDT", START + 4 * 3_600_000, END)

    def tearDown(self):
        self.manifest_path.unlink(missing_ok=True)
        self.database.unlink(missing_ok=True)
        Path(f"{self.database}-wal").unlink(missing_ok=True)
        Path(f"{self.database}-shm").unlink(missing_ok=True)

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    @patch("yatl.backtest.loader.audit_p1_manifest")
    def test_read_only_load_matches_manifest_and_hides_future(self, audit):
        before = self.database.read_bytes()
        dataset = load_accepted_dataset(self.database, self.manifest_path, self.spec)
        view = dataset.snapshot_at(self.spec.start_time_ms)
        self.assertEqual(dataset.spec, self.spec)
        self.assertTrue(all(item.close_time_ms < view.decision_time_ms
                            for values in (view.primary, view.context, view.regime)
                            for item in values))
        self.assertEqual(self.database.read_bytes(), before)
        audit.assert_called_once_with(self.manifest_path)

    @patch("yatl.backtest.loader.audit_p1_manifest")
    def test_missing_row_open_row_and_schema_mismatch_fail_closed(self, audit):
        mutations = (
            "DELETE FROM candles WHERE symbol='BTCUSDT' AND interval='1h'",
            "UPDATE candles SET is_closed=0 WHERE symbol='BTCUSDT' AND interval='1h'",
            "INSERT INTO schema_migrations(version) VALUES (2)",
        )
        for statement in mutations:
            with self.subTest(statement=statement):
                copy = self.database.with_name(f"{uuid4().hex}.sqlite3")
                copy.write_bytes(self.database.read_bytes())
                try:
                    with contextlib.closing(sqlite3.connect(copy)) as connection:
                        with connection:
                            connection.execute(statement)
                    with self.assertRaises(BacktestLoadError):
                        load_accepted_dataset(copy, self.manifest_path, self.spec)
                finally:
                    copy.unlink(missing_ok=True)

    @patch("yatl.backtest.loader.audit_p1_manifest")
    def test_range_identity_paths_and_snapshot_bounds_fail_closed(self, audit):
        outside = BacktestSpec("BTCUSDT", START, END + 3_600_000)
        with self.assertRaises(BacktestLoadError):
            load_accepted_dataset(self.database, self.manifest_path, outside)
        with self.assertRaises(BacktestLoadError):
            load_accepted_dataset("missing.sqlite3", self.manifest_path, self.spec)
        with self.assertRaises(BacktestLoadError):
            load_accepted_dataset(self.database, self.manifest_path, object())
        dataset = load_accepted_dataset(self.database, self.manifest_path, self.spec)
        for decision in (self.spec.start_time_ms - 1, self.spec.end_time_ms, True):
            with self.subTest(decision=decision), self.assertRaises(BacktestLoadError):
                dataset.snapshot_at(decision)

    @patch("yatl.backtest.loader.audit_p1_manifest")
    def test_latest_spec_uses_bounded_tail_with_regime_warmup(self, audit):
        spec = latest_spec_from_manifest(self.manifest_path, "ETHUSDT", hours=2)
        self.assertEqual((spec.start_time_ms, spec.end_time_ms),
                         (END - 2 * 3_600_000, END))
        for hours in (0, True, 24 * 365 + 1):
            with self.subTest(hours=hours), self.assertRaises(BacktestLoadError):
                latest_spec_from_manifest(self.manifest_path, "ETHUSDT", hours=hours)

    def test_manifest_audit_failure_is_normalized(self):
        with self.assertRaisesRegex(BacktestLoadError, "acceptance gate"):
            load_accepted_dataset(self.database, self.manifest_path, self.spec)

    @patch("yatl.__main__.load_accepted_dataset")
    @patch("yatl.__main__.latest_spec_from_manifest")
    @patch("sys.argv", ["yatl", "backtest-load-check"])
    def test_cli_reports_only_safe_read_summary(self, latest, load):
        latest.return_value = self.spec
        load.return_value = type("Loaded", (), {
            "primary": tuple(range(8)), "context": tuple(range(32)),
            "regime": tuple(range(2)),
            "snapshot_at": lambda value, decision: type("View", (), {
                "primary": tuple(range(4)), "context": tuple(range(16)),
                "regime": (1,),
            })(),
        })()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("accepted P1 dataset loaded read-only", text)
        self.assertIn("visible=4/16/1", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
