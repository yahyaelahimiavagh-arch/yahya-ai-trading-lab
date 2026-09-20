import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from yatl.analyst.scenarios import (
    ARTIFACT_KIND,
    MATRIX_KIND,
    SCENARIOS,
    AnalystScenarioError,
    AnalystScenarioMatrixResult,
    AnalystScenarioResult,
    analyst_matrix_sha256,
    run_adversarial_analyst_matrix,
    scenario_artifact_json,
    write_adversarial_analyst_matrix,
)


class AnalystScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_adversarial_analyst_matrix()

    def test_matrix_has_exact_symbol_scenario_coverage(self):
        self.assertEqual(len(SCENARIOS), 8)
        self.assertEqual(len(self.result.runs), 16)
        self.assertEqual(
            tuple((item.symbol, item.name) for item in self.result.runs),
            tuple(
                (symbol, name)
                for symbol in ("BTCUSDT", "ETHUSDT")
                for name in SCENARIOS
            ),
        )

    def test_matrix_replay_is_byte_identical(self):
        replay = run_adversarial_analyst_matrix()
        self.assertEqual(self.result, replay)
        self.assertEqual(self.result.index_json, replay.index_json)
        self.assertEqual(
            analyst_matrix_sha256(self.result),
            analyst_matrix_sha256(replay),
        )

    def test_results_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.result.runs[0].name = "CHANGED"

    def test_prompt_injection_is_inert_not_authoritative(self):
        for item in self.result.runs:
            if item.name != "PROMPT_INJECTION":
                continue
            record = json.loads(item.artifact_json)
            observed = record["observed"]
            self.assertEqual(observed["response_code"], "ACCEPTED")
            self.assertEqual(observed["grounding_code"], "GROUNDED")
            self.assertEqual(observed["disposition"], "REVIEW")
            self.assertEqual(observed["handling"], "UNTRUSTED_DATA_ONLY")
            self.assertEqual(observed["transport"], "NONE")
            self.assertTrue(observed["injection_in_material"])
            self.assertFalse(observed["injection_in_instructions"])
            self.assertTrue(observed["instructions_fixed"])

    def test_all_other_scenarios_fail_closed(self):
        for item in self.result.runs:
            if item.name == "PROMPT_INJECTION":
                continue
            with self.subTest(symbol=item.symbol, scenario=item.name):
                record = json.loads(item.artifact_json)
                observed = record["observed"]
                self.assertIn(
                    observed.get("disposition"),
                    ("INSUFFICIENT_DATA", None),
                )
                if item.name in {"STALE_INPUT", "FUTURE_INPUT"}:
                    self.assertEqual(observed["stage"], "EVIDENCE")
                    self.assertEqual(observed["code"], "INPUT_REJECTED")
                    self.assertEqual(observed["disposition"], "INSUFFICIENT_DATA")
                else:
                    self.assertEqual(observed["disposition"], "INSUFFICIENT_DATA")
                    self.assertEqual(observed["claims"], 0)

    def test_exact_rejection_codes(self):
        expected = {
            "UNSUPPORTED_CERTAINTY": ("ACCEPTED", "CONTRADICTION"),
            "FABRICATED_EVIDENCE": ("CONTRACT_REJECTED", "UPSTREAM_REJECTED"),
            "SCHEMA_SMUGGLING": ("SCHEMA_REJECTED", "UPSTREAM_REJECTED"),
            "EXECUTABLE_ACTION_REQUEST": ("FORBIDDEN_CONTENT", "UPSTREAM_REJECTED"),
            "PROVIDER_RESPONSE_CORRUPTION": ("MALFORMED_JSON", "UPSTREAM_REJECTED"),
        }
        for item in self.result.runs:
            if item.name not in expected:
                continue
            with self.subTest(symbol=item.symbol, scenario=item.name):
                observed = json.loads(item.artifact_json)["observed"]
                self.assertEqual(
                    (observed["response_code"], observed["grounding_code"]),
                    expected[item.name],
                )

    def test_all_artifacts_preserve_frozen_safety_state(self):
        for item in self.result.runs:
            record = json.loads(item.artifact_json)
            self.assertEqual(record["artifact_kind"], ARTIFACT_KIND)
            self.assertTrue(record["passed"])
            self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
            self.assertTrue(record["paper_only"])
            self.assertTrue(record["analysis_only"])
            self.assertEqual(record["live_master_lock"], "OFF")
            self.assertFalse(record["allow_short"])
            self.assertFalse(record["allow_leverage"])
            self.assertFalse(record["trade_permission"])
            self.assertFalse(record["order_endpoints"])
            self.assertFalse(record["quantity_authority"])
            self.assertFalse(record["risk_authorization_mutation"])
            self.assertFalse(record["ai_direct_execution"])

    def test_artifacts_are_canonical_bounded_and_sanitized(self):
        for item in self.result.runs:
            self.assertEqual(
                scenario_artifact_json(json.loads(item.artifact_json)),
                item.artifact_json,
            )
            encoded = item.artifact_json.lower()
            for forbidden in (
                '"api_key"',
                '"api_secret"',
                '"password"',
                '"credential"',
                '"endpoint_url"',
                '"raw_response"',
                '"canonical_response_json"',
                '"approved_quantity"',
                '"order_request"',
                '"risk_authorization"',
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, encoded)

    def test_index_is_canonical_and_sanitized(self):
        index = json.loads(self.result.index_json)
        self.assertEqual(index["artifact_kind"], MATRIX_KIND)
        self.assertEqual(index["symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(index["scenarios"], list(SCENARIOS))
        self.assertEqual(len(index["runs"]), 16)
        self.assertEqual(index["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(index["trade_permission"])
        self.assertFalse(index["order_endpoints"])
        self.assertFalse(index["quantity_authority"])
        self.assertFalse(index["risk_authorization_mutation"])
        self.assertFalse(index["ai_direct_execution"])

    def test_atomic_write_produces_exact_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p6-009-evidence"
            write_adversarial_analyst_matrix(self.result, target)
            names = sorted(path.name for path in target.iterdir())
            self.assertEqual(len(names), 17)
            self.assertIn("p6-009-index.json", names)
            self.assertEqual(
                (target / "p6-009-index.json").read_text(encoding="utf-8"),
                self.result.index_json,
            )

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p6-009-evidence"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(AnalystScenarioError):
                write_adversarial_analyst_matrix(self.result, target)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_invalid_result_and_matrix_are_rejected(self):
        item = self.result.runs[0]
        with self.assertRaises(AnalystScenarioError):
            AnalystScenarioResult(
                item.symbol,
                item.name,
                item.artifact_json,
                "0" * 64,
            )
        with self.assertRaises(AnalystScenarioError):
            AnalystScenarioMatrixResult(tuple(reversed(self.result.runs)), self.result.index_json)

    def test_source_has_no_provider_network_environment_or_execution_access(self):
        import yatl.analyst.scenarios as scenarios_module

        source = inspect.getsource(scenarios_module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "websockets",
            "socket",
            "os.getenv",
            "os.environ",
            "subprocess",
            "requests",
            "httpx",
            "aiohttp",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
