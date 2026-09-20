import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from yatl.analytics.scenarios import (
    ACCEPTED_UPSTREAM_IDENTITIES,
    ARTIFACT_KIND,
    MATRIX_KIND,
    SCENARIOS,
    AnalyticsScenarioError,
    AnalyticsScenarioMatrixResult,
    AnalyticsScenarioResult,
    analytics_matrix_sha256,
    run_adversarial_analytics_matrix,
    scenario_artifact_json,
    write_adversarial_analytics_matrix,
)


class AnalyticsScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_adversarial_analytics_matrix()

    def test_matrix_has_exact_symbol_scenario_coverage(self):
        self.assertEqual(len(SCENARIOS), 9)
        self.assertEqual(len(self.result.runs), 18)
        self.assertEqual(
            tuple((item.symbol, item.name) for item in self.result.runs),
            tuple(
                (symbol, name)
                for symbol in ("BTCUSDT", "ETHUSDT")
                for name in SCENARIOS
            ),
        )

    def test_matrix_replay_is_byte_identical(self):
        replay = run_adversarial_analytics_matrix()
        self.assertEqual(self.result, replay)
        self.assertEqual(self.result.index_json, replay.index_json)
        self.assertEqual(
            analytics_matrix_sha256(self.result),
            analytics_matrix_sha256(replay),
        )

    def test_results_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.result.runs[0].name = "CHANGED"

    def test_quality_failures_have_exact_codes_and_no_partial_payload(self):
        expected = {
            "UPSTREAM_TAMPERING": "UPSTREAM_DIGEST_CHANGED",
            "DUPLICATE_ORPHAN_FILL": "ORPHAN_RELATIONSHIP",
            "CROSS_SYMBOL_LINKAGE": "ANALYTICS_CHAIN_INVALID",
            "FUTURE_TIMESTAMP": "FUTURE_TIMESTAMP",
            "CHANGED_COST_EQUITY_TOTALS": "INCONSISTENT_TOTALS",
            "FABRICATED_PROFITABILITY": "INCONSISTENT_TOTALS",
            "SCHEMA_SMUGGLING": "ANALYTICS_CHAIN_INVALID",
        }
        for item in self.result.runs:
            if item.name not in expected:
                continue
            with self.subTest(symbol=item.symbol, scenario=item.name):
                record = json.loads(item.artifact_json)
                observed = record["observed"]
                self.assertEqual(observed["status"], "FAIL")
                self.assertFalse(observed["publication_allowed"])
                self.assertFalse(observed["accepted_chain_present"])
                self.assertFalse(observed["analytics_payload_present"])
                self.assertEqual(
                    [entry["code"] for entry in observed["diagnostics"]],
                    [expected[item.name]],
                )

    def test_evidence_upgrade_attempt_is_rejected(self):
        for item in self.result.runs:
            if item.name != "EVIDENCE_LABEL_UPGRADE":
                continue
            observed = json.loads(item.artifact_json)["observed"]
            self.assertEqual(
                observed["code"],
                "EVIDENCE_LABEL_UPGRADE_REJECTED",
            )
            self.assertEqual(
                observed["strategy_evidence"],
                "INSUFFICIENT_EVIDENCE",
            )
            self.assertFalse(observed["publication_allowed"])

    def test_readonly_journal_mutation_is_rejected_and_quality_survives(self):
        for item in self.result.runs:
            if item.name != "JOURNAL_MUTATION":
                continue
            observed = json.loads(item.artifact_json)["observed"]
            self.assertEqual(
                observed["code"],
                "READ_ONLY_MUTATION_REJECTED",
            )
            self.assertTrue(observed["no_write"])
            self.assertEqual(observed["quality_after_attempt"], "PASS")

    def test_every_artifact_preserves_frozen_safety_state_and_identities(self):
        for item in self.result.runs:
            record = json.loads(item.artifact_json)
            self.assertEqual(record["artifact_kind"], ARTIFACT_KIND)
            self.assertTrue(record["passed"])
            self.assertEqual(
                record["accepted_upstream_identities"],
                ACCEPTED_UPSTREAM_IDENTITIES,
            )
            self.assertEqual(
                record["strategy_evidence"],
                "INSUFFICIENT_EVIDENCE",
            )
            self.assertTrue(record["paper_only"])
            self.assertTrue(record["read_only_analytics"])
            self.assertEqual(record["live_master_lock"], "OFF")
            self.assertTrue(record["spot_only"])
            self.assertFalse(record["allow_short"])
            self.assertFalse(record["allow_margin"])
            self.assertFalse(record["allow_futures"])
            self.assertFalse(record["allow_leverage"])
            self.assertFalse(record["allow_withdrawal"])
            self.assertFalse(record["trade_permission"])
            self.assertFalse(record["order_endpoints"])
            self.assertFalse(record["quantity_authority"])
            self.assertFalse(record["risk_authorization_mutation"])
            self.assertFalse(record["ai_direct_execution"])
            self.assertFalse(record["partial_publication_on_failure"])

    def test_artifacts_are_canonical_bounded_and_sanitized(self):
        for item in self.result.runs:
            self.assertEqual(
                scenario_artifact_json(json.loads(item.artifact_json)),
                item.artifact_json,
            )
            lowered = item.artifact_json.casefold()
            for forbidden in (
                '"api_key"',
                '"api_secret"',
                '"password"',
                '"credential"',
                '"endpoint_url"',
                '"raw_response"',
                '"canonical_response_json"',
                '"database_path"',
                '"private_key"',
                '"account_id"',
                '"risk_authorization"',
                '"approved_quantity"',
                '"order_request"',
                "traceback",
                "select ",
                "update ",
                "insert ",
                "delete ",
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, lowered)

    def test_index_is_canonical_and_preserves_accepted_identities(self):
        index = json.loads(self.result.index_json)
        self.assertEqual(index["artifact_kind"], MATRIX_KIND)
        self.assertEqual(index["symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(index["scenarios"], list(SCENARIOS))
        self.assertEqual(len(index["runs"]), 18)
        self.assertEqual(
            index["accepted_upstream_identities"],
            ACCEPTED_UPSTREAM_IDENTITIES,
        )
        self.assertEqual(
            index["strategy_evidence"],
            "INSUFFICIENT_EVIDENCE",
        )
        self.assertFalse(index["trade_permission"])
        self.assertFalse(index["order_endpoints"])
        self.assertFalse(index["quantity_authority"])
        self.assertFalse(index["risk_authorization_mutation"])
        self.assertFalse(index["ai_direct_execution"])

    def test_atomic_write_produces_exact_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p7-009-evidence"
            write_adversarial_analytics_matrix(self.result, target)
            names = sorted(path.name for path in target.iterdir())
            self.assertEqual(len(names), 19)
            self.assertIn("p7-009-index.json", names)
            self.assertEqual(
                (target / "p7-009-index.json").read_text(encoding="utf-8"),
                self.result.index_json,
            )

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p7-009-evidence"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(AnalyticsScenarioError):
                write_adversarial_analytics_matrix(self.result, target)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_invalid_result_and_matrix_are_rejected(self):
        item = self.result.runs[0]
        with self.assertRaises(AnalyticsScenarioError):
            AnalyticsScenarioResult(
                item.symbol,
                item.name,
                item.artifact_json,
                "0" * 64,
            )
        with self.assertRaises(AnalyticsScenarioError):
            AnalyticsScenarioMatrixResult(
                tuple(reversed(self.result.runs)),
                self.result.index_json,
            )

    def test_source_has_no_execution_backtest_account_risk_network_or_provider_import(self):
        import yatl.analytics.scenarios as module

        source = inspect.getsource(module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.backtest",
            "import yatl.backtest",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "subprocess",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
