import inspect
import json
import tempfile
import unittest
from pathlib import Path

from yatl.data import SYMBOLS
from yatl.execution import scenarios
from yatl.execution.scenarios import (
    SCENARIOS,
    ExecutionScenarioError,
    execution_matrix_sha256,
    run_adversarial_execution_matrix,
    scenario_artifact_json,
    write_adversarial_execution_matrix,
)


class ExecutionScenarioMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_adversarial_execution_matrix()

    def test_fixed_scenario_order_is_complete(self):
        self.assertEqual(
            SCENARIOS,
            (
                "DUPLICATE_INTENT",
                "CRASH_ROLLBACK",
                "STALE_AUTHORIZATION",
                "OUT_OF_ORDER_EVENT",
                "JOURNAL_CORRUPTION",
                "SNAPSHOT_CORRUPTION",
                "MISSING_FILL_CANDLE",
                "COST_POLICY_MISMATCH",
                "UNCERTAIN_COMMIT",
            ),
        )

    def test_matrix_contains_every_symbol_and_scenario_in_fixed_order(self):
        expected = tuple(
            (symbol, name)
            for symbol in SYMBOLS
            for name in SCENARIOS
        )
        actual = tuple((item.symbol, item.name) for item in self.result.runs)
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.result.runs), len(SYMBOLS) * len(SCENARIOS))

    def test_every_scenario_passes_atomic_fail_closed_contract(self):
        for item in self.result.runs:
            with self.subTest(symbol=item.symbol, scenario=item.name):
                record = json.loads(item.artifact_json)
                self.assertTrue(record["passed"])
                self.assertTrue(record["atomic_state_preserved"])
                self.assertTrue(
                    all(
                        record["observed"].get(key) == value
                        for key, value in record["expected"].items()
                    )
                )
                self.assertEqual(record["symbol"], item.symbol)
                self.assertEqual(record["scenario"], item.name)

    def test_engineering_fixture_cannot_claim_real_strategy_readiness(self):
        for item in self.result.runs:
            record = json.loads(item.artifact_json)
            self.assertTrue(record["engineering_fixture"])
            self.assertFalse(record["real_strategy_qualification"])
            self.assertTrue(record["paper_only"])
            self.assertEqual(record["live_master_lock"], "OFF")
            self.assertFalse(record["trade_permission"])
            self.assertFalse(record["exchange_order_submission"])
            self.assertFalse(record["ai_direct_execution"])
            self.assertFalse(record["allow_short"])
            self.assertFalse(record["allow_leverage"])

    def test_matrix_replay_is_byte_identical(self):
        replay = run_adversarial_execution_matrix()
        self.assertEqual(self.result, replay)
        self.assertEqual(self.result.index_json, replay.index_json)
        self.assertEqual(
            execution_matrix_sha256(self.result),
            execution_matrix_sha256(replay),
        )

    def test_corruption_and_uncertain_state_codes_are_exact(self):
        by_key = {
            (item.symbol, item.name): json.loads(item.artifact_json)
            for item in self.result.runs
        }
        for symbol in SYMBOLS:
            self.assertEqual(
                by_key[(symbol, "JOURNAL_CORRUPTION")]["observed"],
                {"clean": "MATCH", "corrupt": "INTENT_INVALID", "ready": False},
            )
            self.assertEqual(
                by_key[(symbol, "SNAPSHOT_CORRUPTION")]["observed"],
                {"code": "SNAPSHOT_CORRUPT", "ready": False},
            )
            uncertain = by_key[(symbol, "UNCERTAIN_COMMIT")]["observed"]
            self.assertEqual(uncertain["code"], "AMBIGUOUS_COMMIT")
            self.assertFalse(uncertain["ready"])
            self.assertTrue(uncertain["pending_preserved"])
            self.assertTrue(uncertain["confirmation_available"])

    def test_duplicate_stale_and_order_faults_preserve_single_effect(self):
        by_key = {
            (item.symbol, item.name): json.loads(item.artifact_json)
            for item in self.result.runs
        }
        for symbol in SYMBOLS:
            duplicate = by_key[(symbol, "DUPLICATE_INTENT")]["observed"]
            self.assertEqual(duplicate["intent_count"], 1)
            self.assertFalse(duplicate["duplicate_effect"])

            stale = by_key[(symbol, "STALE_AUTHORIZATION")]["observed"]
            self.assertTrue(stale["stale_rejected"])
            self.assertTrue(stale["original_preserved"])
            self.assertEqual(stale["intent_count"], 1)

            order = by_key[(symbol, "OUT_OF_ORDER_EVENT")]["observed"]
            self.assertTrue(order["out_of_order_rejected"])
            self.assertEqual(order["event_count"], 1)
            self.assertEqual(order["state_sequence"], 0)

    def test_atomic_writer_publishes_once_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "p5-009-evidence"
            path = write_adversarial_execution_matrix(self.result, output)
            self.assertEqual(path, output)
            files = sorted(item.name for item in output.iterdir())
            self.assertEqual(len(files), 1 + len(self.result.runs))
            self.assertIn("p5-009-index.json", files)
            stored = (output / "p5-009-index.json").read_text(encoding="utf-8")
            self.assertEqual(stored, self.result.index_json)
            with self.assertRaises(ExecutionScenarioError):
                write_adversarial_execution_matrix(self.result, output)

    def test_artifacts_are_canonical_bounded_and_source_has_no_external_capability(self):
        for item in self.result.runs:
            record = json.loads(item.artifact_json)
            self.assertEqual(scenario_artifact_json(record), item.artifact_json)
            self.assertLessEqual(
                len(item.artifact_json.encode("utf-8")),
                scenarios.MAX_ARTIFACT_BYTES,
            )
        source = inspect.getsource(scenarios)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "websockets",
            "socket",
            "API_KEY",
            "API_SECRET",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
