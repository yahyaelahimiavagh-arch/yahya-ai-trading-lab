import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.data import (BinancePublicRestClient, CheckpointRebuildError,
                       rebuild_accepted_database)


class PublicCheckpointClient(BinancePublicRestClient):
    def __init__(self, *, empty=False):
        self.empty = empty

    def klines(self, symbol, interval, *, limit=500, start_time=None,
               end_time=None):
        if self.empty:
            return []
        duration = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[interval]
        stop = min(end_time + 1, start_time + limit * duration)
        return [[
            opened, "100", "101", "99", "100", "1",
            opened + duration - 1, "100", 1, "0", "0", "0",
        ] for opened in range(start_time, stop, duration)]


class CheckpointRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "accepted.sqlite3"
        self.manifest = Path("manifests/p1-market-data.json")

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_public_checkpoint_is_rebuilt_atomically(self):
        before = self.manifest.read_bytes()
        result = rebuild_accepted_database(
            self.database, self.manifest, client=PublicCheckpointClient())
        self.assertEqual((result.datasets, result.closed_rows), (6, 7560))
        self.assertTrue(self.database.is_file())
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(list(Path(self.temporary.name).iterdir()), [self.database])

    def test_existing_database_is_never_overwritten(self):
        self.database.write_bytes(b"preserve")
        with self.assertRaises(CheckpointRebuildError):
            rebuild_accepted_database(
                self.database, self.manifest, client=PublicCheckpointClient())
        self.assertEqual(self.database.read_bytes(), b"preserve")

    def test_incomplete_remote_range_publishes_no_partial_database(self):
        with self.assertRaises(CheckpointRebuildError):
            rebuild_accepted_database(
                self.database, self.manifest,
                client=PublicCheckpointClient(empty=True))
        self.assertFalse(self.database.exists())
        self.assertEqual(list(Path(self.temporary.name).iterdir()), [])

    @patch("yatl.__main__.rebuild_accepted_database")
    @patch("sys.argv", ["yatl", "dataset-restore-checkpoint"])
    def test_cli_reports_only_public_safe_summary(self, rebuild):
        from yatl.__main__ import main
        from yatl.data import CheckpointRebuildResult
        rebuild.return_value = CheckpointRebuildResult(6, 7560, 1788971310603)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("datasets=6 closed_rows=7560", text)
        self.assertIn("No credentials", text)
        self.assertNotIn("api_key", text.lower())


if __name__ == "__main__":
    unittest.main()
