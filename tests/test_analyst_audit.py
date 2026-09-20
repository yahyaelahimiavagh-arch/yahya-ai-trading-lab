import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.analyst.audit import (
    EXPECTED_EVIDENCE_SHA256,
    EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256,
    P6AuditError,
    _audit_exact_outcome,
    _audit_records,
    _audit_source_safety,
    _evidence_sha256,
    _policy_sha256,
    _read_evidence,
    audit_p6,
)
from yatl.analyst.scenarios import (
    run_adversarial_analyst_matrix,
    write_adversarial_analyst_matrix,
)


def _records(matrix):
    records = {"p6-009-index.json": json.loads(matrix.index_json)}
    for item in matrix.runs:
        name = (
            f"{item.symbol.lower()}-"
            f"{item.name.lower().replace('_', '-')}.json"
        )
        records[name] = json.loads(item.artifact_json)
    return records


class P6FinalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = run_adversarial_analyst_matrix()

    def test_final_audit_recomputes_and_checks_all_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analyst_matrix(self.matrix, evidence)
            result = audit_p6(evidence)
        self.assertEqual(
            (result.symbols, result.scenarios, result.runs, result.files),
            (2, 8, 16, 17),
        )
        self.assertEqual(result.index_sha256, EXPECTED_INDEX_SHA256)
        self.assertEqual(result.policy_sha256, EXPECTED_POLICY_SHA256)
        self.assertEqual(result.evidence_sha256, EXPECTED_EVIDENCE_SHA256)
        self.assertTrue(result.exact_outcomes)
        self.assertTrue(result.replay_equal)
        self.assertTrue(result.source_safe)

    def test_policy_and_evidence_digests_are_frozen(self):
        self.assertEqual(_policy_sha256(), EXPECTED_POLICY_SHA256)
        self.assertEqual(_evidence_sha256(), EXPECTED_EVIDENCE_SHA256)

    def test_all_exact_scenario_outcomes_are_independently_checked(self):
        records = _records(self.matrix)
        _audit_records(records)
        for name, record in records.items():
            if name != "p6-009-index.json":
                _audit_exact_outcome(record)

    def test_changed_exact_outcome_fails_closed(self):
        records = _records(self.matrix)
        target = records["btcusdt-unsupported-certainty.json"]
        target["observed"]["grounding_code"] = "GROUNDED"
        with self.assertRaises(P6AuditError):
            _audit_exact_outcome(target)

    def test_prompt_injection_escalation_fails_closed(self):
        records = _records(self.matrix)
        target = records["ethusdt-prompt-injection.json"]
        target["observed"]["transport"] = "PROVIDER"
        with self.assertRaises(P6AuditError):
            _audit_exact_outcome(target)

    def test_tampering_and_noncanonical_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analyst_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-provider-response-corruption.json"
            target.write_text(
                target.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            with self.assertRaises(P6AuditError):
                _read_evidence(evidence)

    def test_missing_extra_and_symlink_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analyst_matrix(self.matrix, evidence)
            target = evidence / "ethusdt-future-input.json"
            original = target.read_bytes()
            target.unlink()
            with self.assertRaises(P6AuditError):
                _read_evidence(evidence)
            target.write_bytes(original)

            extra = evidence / "extra.json"
            extra.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P6AuditError):
                _read_evidence(evidence)
            extra.unlink()

            target.unlink()
            target.symlink_to(evidence / "p6-009-index.json")
            with self.assertRaises(P6AuditError):
                _read_evidence(evidence)

    def test_changed_frozen_replay_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analyst_matrix(self.matrix, evidence)
            with patch(
                "yatl.analyst.audit.EXPECTED_INDEX_SHA256",
                "0" * 64,
            ):
                with self.assertRaises(P6AuditError):
                    audit_p6(evidence)

    def test_changed_frozen_policy_or_evidence_digest_fails_closed(self):
        with patch(
            "yatl.analyst.audit.EXPECTED_POLICY_SHA256",
            "0" * 64,
        ):
            with self.assertRaises(P6AuditError):
                _policy_sha256()
        with patch(
            "yatl.analyst.audit.EXPECTED_EVIDENCE_SHA256",
            "0" * 64,
        ):
            with self.assertRaises(P6AuditError):
                _evidence_sha256()

    def test_source_safety_is_independently_checked(self):
        self.assertTrue(_audit_source_safety())

    def test_index_tamper_fails_closed(self):
        records = _records(self.matrix)
        records["p6-009-index.json"]["trade_permission"] = True
        with self.assertRaises(P6AuditError):
            _audit_records(records)

    def test_file_digest_mismatch_fails_closed(self):
        records = _records(self.matrix)
        records["p6-009-index.json"]["runs"][0]["sha256"] = "0" * 64
        with self.assertRaises(P6AuditError):
            _audit_records(records)

    def test_forbidden_material_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analyst_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-schema-smuggling.json"
            record = json.loads(target.read_text(encoding="utf-8"))
            record["observed"]["raw_response"] = "private"
            target.write_text(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P6AuditError):
                _read_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
