import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory import production_ssh_gateway as ssh


class SshGatewayTest(unittest.TestCase):
    def test_forced_command_claim_uses_pinned_node_identity(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(ssh, "init_coordinator"), \
             patch.object(ssh, "claim_batch", return_value={
                 "status": "BATCH_CLAIMED",
                 "batch_code": "B003",
                 "node_id": "NODE-LAPTOP",
             }) as claim:
            out = ssh.execute_server_command(
                "claim B003 7200",
                node_id="NODE-LAPTOP",
                plan={},
                db=Path(tmp) / "c.sqlite3",
                results_root=Path(tmp) / "results",
                spool_root=Path(tmp) / "spool",
            )
        self.assertEqual(out["status"], "BATCH_CLAIMED")
        self.assertEqual(claim.call_args.kwargs["node_id"], "NODE-LAPTOP")
        self.assertEqual(claim.call_args.kwargs["batch_code"], "B003")
        self.assertEqual(claim.call_args.kwargs["lease_seconds"], 7200)

    def test_forced_command_rejects_shell_like_extra_tokens(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ssh, "init_coordinator"):
            with self.assertRaisesRegex(MCFError, "not allowed"):
                ssh.execute_server_command(
                    "status ; id",
                    node_id="NODE-WORKPC",
                    plan={},
                    db=Path(tmp) / "c.sqlite3",
                    results_root=Path(tmp) / "results",
                    spool_root=Path(tmp) / "spool",
                )

    def test_bundle_is_bounded_content_addressed_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "worker"
            out_root = base / "bundle-out"
            candidate = "MCF-PROD-001-000001"
            artifact_sha = "a" * 64
            artifact = {
                "candidate_id": candidate,
                "candidate_spec_sha256": "b" * 64,
                "result_artifact_sha256": artifact_sha,
            }
            raw = canonical(artifact)
            path = root / "results" / "B001" / candidate / f"result-{artifact_sha}.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            manifest = {
                "batch_code": "B001",
                "candidate_count": 1,
                "batch_result_manifest_sha256": "c" * 64,
                "artifacts": [{
                    "candidate_id": candidate,
                    "candidate_spec_sha256": "b" * 64,
                    "result_artifact_sha256": artifact_sha,
                }],
            }
            with patch.object(ssh, "validate_plan"), \
                 patch.object(ssh, "build_batch_manifest", return_value=manifest), \
                 patch.object(ssh, "verify_batch_manifest"), \
                 patch.object(ssh, "validate_candidate_result_document"):
                result = ssh.build_batch_bundle(root, {"plan_sha256": "d" * 64}, "B001", out_root)
            bundle = Path(result["bundle_path"])
            payload = bundle.read_bytes()
            self.assertEqual(result["bundle_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(result["bundle_bytes"], len(payload))
            self.assertEqual(len(payload.splitlines()), 2)
            header = json.loads(payload.splitlines()[0])
            self.assertEqual(header["batch_result_manifest_sha256"], "c" * 64)

    def test_ingest_verifies_before_marking_coordinator_ingested(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bundle = base / "bundle.jsonl"
            results = base / "results"
            candidate = "MCF-PROD-001-000001"
            artifact_sha = "a" * 64
            artifact = {
                "candidate_id": candidate,
                "candidate_spec_sha256": "b" * 64,
                "result_artifact_sha256": artifact_sha,
            }
            manifest = {
                "batch_code": "B001",
                "candidate_count": 1,
                "batch_result_manifest_sha256": "c" * 64,
                "artifacts": [{
                    "candidate_id": candidate,
                    "candidate_spec_sha256": "b" * 64,
                    "result_artifact_sha256": artifact_sha,
                }],
            }
            header = {
                "schema": ssh.BUNDLE_SCHEMA,
                "plan_sha256": "d" * 64,
                "batch_code": "B001",
                "candidate_count": 1,
                "batch_result_manifest_sha256": "c" * 64,
                "manifest": manifest,
            }
            bundle.write_bytes(canonical(header) + canonical(artifact))

            with patch.object(ssh, "validate_plan"), \
                 patch.object(ssh, "validate_batch_manifest_structure"), \
                 patch.object(ssh, "validate_candidate_result_document"), \
                 patch.object(ssh, "verify_batch_manifest", return_value={"candidate_count": 1}) as verify, \
                 patch.object(ssh, "mark_ingested", return_value={"status": "BATCH_INGESTED"}) as mark:
                out = ssh.ingest_batch_bundle(
                    bundle,
                    results_root=results,
                    plan={"plan_sha256": "d" * 64},
                    coordinator_db=base / "coordinator.sqlite3",
                    uploader_node_id="NODE-LAPTOP",
                )

            self.assertEqual(out["status"], "SSH_BATCH_INGESTED_ACCEPTED")
            target = results / "results" / "B001" / candidate / f"result-{artifact_sha}.json"
            self.assertEqual(target.read_bytes(), canonical(artifact))
            verify.assert_called_once()
            mark.assert_called_once()

    def test_ssh_client_pins_host_key_and_disables_forwarding(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            identity = base / "id_ed25519"
            known = base / "known_hosts"
            identity.write_text("private-placeholder")
            known.write_text("vps ssh-ed25519 AAAAplaceholder")
            completed = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"status": "COORDINATOR_STATUS"}),
                stderr="",
            )
            with patch("subprocess.run", return_value=completed) as run:
                out = ssh.ssh_request(
                    host="vps.example",
                    user="yatl-node",
                    identity_file=identity,
                    known_hosts=known,
                    remote_args=["status"],
                )
            self.assertEqual(out["status"], "COORDINATOR_STATUS")
            cmd = run.call_args.args[0]
            joined = " ".join(cmd)
            self.assertIn("BatchMode=yes", joined)
            self.assertIn("IdentitiesOnly=yes", joined)
            self.assertIn("StrictHostKeyChecking=yes", joined)
            self.assertIn("ClearAllForwardings=yes", joined)
            self.assertNotIn("accept-new", joined)

    def test_upload_checks_owner_before_accepting_stdin(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(ssh, "init_coordinator"), \
             patch.object(ssh, "_owned_batch", side_effect=MCFError("owner mismatch")), \
             patch.object(ssh, "_receive_stdin") as receive:
            with self.assertRaisesRegex(MCFError, "owner mismatch"):
                ssh.execute_server_command(
                    "upload B001 " + "a" * 64 + " 100 " + "b" * 64,
                    node_id="NODE-LAPTOP",
                    plan={},
                    db=Path(tmp) / "c.sqlite3",
                    results_root=Path(tmp) / "results",
                    spool_root=Path(tmp) / "spool",
                )
            receive.assert_not_called()


if __name__ == "__main__":
    unittest.main()
