import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, digest
from research.mass_candidate_factory import production_worker_runner as runner


GIT_SHA = "a" * 40
RUNNER_SHA = "b" * 64
PLAN_SHA = "c" * 64


def authorization():
    base = {
        "schema": runner.AUTH_SCHEMA,
        "scope": runner.AUTH_SCOPE,
        "authorized": True,
        "plan_sha256": PLAN_SHA,
        "runner_input_sha256": RUNNER_SHA,
        "git_sha": GIT_SHA,
        "capacity_benchmark_sha256": "e" * 64,
        "capacity_benchmark_candidate_count": 24,
        "candidate_count": 6852,
        "batch_count": 14,
        "max_concurrent_microshards_per_node": 1,
        "selection_authorized": False,
        "promotion_authorized": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "live": False,
        "futures": False,
        "leverage": False,
        "short": False,
    }
    return {**base, "authorization_sha256": digest(base)}


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.release_calls = 0

    def run(self, candidate_id, *, director_authorized=False):
        self.calls.append((candidate_id, director_authorized))
        return {"candidate_id": candidate_id}

    def release_transient_features(self):
        self.release_calls += 1


class DistributedWorkerRunnerTest(unittest.TestCase):
    def test_authorization_is_content_addressed_and_exactly_bound(self):
        doc = authorization()
        accepted = runner.validate_authorization(
            doc,
            plan_sha256=PLAN_SHA,
            runner_input_sha256=RUNNER_SHA,
            git_sha=GIT_SHA,
        )
        self.assertTrue(accepted["authorized"])

        changed = dict(doc)
        changed["plan_sha256"] = "d" * 64
        with self.assertRaisesRegex(MCFError, "authorization boundary"):
            runner.validate_authorization(
                changed,
                plan_sha256=PLAN_SHA,
                runner_input_sha256=RUNNER_SHA,
                git_sha=GIT_SHA,
            )

    def test_authorization_cannot_open_sealed_or_live_boundaries(self):
        for key in (
            "selection_authorized",
            "promotion_authorized",
            "fresh_oos_read",
            "recent_reserve_read",
            "p10_read",
            "p10_write",
            "live",
            "futures",
            "leverage",
            "short",
        ):
            doc = authorization()
            doc[key] = True
            base = {k: v for k, v in doc.items() if k != "authorization_sha256"}
            doc["authorization_sha256"] = digest(base)
            with self.assertRaises(MCFError, msg=key):
                runner.validate_authorization(
                    doc,
                    plan_sha256=PLAN_SHA,
                    runner_input_sha256=RUNNER_SHA,
                    git_sha=GIT_SHA,
                )

    def test_microshard_skips_verified_checkpoint_and_releases_transients(self):
        fake_runtime = FakeRuntime()
        shard = {
            "microshard_code": "B001-S001",
            "candidate_count": 3,
            "candidates": [
                {"candidate_id": "MCF-PROD-001-000001"},
                {"candidate_id": "MCF-PROD-001-000002"},
                {"candidate_id": "MCF-PROD-001-000003"},
            ],
        }
        reader = SimpleNamespace(expected_sha256=RUNNER_SHA)
        completed = {"MCF-PROD-001-000001"}
        written = []
        progress = []

        with patch.object(runner, "validate_plan"), \
             patch.object(runner, "_microshard", return_value=shard), \
             patch.object(runner.ProductionRuntime, "from_frozen_input", return_value=fake_runtime), \
             patch.object(runner, "pause_requested", return_value=False), \
             patch.object(runner, "candidate_completed", side_effect=lambda root, plan, batch, cid: cid in completed), \
             patch.object(runner, "write_candidate_result", side_effect=lambda *a, **kw: written.append((a, kw))):
            out = runner.run_microshard(
                root=Path("."),
                plan={},
                reader=reader,
                node_id="NODE-LAPTOP",
                batch_code="B001",
                shard_code="B001-S001",
                git_sha=GIT_SHA,
                progress=progress.append,
            )

        self.assertEqual(out["status"], "MICROSHARD_COMPLETE")
        self.assertEqual(out["executed"], 2)
        self.assertEqual(out["skipped_completed"], 1)
        self.assertEqual(
            fake_runtime.calls,
            [
                ("MCF-PROD-001-000002", True),
                ("MCF-PROD-001-000003", True),
            ],
        )
        self.assertEqual(fake_runtime.release_calls, 2)
        self.assertEqual(len(written), 2)
        self.assertEqual(len(progress), 2)
        self.assertTrue(all(x[1]["git_sha"] == GIT_SHA for x in written))
        self.assertTrue(all(x[1]["runner_input_sha256"] == RUNNER_SHA for x in written))

    def test_safe_pause_starts_no_new_candidate(self):
        fake_runtime = FakeRuntime()
        shard = {
            "microshard_code": "B001-S001",
            "candidate_count": 1,
            "candidates": [{"candidate_id": "MCF-PROD-001-000001"}],
        }
        reader = SimpleNamespace(expected_sha256=RUNNER_SHA)

        with patch.object(runner, "validate_plan"), \
             patch.object(runner, "_microshard", return_value=shard), \
             patch.object(runner.ProductionRuntime, "from_frozen_input", return_value=fake_runtime), \
             patch.object(runner, "pause_requested", return_value=True), \
             patch.object(runner, "candidate_completed") as completed, \
             patch.object(runner, "write_candidate_result") as write:
            out = runner.run_microshard(
                root=Path("."),
                plan={},
                reader=reader,
                node_id="NODE-WORKPC",
                batch_code="B001",
                shard_code="B001-S001",
                git_sha=GIT_SHA,
            )

        self.assertEqual(out["status"], "MICROSHARD_PAUSED_SAFE")
        self.assertEqual(fake_runtime.calls, [])
        completed.assert_not_called()
        write.assert_not_called()

    def test_child_command_pins_all_scientific_identities(self):
        args = SimpleNamespace(
            root=Path("/tmp/results"),
            plan=Path("/tmp/plan.json"),
            runtime_root=Path("/tmp/runtime"),
            input_relative=f"runner-input/input-{RUNNER_SHA}.json",
            expected_input_sha256=RUNNER_SHA,
            authorization=Path("/tmp/authorization.json"),
            node_id="NODE-VPS",
            batch="B014",
            expected_git_sha=GIT_SHA,
        )
        cmd = runner._child_command(args, "B014-S015")
        joined = " ".join(cmd)
        self.assertIn("run-shard", cmd)
        self.assertIn(RUNNER_SHA, cmd)
        self.assertIn(GIT_SHA, cmd)
        self.assertIn("NODE-VPS", cmd)
        self.assertIn("B014-S015", cmd)
        self.assertNotIn("fresh", joined.lower())
        self.assertNotIn("p10", joined.lower())


if __name__ == "__main__":
    unittest.main()
