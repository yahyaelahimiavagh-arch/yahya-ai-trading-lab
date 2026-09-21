import json
import tempfile
import unittest
from pathlib import Path

from yatl.notifications.scenarios import (
    SCENARIOS,
    SYMBOLS,
    NotificationAcceptedFixture,
    NotificationScenarioError,
    notification_matrix_sha256,
    run_adversarial_notification_matrix,
    scenario_artifact_json,
    write_adversarial_notification_matrix,
    _fixture,
)


class NotificationScenarioTests(unittest.TestCase):
    def test_fixed_matrix_shape_and_exact_scenarios(self):
        self.assertEqual(
            SCENARIOS,
            (
                "SOURCE_TAMPERING",
                "EVIDENCE_UPGRADE",
                "COMMAND_AUTHORITY_INJECTION",
                "SECRET_LEAKAGE",
                "URL_MARKUP_INJECTION",
                "DUPLICATE_DELIVERY",
                "CROSS_SYMBOL_MATERIAL",
                "TRANSPORT_RESPONSE_CORRUPTION",
            ),
        )
        self.assertEqual(SYMBOLS, ("BTCUSDT", "ETHUSDT"))
        result = run_adversarial_notification_matrix()
        self.assertEqual(len(result.runs), 16)
        self.assertEqual(
            [(item.symbol, item.name) for item in result.runs],
            [
                (symbol, scenario)
                for symbol in SYMBOLS
                for scenario in SCENARIOS
            ],
        )

    def test_matrix_is_deterministic_and_canonical(self):
        first = run_adversarial_notification_matrix()
        second = run_adversarial_notification_matrix()
        self.assertEqual(first, second)
        self.assertEqual(first.index_json, second.index_json)
        self.assertEqual(
            notification_matrix_sha256(first),
            notification_matrix_sha256(second),
        )
        index = json.loads(first.index_json)
        self.assertEqual(index["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(index["paper_only"])
        self.assertTrue(index["outbound_only"])
        self.assertTrue(index["source_read_only"])
        self.assertEqual(index["live_master_lock"], "OFF")
        self.assertFalse(index["trade_permission"])
        self.assertFalse(index["order_endpoints"])
        self.assertFalse(index["ai_direct_execution"])
        self.assertFalse(index["inbound_commands"])
        self.assertFalse(index["real_network_called"])

    def test_every_scenario_exactly_passes_and_preserves_safety(self):
        result = run_adversarial_notification_matrix()
        for item in result.runs:
            with self.subTest(symbol=item.symbol, scenario=item.name):
                record = json.loads(item.artifact_json)
                self.assertTrue(record["passed"])
                self.assertTrue(record["replay_equal"])
                self.assertEqual(record["expected"], record["observed"])
                self.assertEqual(
                    record["strategy_evidence"],
                    "INSUFFICIENT_EVIDENCE",
                )
                self.assertTrue(record["paper_only"])
                self.assertTrue(record["outbound_only"])
                self.assertTrue(record["source_read_only"])
                self.assertEqual(record["live_master_lock"], "OFF")
                self.assertFalse(record["trade_permission"])
                self.assertFalse(record["order_endpoints"])
                self.assertFalse(record["quantity_authority"])
                self.assertFalse(record["risk_authorization_mutation"])
                self.assertFalse(record["ai_direct_execution"])
                self.assertFalse(record["inbound_commands"])
                self.assertFalse(record["webhook_receiver"])
                self.assertFalse(record["polling_receiver"])
                self.assertFalse(record["real_network_called"])
                self.assertEqual(
                    scenario_artifact_json(record),
                    item.artifact_json,
                )

    def test_duplicate_scenario_sends_once_and_reuses_state(self):
        result = run_adversarial_notification_matrix()
        duplicate = [
            json.loads(item.artifact_json)
            for item in result.runs
            if item.name == "DUPLICATE_DELIVERY"
        ]
        self.assertEqual(len(duplicate), 2)
        for record in duplicate:
            observed = record["observed"]
            self.assertEqual(observed["first_code"], "DELIVERED")
            self.assertEqual(observed["second_code"], "DUPLICATE_SUPPRESSED")
            self.assertEqual(observed["sender_calls"], 1)
            self.assertTrue(observed["same_delivery_id"])
            self.assertTrue(observed["state_replay_equal"])
            self.assertTrue(observed["accepted_source_unchanged"])

    def test_rejection_scenarios_never_create_delivery_state(self):
        result = run_adversarial_notification_matrix()
        names = {
            "SOURCE_TAMPERING",
            "EVIDENCE_UPGRADE",
            "COMMAND_AUTHORITY_INJECTION",
            "SECRET_LEAKAGE",
            "URL_MARKUP_INJECTION",
            "CROSS_SYMBOL_MATERIAL",
            "TRANSPORT_RESPONSE_CORRUPTION",
        }
        for item in result.runs:
            if item.name not in names:
                continue
            with self.subTest(symbol=item.symbol, scenario=item.name):
                observed = json.loads(item.artifact_json)["observed"]
                self.assertTrue(observed["state_absent"])

    def test_fixture_identity_is_bound_to_canonical_batch_sha(self):
        fixture = _fixture("BTCUSDT")
        with self.assertRaises(NotificationScenarioError):
            NotificationAcceptedFixture(
                fixture.symbol,
                fixture.canonical_batch_json,
                "0" * 64,
            )
        with self.assertRaises(NotificationScenarioError):
            NotificationAcceptedFixture(
                "ETHUSDT",
                fixture.canonical_batch_json,
                fixture.batch_sha256,
            )

    def test_artifact_tampering_is_rejected(self):
        result = run_adversarial_notification_matrix()
        record = json.loads(result.runs[0].artifact_json)
        record["trade_permission"] = True
        with self.assertRaises(NotificationScenarioError):
            scenario_artifact_json(record)

        record = json.loads(result.runs[0].artifact_json)
        record["observed"] = dict(record["observed"])
        record["observed"]["state_absent"] = False
        with self.assertRaises(NotificationScenarioError):
            scenario_artifact_json(record)

    def test_evidence_writer_is_atomic_bounded_and_no_overwrite(self):
        result = run_adversarial_notification_matrix()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "p9-005-evidence"
            written = write_adversarial_notification_matrix(result, target)
            self.assertEqual(written, target)
            files = sorted(item.name for item in target.iterdir())
            self.assertEqual(len(files), 17)
            self.assertIn("p9-005-index.json", files)
            self.assertEqual(
                (target / "p9-005-index.json").read_text(encoding="utf-8"),
                result.index_json,
            )
            with self.assertRaises(NotificationScenarioError):
                write_adversarial_notification_matrix(result, target)

    def test_artifacts_do_not_contain_remote_or_secret_material(self):
        result = run_adversarial_notification_matrix()
        combined = result.index_json + "".join(
            item.artifact_json for item in result.runs
        )
        lowered = combined.lower()
        self.assertIn('"risk_authorization_mutation":false', lowered)
        self.assertNotIn('"risk_authorization":', lowered)
        for forbidden in (
            "http://",
            "https://",
            '"bot_token"',
            '"chat_id"',
            '"api_key"',
            '"api_secret"',
            "authorization:",
            "bearer ",
            "traceback",
            "approved_quantity",
            '"risk_authorization":',
            '"risk_authorization_payload":',
            '"risk_authorization_record":',
            "order_request",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_scenario_source_has_no_real_network_or_execution_import(self):
        import inspect
        import yatl.notifications.scenarios as scenarios

        source = inspect.getsource(scenarios)
        for forbidden in (
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "ssl.",
            "os.environ",
            "os.getenv",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
