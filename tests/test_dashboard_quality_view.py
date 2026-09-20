import copy
import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.contracts import DiagnosticSeverity
from yatl.dashboard.loader import load_p7_export
from yatl.dashboard.quality_view import (
    QUALITY_CHECKS,
    QUALITY_CODES,
    QUALITY_COMPONENTS,
    QualityDiagnosticProjectionError,
    project_quality_diagnostics,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    material = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class QualityDiagnosticViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        healthy_root = self.root / "healthy"
        healthy_root.mkdir()
        _, _, specs = _fixture(healthy_root)
        healthy_gate = run_quality_gate(SNAPSHOT, specs)
        self.export_record, encoded = _export_payload(healthy_gate)
        self.export_path = self.root / "accepted.json"
        self.export_path.write_text(encoded, encoding="utf-8")
        self.loaded = load_p7_export(
            self.export_path,
            self.export_record["export_sha256"],
        )

        failed_root = self.root / "failed"
        failed_root.mkdir()
        _, p6, failed_specs = _fixture(failed_root)
        p6.unlink()
        self.failed_gate = run_quality_gate(SNAPSHOT, failed_specs)
        self.failed_record = self.failed_gate.report.as_record()

    def tearDown(self):
        self.temp.cleanup()

    def test_pass_projection_is_deterministic_and_allows_analytics(self):
        first = project_quality_diagnostics(loaded=self.loaded)
        second = project_quality_diagnostics(loaded=self.loaded)
        self.assertEqual(first, second)
        self.assertEqual(first.projection_sha256, second.projection_sha256)
        self.assertEqual(first.quality_status, "PASS")
        self.assertIs(first.status_severity, DiagnosticSeverity.INFO)
        self.assertTrue(first.publication_allowed)
        self.assertTrue(first.analytics_presentation_allowed)
        self.assertFalse(first.partial_analytics_visible)
        self.assertEqual(first.diagnostics, ())

    def test_pass_projection_requires_complete_known_check_set(self):
        view = project_quality_diagnostics(loaded=self.loaded)
        self.assertEqual(view.passed_checks, QUALITY_CHECKS)

    def test_pass_projection_binds_quality_and_export_hashes(self):
        view = project_quality_diagnostics(loaded=self.loaded)
        self.assertEqual(view.source_quality_sha256, self.loaded.quality_sha256)
        self.assertEqual(view.source_export_sha256, self.loaded.export_sha256)
        self.assertEqual(view.snapshot_time_ms, self.loaded.source.observed_at_ms)

    def test_pass_projection_is_frozen(self):
        view = project_quality_diagnostics(loaded=self.loaded)
        with self.assertRaises(FrozenInstanceError):
            view.quality_status = "FAIL"

    def test_pass_projection_rejects_tampered_loaded_quality(self):
        record = self.loaded.record()
        record["quality"]["publication_allowed"] = False
        forged = replace(self.loaded, canonical_json=canonical(record) + "\n")
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(loaded=forged)

    def test_raw_pass_quality_cannot_bypass_accepted_export_loader(self):
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(
                quality_record=self.export_record["quality"],
            )

    def test_fail_projection_blocks_all_analytics_presentation(self):
        view = project_quality_diagnostics(quality_record=self.failed_record)
        self.assertEqual(view.quality_status, "FAIL")
        self.assertIs(view.status_severity, DiagnosticSeverity.ERROR)
        self.assertFalse(view.publication_allowed)
        self.assertFalse(view.analytics_presentation_allowed)
        self.assertFalse(view.partial_analytics_visible)
        self.assertIsNone(view.source_export_sha256)

    def test_fail_projection_preserves_only_sanitized_p7_diagnostics(self):
        view = project_quality_diagnostics(quality_record=self.failed_record)
        self.assertEqual(len(view.diagnostics), 1)
        item = view.diagnostics[0]
        self.assertEqual(item.code, "MISSING_SOURCE")
        self.assertIs(item.severity, DiagnosticSeverity.ERROR)
        self.assertTrue(item.display_only)
        self.assertIn("Component: SOURCE.", item.message)

    def test_diagnostic_hash_binds_exact_p7_code_component(self):
        view = project_quality_diagnostics(quality_record=self.failed_record)
        source = self.failed_record["diagnostics"][0]
        expected = digest({
            "schema_version": 1,
            "diagnostic": source,
        })
        self.assertEqual(view.diagnostics[0].source_diagnostic_sha256, expected)

    def test_all_known_codes_have_stable_error_mapping(self):
        for code in QUALITY_CODES:
            with self.subTest(code=code):
                record = copy.deepcopy(self.failed_record)
                record["diagnostics"] = [{"code": code, "component": "GATE"}]
                view = project_quality_diagnostics(quality_record=record)
                self.assertEqual(view.diagnostics[0].code, code)
                self.assertIs(view.diagnostics[0].severity, DiagnosticSeverity.ERROR)
                self.assertTrue(view.diagnostics[0].message.endswith("Component: GATE."))

    def test_all_known_components_are_accepted(self):
        for component in QUALITY_COMPONENTS:
            with self.subTest(component=component):
                record = copy.deepcopy(self.failed_record)
                record["diagnostics"] = [
                    {"code": "ANALYTICS_CHAIN_INVALID", "component": component}
                ]
                view = project_quality_diagnostics(quality_record=record)
                self.assertIn(f"Component: {component}.", view.diagnostics[0].message)

    def test_fail_quality_hash_is_exact_canonical_record_digest(self):
        view = project_quality_diagnostics(quality_record=self.failed_record)
        self.assertEqual(view.source_quality_sha256, digest(self.failed_record))

    def test_absent_quality_blocks_analytics_without_invented_diagnostics(self):
        view = project_quality_diagnostics()
        self.assertEqual(view.quality_status, "ABSENT")
        self.assertIs(view.status_severity, DiagnosticSeverity.ERROR)
        self.assertFalse(view.publication_allowed)
        self.assertFalse(view.analytics_presentation_allowed)
        self.assertFalse(view.partial_analytics_visible)
        self.assertEqual(view.diagnostics, ())
        self.assertEqual(view.passed_checks, ())
        self.assertIsNone(view.source_quality_sha256)
        self.assertIsNone(view.source_export_sha256)
        self.assertIsNone(view.snapshot_time_ms)

    def test_absent_projection_is_deterministic(self):
        first = project_quality_diagnostics()
        second = project_quality_diagnostics()
        self.assertEqual(first, second)
        self.assertEqual(first.projection_sha256, second.projection_sha256)

    def test_both_source_modes_are_rejected(self):
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(
                loaded=self.loaded,
                quality_record=self.failed_record,
            )

    def test_unknown_diagnostic_code_fails_closed(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"] = [{"code": "UNKNOWN_CODE", "component": "SOURCE"}]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_unknown_diagnostic_component_fails_closed(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"] = [
            {"code": "MISSING_SOURCE", "component": "UNKNOWN_COMPONENT"}
        ]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_unknown_passed_check_fails_closed(self):
        record = copy.deepcopy(self.failed_record)
        record["passed_checks"] = ["UNKNOWN_CHECK"]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_duplicate_diagnostic_is_rejected(self):
        record = copy.deepcopy(self.failed_record)
        item = record["diagnostics"][0]
        record["diagnostics"] = [copy.deepcopy(item), copy.deepcopy(item)]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_unordered_diagnostics_are_rejected(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"] = [
            {"code": "UPSTREAM_MUTATION", "component": "SOURCE"},
            {"code": "MISSING_SOURCE", "component": "SOURCE"},
        ]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_more_than_eight_diagnostics_are_rejected(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"] = [
            {"code": code, "component": "SOURCE"}
            for code in QUALITY_CODES[:9]
        ]
        record["diagnostics"] = sorted(
            record["diagnostics"],
            key=lambda item: (item["code"], item["component"]),
        )
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_requires_at_least_one_diagnostic(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"] = []
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_rejects_partial_accepted_chain(self):
        record = copy.deepcopy(self.failed_record)
        record["accepted_chain"] = self.export_record["quality"]["accepted_chain"]
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_rejects_publication_allowed_true(self):
        record = copy.deepcopy(self.failed_record)
        record["publication_allowed"] = True
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_rejects_strategy_evidence_upgrade(self):
        record = copy.deepcopy(self.failed_record)
        record["strategy_evidence"] = "PROVEN"
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_rejects_safety_weakening(self):
        record = copy.deepcopy(self.failed_record)
        record["safety"]["partial_publication_on_failure"] = True
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_extra_free_text_or_path_field_is_rejected(self):
        record = copy.deepcopy(self.failed_record)
        record["diagnostics"][0]["message"] = "/tmp/private.sqlite3 SELECT * Traceback"
        with self.assertRaises(QualityDiagnosticProjectionError):
            project_quality_diagnostics(quality_record=record)

    def test_fail_projection_contains_no_analytics_payload_or_private_strings(self):
        view = project_quality_diagnostics(quality_record=self.failed_record)
        encoded = canonical(view.as_record())
        for forbidden in (
            "trade_metrics",
            "trade_segments",
            "analyst_segments",
            "database_path",
            ".sqlite3",
            "SELECT ",
            "Traceback",
            "api_key",
            "api_secret",
            "account_id",
            str(self.root),
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_pass_projection_record_contains_no_analytics_payload(self):
        view = project_quality_diagnostics(loaded=self.loaded)
        record = view.as_record()
        self.assertNotIn("analytics", record)
        self.assertNotIn("trade_metrics", record)
        self.assertNotIn("segment_rows", record)

    def test_quality_view_source_has_no_analytics_runtime_database_or_network_import(self):
        import yatl.dashboard.quality_view as quality_view

        source_text = inspect.getsource(quality_view)
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


if __name__ == "__main__":
    unittest.main()
