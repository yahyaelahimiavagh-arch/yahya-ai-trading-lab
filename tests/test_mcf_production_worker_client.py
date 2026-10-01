import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory import production_worker_client as client


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class WorkerClientTest(unittest.TestCase):
    def test_https_required(self):
        with self.assertRaises(MCFError):
            client.request_json(
                "http://example.test",
                "/v1/status",
                token="secret",
                method="GET",
                node_id="NODE-LAPTOP",
            )

    def test_claim_never_persists_token_and_sends_expected_payload(self):
        captured = {}

        def fake_open(request, timeout):
            captured["url"] = request.full_url
            captured["auth"] = request.headers["Authorization"]
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse({
                "status": "BATCH_CLAIMED",
                "batch_code": "B001",
                "node_id": "NODE-LAPTOP",
            })

        with patch("urllib.request.urlopen", side_effect=fake_open):
            result = client.claim(
                "https://coordinator.example",
                "NODE-LAPTOP",
                batch_code="B001",
                token="TOP_SECRET",
            )
        self.assertEqual(result["batch_code"], "B001")
        self.assertEqual(captured["url"], "https://coordinator.example/v1/claim")
        self.assertEqual(captured["auth"], "Bearer TOP_SECRET")
        self.assertEqual(captured["body"]["node_id"], "NODE-LAPTOP")
        self.assertEqual(captured["body"]["batch_code"], "B001")
        self.assertNotIn("TOP_SECRET", json.dumps(result))

    def test_status_uses_node_header(self):
        captured = {}

        def fake_open(request, timeout):
            captured["node"] = request.headers["X-yatl-node"]
            captured["method"] = request.method
            return FakeResponse({"status": "COORDINATOR_STATUS", "counts": {}})

        with patch("urllib.request.urlopen", side_effect=fake_open):
            result = client.status(
                "https://coordinator.example",
                "NODE-VPS",
                token="secret",
            )
        self.assertEqual(result["status"], "COORDINATOR_STATUS")
        self.assertEqual(captured["node"], "NODE-VPS")
        self.assertEqual(captured["method"], "GET")

    def test_http_rejection_is_fail_closed(self):
        error = urllib.error.HTTPError(
            "https://coordinator.example/v1/claim",
            409,
            "Conflict",
            {},
            io.BytesIO(json.dumps({"status": "BATCH_UNAVAILABLE"}).encode()),
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(MCFError, "BATCH_UNAVAILABLE"):
                client.claim(
                    "https://coordinator.example",
                    "NODE-LAPTOP",
                    token="secret",
                )

    def test_environment_token_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(MCFError, "YATL_NODE_TOKEN"):
                client._token()


if __name__ == "__main__":
    unittest.main()
