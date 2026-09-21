import contextlib
import hashlib
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yatl.validation import cli
from yatl.validation.cli import (
    EXIT_EXISTS,
    EXIT_INVALID,
    EXIT_NOT_READY,
    EXIT_OK,
    MAX_CLI_OUTPUT_BYTES,
    ValidationCliCode,
    ValidationCliError,
    ValidationEvidenceBundle,
    _export_from_bundle,
    _export_payload,
    _pipeline,
    _status_from_bundle,
    _summary_from_bundle,
    _warmup_ready,
    snapshot_json,
    validation_export,
    validation_status,
    validation_summary,
)
from yatl.validation.paper_runner_runtime import build_mock_forward_runner_fixture


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def family_sha(path):
    values = {"database": file_sha(path)}
    wal = Path(str(path) + "-wal")
    if wal.exists():
        values["wal"] = file_sha(wal)
    return values


class ValidationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        store, cls.snapshot, cls.client = build_mock_forward_runner_fixture(cls.root)
        cls.database = cls.root / "p10-forward.sqlite3"
        store.close()
        cls.snapshot_path = cls.root / "snapshot.json"
        cls.snapshot_path.write_text(snapshot_json(cls.snapshot), encoding="utf-8")
        cls.upstream_before = family_sha(cls.database)
        cls.snapshot_before = file_sha(cls.snapshot_path)
        cls.bundle = _pipeline(cls.database, cls.snapshot_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.work_root = Path(self.work.name)

    def tearDown(self):
        self.work.cleanup()

    def test_pipeline_reconstructs_complete_frozen_chain(self):
        bundle = self.bundle
        self.assertTrue(bundle.ready)
        self.assertEqual(bundle.snapshot, self.snapshot)
        self.assertEqual(bundle.run.ingestion_snapshot_sha256, self.snapshot.snapshot_sha256)
        self.assertEqual(bundle.economics.as_record()["input_run_sha256"], bundle.run.run_sha256)
        self.assertEqual(
            bundle.gate.as_record()["input_economics_sha256"],
            bundle.economics.report_sha256,
        )
        self.assertEqual(bundle.gate.as_record()["disposition"], "INSUFFICIENT_DATA")

    def test_pipeline_never_mutates_upstream_database_or_snapshot(self):
        self.assertEqual(family_sha(self.database), self.upstream_before)
        self.assertEqual(file_sha(self.snapshot_path), self.snapshot_before)

    def test_snapshot_file_representation_is_canonical(self):
        raw = self.snapshot_path.read_text(encoding="utf-8")
        self.assertEqual(raw, snapshot_json(self.snapshot))
        self.assertTrue(raw.endswith("\n"))
        parsed = json.loads(raw)
        self.assertEqual(
            raw,
            json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n",
        )

    def test_status_is_deterministic_and_safety_locked(self):
        first = _status_from_bundle(self.bundle)
        second = _status_from_bundle(self.bundle)
        self.assertEqual(first, second)
        self.assertEqual(first["code"], ValidationCliCode.STATUS_READY.value)
        self.assertEqual(first["disposition"], "INSUFFICIENT_DATA")
        self.assertTrue(first["paper_only"])
        self.assertEqual(first["live_master_lock"], "OFF")
        self.assertEqual(first["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(first["p11_unlocked"])

    def test_summary_is_bounded_and_has_registered_criteria(self):
        record = _summary_from_bundle(self.bundle)
        self.assertEqual(record["code"], ValidationCliCode.SUMMARY_READY.value)
        self.assertEqual(record["completed_trades"], 2)
        self.assertEqual(len(record["symbols"]), 2)
        self.assertEqual(
            set(record["criteria"]),
            {
                "NET_PNL_AFTER_COSTS",
                "MAX_DRAWDOWN",
                "SAMPLE_SIZE",
                "CONSISTENCY",
                "REGIME_STABILITY",
                "FAILURE_RECOVERY",
                "RISK_CONTROLS",
            },
        )
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
        self.assertLessEqual(len(encoded.encode()), MAX_CLI_OUTPUT_BYTES)

    def test_export_contains_one_canonical_audit_package(self):
        record, encoded = _export_payload(self.bundle)
        self.assertEqual(
            set(record),
            {
                "schema_version",
                "candidate",
                "gate_registry",
                "window",
                "provenance",
                "forward_paper",
                "economics",
                "gate",
                "audit_sha256",
            },
        )
        material = {key: value for key, value in record.items() if key != "audit_sha256"}
        expected = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(record["audit_sha256"], expected)
        self.assertEqual(encoded, json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertEqual(record["gate"]["disposition"], "INSUFFICIENT_DATA")
        self.assertFalse(record["gate"]["safety"]["p11_unlocked"])

    def test_export_is_path_free_and_secret_free(self):
        _, encoded = _export_payload(self.bundle)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("database_path", encoded)
        for marker in ("api_key", "api_secret", "password", "private_key", "access_token"):
            self.assertNotIn(marker, encoded.casefold())

    def test_atomic_export_refuses_overwrite(self):
        target = self.work_root / "audit.json"
        first = _export_from_bundle(self.bundle, target)
        original = target.read_bytes()
        self.assertEqual(first["code"], ValidationCliCode.EXPORTED.value)
        with self.assertRaises(ValidationCliError) as caught:
            _export_from_bundle(self.bundle, target)
        self.assertIs(caught.exception.code, ValidationCliCode.OUTPUT_EXISTS)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(tuple(self.work_root.glob(".yatl-p10-export-*.tmp")), ())

    def test_two_export_targets_are_byte_identical(self):
        one = self.work_root / "one.json"
        two = self.work_root / "two.json"
        first = _export_from_bundle(self.bundle, one)
        second = _export_from_bundle(self.bundle, two)
        self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertEqual(first["audit_sha256"], second["audit_sha256"])

    def test_public_wrappers_use_same_reconciled_bundle(self):
        with mock.patch.object(cli, "_pipeline", return_value=self.bundle):
            self.assertEqual(
                validation_status("hidden-db", "hidden-snapshot"),
                _status_from_bundle(self.bundle),
            )
            self.assertEqual(
                validation_summary("hidden-db", "hidden-snapshot"),
                _summary_from_bundle(self.bundle),
            )
            output = self.work_root / "wrapper.json"
            result = validation_export("hidden-db", "hidden-snapshot", output)
            self.assertEqual(result["code"], ValidationCliCode.EXPORTED.value)

    def test_not_ready_is_explicit_and_never_upgrades_evidence(self):
        bundle = ValidationEvidenceBundle(
            self.snapshot,
            self.bundle.database_snapshot_sha256,
            False,
        )
        with mock.patch.object(cli, "_pipeline", return_value=bundle):
            record = validation_status("db", "snapshot")
            self.assertEqual(record["code"], ValidationCliCode.NOT_READY.value)
            self.assertEqual(record["reason"], "FORWARD_WARMUP_NOT_COMPLETE")
            self.assertFalse(record["p11_unlocked"])
            self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")

    def test_warmup_boundary_is_strict(self):
        first_decision = self.snapshot.datasets[0].requested_start_time_ms + 51 * 14_400_000
        before = SimpleNamespace(datasets=(
            SimpleNamespace(requested_end_time_ms=first_decision),
        ))
        after = SimpleNamespace(datasets=(
            SimpleNamespace(requested_end_time_ms=first_decision + 900_000),
        ))
        self.assertFalse(_warmup_ready(before))
        self.assertTrue(_warmup_ready(after))

    def test_noncanonical_snapshot_is_rejected(self):
        target = self.work_root / "snapshot.json"
        target.write_text(
            json.dumps(self.snapshot.as_record(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with self.assertRaises(ValidationCliError) as caught:
            _pipeline(self.database, target)
        self.assertIs(caught.exception.code, ValidationCliCode.SOURCE_REJECTED)

    def test_duplicate_snapshot_keys_are_rejected(self):
        target = self.work_root / "snapshot.json"
        target.write_text('{"ingestion_id":"x","ingestion_id":"x"}\n', encoding="utf-8")
        with self.assertRaises(ValidationCliError) as caught:
            _pipeline(self.database, target)
        self.assertIs(caught.exception.code, ValidationCliCode.SOURCE_REJECTED)

    def test_secret_like_snapshot_is_rejected(self):
        target = self.work_root / "snapshot.json"
        target.write_text('{"api_key":"never"}\n', encoding="utf-8")
        with self.assertRaises(ValidationCliError) as caught:
            _pipeline(self.database, target)
        self.assertIs(caught.exception.code, ValidationCliCode.SOURCE_REJECTED)

    def test_snapshot_symlink_is_rejected(self):
        link = self.work_root / "snapshot-link.json"
        link.symlink_to(self.snapshot_path)
        with self.assertRaises(ValidationCliError) as caught:
            _pipeline(self.database, link)
        self.assertIs(caught.exception.code, ValidationCliCode.SOURCE_REJECTED)

    def test_database_symlink_is_rejected(self):
        link = self.work_root / "db-link.sqlite3"
        link.symlink_to(self.database)
        with self.assertRaises(ValidationCliError) as caught:
            _pipeline(link, self.snapshot_path)
        self.assertIs(caught.exception.code, ValidationCliCode.SOURCE_REJECTED)

    def test_export_parent_must_exist_and_be_real_directory(self):
        with self.assertRaises(ValidationCliError) as caught:
            _export_from_bundle(self.bundle, self.work_root / "missing" / "audit.json")
        self.assertIs(caught.exception.code, ValidationCliCode.STORAGE_ERROR)

    def test_export_symlink_target_is_rejected(self):
        target = self.work_root / "target.json"
        target.write_text("old", encoding="utf-8")
        link = self.work_root / "audit.json"
        link.symlink_to(target)
        with self.assertRaises(ValidationCliError) as caught:
            _export_from_bundle(self.bundle, link)
        self.assertIs(caught.exception.code, ValidationCliCode.STORAGE_ERROR)
        self.assertEqual(target.read_text(), "old")

    def call_main(self, argv):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = cli.main(argv)
        self.assertEqual(errors.getvalue(), "")
        return code, json.loads(output.getvalue())

    def test_main_status_summary_and_export_exit_zero(self):
        with mock.patch.object(cli, "_pipeline", return_value=self.bundle):
            code, status = self.call_main(["status", "--database", "db", "--snapshot", "snap"])
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(status["code"], ValidationCliCode.STATUS_READY.value)

            code, summary = self.call_main(["summary", "--database", "db", "--snapshot", "snap"])
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(summary["code"], ValidationCliCode.SUMMARY_READY.value)

            output = self.work_root / "main-export.json"
            code, export = self.call_main([
                "export", "--database", "db", "--snapshot", "snap",
                "--output", str(output),
            ])
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(export["code"], ValidationCliCode.EXPORTED.value)

    def test_main_not_ready_has_stable_exit_code(self):
        bundle = ValidationEvidenceBundle(
            self.snapshot,
            self.bundle.database_snapshot_sha256,
            False,
        )
        with mock.patch.object(cli, "_pipeline", return_value=bundle):
            code, record = self.call_main(["status", "--database", "db", "--snapshot", "snap"])
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertEqual(record["code"], ValidationCliCode.NOT_READY.value)

    def test_main_output_exists_has_stable_exit_code(self):
        target = self.work_root / "audit.json"
        target.write_text("existing", encoding="utf-8")
        with mock.patch.object(cli, "_pipeline", return_value=self.bundle):
            code, record = self.call_main([
                "export", "--database", "db", "--snapshot", "snap",
                "--output", str(target),
            ])
        self.assertEqual(code, EXIT_EXISTS)
        self.assertEqual(record["code"], ValidationCliCode.OUTPUT_EXISTS.value)

    def test_cli_has_no_overwrite_option(self):
        marker = "DO_NOT_ECHO_OVERWRITE_VALUE"
        code, record = self.call_main([
            "export", "--database", "db", "--snapshot", "snap",
            "--output", marker, "--overwrite",
        ])
        self.assertEqual(code, EXIT_INVALID)
        self.assertEqual(record["code"], ValidationCliCode.INVALID_REQUEST.value)
        self.assertNotIn(marker, json.dumps(record))

    def test_rejected_arguments_never_echo_caller_values(self):
        marker = "SUPER_PRIVATE_P10_PATH_AND_SECRET"
        code, record = self.call_main([
            "status", "--database", marker, "--snapshot", marker, "--endpoint", marker,
        ])
        self.assertEqual(code, EXIT_INVALID)
        encoded = json.dumps(record)
        self.assertNotIn(marker, encoded)

    def test_cli_output_never_echoes_source_or_output_paths(self):
        with mock.patch.object(cli, "_pipeline", return_value=self.bundle):
            source = "PRIVATE_DATABASE_PATH"
            snapshot = "PRIVATE_SNAPSHOT_PATH"
            code, record = self.call_main([
                "summary", "--database", source, "--snapshot", snapshot,
            ])
            self.assertEqual(code, EXIT_OK)
            encoded = json.dumps(record)
            self.assertNotIn(source, encoded)
            self.assertNotIn(snapshot, encoded)

    def test_source_has_no_collection_execution_secret_or_network_capability(self):
        source = inspect.getsource(cli)
        for forbidden in (
            "collect_forward_snapshot",
            "BinancePublicRestClient",
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
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "API_KEY",
            "API_SECRET",
            "subprocess",
            "input(",
            "eval(",
            "exec(",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "CREATE TABLE",
            "DROP TABLE",
            "ALTER TABLE",
            "journal_mode",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
