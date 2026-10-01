import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.mass_candidate_factory.models import MCFError, canonical, digest
from research.mass_candidate_factory.production_distributed import (
    EXPECTED_EXECUTABLE_COUNT,
    SAFETY,
    batch,
    batch_candidates,
    build_batch_manifest,
    build_execution_plan,
    claim_batch,
    clear_pause,
    coordinator_status,
    coordinator_pause_request,
    coordinator_mark_paused,
    coordinator_resume,
    coordinator_release,
    d1_seed_sql,
    heartbeat,
    init_coordinator,
    mark_ingested,
    next_candidate,
    request_pause,
    status,
    validate_plan,
    verify_batch_manifest,
    write_candidate_result,
)


GIT_SHA = "a" * 40
RUNNER_SHA = "b" * 64


def result_for(row):
    body = {
        "schema": "MCF_PRODUCTION_ACCOUNTING/1.0.0",
        "candidate_id": row["candidate_id"],
        "candidate_spec_sha256": row["candidate_spec_sha256"],
        "family_id": "FAM",
        "economic_mechanism_id": row["family"],
        "family_spec_sha256": "f" * 64,
        "neighbor_graph_sha256": "e" * 64,
        "evidence_partition": "DEVELOPMENT",
        "exact_accounting": True,
        "completed_trades": 10,
        "aggregate_stress_net_return": "0.01",
        "median_symbol_stress_net_return": "0.01",
        "fold_stress_returns": ("0.01",) * 6,
        "maximum_normalized_drawdown": "0.01",
        "mean_turnover": "1.0",
        "f0_f3_state": "DEVELOPMENT_FAIL",
        "daily_return_series": {
            "calendar_days": (1, 2, 3),
            "returns": ("0.0", "0.0", "0.0"),
            "valid_mask": (True, True, True),
        },
        "per_symbol_base": ({"huge": "base"},),
        "per_symbol_stress": ({"huge": "stress"},),
        "per_symbol_daily_return_series": ({"huge": "daily"},),
    }
    return {**body, "result_sha256": digest(body)}


class DistributedExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_execution_plan()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "coordinator.sqlite3"

    def test_exact_partition_and_hashes(self):
        plan = self.plan
        validate_plan(plan)
        self.assertEqual(plan["candidate_count"], EXPECTED_EXECUTABLE_COUNT)
        self.assertEqual(plan["batch_count"], 14)
        self.assertEqual([x["candidate_count"] for x in plan["batches"][:-1]], [500] * 13)
        self.assertEqual(plan["batches"][-1]["candidate_count"], 352)
        self.assertEqual(plan["safety"], SAFETY)
        self.assertFalse(plan["safety"]["performance_execution_authorized"])
        self.assertEqual(
            sum(len(x["microshards"]) for x in plan["batches"]),
            EXPECTED_EXECUTABLE_COUNT,
        )
        self.assertTrue(all(
            shard["candidate_count"] == 1
            for item in plan["batches"]
            for shard in item["microshards"]
        ))

    def test_plan_is_deterministic(self):
        self.assertEqual(self.plan, build_execution_plan())

    def test_d1_seed_contains_exact_plan_and_all_batches(self):
        sql = d1_seed_sql(self.plan)
        self.assertIn(self.plan["plan_sha256"], sql)
        self.assertEqual(sql.count("INSERT INTO batches("), 14)
        self.assertIn("'B001'", sql)
        self.assertIn("'B014'", sql)
        self.assertNotIn("NODE-", sql)

    def test_plan_tamper_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed["batches"][0]["microshards"][0]["candidates"][0]["candidate_id"] = "CHANGED"
        with self.assertRaises(MCFError):
            validate_plan(changed)

    def test_pause_resume_and_next_candidate(self):
        first = batch_candidates(self.plan, "B001")[0]
        self.assertEqual(next_candidate(self.root, self.plan, "B001")["candidate_id"], first["candidate_id"])
        self.assertEqual(request_pause(self.root, self.plan, "B001")["status"], "PAUSE_REQUESTED")
        self.assertIsNone(next_candidate(self.root, self.plan, "B001"))
        self.assertEqual(status(self.root, self.plan, "B001")["status"], "PAUSED_SAFE")
        self.assertEqual(clear_pause(self.root, self.plan, "B001")["status"], "RESUME_ALLOWED")
        self.assertEqual(next_candidate(self.root, self.plan, "B001")["candidate_id"], first["candidate_id"])

    def test_candidate_result_is_idempotent_and_resume_skips_completed(self):
        rows = batch_candidates(self.plan, "B001")
        first = rows[0]
        saved = write_candidate_result(
            self.root, self.plan, "B001", first["candidate_id"],
            node_id="NODE-LAPTOP", git_sha=GIT_SHA,
            runner_input_sha256=RUNNER_SHA, result=result_for(first),
        )
        same = write_candidate_result(
            self.root, self.plan, "B001", first["candidate_id"],
            node_id="NODE-LAPTOP", git_sha=GIT_SHA,
            runner_input_sha256=RUNNER_SHA, result=result_for(first),
        )
        self.assertEqual(saved, same)
        artifact = self.root / saved["artifact"]
        envelope = json.loads(artifact.read_bytes())
        compact = envelope["result"]
        self.assertNotIn("per_symbol_base", compact)
        self.assertNotIn("per_symbol_stress", compact)
        self.assertNotIn("per_symbol_daily_return_series", compact)
        self.assertEqual(compact["projection_schema"], "MCF_PRODUCTION_RESULT_PROJECTION/1.0.0")
        report = status(self.root, self.plan, "B001")
        self.assertEqual(report["complete"], 1)
        self.assertEqual(report["remaining"], 499)
        self.assertEqual(report["next_candidate_id"], rows[1]["candidate_id"])
        self.assertEqual(next_candidate(self.root, self.plan, "B001")["candidate_id"], rows[1]["candidate_id"])


    def test_identical_cross_node_rerun_is_idempotent(self):
        row = batch_candidates(self.plan, "B001")[0]
        first = write_candidate_result(
            self.root, self.plan, "B001", row["candidate_id"],
            node_id="NODE-VPS", git_sha=GIT_SHA,
            runner_input_sha256=RUNNER_SHA, result=result_for(row),
        )
        second = write_candidate_result(
            self.root, self.plan, "B001", row["candidate_id"],
            node_id="NODE-LAPTOP", git_sha=GIT_SHA,
            runner_input_sha256=RUNNER_SHA, result=result_for(row),
        )
        self.assertEqual(first["result_artifact_sha256"], second["result_artifact_sha256"])
        self.assertEqual(first["artifact"], second["artifact"])
        doc = json.loads((self.root / first["artifact"]).read_bytes())
        self.assertEqual(doc["producer_node_id"], "NODE-VPS")

    def test_nondeterministic_duplicate_result_rejected(self):
        row = batch_candidates(self.plan, "B001")[0]
        write_candidate_result(
            self.root, self.plan, "B001", row["candidate_id"],
            node_id="NODE-VPS", git_sha=GIT_SHA,
            runner_input_sha256=RUNNER_SHA, result=result_for(row),
        )
        changed = result_for(row)
        changed["net_return"] = "0.02"
        with self.assertRaises(MCFError):
            write_candidate_result(
                self.root, self.plan, "B001", row["candidate_id"],
                node_id="NODE-VPS", git_sha=GIT_SHA,
                runner_input_sha256=RUNNER_SHA, result=changed,
            )

    def test_candidate_cannot_escape_assigned_batch(self):
        row = batch_candidates(self.plan, "B002")[0]
        with self.assertRaises(MCFError):
            write_candidate_result(
                self.root, self.plan, "B001", row["candidate_id"],
                node_id="NODE-VPS", git_sha=GIT_SHA,
                runner_input_sha256=RUNNER_SHA, result=result_for(row),
            )

    def _complete_last_batch(self):
        for i, row in enumerate(batch_candidates(self.plan, "B014")):
            node = ("NODE-VPS", "NODE-LAPTOP", "NODE-WORKPC")[i % 3]
            write_candidate_result(
                self.root, self.plan, "B014", row["candidate_id"],
                node_id=node, git_sha=GIT_SHA,
                runner_input_sha256=RUNNER_SHA, result=result_for(row),
            )

    def test_complete_batch_manifest_reconciles_across_nodes(self):
        self._complete_last_batch()
        report = status(self.root, self.plan, "B014")
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["complete"], 352)
        manifest = build_batch_manifest(self.root, self.plan, "B014")
        self.assertEqual(manifest["candidate_count"], 352)
        self.assertEqual(manifest["nodes"], ["NODE-LAPTOP", "NODE-VPS", "NODE-WORKPC"])
        verified = verify_batch_manifest(self.root, self.plan, manifest)
        self.assertEqual(verified["status"], "BATCH_RECONCILED_READY_FOR_INGEST")

    def test_batch_manifest_rejects_mixed_runtime_identity(self):
        rows = batch_candidates(self.plan, "B014")
        for i, row in enumerate(rows):
            write_candidate_result(
                self.root, self.plan, "B014", row["candidate_id"],
                node_id="NODE-VPS", git_sha=GIT_SHA,
                runner_input_sha256=("c" * 64 if i == 0 else RUNNER_SHA),
                result=result_for(row),
            )
        with self.assertRaises(MCFError):
            build_batch_manifest(self.root, self.plan, "B014")

    def test_coordinator_claim_blocks_duplicate_live_owner_and_expiry_recovers(self):
        init_coordinator(self.db, self.plan)
        first = claim_batch(
            self.db, self.plan, node_id="NODE-VPS", batch_code="B001",
            lease_seconds=60, now_ms=1_000,
        )
        self.assertEqual(first["status"], "BATCH_CLAIMED")
        with self.assertRaises(MCFError):
            claim_batch(
                self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B001",
                lease_seconds=60, now_ms=2_000,
            )
        renewed = heartbeat(
            self.db, self.plan, node_id="NODE-VPS", batch_code="B001",
            lease_seconds=60, now_ms=30_000,
        )
        self.assertEqual(renewed["lease_until_ms"], 90_000)
        recovered = claim_batch(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B001",
            lease_seconds=60, now_ms=90_001,
        )
        self.assertEqual(recovered["node_id"], "NODE-LAPTOP")

    def test_coordinator_pause_survives_lease_expiry_until_explicit_resume_or_release(self):
        init_coordinator(self.db, self.plan)
        claim_batch(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            lease_seconds=60, now_ms=1_000,
        )
        requested = coordinator_pause_request(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            now_ms=2_000,
        )
        self.assertEqual(requested["status"], "PAUSE_REQUESTED")
        paused = coordinator_mark_paused(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            now_ms=3_000,
        )
        self.assertEqual(paused["status"], "PAUSED_SAFE")
        with self.assertRaises(MCFError):
            claim_batch(
                self.db, self.plan, node_id="NODE-WORKPC", batch_code="B002",
                lease_seconds=60, now_ms=1_000_000,
            )
        resumed = coordinator_resume(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            lease_seconds=60, now_ms=1_000_001,
        )
        self.assertEqual(resumed["status"], "BATCH_RESUMED")
        coordinator_pause_request(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            now_ms=1_000_002,
        )
        coordinator_mark_paused(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            now_ms=1_000_003,
        )
        released = coordinator_release(
            self.db, self.plan, node_id="NODE-LAPTOP", batch_code="B002",
            now_ms=1_000_004,
        )
        self.assertEqual(released["status"], "BATCH_RELEASED")
        reclaimed = claim_batch(
            self.db, self.plan, node_id="NODE-WORKPC", batch_code="B002",
            lease_seconds=60, now_ms=1_000_005,
        )
        self.assertEqual(reclaimed["node_id"], "NODE-WORKPC")

    def test_auto_claim_assigns_distinct_batches_to_three_nodes(self):
        init_coordinator(self.db, self.plan)
        claims = [
            claim_batch(self.db, self.plan, node_id=node, lease_seconds=300, now_ms=1_000)
            for node in ("NODE-VPS", "NODE-LAPTOP", "NODE-WORKPC")
        ]
        self.assertEqual([x["batch_code"] for x in claims], ["B001", "B002", "B003"])
        report = coordinator_status(self.db, self.plan)
        self.assertEqual(report["counts"]["CLAIMED"], 3)
        self.assertEqual(report["counts"]["AVAILABLE"], 11)

    def test_coordinator_refuses_different_plan(self):
        init_coordinator(self.db, self.plan)
        changed = copy.deepcopy(self.plan)
        changed["plan_sha256"] = "f" * 64
        with self.assertRaises(MCFError):
            coordinator_status(self.db, changed)

    def test_mark_ingested_is_idempotent_but_conflict_fails(self):
        init_coordinator(self.db, self.plan)
        item = batch(self.plan, "B014")
        artifacts = [
            {
                "candidate_id": row["candidate_id"],
                "candidate_spec_sha256": row["candidate_spec_sha256"],
                "result_artifact_sha256": f"{i % 16:x}" * 64,
            }
            for i, row in enumerate(batch_candidates(self.plan, "B014"))
        ]
        base = {
            "schema": "MCF_DISTRIBUTED_BATCH_RESULT_MANIFEST/1.0.0",
            "generation_id": "MCF-PROD-001",
            "plan_sha256": self.plan["plan_sha256"],
            "batch_code": "B014",
            "batch_sha256": item["batch_sha256"],
            "candidate_count": item["candidate_count"],
            "git_sha": GIT_SHA,
            "runner_input_sha256": RUNNER_SHA,
            "nodes": ["NODE-LAPTOP"],
            "artifacts": artifacts,
        }
        manifest = {**base, "batch_result_manifest_sha256": digest(base)}
        first = mark_ingested(self.db, self.plan, manifest=manifest, now_ms=1_000)
        second = mark_ingested(self.db, self.plan, manifest=manifest, now_ms=2_000)
        self.assertEqual(first["batch_result_manifest_sha256"], second["batch_result_manifest_sha256"])
        bad = copy.deepcopy(manifest)
        bad["artifacts"][0]["candidate_id"] = "WRONG"
        bad["batch_result_manifest_sha256"] = digest({
            k: v for k, v in bad.items() if k != "batch_result_manifest_sha256"
        })
        with self.assertRaises(MCFError):
            mark_ingested(self.db, self.plan, manifest=bad, now_ms=3_000)


if __name__ == "__main__":
    unittest.main()
