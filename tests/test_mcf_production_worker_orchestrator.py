import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory import production_worker_orchestrator as orch


class FakeControl:
    def __init__(self, heartbeat_side_effect=None):
        self.heartbeats = []
        self.heartbeat_side_effect = heartbeat_side_effect

    def heartbeat(self, batch_code, lease_seconds):
        self.heartbeats.append((batch_code, lease_seconds))
        if self.heartbeat_side_effect:
            raise self.heartbeat_side_effect
        return {"status": "HEARTBEAT_ACCEPTED"}


class FakeProcess:
    def __init__(self, *, polls, stdout):
        self._polls = list(polls)
        self._stdout = stdout
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        if self._polls:
            value = self._polls.pop(0)
            if value is not None:
                self.returncode = value
            return value
        self.returncode = 0
        return 0

    def communicate(self):
        if self.returncode is None:
            self.returncode = 0
        return self._stdout, None

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class AutoWorkerTest(unittest.TestCase):
    def test_child_heartbeats_while_running_and_returns_result(self):
        process = FakeProcess(
            polls=[None, None, 0],
            stdout=json.dumps({"status": "MICROSHARD_COMPLETE"}),
        )
        control = FakeControl()
        times = iter([0, 20, 40])
        with patch.object(orch, "ROOT", Path(".")):
            out = orch.run_child_with_heartbeat(
                ["python", "worker"],
                batch_code="B001",
                control=control,
                lease_seconds=60,
                heartbeat_seconds=15,
                popen_factory=lambda *a, **kw: process,
                monotonic=lambda: next(times),
                sleeper=lambda _: None,
            )
        self.assertEqual(out["status"], "MICROSHARD_COMPLETE")
        self.assertGreaterEqual(len(control.heartbeats), 2)
        self.assertFalse(process.terminated)

    def test_heartbeat_failure_terminates_child_fail_closed(self):
        process = FakeProcess(
            polls=[None],
            stdout=json.dumps({"status": "MICROSHARD_COMPLETE"}),
        )
        control = FakeControl(heartbeat_side_effect=MCFError("lease lost"))
        # First heartbeat happens before the child exists, so allow it once and
        # fail on the next renewal.
        calls = {"n": 0}

        def heartbeat(batch_code, lease_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise MCFError("lease lost")
            return {"status": "HEARTBEAT_ACCEPTED"}

        control.heartbeat = heartbeat
        times = iter([0, 20])
        with self.assertRaisesRegex(MCFError, "lease lost"):
            orch.run_child_with_heartbeat(
                ["python", "worker"],
                batch_code="B002",
                control=control,
                lease_seconds=60,
                heartbeat_seconds=15,
                popen_factory=lambda *a, **kw: process,
                monotonic=lambda: next(times),
                sleeper=lambda _: None,
            )
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)

    def test_child_command_pins_authorized_identities(self):
        cmd = orch._child_command(
            root=Path("/tmp/state"),
            plan_path=Path("/tmp/runtime/distributed-plan.json"),
            runtime_root=Path("/tmp/runtime"),
            input_relative="runner-input/input-" + "a" * 64 + ".json",
            runner_input_sha256="a" * 64,
            authorization_path=Path("/tmp/auth.json"),
            node_id="NODE-LAPTOP",
            batch_code="B003",
            microshard_code="B003-S004",
            git_sha="b" * 40,
        )
        joined = " ".join(cmd)
        self.assertIn("B003-S004", joined)
        self.assertIn("NODE-LAPTOP", joined)
        self.assertIn("a" * 64, joined)
        self.assertIn("b" * 40, joined)
        self.assertIn("/tmp/auth.json", joined)

    def test_local_control_completes_batch_without_ssh(self):
        control = orch.LocalControl(
            node_id="NODE-VPS",
            db_path=Path("/tmp/coordinator.sqlite3"),
            plan={"plan_sha256": "a" * 64},
        )
        manifest = {
            "batch_code": "B001",
            "batch_result_manifest_sha256": "b" * 64,
        }
        with patch.object(orch, "build_batch_manifest", return_value=manifest), \
             patch.object(orch, "verify_batch_manifest") as verify, \
             patch.object(orch, "local_mark_ingested", return_value={"status": "BATCH_INGESTED"}) as mark:
            out = control.complete_batch(
                Path("/tmp/results"),
                {"plan_sha256": "a" * 64},
                "B001",
            )
        self.assertEqual(out["status"], "LOCAL_BATCH_INGESTED_ACCEPTED")
        verify.assert_called_once()
        mark.assert_called_once()

    def test_authorization_is_checked_before_remote_claim(self):
        plan = {"plan_sha256": "a" * 64, "batch_count": 14}
        manifest = {
            "runner_input_sha256": "b" * 64,
            "runner_input_relative": "runner-input/input-" + "b" * 64 + ".json",
            "git_sha": "c" * 40,
        }
        auth = {"authorization_sha256": "d" * 64}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            runtime.mkdir()
            plan_path = runtime / "distributed-plan.json"
            manifest_path = runtime / "worker-bundle-manifest.json"
            auth_path = root / "auth.json"
            plan_path.write_text("{}")
            manifest_path.write_text("{}")
            auth_path.write_text("{}")

            with patch.object(orch, "_load_canonical", side_effect=[plan, manifest, auth]), \
                 patch.object(orch, "validate_plan"), \
                 patch.object(orch, "current_git_sha", return_value="c" * 40), \
                 patch.object(orch, "validate_authorization", side_effect=MCFError("auth blocked")), \
                 patch.object(orch.SshControl, "from_environment") as remote:
                with self.assertRaisesRegex(MCFError, "auth blocked"):
                    orch.run_auto_worker(
                        runtime_root=runtime,
                        worker_root=root / "state",
                        authorization_path=auth_path,
                        node_id="NODE-LAPTOP",
                    )
            remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
