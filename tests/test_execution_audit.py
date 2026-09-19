import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.execution import (
    P5AuditError,
    audit_p5,
    run_adversarial_execution_matrix,
    write_adversarial_execution_matrix,
)
from yatl.execution.audit import (
    EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256,
    _audit_exact_outcome,
    _audit_records,
    _audit_source_safety,
    _policy_sha256,
    _read_evidence,
)


def _records(matrix):
    records = {"p5-009-index.json": json.loads(matrix.index_json)}
    for item in matrix.runs:
        name = (
            f"{item.symbol.lower()}-"
            f"{item.name.lower().replace('_', '-')}.json"
        )
        records[name] = json.loads(item.artifact_json)
    return records


class P5FinalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = run_adversarial_execution_matrix()

    def test_final_audit_recomputes_and_checks_all_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_execution_matrix(self.matrix, evidence)
            result = audit_p5(evidence)
        self.assertEqual(
            (result.symbols, result.scenarios, result.runs, result.files),
            (2, 9, 18, 19),
        )
        self.assertEqual(result.index_sha256, EXPECTED_INDEX_SHA256)
        self.assertEqual(result.policy_sha256, EXPECTED_POLICY_SHA256)
        self.assertTrue(result.exact_outcomes)
        self.assertTrue(result.replay_equal)
        self.assertTrue(result.source_safe)

    def test_policy_digest_is_frozen(self):
        self.assertEqual(_policy_sha256(), EXPECTED_POLICY_SHA256)

    def test_all_exact_scenario_outcomes_are_independently_checked(self):
        records = _records(self.matrix)
        _audit_records(records)
        for name, record in records.items():
            if name != "p5-009-index.json":
                _audit_exact_outcome(record)

    def test_changed_exact_outcome_fails_closed(self):
        records = _records(self.matrix)
        record = records["btcusdt-duplicate-intent.json"]
        record["observed"]["intent_count"] = 2
        with self.assertRaises(P5AuditError):
            _audit_exact_outcome(record)

    def test_tampering_and_noncanonical_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_execution_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-journal-corruption.json"
            target.write_text(
                target.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            with self.assertRaises(P5AuditError):
                _read_evidence(evidence)

    def test_missing_extra_and_symlink_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_execution_matrix(self.matrix, evidence)
            target = evidence / "ethusdt-uncertain-commit.json"
            original = target.read_bytes()
            target.unlink()
            with self.assertRaises(P5AuditError):
                _read_evidence(evidence)
            target.write_bytes(original)
            extra = evidence / "extra.json"
            extra.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P5AuditError):
                _read_evidence(evidence)
            extra.unlink()
            target.unlink()
            target.symlink_to(evidence / "p5-009-index.json")
            with self.assertRaises(P5AuditError):
                _read_evidence(evidence)

    def test_changed_frozen_replay_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_execution_matrix(self.matrix, evidence)
            with patch(
                "yatl.execution.audit.EXPECTED_INDEX_SHA256",
                "0" * 64,
            ):
                with self.assertRaises(P5AuditError):
                    audit_p5(evidence)

    def test_source_safety_is_independently_checked(self):
        self.assertTrue(_audit_source_safety())

    def test_evidence_with_forbidden_material_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_execution_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-missing-fill-candle.json"
            record = json.loads(target.read_text(encoding="utf-8"))
            record["api_key"] = "forbidden"
            target.write_text(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P5AuditError):
                _read_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
