import json
import tempfile
import unittest
from pathlib import Path

from research.model_lab import atria_worker as worker


class FakeTransport:
    def __init__(self, analysis):
        self.analysis = analysis
        self.calls = []

    def post(self, body, bearer_secret):
        self.calls.append((body, bearer_secret))
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    self.analysis,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ),
                            }
                        ]
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def research_artifact():
    return {
        "schema": "TEST_RESEARCH",
        "value": {"metric": "0.123"},
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def write_artifact(root, name="input.json", record=None):
    if record is None:
        record = research_artifact()
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return name


class AtriaResearchWorkerTests(unittest.TestCase):
    def test_packet_accepts_only_isolated_research_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_artifact(directory)
            packet = worker.build_packet(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="COMPARE_EVIDENCE",
            )
            self.assertEqual(
                packet["schema"], "YATL_ATRIA_RESEARCH_PACKET"
            )
            self.assertTrue(packet["research_only"])
            self.assertFalse(packet["p10_write_allowed"])
            self.assertFalse(packet["trade_permission"])
            self.assertFalse(packet["order_endpoint"])
            self.assertFalse(packet["quantity_authority"])
            self.assertFalse(packet["ai_direct_execution"])
            self.assertTrue(packet["p11_locked"])
            self.assertEqual(len(packet["packet_sha256"]), 64)

    def test_packet_rejects_sensitive_artifact_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            record = research_artifact()
            record["nested"] = {"api_key": "do-not-send"}
            relative = write_artifact(
                directory, record=record
            )
            with self.assertRaises(worker.AtriaResearchError):
                worker.build_packet(
                    runtime_root=Path(directory),
                    artifact_paths=[relative],
                    objective="FIND_ANOMALIES",
                )

    def test_packet_rejects_non_research_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            record = research_artifact()
            record["research_only"] = False
            relative = write_artifact(
                directory, record=record
            )
            with self.assertRaises(worker.AtriaResearchError):
                worker.build_packet(
                    runtime_root=Path(directory),
                    artifact_paths=[relative],
                    objective="FIND_ANOMALIES",
                )

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(worker.AtriaResearchError):
            worker.build_packet(
                runtime_root=Path("/var/lib/yatl/p10"),
                artifact_paths=["anything.json"],
                objective="COMPARE_EVIDENCE",
            )

    def test_provider_request_is_fixed_to_atria_responses_model(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_artifact(directory)
            packet = worker.build_packet(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="PROPOSE_FALSIFIABLE_TESTS",
            )
            request = worker.build_provider_request(packet)
            self.assertEqual(
                worker.API_ENDPOINT,
                "https://api.atria-asi.ai/v1/responses",
            )
            self.assertEqual(
                request["model"], "Atria-Dawn-Preview"
            )
            self.assertEqual(request["max_output_tokens"], 4096)
            self.assertIn(
                "Do not create or recommend trade actions",
                request["input"],
            )

    def test_validated_worker_output_remains_research_only(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_artifact(directory)
            packet = worker.build_packet(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="COMPARE_EVIDENCE",
            )
            digest = packet["artifacts"][0]["sha256"]
            analysis = {
                "schema_version": 1,
                "mode": "YATL_RESEARCH_CRITIC",
                "summary": "The supplied evidence is limited.",
                "findings": [
                    {
                        "finding_id": "F001",
                        "text": "One bounded metric is present.",
                        "evidence_sha256": [digest],
                    }
                ],
                "hypotheses": [
                    {
                        "hypothesis_id": "H001",
                        "text": "The behavior may differ in other windows.",
                        "falsification_test": (
                            "Replay preregistered ordinary windows."
                        ),
                        "evidence_sha256": [digest],
                    }
                ],
                "uncertainties": [
                    "The artifact alone cannot establish robustness."
                ],
            }
            fake = FakeTransport(analysis)
            result = worker.run_worker(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="COMPARE_EVIDENCE",
                bearer_secret="atr_test_secret",
                transport=fake,
            )
            self.assertEqual(result["usage"]["total_tokens"], 150)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(
                fake.calls[0][0]["model"],
                "Atria-Dawn-Preview",
            )
            self.assertEqual(
                fake.calls[0][1], "atr_test_secret"
            )

            output_path = (
                Path(directory) / result["manifest_relative_path"]
            )
            stored = json.loads(
                output_path.read_text(encoding="utf-8")
            )
            encoded = json.dumps(stored, sort_keys=True)
            self.assertNotIn("atr_test_secret", encoded)
            self.assertTrue(stored["research_only"])
            self.assertFalse(stored["p10_write_allowed"])
            self.assertEqual(
                stored["p10_evidence_effect"], "NONE"
            )
            self.assertFalse(stored["trade_permission"])
            self.assertFalse(stored["order_endpoint"])
            self.assertFalse(stored["quantity_authority"])
            self.assertFalse(
                stored["risk_authorization_mutation"]
            )
            self.assertFalse(stored["ai_direct_execution"])
            self.assertTrue(stored["p11_locked"])
            self.assertFalse(stored["provider_output_trusted"])

    def test_unknown_evidence_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_artifact(directory)
            packet = worker.build_packet(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="COMPARE_EVIDENCE",
            )
            raw = json.dumps(
                {
                    "schema_version": 1,
                    "mode": "YATL_RESEARCH_CRITIC",
                    "summary": "Summary.",
                    "findings": [
                        {
                            "finding_id": "F001",
                            "text": "Finding.",
                            "evidence_sha256": ["f" * 64],
                        }
                    ],
                    "hypotheses": [],
                    "uncertainties": ["Uncertain."],
                }
            )
            with self.assertRaises(worker.AtriaResearchError):
                worker.validate_analysis(raw, packet=packet)

    def test_execution_shaped_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            relative = write_artifact(directory)
            packet = worker.build_packet(
                runtime_root=Path(directory),
                artifact_paths=[relative],
                objective="COMPARE_EVIDENCE",
            )
            digest = packet["artifacts"][0]["sha256"]
            raw = json.dumps(
                {
                    "schema_version": 1,
                    "mode": "YATL_RESEARCH_CRITIC",
                    "summary": "Summary.",
                    "findings": [
                        {
                            "finding_id": "F001",
                            "text": "Finding.",
                            "evidence_sha256": [digest],
                            "action": "forbidden",
                        }
                    ],
                    "hypotheses": [],
                    "uncertainties": ["Uncertain."],
                }
            )
            with self.assertRaises(worker.AtriaResearchError):
                worker.validate_analysis(raw, packet=packet)


if __name__ == "__main__":
    unittest.main()
