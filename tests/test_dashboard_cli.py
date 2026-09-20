import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard import cli as dashboard_cli
from yatl.dashboard.cli import (
    DashboardCliCode,
    DashboardCliError,
    EXIT_EXISTS,
    EXIT_INTERNAL,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_SOURCE,
    EXIT_STORAGE,
    dashboard_build,
    dashboard_summary,
    dashboard_validate,
)


class DashboardCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_root = self.root / "source-data"
        source_root.mkdir()
        _, _, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        self.record, encoded = _export_payload(gate)
        self.source = self.root / "accepted-p7-export.json"
        self.source.write_text(encoded, encoding="utf-8")
        self.expected = self.record["export_sha256"]

    def tearDown(self):
        self.temp.cleanup()

    def call_main(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = dashboard_cli.main(argv)
        output = stream.getvalue()
        self.assertTrue(output.endswith("\n"))
        return code, json.loads(output)

    def temp_leftovers(self):
        return tuple(self.root.glob(".yatl-p8-dashboard-*.tmp"))

    def test_validate_success_is_stable_and_path_free(self):
        record = dashboard_validate(self.source, self.expected)
        self.assertEqual(record["code"], DashboardCliCode.VALIDATED.value)
        self.assertTrue(record["ok"])
        self.assertEqual(record["source_export_sha256"], self.expected)
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn(str(self.source), encoded)

    def test_validate_preserves_source_bytes(self):
        before = self.source.read_bytes()
        dashboard_validate(self.source, self.expected)
        self.assertEqual(self.source.read_bytes(), before)

    def test_summary_is_deterministic(self):
        first = dashboard_summary(self.source, self.expected)
        second = dashboard_summary(self.source, self.expected)
        self.assertEqual(first, second)
        self.assertEqual(first["code"], DashboardCliCode.SUMMARY_READY.value)

    def test_summary_reports_bounded_projection_counts(self):
        record = dashboard_summary(self.source, self.expected)
        self.assertEqual(record["overview_card_count"], 15)
        self.assertEqual(record["performance_metric_count"], 19)
        self.assertLessEqual(record["rendered_trade_count"], 50)
        self.assertLessEqual(
            record["rendered_trade_count"],
            record["completed_trade_count"],
        )
        self.assertGreaterEqual(record["trade_segment_count"], 1)
        self.assertGreaterEqual(record["analyst_segment_count"], 1)

    def test_summary_preserves_source_bytes(self):
        before = self.source.read_bytes()
        dashboard_summary(self.source, self.expected)
        self.assertEqual(self.source.read_bytes(), before)

    def test_build_creates_exact_static_html(self):
        output = self.root / "dashboard.html"
        record = dashboard_build(self.source, self.expected, output)
        data = output.read_bytes()
        self.assertEqual(record["code"], DashboardCliCode.BUILT.value)
        self.assertEqual(record["bytes"], len(data))
        self.assertEqual(
            record["dashboard_sha256"],
            hashlib.sha256(data).hexdigest(),
        )
        self.assertTrue(data.startswith(b"<!doctype html>\n<html lang=\"en\">"))
        self.assertIn(b"Content-Security-Policy", data)

    def test_build_preserves_source_bytes(self):
        before = self.source.read_bytes()
        dashboard_build(self.source, self.expected, self.root / "dashboard.html")
        self.assertEqual(self.source.read_bytes(), before)

    def test_build_refuses_overwrite_by_default_and_preserves_existing(self):
        output = self.root / "dashboard.html"
        output.write_bytes(b"existing")
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(self.source, self.expected, output)
        self.assertIs(caught.exception.code, DashboardCliCode.OUTPUT_EXISTS)
        self.assertEqual(output.read_bytes(), b"existing")

    def test_build_explicit_overwrite_replaces_existing_atomically(self):
        output = self.root / "dashboard.html"
        output.write_bytes(b"existing")
        record = dashboard_build(
            self.source,
            self.expected,
            output,
            overwrite=True,
        )
        self.assertTrue(record["overwrite_requested"])
        self.assertTrue(record["replaced_existing"])
        self.assertNotEqual(output.read_bytes(), b"existing")
        self.assertEqual(
            hashlib.sha256(output.read_bytes()).hexdigest(),
            record["dashboard_sha256"],
        )

    def test_overwrite_requested_on_absent_target_reports_not_replaced(self):
        output = self.root / "dashboard.html"
        record = dashboard_build(
            self.source,
            self.expected,
            output,
            overwrite=True,
        )
        self.assertTrue(record["overwrite_requested"])
        self.assertFalse(record["replaced_existing"])

    def test_two_distinct_build_targets_are_byte_identical(self):
        first = self.root / "one.html"
        second = self.root / "two.html"
        one = dashboard_build(self.source, self.expected, first)
        two = dashboard_build(self.source, self.expected, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(one["dashboard_sha256"], two["dashboard_sha256"])
        self.assertEqual(one["view_model_sha256"], two["view_model_sha256"])

    def test_build_record_never_contains_output_path(self):
        output = self.root / "private-output-name.html"
        record = dashboard_build(self.source, self.expected, output)
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn(str(output), encoded)
        self.assertNotIn(str(self.source), encoded)

    def test_source_and_output_same_path_is_rejected(self):
        before = self.source.read_bytes()
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                self.source,
                overwrite=True,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.INVALID_REQUEST)
        self.assertEqual(self.source.read_bytes(), before)

    def test_source_and_output_equivalent_relative_path_is_rejected(self):
        before = self.source.read_bytes()
        alternate = self.source.parent / "." / self.source.name
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                alternate,
                overwrite=True,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.INVALID_REQUEST)
        self.assertEqual(self.source.read_bytes(), before)

    def test_existing_hardlink_to_source_is_rejected(self):
        output = self.root / "hardlink.html"
        os.link(self.source, output)
        before = self.source.read_bytes()
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                output,
                overwrite=True,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.INVALID_REQUEST)
        self.assertEqual(self.source.read_bytes(), before)

    def test_output_symlink_is_rejected_without_touching_target(self):
        target = self.root / "target.html"
        target.write_bytes(b"target")
        link = self.root / "dashboard.html"
        link.symlink_to(target)
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                link,
                overwrite=True,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)
        self.assertEqual(target.read_bytes(), b"target")

    def test_missing_output_parent_is_storage_error(self):
        output = self.root / "missing" / "dashboard.html"
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(self.source, self.expected, output)
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)

    def test_symlink_output_parent_is_storage_error(self):
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                linked_parent / "dashboard.html",
            )
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)

    def test_output_directory_is_storage_error(self):
        output = self.root / "dashboard.html"
        output.mkdir()
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_build(
                self.source,
                self.expected,
                output,
                overwrite=True,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)

    def test_invalid_expected_sha_is_invalid_request(self):
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_validate(self.source, "not-a-sha")
        self.assertIs(caught.exception.code, DashboardCliCode.INVALID_REQUEST)

    def test_wrong_valid_expected_sha_rejects_source(self):
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_validate(self.source, "a" * 64)
        self.assertIs(caught.exception.code, DashboardCliCode.SOURCE_REJECTED)

    def test_missing_source_rejects_source(self):
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_validate(self.root / "missing.json", self.expected)
        self.assertIs(caught.exception.code, DashboardCliCode.SOURCE_REJECTED)

    def test_source_symlink_rejects_source(self):
        link = self.root / "source-link.json"
        link.symlink_to(self.source)
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_validate(link, self.expected)
        self.assertIs(caught.exception.code, DashboardCliCode.SOURCE_REJECTED)

    def test_tampered_source_rejects_source(self):
        self.source.write_bytes(self.source.read_bytes() + b" ")
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_validate(self.source, self.expected)
        self.assertIs(caught.exception.code, DashboardCliCode.SOURCE_REJECTED)

    def test_non_boolean_overwrite_is_invalid_request(self):
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_cli._atomic_publish(
                self.root / "dashboard.html",
                dashboard_cli._pipeline(self.source, self.expected)[-1],
                overwrite="yes",
            )
        self.assertIs(caught.exception.code, DashboardCliCode.INVALID_REQUEST)

    def test_temp_file_is_created_in_same_output_directory(self):
        parent = self.root / "publish"
        parent.mkdir()
        output = parent / "dashboard.html"
        real = tempfile.NamedTemporaryFile
        with mock.patch(
            "yatl.dashboard.cli.tempfile.NamedTemporaryFile",
            wraps=real,
        ) as named:
            dashboard_build(self.source, self.expected, output)
        self.assertTrue(named.called)
        self.assertEqual(Path(named.call_args.kwargs["dir"]), parent)

    def test_temp_files_are_cleaned_after_success(self):
        dashboard_build(self.source, self.expected, self.root / "dashboard.html")
        self.assertEqual(self.temp_leftovers(), ())

    def test_temp_files_are_cleaned_when_output_exists(self):
        output = self.root / "dashboard.html"
        output.write_bytes(b"existing")
        with self.assertRaises(DashboardCliError):
            dashboard_build(self.source, self.expected, output)
        self.assertEqual(self.temp_leftovers(), ())

    def test_replace_failure_preserves_old_target_and_cleans_temp(self):
        output = self.root / "dashboard.html"
        output.write_bytes(b"existing")
        with mock.patch(
            "yatl.dashboard.cli.os.replace",
            side_effect=OSError("simulated"),
        ):
            with self.assertRaises(DashboardCliError) as caught:
                dashboard_build(
                    self.source,
                    self.expected,
                    output,
                    overwrite=True,
                )
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)
        self.assertEqual(output.read_bytes(), b"existing")
        self.assertEqual(self.temp_leftovers(), ())

    def test_link_failure_leaves_no_target_and_cleans_temp(self):
        output = self.root / "dashboard.html"
        with mock.patch(
            "yatl.dashboard.cli.os.link",
            side_effect=OSError("simulated"),
        ):
            with self.assertRaises(DashboardCliError) as caught:
                dashboard_build(self.source, self.expected, output)
        self.assertIs(caught.exception.code, DashboardCliCode.STORAGE_ERROR)
        self.assertFalse(output.exists())
        self.assertEqual(self.temp_leftovers(), ())

    def test_explicit_source_mutation_detection_fails_closed(self):
        initial = dashboard_cli._pipeline(self.source, self.expected)[0]
        self.source.write_bytes(self.source.read_bytes() + b" ")
        with self.assertRaises(DashboardCliError) as caught:
            dashboard_cli._assert_source_unchanged(
                initial,
                self.source,
                self.expected,
            )
        self.assertIs(caught.exception.code, DashboardCliCode.SOURCE_MUTATED)

    def test_main_validate_exit_zero_and_canonical_json(self):
        code, record = self.call_main([
            "validate",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(record["code"], DashboardCliCode.VALIDATED.value)

    def test_main_summary_exit_zero(self):
        code, record = self.call_main([
            "summary",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(record["code"], DashboardCliCode.SUMMARY_READY.value)

    def test_main_build_exit_zero(self):
        output = self.root / "dashboard.html"
        code, record = self.call_main([
            "build",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
            "--output",
            str(output),
        ])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(record["code"], DashboardCliCode.BUILT.value)
        self.assertTrue(output.exists())

    def test_main_output_exists_uses_stable_exit_code(self):
        output = self.root / "dashboard.html"
        output.write_bytes(b"existing")
        code, record = self.call_main([
            "build",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
            "--output",
            str(output),
        ])
        self.assertEqual(code, EXIT_EXISTS)
        self.assertEqual(record["code"], DashboardCliCode.OUTPUT_EXISTS.value)

    def test_main_invalid_parse_is_redacted(self):
        secret = "SUPER_SECRET_api_key_password_value"
        code, record = self.call_main(["validate", "--input", secret])
        self.assertEqual(code, EXIT_INVALID)
        self.assertEqual(record["code"], DashboardCliCode.INVALID_REQUEST.value)
        encoded = json.dumps(record)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("api_key", encoded.lower())
        self.assertNotIn("password", encoded.lower())

    def test_main_source_rejection_does_not_echo_path(self):
        missing = self.root / "VERY_PRIVATE_SOURCE_NAME.json"
        code, record = self.call_main([
            "validate",
            "--input",
            str(missing),
            "--expected-export-sha256",
            self.expected,
        ])
        self.assertEqual(code, EXIT_SOURCE)
        self.assertEqual(record["code"], DashboardCliCode.SOURCE_REJECTED.value)
        self.assertNotIn(str(missing), json.dumps(record))

    def test_main_storage_error_does_not_echo_output_path(self):
        output = self.root / "missing-parent" / "private-dashboard.html"
        code, record = self.call_main([
            "build",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
            "--output",
            str(output),
        ])
        self.assertEqual(code, EXIT_STORAGE)
        self.assertEqual(record["code"], DashboardCliCode.STORAGE_ERROR.value)
        self.assertNotIn(str(output), json.dumps(record))

    def test_main_unexpected_exception_is_stable_internal_error(self):
        with mock.patch(
            "yatl.dashboard.cli.dashboard_validate",
            side_effect=RuntimeError("private path /tmp/secret"),
        ):
            code, record = self.call_main([
                "validate",
                "--input",
                str(self.source),
                "--expected-export-sha256",
                self.expected,
            ])
        self.assertEqual(code, EXIT_INTERNAL)
        self.assertEqual(record["code"], DashboardCliCode.INTERNAL_ERROR.value)
        self.assertNotIn("private path", json.dumps(record))

    def test_main_success_never_echoes_input_or_output_paths(self):
        output = self.root / "secret-output-name.html"
        _, record = self.call_main([
            "build",
            "--input",
            str(self.source),
            "--expected-export-sha256",
            self.expected,
            "--output",
            str(output),
        ])
        encoded = json.dumps(record)
        self.assertNotIn(str(self.source), encoded)
        self.assertNotIn(str(output), encoded)

    def test_cli_records_preserve_paper_only_boundary(self):
        for record in (
            dashboard_validate(self.source, self.expected),
            dashboard_summary(self.source, self.expected),
        ):
            self.assertTrue(record["paper_only"])
            self.assertEqual(record["live_master_lock"], "OFF")
            self.assertEqual(record["strategy_evidence"], "INSUFFICIENT_EVIDENCE")

    def test_cli_source_has_no_analytics_runtime_or_network_execution_import(self):
        import inspect

        source_text = inspect.getsource(dashboard_cli)
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
                self.assertNotIn(forbidden, source_text)

    def test_cli_source_is_noninteractive(self):
        import inspect

        source_text = inspect.getsource(dashboard_cli)
        for forbidden in (
            "input(",
            "getpass",
            "eval(",
            "exec(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
