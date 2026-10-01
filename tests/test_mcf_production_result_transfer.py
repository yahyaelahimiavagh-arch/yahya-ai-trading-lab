import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory import production_result_transfer as transfer


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount=None):
        if amount is None:
            return self.payload
        return self.payload[:amount]


class ResultTransferTest(unittest.TestCase):
    def test_put_bytes_sends_raw_hash_separate_from_semantic_hash(self):
        captured = {}
        payload = b'{"hello":"world"}\n'
        raw_sha = transfer._raw_sha_bytes(payload)
        semantic = "a" * 64

        def fake_open(request, timeout):
            captured["url"] = request.full_url
            captured["raw"] = request.headers["X-yatl-body-sha256"]
            captured["semantic"] = request.headers["X-yatl-semantic-sha256"]
            captured["node"] = request.headers["X-yatl-node"]
            captured["body"] = request.data
            return FakeResponse(json.dumps({
                "status": "RESULT_ARTIFACT_STORED",
                "raw_sha256": raw_sha,
            }).encode())

        with patch("urllib.request.urlopen", side_effect=fake_open):
            out = transfer._put_bytes(
                "https://coord.example",
                "/v1/artifact/B001/MCF-PROD-001-000001/" + semantic,
                token="secret",
                node_id="NODE-LAPTOP",
                payload=payload,
                semantic_sha256=semantic,
            )
        self.assertEqual(out["status"], "RESULT_ARTIFACT_STORED")
        self.assertEqual(captured["raw"], raw_sha)
        self.assertEqual(captured["semantic"], semantic)
        self.assertNotEqual(captured["raw"], semantic)
        self.assertEqual(captured["node"], "NODE-LAPTOP")
        self.assertEqual(captured["body"], payload)

    def test_get_object_rejects_wrong_raw_metadata(self):
        payload = b"payload"
        headers = {
            "x-yatl-raw-sha256": "f" * 64,
            "x-yatl-semantic-sha256": "a" * 64,
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload, headers=headers)):
            with self.assertRaisesRegex(MCFError, "raw SHA"):
                transfer._get_object(
                    "https://coord.example",
                    "results/key",
                    token="admin",
                    expected_semantic_sha256="a" * 64,
                )

    def test_upload_batch_uploads_results_manifest_then_marks_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = "MCF-PROD-001-000001"
            semantic = "a" * 64
            path = root / "results" / "B001" / candidate / f"result-{semantic}.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{"result":"compact"}\n')
            manifest = {
                "batch_code": "B001",
                "candidate_count": 1,
                "batch_result_manifest_sha256": "b" * 64,
                "artifacts": [{
                    "candidate_id": candidate,
                    "candidate_spec_sha256": "c" * 64,
                    "result_artifact_sha256": semantic,
                }],
            }
            uploaded = []

            def fake_put(base_url, path, **kwargs):
                uploaded.append((path, kwargs["payload"]))
                if path.startswith("/v1/manifest/"):
                    return {"status": "BATCH_MANIFEST_STORED", "raw_sha256": transfer._raw_sha_bytes(kwargs["payload"])}
                return {"status": "RESULT_ARTIFACT_STORED", "raw_sha256": transfer._raw_sha_bytes(kwargs["payload"])}

            with patch.object(transfer, "validate_plan"),                  patch.object(transfer, "validate_batch_manifest_structure"),                  patch.object(transfer, "verify_batch_manifest"),                  patch.object(transfer, "_put_bytes", side_effect=fake_put),                  patch.object(transfer, "ready", return_value={"status": "BATCH_AWAITING_INGEST"}) as ready_mock:
                out = transfer.upload_batch(
                    root,
                    {"plan_sha256": "d" * 64},
                    manifest,
                    coordinator_url="https://coord.example",
                    node_id="NODE-LAPTOP",
                    token="secret",
                )
            self.assertEqual(out["status"], "BATCH_UPLOADED_AWAITING_INGEST")
            self.assertEqual(out["candidate_count"], 1)
            self.assertEqual(len(uploaded), 2)
            ready_mock.assert_called_once()
            self.assertEqual(ready_mock.call_args.kwargs["transfer_mode"], "R2")

    def test_ingest_once_skips_non_r2_transfer(self):
        status_doc = {
            "status": "COORDINATOR_STATUS",
            "batches": [
                {
                    "batch_code": "B002",
                    "state": "AWAITING_INGEST",
                    "transfer_mode": "DIRECT_PULL",
                    "result_manifest_sha256": "a" * 64,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp,              patch.object(transfer, "validate_plan"),              patch.object(transfer, "_admin_json", return_value=status_doc),              patch.object(transfer, "ingest_batch_from_r2") as ingest:
            out = transfer.ingest_ready_batches_once(
                Path(tmp),
                {"plan_sha256": "d" * 64},
                coordinator_url="https://coord.example",
                admin_token="admin",
            )
        self.assertEqual(out["ingested_count"], 0)
        self.assertEqual(out["skipped"][0]["reason"], "NON_R2_TRANSFER_MODE")
        ingest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
