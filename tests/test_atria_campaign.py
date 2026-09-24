import json
import tempfile
import unittest
from pathlib import Path

from research.model_lab import atria_campaign as campaign


def artifact():
    return {
        "schema": "TEST",
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def write_json(root, relative, record):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return relative


def campaign_record():
    return {
        "schema": "YATL_ATRIA_RESEARCH_CAMPAIGN",
        "schema_version": "0.1.0",
        "campaign_id": "CRL_REVIEW_V1",
        "tasks": [
            {
                "task_id": "TASK_001",
                "objective": "COMPARE_EVIDENCE",
                "artifacts": ["a.json"],
                "max_output_tokens": 2048,
            },
            {
                "task_id": "TASK_002",
                "objective": "PROPOSE_FALSIFIABLE_TESTS",
                "artifacts": ["b.json"],
                "max_output_tokens": 4096,
            },
        ],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls)
        return {
            "manifest_relative_path": f"model-lab/atria/result-{index}.json",
            "manifest_file_sha256": "a" * 64,
            "result_sha256": "b" * 64,
            "analysis_sha256": "c" * 64,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            },
            "research_only": True,
            "p10_write_allowed": False,
            "p11_locked": True,
        }


class AtriaCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write_json(self.root, "a.json", artifact())
        write_json(self.root, "b.json", artifact())
        self.manifest = self.root / "campaign.json"
        self.manifest.write_text(
            json.dumps(
                campaign_record(),
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_is_network_free_and_budgeted(self):
        result = campaign.plan_campaign(
            runtime_root=self.root,
            campaign_path=self.manifest,
        )
        self.assertEqual(result["task_count"], 2)
        self.assertEqual(result["max_output_tokens_budget"], 6144)
        self.assertFalse(result["network_used"])
        self.assertFalse(result["credential_read"])
        self.assertFalse(result["p10_write_allowed"])
        self.assertFalse(result["ai_direct_execution"])
        self.assertTrue(result["p11_locked"])

    def test_run_writes_receipts_and_second_run_reuses_them(self):
        fake = FakeRunner()
        first = campaign.run_campaign(
            runtime_root=self.root,
            campaign_path=self.manifest,
            bearer_secret="atr_test_secret",
            task_runner=fake,
        )
        self.assertEqual(first["executed_count"], 2)
        self.assertEqual(first["receipt_reused_count"], 0)
        self.assertEqual(len(fake.calls), 2)

        second = campaign.run_campaign(
            runtime_root=self.root,
            campaign_path=self.manifest,
            bearer_secret="atr_test_secret",
            task_runner=fake,
        )
        self.assertEqual(second["executed_count"], 0)
        self.assertEqual(second["receipt_reused_count"], 2)
        self.assertEqual(len(fake.calls), 2)

        for receipt in (self.root / "model-lab/atria/campaigns/CRL_REVIEW_V1").glob("*.json"):
            text = receipt.read_text(encoding="utf-8")
            self.assertNotIn("atr_test_secret", text)

    def test_duplicate_or_unsorted_task_ids_fail_closed(self):
        record = campaign_record()
        record["tasks"][1]["task_id"] = "TASK_001"
        self.manifest.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(campaign.AtriaCampaignError):
            campaign.plan_campaign(
                runtime_root=self.root,
                campaign_path=self.manifest,
            )

    def test_duplicate_objective_artifact_work_fails_closed(self):
        record = campaign_record()
        record["tasks"][1]["objective"] = "COMPARE_EVIDENCE"
        record["tasks"][1]["artifacts"] = ["a.json"]
        self.manifest.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(campaign.AtriaCampaignError):
            campaign.plan_campaign(
                runtime_root=self.root,
                campaign_path=self.manifest,
            )

    def test_campaign_token_ceiling_fails_closed(self):
        record = campaign_record()
        record["tasks"] = [
            {
                "task_id": f"TASK_{i:03d}",
                "objective": "COMPARE_EVIDENCE",
                "artifacts": ["a.json"],
                "max_output_tokens": 16384,
            }
            for i in range(1, 10)
        ]
        self.manifest.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(campaign.AtriaCampaignError):
            campaign.plan_campaign(
                runtime_root=self.root,
                campaign_path=self.manifest,
            )

    def test_p10_root_is_rejected(self):
        with self.assertRaises(campaign.AtriaCampaignError):
            campaign.plan_campaign(
                runtime_root=Path("/var/lib/yatl/p10"),
                campaign_path=self.manifest,
            )


if __name__ == "__main__":
    unittest.main()
