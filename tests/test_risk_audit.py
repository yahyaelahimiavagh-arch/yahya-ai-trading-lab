import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from decimal import localcontext
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import main
from yatl.risk import (
    P4AuditError,
    P4AuditResult,
    audit_p4,
    write_adversarial_scenario_matrix,
)
from yatl.risk.audit import (
    EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256,
    _audit_exact_decision,
    _audit_records,
    _policy_sha256,
    _read_evidence,
)

from tests.test_risk_scenarios import _latest, _load, _run_matrix


def _records(matrix):
    result = {"p4-009-index.json": json.loads(matrix.index_json)}
    for item in matrix.runs:
        name = (
            f"{item.symbol.lower()}-"
            f"{item.name.lower().replace('_', '-')}.json"
        )
        result[name] = json.loads(item.artifact_json)
    return result


class P4AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = _run_matrix()
        cls.index_sha256 = hashlib.sha256(
            cls.matrix.index_json.encode("utf-8")
        ).hexdigest()

    def _audit(self, evidence):
        with (
            patch("yatl.risk.audit.audit_p1_manifest") as p1,
            patch(
                "yatl.risk.scenarios.latest_spec_from_manifest",
                side_effect=_latest,
            ),
            patch(
                "yatl.risk.scenarios.load_accepted_dataset",
                side_effect=_load,
            ),
            patch("yatl.risk.audit.EXPECTED_INDEX_SHA256", self.index_sha256),
        ):
            result = audit_p4("database", "manifest", evidence)
        p1.assert_called_once_with("manifest")
        return result

    def test_final_audit_recomputes_and_checks_all_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, evidence)
            result = self._audit(evidence)
        self.assertEqual(
            (result.symbols, result.scenarios, result.runs, result.files),
            (2, 8, 16, 17),
        )
        self.assertEqual(result.index_sha256, self.index_sha256)
        self.assertEqual(result.policy_sha256, EXPECTED_POLICY_SHA256)
        self.assertTrue(result.exact_decisions)
        self.assertTrue(result.replay_equal)

    def test_policy_digest_is_frozen(self):
        self.assertEqual(_policy_sha256(), EXPECTED_POLICY_SHA256)

    def test_all_exact_scenario_decisions_are_independently_checked(self):
        records = _records(self.matrix)
        _audit_records(records)
        for name, record in records.items():
            if name != "p4-009-index.json":
                _audit_exact_decision(record)

    def test_changed_exact_decision_fails_closed(self):
        records = _records(self.matrix)
        name = "btcusdt-session-loss-boundary.json"
        records[name]["observed"]["risk_reason"] = "RISK_CHECKS_PASSED"
        with self.assertRaises(P4AuditError):
            _audit_exact_decision(records[name])

    def test_tampering_and_noncanonical_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-gap-fail-closed.json"
            target.write_text(target.read_text(encoding="utf-8") + " ",
                              encoding="utf-8")
            with self.assertRaises(P4AuditError):
                _read_evidence(evidence)

    def test_missing_extra_and_symlink_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, evidence)
            missing = evidence / "ethusdt-stale-state-rejection.json"
            original = missing.read_bytes()
            missing.unlink()
            with self.assertRaises(P4AuditError):
                _read_evidence(evidence)
            missing.write_bytes(original)
            extra = evidence / "extra.json"
            extra.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P4AuditError):
                _read_evidence(evidence)
            extra.unlink()
            missing.unlink()
            missing.symlink_to(evidence / "p4-009-index.json")
            with self.assertRaises(P4AuditError):
                _read_evidence(evidence)

    def test_changed_accepted_replay_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, evidence)
            with (
                patch("yatl.risk.audit.audit_p1_manifest"),
                patch(
                    "yatl.risk.scenarios.latest_spec_from_manifest",
                    side_effect=_latest,
                ),
                patch(
                    "yatl.risk.scenarios.load_accepted_dataset",
                    side_effect=_load,
                ),
            ):
                with self.assertRaises(P4AuditError):
                    audit_p4("database", "manifest", evidence)

    def test_recomputation_ignores_ambient_decimal_precision(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, evidence)
            with localcontext() as arithmetic:
                arithmetic.prec = 6
                result = self._audit(evidence)
        self.assertTrue(result.replay_equal)

    @patch("yatl.__main__.audit_p4")
    @patch("sys.argv", ["yatl", "p4-audit"])
    def test_cli_reports_safe_final_audit(self, audit):
        audit.return_value = P4AuditResult(
            2, 8, 16, 17, EXPECTED_INDEX_SHA256,
            EXPECTED_POLICY_SHA256, True, True,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 final acceptance audit", text)
        self.assertIn("files=17", text)
        self.assertIn("exact_decisions=true replay_equal=true", text)
        self.assertIn("P5 unopened", text)
        self.assertIn("No trade permission", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
