import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory import production_execution_authorization as auth


class FullRunAuthorizationTest(unittest.TestCase):
    def benchmark(self, runner_sha):
        return {
            "status": "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION",
            "runner_input_sha256": runner_sha,
            "executable_candidate_count": 6852,
            "benchmark_candidate_count": 24,
            "candidate_performance_exposed": False,
            "performance_artifacts_written": False,
            "selection_authorized": False,
            "full_batch_authorized": False,
        }

    def test_freeze_requires_explicit_director_token_and_capacity_evidence(self):
        runner_sha = "b" * 64
        git_sha = "c" * 40
        plan = {"plan_sha256": "a" * 64, "candidate_count": 6852, "batch_count": 14}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            benchmark_path = root / "benchmark.json"
            output = root / "authorization.json"
            plan_path.write_bytes(canonical(plan))
            benchmark_path.write_bytes(canonical(self.benchmark(runner_sha)))

            reader = SimpleNamespace(assert_unchanged=lambda: None)
            with patch.object(auth, "validate_plan"), \
                 patch.object(auth, "current_git_sha", return_value=git_sha), \
                 patch.object(auth, "FrozenRunnerInput", return_value=reader), \
                 patch.object(auth, "validate_authorization"):
                result = auth.freeze_authorization(
                    plan_path=plan_path,
                    runtime_root=root,
                    runner_input_relative=f"runner-input/input-{runner_sha}.json",
                    runner_input_sha256=runner_sha,
                    benchmark_path=benchmark_path,
                    expected_git_sha=git_sha,
                    output=output,
                    director_token=auth.DIRECTOR_TOKEN,
                )

            self.assertEqual(result["status"], "FULL_6852_DEVELOPMENT_AUTHORIZATION_FROZEN")
            doc = json.loads(output.read_bytes())
            self.assertEqual(doc["capacity_benchmark_candidate_count"], 24)
            self.assertEqual(doc["candidate_count"], 6852)
            self.assertEqual(doc["batch_count"], 14)
            self.assertEqual(doc["max_concurrent_microshards_per_node"], 1)
            self.assertFalse(doc["selection_authorized"])
            self.assertFalse(doc["promotion_authorized"])
            self.assertFalse(doc["fresh_oos_read"])
            self.assertFalse(doc["p10_read"])
            self.assertFalse(doc["live"])

    def test_wrong_director_token_blocks_before_input_or_benchmark_use(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(auth, "FrozenRunnerInput") as reader:
            root = Path(tmp)
            with self.assertRaisesRegex(MCFError, "Director"):
                auth.freeze_authorization(
                    plan_path=root / "plan.json",
                    runtime_root=root,
                    runner_input_relative="x",
                    runner_input_sha256="a" * 64,
                    benchmark_path=root / "benchmark.json",
                    expected_git_sha="b" * 40,
                    output=root / "auth.json",
                    director_token="NO",
                )
            reader.assert_not_called()

    def test_benchmark_exposing_performance_is_rejected(self):
        runner_sha = "b" * 64
        git_sha = "c" * 40
        plan = {"plan_sha256": "a" * 64, "candidate_count": 6852, "batch_count": 14}
        bad = self.benchmark(runner_sha)
        bad["candidate_performance_exposed"] = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            benchmark_path = root / "benchmark.json"
            plan_path.write_bytes(canonical(plan))
            benchmark_path.write_bytes(canonical(bad))
            reader = SimpleNamespace(assert_unchanged=lambda: None)
            with patch.object(auth, "validate_plan"), \
                 patch.object(auth, "current_git_sha", return_value=git_sha), \
                 patch.object(auth, "FrozenRunnerInput", return_value=reader):
                with self.assertRaisesRegex(MCFError, "capacity benchmark"):
                    auth.freeze_authorization(
                        plan_path=plan_path,
                        runtime_root=root,
                        runner_input_relative="x",
                        runner_input_sha256=runner_sha,
                        benchmark_path=benchmark_path,
                        expected_git_sha=git_sha,
                        output=root / "auth.json",
                        director_token=auth.DIRECTOR_TOKEN,
                    )


if __name__ == "__main__":
    unittest.main()
