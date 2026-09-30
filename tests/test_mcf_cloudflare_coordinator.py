import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "infra/cloudflare/yatl-coordinator/src/index.js"
SCHEMA = ROOT / "infra/cloudflare/yatl-coordinator/schema.sql"


class CloudflareCoordinatorSourceTest(unittest.TestCase):
    def test_worker_source_has_expected_private_control_surface(self):
        source = WORKER.read_text()
        for needle in (
            "/v1/claim",
            "/v1/heartbeat",
            "/v1/release",
            "/v1/pause-request",
            "/v1/paused",
            "/v1/resume",
            "/v1/ready",
            "/v1/ingested",
            "/v1/status",
            "YATL_ADMIN_TOKEN_SHA256",
            "RESULTS",
            "ARTIFACT_RAW_SHA_MISMATCH",
            "MANIFEST_RAW_SHA_MISMATCH",
        ):
            self.assertIn(needle, source)

        for literal, regex_form in (
            ("/v1/artifact/", r"\/v1\/artifact\/"),
            ("/v1/manifest/", r"\/v1\/manifest\/"),
            ("/v1/admin/object/", r"\/v1\/admin\/object\/"),
        ):
            self.assertTrue(
                literal in source or regex_form in source,
                msg=f"missing route source for {literal}",
            )
        self.assertNotIn("API_KEY", source)
        self.assertNotIn("API_SECRET", source)
        self.assertNotIn("withdraw", source.lower())
        self.assertNotIn("order_endpoint", source.lower())

    def test_schema_has_lease_ingest_and_transfer_states(self):
        source = SCHEMA.read_text()
        for needle in (
            "AVAILABLE",
            "CLAIMED",
            "PAUSE_REQUESTED",
            "PAUSED",
            "AWAITING_INGEST",
            "INGESTED",
            "lease_until_ms",
            "token_sha256",
            "transfer_mode",
        ):
            self.assertIn(needle, source)

    def test_worker_javascript_syntax_when_node_is_available(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node executable unavailable")
        completed = subprocess.run(
            [node, "--check", str(WORKER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"node --check failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
