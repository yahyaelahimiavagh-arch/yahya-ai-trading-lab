import contextlib
import copy
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from yatl.__main__ import main
from yatl.data.audit import AuditError, MAX_MANIFEST_BYTES, audit_p1_manifest


ROOT = Path(__file__).resolve().parents[1]
TRACKED_MANIFEST = ROOT / "manifests" / "p1-market-data.json"


class P1AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(os.environ.get("YATL_TEST_TEMP_DIR", os.environ.get("TEMP", ".")))
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            path.unlink(missing_ok=True)

    def write(self, value):
        path = self.temp_root / f"audit-{uuid4().hex}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        self.paths.append(path)
        return path

    def manifest(self):
        return json.loads(TRACKED_MANIFEST.read_text(encoding="utf-8"))

    def test_tracked_manifest_passes_exact_p1_gate(self):
        result = audit_p1_manifest(TRACKED_MANIFEST)
        self.assertEqual((result.datasets, result.closed_rows, result.range_days),
                         (6, 7_560, 30))

    def test_identity_coverage_and_counts_fail_closed(self):
        mutations = []
        for key, value in (("schema_version", 2), ("database_schema_version", 2),
                           ("dataset_kind", "other"), ("range_days", 29),
                           ("generated_at_ms", True)):
            item = self.manifest(); item[key] = value; mutations.append(item)
        item = self.manifest(); item["datasets"].pop(); mutations.append(item)
        item = self.manifest(); item["datasets"][1] = copy.deepcopy(item["datasets"][0]); mutations.append(item)
        item = self.manifest(); item["datasets"][0]["total_rows"] -= 1; mutations.append(item)
        item = self.manifest(); item["datasets"][0]["requested_end_time_ms"] = "unsafe"; mutations.append(item)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(AuditError):
                audit_p1_manifest(self.write(value))

    def test_each_health_failure_fails_closed(self):
        changes = {
            "backtest_ready": False, "fresh": False, "open_rows": 1,
            "malformed_rows": 1, "conflicting_rows": 1,
            "duplicate_open_times": [1], "historical_gap_open_times": [1],
            "unexpected_open_times": [1], "repair_ranges": [[1, 2]],
            "failure_reasons": ["unsafe"],
        }
        for key, value in changes.items():
            manifest = self.manifest(); manifest["datasets"][0][key] = value
            with self.subTest(key=key), self.assertRaises(AuditError):
                audit_p1_manifest(self.write(manifest))

    def test_missing_malformed_and_oversized_files_fail_closed(self):
        missing = self.temp_root / f"missing-{uuid4().hex}.json"
        with self.assertRaises(AuditError):
            audit_p1_manifest(missing)
        malformed = self.temp_root / f"audit-{uuid4().hex}.json"
        malformed.write_text("{", encoding="utf-8"); self.paths.append(malformed)
        with self.assertRaises(AuditError):
            audit_p1_manifest(malformed)
        oversized = self.temp_root / f"audit-{uuid4().hex}.json"
        oversized.write_bytes(b"x" * (MAX_MANIFEST_BYTES + 1)); self.paths.append(oversized)
        with self.assertRaises(AuditError):
            audit_p1_manifest(oversized)

    @patch("sys.argv", ["yatl", "p1-audit", "--manifest", str(TRACKED_MANIFEST)])
    def test_cli_reports_only_safe_acceptance_summary(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P1 manifest acceptance gate", text)
        self.assertIn("datasets=6", text)
        self.assertIn("closed_rows=7560", text)
        self.assertIn("No credentials", text)

    @patch("sys.argv", ["yatl", "p1-audit", "--manifest", "missing.json"])
    def test_cli_failure_is_redacted_and_nonzero(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual(main(), 1)
        self.assertEqual(output.getvalue(), "Error: P1 manifest cannot be read\n")


if __name__ == "__main__":
    unittest.main()
