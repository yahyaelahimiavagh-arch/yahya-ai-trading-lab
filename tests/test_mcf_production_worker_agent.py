import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory import production_worker_agent as agent


class WorkerAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_text("{}")

    def env(self):
        return {
            "YATL_NODE_ID": "NODE-LAPTOP",
            "YATL_COORDINATOR_URL": "https://coord.example",
            "YATL_NODE_TOKEN": "secret-token",
        }

    def test_doctor_is_nonperformance(self):
        with patch.dict(os.environ, self.env(), clear=True),              patch.object(agent, "preflight", return_value={
                 "status": "NODE_PREFLIGHT_COMPLETE_NO_PERFORMANCE",
                 "performance_execution_authorized": False,
             }):
            rc = agent.main([
                "--root", str(self.root / "state"),
                "--plan", str(self.plan),
                "doctor",
            ])
        self.assertEqual(rc, 0)

    def test_claim_uses_single_environment_control_surface(self):
        fake_plan = {"plan_sha256": "a" * 64}
        with patch.dict(os.environ, self.env(), clear=True),              patch.object(agent, "_load", return_value=fake_plan),              patch.object(agent, "validate_plan"),              patch.object(agent, "claim", return_value={
                 "status": "BATCH_CLAIMED",
                 "batch_code": "B003",
                 "node_id": "NODE-LAPTOP",
             }) as claim_mock:
            rc = agent.main([
                "--root", str(self.root / "state"),
                "--plan", str(self.plan),
                "claim", "B003",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(claim_mock.call_args.kwargs["batch_code"], "B003")
        self.assertEqual(claim_mock.call_args.args[1], "NODE-LAPTOP")

    def test_pause_sets_local_marker_before_remote_request(self):
        events = []
        fake_plan = {"plan_sha256": "a" * 64}

        def local(*args, **kwargs):
            events.append("local")
            return {"status": "PAUSE_REQUESTED"}

        def remote(*args, **kwargs):
            events.append("remote")
            return {"status": "PAUSE_REQUESTED"}

        with patch.dict(os.environ, self.env(), clear=True),              patch.object(agent, "_load", return_value=fake_plan),              patch.object(agent, "validate_plan"),              patch.object(agent, "request_pause", side_effect=local),              patch.object(agent, "pause_request", side_effect=remote):
            rc = agent.main([
                "--root", str(self.root / "state"),
                "--plan", str(self.plan),
                "pause", "B002",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(events, ["local", "remote"])

    def test_resume_clears_local_pause_only_after_remote_accepts(self):
        events = []
        fake_plan = {"plan_sha256": "a" * 64}

        def remote(*args, **kwargs):
            events.append("remote")
            return {"status": "BATCH_RESUMED", "lease_until_ms": 123}

        def local(*args, **kwargs):
            events.append("local")
            return {"status": "RESUME_ALLOWED"}

        with patch.dict(os.environ, self.env(), clear=True),              patch.object(agent, "_load", return_value=fake_plan),              patch.object(agent, "validate_plan"),              patch.object(agent, "resume", side_effect=remote),              patch.object(agent, "clear_pause", side_effect=local):
            rc = agent.main([
                "--root", str(self.root / "state"),
                "--plan", str(self.plan),
                "resume", "B002",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(events, ["remote", "local"])

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            rc = agent.main([
                "--node-id", "NODE-LAPTOP",
                "--coordinator-url", "https://coord.example",
                "--root", str(self.root / "state"),
                "--plan", str(self.plan),
                "status",
            ])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
