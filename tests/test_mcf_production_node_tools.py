import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_node_tools import (
    generate_enrollment,
    preflight,
    token_sha256,
    validate_node_id,
)


class NodeToolsTest(unittest.TestCase):
    def test_enrollment_generates_distinct_secret_and_hash_only_sql(self):
        first = generate_enrollment("NODE-LAPTOP", max_workers=4)
        second = generate_enrollment("NODE-LAPTOP", max_workers=4)
        self.assertEqual(first["node_id"], "NODE-LAPTOP")
        self.assertEqual(first["max_workers"], 4)
        self.assertNotEqual(first["node_token"], second["node_token"])
        self.assertEqual(first["token_sha256"], token_sha256(first["node_token"]))
        self.assertIn(first["token_sha256"], first["d1_sql"])
        self.assertNotIn(first["node_token"], first["d1_sql"])
        self.assertEqual(first["warning"], "PLAINTEXT_TOKEN_SHOWN_ONCE_DO_NOT_COMMIT")

    def test_invalid_node_and_worker_count_fail_closed(self):
        for bad in ("laptop", "NODE x", "NODE-", "../NODE-LAPTOP"):
            with self.subTest(bad=bad), self.assertRaises(MCFError):
                validate_node_id(bad)
        with self.assertRaises(MCFError):
            generate_enrollment("NODE-LAPTOP", max_workers=0)
        with self.assertRaises(MCFError):
            generate_enrollment("NODE-LAPTOP", max_workers=33)

    def test_preflight_is_nonperformance_and_reports_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.cpu_count", return_value=8):
                result = preflight("NODE-WORKPC", Path(tmp) / "worker")
        self.assertEqual(result["status"], "NODE_PREFLIGHT_COMPLETE_NO_PERFORMANCE")
        self.assertEqual(result["cpu_logical_count"], 8)
        self.assertGreater(result["disk_total_bytes"], 0)
        self.assertGreaterEqual(result["disk_free_bytes"], 0)
        self.assertFalse(result["performance_execution_authorized"])
        self.assertFalse(result["gpu_required"])


if __name__ == "__main__":
    unittest.main()
