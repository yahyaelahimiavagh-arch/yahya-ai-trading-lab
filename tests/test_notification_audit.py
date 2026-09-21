import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.notifications.audit import (
    EXPECTED_DELIVERY_POLICY_SHA256,
    EXPECTED_DELIVERY_RESULTS,
    EXPECTED_IDENTITIES,
    EXPECTED_IDENTITY_SET_SHA256,
    EXPECTED_INDEX_SHA256,
    EXPECTED_NOTIFICATION_POLICY_SHA256,
    EXPECTED_TRANSPORT_POLICY_SHA256,
    P9AuditError,
    P9AuditResult,
    _accepted_fixture,
    _audit_delivery_replay,
    _audit_evidence_records,
    _audit_delivery_replay,
    _audit_identity_set,
    _audit_policy_hashes,
    _audit_source_safety,
    _read_evidence,
    audit_p9,
)
from yatl.notifications.scenarios import (
    SCENARIOS,
    SYMBOLS,
    run_adversarial_notification_matrix,
    write_adversarial_notification_matrix,
)


class P9IndependentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.fixtures, cls.identities, cls.identity_set_sha = _audit_identity_set()
        cls.matrix = run_adversarial_notification_matrix(cls.fixtures)
        cls.evidence = cls.root / "p9-005-evidence"
        write_adversarial_notification_matrix(cls.matrix, cls.evidence)
        cls.before = {
            path.name: path.read_bytes()
            for path in sorted(cls.evidence.iterdir(), key=lambda item: item.name)
        }
        cls.result = audit_p9(cls.evidence)
        cls.after = {
            path.name: path.read_bytes()
            for path in sorted(cls.evidence.iterdir(), key=lambda item: item.name)
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_audit_result_exact_counts(self):
        self.assertEqual(
            (
                self.result.symbols,
                self.result.scenarios,
                self.result.runs,
                self.result.files,
            ),
            (2, 8, 16, 17),
        )

    def test_all_frozen_policy_hashes_match(self):
        notification, transport, delivery = _audit_policy_hashes()
        self.assertEqual(notification, EXPECTED_NOTIFICATION_POLICY_SHA256)
        self.assertEqual(transport, EXPECTED_TRANSPORT_POLICY_SHA256)
        self.assertEqual(delivery, EXPECTED_DELIVERY_POLICY_SHA256)
        self.assertEqual(
            self.result.notification_policy_sha256,
            EXPECTED_NOTIFICATION_POLICY_SHA256,
        )
        self.assertEqual(
            self.result.transport_policy_sha256,
            EXPECTED_TRANSPORT_POLICY_SHA256,
        )
        self.assertEqual(
            self.result.delivery_policy_sha256,
            EXPECTED_DELIVERY_POLICY_SHA256,
        )

    def test_identity_set_is_frozen(self):
        self.assertEqual(self.identities, EXPECTED_IDENTITIES)
        self.assertEqual(self.identity_set_sha, EXPECTED_IDENTITY_SET_SHA256)
        self.assertEqual(
            self.result.identity_set_sha256,
            EXPECTED_IDENTITY_SET_SHA256,
        )

    def test_each_symbol_identity_is_exact_and_valid(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                fixture, identity = _accepted_fixture(symbol)
                self.assertEqual(identity, EXPECTED_IDENTITIES[symbol])
                self.assertEqual(
                    fixture.batch_sha256,
                    EXPECTED_IDENTITIES[symbol]["batch_sha256"],
                )
                for value in identity.values():
                    self.assertEqual(len(value), 64)
                    int(value, 16)

    def test_fixture_replay_is_deterministic(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                first = _accepted_fixture(symbol)
                second = _accepted_fixture(symbol)
                self.assertEqual(first, second)

    def test_unsupported_fixture_symbol_is_rejected(self):
        with self.assertRaises(P9AuditError):
            _accepted_fixture("SOLUSDT")

    def test_delivery_boundary_is_recomputed_with_restart_dedupe(self):
        results = _audit_delivery_replay(self.identities)
        self.assertEqual(set(results), set(SYMBOLS))
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertEqual(
                    results[symbol]["delivery_id"],
                    EXPECTED_IDENTITIES[symbol]["delivery_id"],
                )
                self.assertEqual(
                    results[symbol]["receipt_sha256"],
                    EXPECTED_DELIVERY_RESULTS[symbol]["receipt_sha256"],
                )
                self.assertEqual(
                    results[symbol]["state_sha256"],
                    EXPECTED_DELIVERY_RESULTS[symbol]["state_sha256"],
                )
                self.assertEqual(results[symbol]["sender_calls"], 1)
                self.assertEqual(results[symbol]["first_status"], "DELIVERED")
                self.assertEqual(
                    results[symbol]["restart_status"],
                    "DUPLICATE_SUPPRESSED",
                )

    def test_delivery_boundary_rejects_unknown_identity_set(self):
        changed = json.loads(json.dumps(self.identities))
        changed["BTCUSDT"]["delivery_id"] = "a" * 64
        with self.assertRaises(P9AuditError):
            _audit_delivery_replay(changed)

    def test_delivery_replay_is_independent_frozen_and_duplicate_safe(self):
        replay, replay_set_sha = _audit_delivery_replay(self.fixtures)
        self.assertEqual(replay, EXPECTED_DELIVERY_REPLAY)
        self.assertEqual(
            replay_set_sha,
            EXPECTED_DELIVERY_REPLAY_SET_SHA256,
        )
        self.assertEqual(
            self.result.delivery_replay_set_sha256,
            EXPECTED_DELIVERY_REPLAY_SET_SHA256,
        )
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertEqual(
                    replay[symbol]["telegram_message_id"],
                    9101 if symbol == "BTCUSDT" else 9102,
                )
                self.assertEqual(len(replay[symbol]["receipt_sha256"]), 64)
                self.assertEqual(len(replay[symbol]["state_sha256"]), 64)

    def test_delivery_replay_rejects_incomplete_fixture_set(self):
        with self.assertRaises(P9AuditError):
            _audit_delivery_replay({"BTCUSDT": self.fixtures["BTCUSDT"]})

    def test_adversarial_index_sha_is_frozen(self):
        self.assertEqual(self.result.index_sha256, EXPECTED_INDEX_SHA256)
        self.assertEqual(
            self.result.index_sha256,
            self.matrix.index_json and EXPECTED_INDEX_SHA256,
        )

    def test_audit_all_acceptance_booleans_true(self):
        self.assertTrue(self.result.exact_outcomes)
        self.assertTrue(self.result.replay_equal)
        self.assertTrue(self.result.identities_recomputed)
        self.assertTrue(self.result.formatter_recomputed)
        self.assertTrue(self.result.delivery_recomputed)
        self.assertTrue(self.result.evidence_verified)
        self.assertTrue(self.result.no_write)
        self.assertTrue(self.result.source_safe)

    def test_audit_does_not_mutate_evidence(self):
        self.assertEqual(self.before, self.after)

    def test_source_safety_recomputes_true(self):
        self.assertTrue(_audit_source_safety())

    def test_evidence_reader_returns_exact_17_files(self):
        evidence, records = _read_evidence(self.evidence)
        self.assertEqual(len(evidence), 17)
        self.assertEqual(len(records), 17)
        self.assertIn("p9-005-index.json", records)

    def test_evidence_records_independently_validate(self):
        _, records = _read_evidence(self.evidence)
        self.assertIsNone(_audit_evidence_records(records))

    def test_index_has_exact_symbol_scenario_order(self):
        _, records = _read_evidence(self.evidence)
        index = records["p9-005-index.json"]
        self.assertEqual(index["symbols"], list(SYMBOLS))
        self.assertEqual(index["scenarios"], list(SCENARIOS))
        self.assertEqual(
            [(item["symbol"], item["scenario"]) for item in index["runs"]],
            [
                (symbol, scenario)
                for symbol in SYMBOLS
                for scenario in SCENARIOS
            ],
        )

    def test_index_batch_identities_match_independent_audit(self):
        _, records = _read_evidence(self.evidence)
        self.assertEqual(
            records["p9-005-index.json"]["accepted_batch_sha256"],
            {
                symbol: EXPECTED_IDENTITIES[symbol]["batch_sha256"]
                for symbol in SYMBOLS
            },
        )

    def test_missing_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            next(target.glob("btcusdt-*.json")).unlink()
            with self.assertRaises(P9AuditError):
                _read_evidence(target)

    def test_extra_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            (target / "extra.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P9AuditError):
                _read_evidence(target)

    def test_noncanonical_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p9-005-index.json"
            index.write_bytes(index.read_bytes() + b" ")
            with self.assertRaises(P9AuditError):
                _read_evidence(target)

    def test_evidence_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "evidence"
            shutil.copytree(self.evidence, target)
            original = next(target.glob("btcusdt-*.json"))
            backup = root / "backup.json"
            backup.write_bytes(original.read_bytes())
            original.unlink()
            original.symlink_to(backup)
            with self.assertRaises(P9AuditError):
                _read_evidence(target)

    def test_tampered_index_evidence_upgrade_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        index = json.loads(json.dumps(records["p9-005-index.json"]))
        index["strategy_evidence"] = "PROVEN"
        records["p9-005-index.json"] = index
        with self.assertRaises(P9AuditError):
            _audit_evidence_records(records)

    def test_tampered_index_trade_permission_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        index = json.loads(json.dumps(records["p9-005-index.json"]))
        index["trade_permission"] = True
        records["p9-005-index.json"] = index
        with self.assertRaises(P9AuditError):
            _audit_evidence_records(records)

    def test_tampered_index_batch_identity_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        index = json.loads(json.dumps(records["p9-005-index.json"]))
        index["accepted_batch_sha256"]["BTCUSDT"] = "a" * 64
        records["p9-005-index.json"] = index
        with self.assertRaises(P9AuditError):
            _audit_evidence_records(records)

    def test_tampered_scenario_digest_is_rejected(self):
        _, records = _read_evidence(self.evidence)
        records = dict(records)
        name = next(key for key in records if key != "p9-005-index.json")
        scenario = dict(records[name])
        scenario["result_sha256"] = "a" * 64
        records[name] = scenario
        with self.assertRaises(P9AuditError):
            _audit_evidence_records(records)

    def test_full_audit_rejects_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p9-005-index.json"
            record = json.loads(index.read_text(encoding="utf-8"))
            record["trade_permission"] = True
            index.write_text(
                json.dumps(
                    record,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P9AuditError):
                audit_p9(target)

    def test_full_audit_rejects_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            next(target.glob("ethusdt-*.json")).unlink()
            with self.assertRaises(P9AuditError):
                audit_p9(target)

    def test_audit_result_rejects_wrong_notification_policy(self):
        with self.assertRaises(P9AuditError):
            replace(
                self.result,
                notification_policy_sha256="a" * 64,
            )

    def test_audit_result_rejects_wrong_transport_policy(self):
        with self.assertRaises(P9AuditError):
            replace(
                self.result,
                transport_policy_sha256="a" * 64,
            )

    def test_audit_result_rejects_wrong_delivery_policy(self):
        with self.assertRaises(P9AuditError):
            replace(
                self.result,
                delivery_policy_sha256="a" * 64,
            )

    def test_audit_result_rejects_wrong_identity_set(self):
        with self.assertRaises(P9AuditError):
            replace(self.result, identity_set_sha256="a" * 64)

    def test_audit_result_rejects_wrong_delivery_replay_set(self):
        with self.assertRaises(P9AuditError):
            replace(
                self.result,
                delivery_replay_set_sha256="a" * 64,
            )

    def test_audit_result_rejects_wrong_index(self):
        with self.assertRaises(P9AuditError):
            replace(self.result, index_sha256="a" * 64)

    def test_audit_result_rejects_false_acceptance_flag(self):
        with self.assertRaises(P9AuditError):
            replace(self.result, source_safe=False)

    def test_audit_source_has_no_direct_network_execution_or_provider_import(self):
        import inspect
        import yatl.notifications.audit as audit_module

        source = inspect.getsource(audit_module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "os.environ",
            "os.getenv",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
