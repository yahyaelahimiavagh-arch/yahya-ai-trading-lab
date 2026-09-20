import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.dashboard.scenarios import (
    ARTIFACT_KIND,
    MATRIX_KIND,
    SCENARIOS,
    SYMBOLS,
    DashboardAcceptedFixture,
    DashboardScenarioError,
    DashboardScenarioMatrixResult,
    DashboardScenarioResult,
    dashboard_matrix_sha256,
    run_adversarial_dashboard_matrix,
    scenario_artifact_json,
    write_adversarial_dashboard_matrix,
)
from yatl.dashboard.scenarios_runtime import _fixtures


class DashboardAdversarialMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary, cls.fixtures = _fixtures()
        cls.matrix = run_adversarial_dashboard_matrix(cls.fixtures)

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    def records(self):
        return [json.loads(item.artifact_json) for item in self.matrix.runs]

    def by(self, symbol, scenario):
        item = next(
            item for item in self.matrix.runs
            if item.symbol == symbol and item.name == scenario
        )
        return json.loads(item.artifact_json)

    def test_fixture_symbols_are_exact(self):
        self.assertEqual(tuple(self.fixtures), SYMBOLS)

    def test_fixture_exports_are_distinct_per_symbol(self):
        self.assertNotEqual(
            self.fixtures["BTCUSDT"].export_sha256,
            self.fixtures["ETHUSDT"].export_sha256,
        )

    def test_fixture_export_records_bind_exact_symbol(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                record = json.loads(self.fixtures[symbol].canonical_export_json)
                self.assertEqual(record["analytics"]["symbol"], symbol)
                self.assertEqual(record["quality"]["accepted_chain"]["symbol"], symbol)

    def test_matrix_has_exact_18_runs(self):
        self.assertEqual(len(SCENARIOS), 9)
        self.assertEqual(len(SYMBOLS), 2)
        self.assertEqual(len(self.matrix.runs), 18)

    def test_matrix_order_is_symbol_then_scenario(self):
        expected = tuple(
            (symbol, scenario)
            for symbol in SYMBOLS
            for scenario in SCENARIOS
        )
        actual = tuple((item.symbol, item.name) for item in self.matrix.runs)
        self.assertEqual(actual, expected)

    def test_matrix_replay_is_byte_identical(self):
        replay = run_adversarial_dashboard_matrix(self.fixtures)
        self.assertEqual(self.matrix, replay)
        self.assertEqual(self.matrix.index_json, replay.index_json)

    def test_matrix_index_is_canonical(self):
        record = json.loads(self.matrix.index_json)
        self.assertEqual(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            self.matrix.index_json,
        )
        self.assertEqual(record["artifact_kind"], MATRIX_KIND)

    def test_matrix_sha_is_stable_across_replay(self):
        replay = run_adversarial_dashboard_matrix(self.fixtures)
        self.assertEqual(
            dashboard_matrix_sha256(self.matrix),
            dashboard_matrix_sha256(replay),
        )

    def test_matrix_index_binds_two_accepted_source_identities(self):
        index = json.loads(self.matrix.index_json)
        identities = index["accepted_source_identities"]
        self.assertEqual(tuple(identities), SYMBOLS)
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertEqual(
                    identities[symbol]["export_sha256"],
                    self.fixtures[symbol].export_sha256,
                )
                self.assertEqual(identities[symbol]["symbol"], symbol)

    def test_every_scenario_artifact_is_canonical(self):
        for item in self.matrix.runs:
            with self.subTest(symbol=item.symbol, scenario=item.name):
                record = json.loads(item.artifact_json)
                self.assertEqual(record["artifact_kind"], ARTIFACT_KIND)
                self.assertEqual(scenario_artifact_json(record), item.artifact_json)

    def test_every_scenario_expected_equals_observed(self):
        for record in self.records():
            self.assertEqual(record["expected"], record["observed"])
            self.assertTrue(record["passed"])
            self.assertTrue(record["replay_equal"])

    def test_every_scenario_preserves_safety_boundary(self):
        for record in self.records():
            with self.subTest(symbol=record["symbol"], scenario=record["scenario"]):
                self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
                self.assertTrue(record["paper_only"])
                self.assertTrue(record["read_only_source"])
                self.assertTrue(record["local_dashboard_only"])
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
                self.assertFalse(record["remote_resources"])

    def test_every_scenario_preserves_accepted_source_identity(self):
        by_symbol = {}
        for record in self.records():
            symbol = record["symbol"]
            identity = record["accepted_source_identity"]
            by_symbol.setdefault(symbol, identity)
            self.assertEqual(identity, by_symbol[symbol])
            self.assertEqual(identity["export_sha256"], self.fixtures[symbol].export_sha256)
            self.assertTrue(record["observed"]["accepted_source_unchanged"])

    def test_export_tampering_fails_closed_for_both_symbols(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "P7_EXPORT_TAMPERING")
            self.assertEqual(record["observed"]["source_code"], "SOURCE_REJECTED")
            self.assertTrue(record["observed"]["accepted_source_unchanged"])

    def test_fabricated_quality_pass_fails_closed_for_both_symbols(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "FABRICATED_QUALITY_PASS")
            self.assertTrue(record["observed"]["fabricated_pass_blocked"])
            self.assertEqual(record["observed"]["source_code"], "SOURCE_REJECTED")

    def test_evidence_upgrade_fails_closed_for_both_symbols(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "EVIDENCE_LABEL_UPGRADE")
            self.assertTrue(record["observed"]["evidence_upgrade_blocked"])
            self.assertEqual(record["observed"]["source_code"], "SOURCE_REJECTED")

    def test_cross_symbol_row_injection_is_rejected_for_both_symbols(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "CROSS_SYMBOL_ROW_INJECTION")
            self.assertTrue(record["observed"]["cross_symbol_row_rejected"])
            self.assertTrue(record["observed"]["table_identity_preserved"])

    def test_duplicate_trade_identity_is_rejected_for_both_symbols(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "DUPLICATE_TRADE_IDENTITY")
            self.assertTrue(record["observed"]["duplicate_trade_rejected"])

    def test_oversized_input_output_are_both_rejected(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "OVERSIZED_INPUT_OUTPUT")
            self.assertEqual(record["observed"]["input_code"], "SOURCE_REJECTED")
            self.assertTrue(record["observed"]["oversized_input_rejected"])
            self.assertTrue(record["observed"]["oversized_output_rejected"])

    def test_html_script_injection_is_escaped_not_executable(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "HTML_SCRIPT_INJECTION")
            self.assertTrue(record["observed"]["rendered"])
            self.assertTrue(record["observed"]["script_tag_absent"])
            self.assertTrue(record["observed"]["image_tag_absent"])
            self.assertTrue(record["observed"]["escaped_payload_present"])

    def test_path_private_material_smuggling_is_blocked_and_redacted(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "PATH_PRIVATE_MATERIAL_SMUGGLING")
            self.assertEqual(record["observed"]["source_code"], "SOURCE_REJECTED")
            self.assertTrue(record["observed"]["private_material_blocked"])
            self.assertTrue(record["observed"]["cli_error_redacted"])

    def test_dashboard_artifact_mutation_is_rejected(self):
        for symbol in SYMBOLS:
            record = self.by(symbol, "DASHBOARD_ARTIFACT_MUTATION")
            self.assertTrue(record["observed"]["artifact_mutation_rejected"])

    def test_evidence_artifacts_contain_no_forbidden_private_or_executable_material(self):
        forbidden = (
            '"api_key"',
            '"api_secret"',
            '"password"',
            '"credential"',
            '"private_key"',
            '"database_path"',
            "traceback",
            "<script",
            "<img",
            " src=",
            " href=",
        )
        for item in self.matrix.runs:
            lowered = item.artifact_json.lower()
            for token in forbidden:
                with self.subTest(symbol=item.symbol, scenario=item.name, token=token):
                    self.assertNotIn(token, lowered)

    def test_matrix_index_contains_no_private_or_executable_material(self):
        lowered = self.matrix.index_json.lower()
        for token in (
            "api_key",
            "api_secret",
            "database_path",
            "traceback",
            "<script",
            "<img",
            " src=",
            " href=",
        ):
            self.assertNotIn(token, lowered)

    def test_writer_publishes_exact_19_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "evidence"
            write_adversarial_dashboard_matrix(self.matrix, target)
            files = tuple(sorted(target.iterdir(), key=lambda item: item.name))
            self.assertEqual(len(files), 19)
            self.assertTrue(all(item.is_file() and not item.is_symlink() for item in files))

    def test_writer_publishes_exact_index_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            write_adversarial_dashboard_matrix(self.matrix, target)
            self.assertEqual(
                (target / "p8-009-index.json").read_text(encoding="utf-8"),
                self.matrix.index_json,
            )

    def test_writer_publishes_exact_scenario_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            write_adversarial_dashboard_matrix(self.matrix, target)
            for item in self.matrix.runs:
                filename = f"{item.symbol.lower()}-{item.name.lower().replace('_', '-')}.json"
                self.assertEqual(
                    (target / filename).read_text(encoding="utf-8"),
                    item.artifact_json,
                )

    def test_writer_refuses_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            target.mkdir()
            with self.assertRaises(DashboardScenarioError):
                write_adversarial_dashboard_matrix(self.matrix, target)

    def test_writer_requires_existing_regular_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing" / "evidence"
            with self.assertRaises(DashboardScenarioError):
                write_adversarial_dashboard_matrix(self.matrix, target)

    def test_invalid_fixture_set_is_rejected(self):
        with self.assertRaises(DashboardScenarioError):
            run_adversarial_dashboard_matrix({"BTCUSDT": self.fixtures["BTCUSDT"]})

    def test_invalid_fixture_symbol_is_rejected(self):
        valid = self.fixtures["BTCUSDT"]
        with self.assertRaises(DashboardScenarioError):
            DashboardAcceptedFixture(
                "BAD",
                valid.canonical_export_json,
                valid.export_sha256,
            )

    def test_invalid_fixture_export_sha_is_rejected(self):
        valid = self.fixtures["BTCUSDT"]
        with self.assertRaises(DashboardScenarioError):
            DashboardAcceptedFixture(
                "BTCUSDT",
                valid.canonical_export_json,
                "a" * 64,
            )

    def test_tampered_scenario_artifact_digest_is_rejected(self):
        record = json.loads(self.matrix.runs[0].artifact_json)
        record["result_sha256"] = "a" * 64
        with self.assertRaises(DashboardScenarioError):
            scenario_artifact_json(record)

    def test_tampered_scenario_expected_observed_mismatch_is_rejected(self):
        record = json.loads(self.matrix.runs[0].artifact_json)
        record["observed"] = dict(record["observed"])
        first_key = next(iter(record["observed"]))
        record["observed"][first_key] = "TAMPERED"
        material = dict(record)
        material.pop("result_sha256")
        import hashlib
        import json as _json_module
        encoded = _json_module.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        record["result_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self.assertRaises(DashboardScenarioError):
            scenario_artifact_json(record)

    def test_tampered_matrix_index_is_rejected(self):
        index = json.loads(self.matrix.index_json)
        index["strategy_evidence"] = "PROVEN"
        encoded = json.dumps(
            index,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        with self.assertRaises(DashboardScenarioError):
            DashboardScenarioMatrixResult(self.matrix.runs, encoded)

    def test_scenario_result_rejects_wrong_artifact_digest(self):
        item = self.matrix.runs[0]
        with self.assertRaises(DashboardScenarioError):
            DashboardScenarioResult(
                item.symbol,
                item.name,
                item.artifact_json,
                "a" * 64,
            )

    def test_scenario_module_has_no_analytics_runtime_database_or_network_execution_import(self):
        import inspect
        import yatl.dashboard.scenarios as scenarios

        source = inspect.getsource(scenarios)
        for forbidden in (
            "from yatl.analytics",
            "import yatl.analytics",
            "sqlite3",
            "database_path",
            "local_paper",
            "analyst_journal",
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
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
