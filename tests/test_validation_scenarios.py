import inspect
import json
import tempfile
import unittest
from pathlib import Path

import yatl.validation.scenarios as scenarios
from yatl.validation.scenarios import (
    ACCEPTED,
    ARTIFACT_KIND,
    MATRIX_KIND,
    SCENARIOS,
    SYMBOLS,
    CANDIDATE_REJECTED,
    ECONOMICS_REJECTED,
    GATES_REJECTED,
    PROVENANCE_REJECTED,
    SAFETY_REJECTED,
    WINDOW_REJECTED,
    ValidationScenarioError,
    ValidationScenarioMatrixResult,
    ValidationScenarioResult,
    run_adversarial_validation_matrix,
    scenario_artifact_json,
    validation_matrix_sha256,
    write_adversarial_validation_matrix,
)
from yatl.validation.scenarios_runtime import build_mock_validation_scenario_fixture


EXPECTED_CODES = {
    "PRE_WINDOW_DATA_CONTAMINATION": PROVENANCE_REJECTED,
    "CANDIDATE_MUTATION_AFTER_SEAL": CANDIDATE_REJECTED,
    "THRESHOLD_MUTATION_AFTER_SEAL": GATES_REJECTED,
    "FEE_SLIPPAGE_REMOVAL": ECONOMICS_REJECTED,
    "FABRICATED_POSITIVE_PNL": ECONOMICS_REJECTED,
    "DRAWDOWN_SUPPRESSION": ECONOMICS_REJECTED,
    "SAMPLE_DELETION_CHERRY_PICKING": ECONOMICS_REJECTED,
    "CROSS_SYMBOL_CROSS_WINDOW_MATERIAL": WINDOW_REJECTED,
    "DATA_QUALITY_FAILURE": PROVENANCE_REJECTED,
    "RISK_SAFETY_BREACH": SAFETY_REJECTED,
    "EVIDENCE_LABEL_LIVE_READINESS_UPGRADE": SAFETY_REJECTED,
}


class ValidationAdversarialMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary, cls.fixture, cls.client = build_mock_validation_scenario_fixture()
        cls.matrix = run_adversarial_validation_matrix(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def records(self):
        return [json.loads(item.artifact_json) for item in self.matrix.runs]

    def by(self, name):
        item = next(item for item in self.matrix.runs if item.name == name)
        return json.loads(item.artifact_json)

    def test_symbols_and_scenarios_are_exact(self):
        self.assertEqual(SYMBOLS, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(len(SCENARIOS), 11)
        self.assertEqual(tuple(item.name for item in self.matrix.runs), SCENARIOS)

    def test_accepted_fixture_verifies_before_attacks(self):
        record = json.loads(self.fixture.canonical_audit_json)
        self.assertEqual(scenarios._verify_audit(record, self.fixture), ACCEPTED)
        self.assertEqual(record["audit_sha256"], self.fixture.audit_sha256)

    def test_every_attack_is_resigned_and_rejected_exactly(self):
        for record in self.records():
            with self.subTest(scenario=record["scenario"]):
                self.assertTrue(record["expected"]["attack_resigned"])
                self.assertEqual(
                    record["observed"]["verification_code"],
                    EXPECTED_CODES[record["scenario"]],
                )
                self.assertNotEqual(
                    record["observed"]["verification_code"],
                    ACCEPTED,
                )
                self.assertEqual(record["expected"], record["observed"])

    def test_pre_window_contamination_is_rejected(self):
        self.assertEqual(
            self.by("PRE_WINDOW_DATA_CONTAMINATION")["observed"]["verification_code"],
            PROVENANCE_REJECTED,
        )

    def test_candidate_and_threshold_mutation_are_distinct(self):
        self.assertEqual(
            self.by("CANDIDATE_MUTATION_AFTER_SEAL")["observed"]["verification_code"],
            CANDIDATE_REJECTED,
        )
        self.assertEqual(
            self.by("THRESHOLD_MUTATION_AFTER_SEAL")["observed"]["verification_code"],
            GATES_REJECTED,
        )

    def test_all_economic_fabrication_scenarios_are_rejected(self):
        for name in (
            "FEE_SLIPPAGE_REMOVAL",
            "FABRICATED_POSITIVE_PNL",
            "DRAWDOWN_SUPPRESSION",
            "SAMPLE_DELETION_CHERRY_PICKING",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    self.by(name)["observed"]["verification_code"],
                    ECONOMICS_REJECTED,
                )

    def test_cross_symbol_cross_window_is_rejected(self):
        self.assertEqual(
            self.by("CROSS_SYMBOL_CROSS_WINDOW_MATERIAL")["observed"]["verification_code"],
            WINDOW_REJECTED,
        )

    def test_data_quality_failure_is_rejected(self):
        self.assertEqual(
            self.by("DATA_QUALITY_FAILURE")["observed"]["verification_code"],
            PROVENANCE_REJECTED,
        )

    def test_risk_and_live_readiness_upgrades_are_rejected(self):
        for name in (
            "RISK_SAFETY_BREACH",
            "EVIDENCE_LABEL_LIVE_READINESS_UPGRADE",
        ):
            with self.subTest(name=name):
                record = self.by(name)
                self.assertEqual(
                    record["observed"]["verification_code"],
                    SAFETY_REJECTED,
                )
                self.assertFalse(record["p11_unlocked"])
                self.assertEqual(
                    record["strategy_evidence"],
                    "INSUFFICIENT_EVIDENCE",
                )

    def test_accepted_identity_is_unchanged_across_all_scenarios(self):
        identities = [record["accepted_identity"] for record in self.records()]
        self.assertTrue(all(value == identities[0] for value in identities))
        for record in self.records():
            self.assertTrue(record["observed"]["accepted_identities_unchanged"])
            self.assertTrue(record["observed"]["accepted_audit_unchanged"])

    def test_matrix_replay_is_byte_identical(self):
        replay = run_adversarial_validation_matrix(self.fixture)
        self.assertEqual(self.matrix, replay)
        self.assertEqual(self.matrix.index_json, replay.index_json)

    def test_matrix_sha_is_stable(self):
        replay = run_adversarial_validation_matrix(self.fixture)
        self.assertEqual(
            validation_matrix_sha256(self.matrix),
            validation_matrix_sha256(replay),
        )

    def test_matrix_index_is_canonical_and_safety_locked(self):
        record = json.loads(self.matrix.index_json)
        self.assertEqual(record["artifact_kind"], MATRIX_KIND)
        self.assertEqual(record["symbols"], list(SYMBOLS))
        self.assertEqual(record["scenarios"], list(SCENARIOS))
        self.assertEqual(
            self.matrix.index_json,
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n",
        )
        self.assertFalse(record["p11_unlocked"])
        self.assertFalse(record["trade_permission"])
        self.assertFalse(record["order_endpoint"])
        self.assertFalse(record["ai_direct_execution"])
        self.assertFalse(record["accepted_evidence_mutated"])

    def test_each_scenario_artifact_is_canonical_and_hashed(self):
        for item in self.matrix.runs:
            with self.subTest(name=item.name):
                record = json.loads(item.artifact_json)
                self.assertEqual(record["artifact_kind"], ARTIFACT_KIND)
                self.assertEqual(
                    scenario_artifact_json(record),
                    item.artifact_json,
                )
                self.assertEqual(
                    scenarios._sha256(item.artifact_json),
                    item.result_sha256,
                )

    def test_writer_is_atomic_no_overwrite_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            write_adversarial_validation_matrix(self.matrix, target)
            files = tuple(sorted(item.name for item in target.iterdir()))
            self.assertEqual(len(files), 1 + len(SCENARIOS))
            self.assertIn("p10-009-index.json", files)
            with self.assertRaises(ValidationScenarioError):
                write_adversarial_validation_matrix(self.matrix, target)

    def test_writer_requires_existing_real_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing" / "evidence"
            with self.assertRaises(ValidationScenarioError):
                write_adversarial_validation_matrix(self.matrix, target)

    def test_tampered_scenario_artifact_digest_is_rejected(self):
        record = json.loads(self.matrix.runs[0].artifact_json)
        record["result_sha256"] = "a" * 64
        with self.assertRaises(ValidationScenarioError):
            scenario_artifact_json(record)

    def test_tampered_matrix_index_is_rejected(self):
        record = json.loads(self.matrix.index_json)
        record["p11_unlocked"] = True
        encoded = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        with self.assertRaises(ValidationScenarioError):
            ValidationScenarioMatrixResult(self.matrix.runs, encoded)

    def test_scenario_result_rejects_wrong_digest(self):
        item = self.matrix.runs[0]
        with self.assertRaises(ValidationScenarioError):
            ValidationScenarioResult(item.name, item.artifact_json, "a" * 64)

    def test_invalid_fixture_is_rejected(self):
        with self.assertRaises(ValidationScenarioError):
            run_adversarial_validation_matrix(object())

    def test_scenario_source_has_no_network_credential_execution_or_clock_capability(self):
        source = inspect.getsource(scenarios)
        for forbidden in (
            "BinancePublicRestClient",
            "collect_forward_snapshot",
            "write_many(",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "os.environ",
            "os.getenv",
            "dotenv",
            "API_KEY",
            "API_SECRET",
            "openai",
            "anthropic",
            "subprocess",
            "time.time",
            "time.monotonic",
            "datetime.now",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "input(",
            "eval(",
            "exec(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
