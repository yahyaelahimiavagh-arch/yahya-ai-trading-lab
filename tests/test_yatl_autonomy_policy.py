"""No-network YATL agent policy regression tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from infra.autonomy.policy_gate import (
    validate_changed_paths,
    validate_policy,
)

ROOT = Path(__file__).resolve().parents[1]


class AutonomyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(
            (ROOT / "infra/autonomy/policy.json").read_text(encoding="utf-8")
        )

    def test_shipped_policy_is_safe(self) -> None:
        self.assertEqual(validate_policy(self.policy), [])

    def test_disabled_vps_deploy_and_money_are_mandatory(self) -> None:
        for key, value in [
            ("vps_access_allowed", True),
            ("deployment_allowed", True),
            ("real_orders_allowed", True),
            ("agent_external_network_allowed", True),
            ("secrets_access_allowed", True),
            ("quota_reset_allowed", True),
            ("agent_spend_limit_usd", 1),
            ("paper_only", False),
        ]:
            with self.subTest(key=key):
                candidate = dict(self.policy, **{key: value})
                self.assertTrue(validate_policy(candidate))

    def test_fails_closed_on_missing_policy(self) -> None:
        self.assertTrue(validate_policy(None))
        self.assertTrue(validate_policy({}))

    def test_allowed_only_bootstrap_files(self) -> None:
        paths = [
            "AGENTS.md",
            "docs/YATL-AUTONOMY-V1.md",
            "infra/autonomy/policy.json",
            "infra/autonomy/policy_gate.py",
            "tests/test_yatl_autonomy_policy.py",
            ".github/workflows/yatl-autonomy-safety.yml",
            ".github/ISSUE_TEMPLATE/yatl-autonomy-task.yml",
        ]
        self.assertEqual(validate_changed_paths(paths, self.policy), [])

    def test_blocks_runtime_sensitive_changes(self) -> None:
        paths = [
            "ops/systemd/yatl-smart-money-paper.service.example",
            "research/smart_money_lab/paper_copy_next.py",
            "yatl/execution/runner.py",
            ".github/workflows/p3-009.yml",
            ".github/workflows/another-agent.yml",
            ".env",
            "../escape",
            "/etc/systemd/system/yatl.service",
        ]
        self.assertEqual(len(validate_changed_paths(paths, self.policy)), len(paths))

    def test_rejects_policy_scope_expansion(self) -> None:
        candidate = dict(self.policy, allowed_path_prefixes=[""])
        self.assertTrue(validate_policy(candidate))

    def test_prevents_missing_approvals(self) -> None:
        candidate = dict(self.policy, human_approval_required_for=["merge"])
        self.assertTrue(validate_policy(candidate))


if __name__ == "__main__":
    unittest.main()
