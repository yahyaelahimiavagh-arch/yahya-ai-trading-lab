import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.analytics.audit import (
    EXPECTED_BTC_CHAIN,
    EXPECTED_INDEX_SHA256,
    EXPECTED_POLICY_SHA256,
    EXPECTED_UPSTREAM_IDENTITIES,
    P7AuditError,
    _audit_exact_outcome,
    _audit_records,
    _audit_source_safety,
    _chain_record,
    _chain_set_sha256,
    _policy_sha256,
    _read_evidence,
    audit_p7,
)
from yatl.analytics.scenarios import (
    run_adversarial_analytics_matrix,
    write_adversarial_analytics_matrix,
)


def _records(matrix):
    records = {"p7-009-index.json": json.loads(matrix.index_json)}
    for item in matrix.runs:
        name = (
            f"{item.symbol.lower()}-"
            f"{item.name.lower().replace('_', '-')}.json"
        )
        records[name] = json.loads(item.artifact_json)
    return records


class P7FinalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = run_adversarial_analytics_matrix()

    def test_final_audit_recomputes_chain_and_checks_all_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analytics_matrix(self.matrix, evidence)
            result = audit_p7(evidence)
        self.assertEqual(
            (result.symbols, result.scenarios, result.runs, result.files),
            (2, 9, 18, 19),
        )
        self.assertEqual(result.index_sha256, EXPECTED_INDEX_SHA256)
        self.assertEqual(result.policy_sha256, EXPECTED_POLICY_SHA256)
        self.assertEqual(len(result.chain_set_sha256), 64)
        self.assertTrue(result.exact_outcomes)
        self.assertTrue(result.replay_equal)
        self.assertTrue(result.chain_recomputed)
        self.assertTrue(result.no_write)
        self.assertTrue(result.source_safe)

    def test_policy_digest_is_frozen(self):
        self.assertEqual(_policy_sha256(), EXPECTED_POLICY_SHA256)

    def test_btc_accepted_chain_is_frozen_and_recomputed(self):
        record = _chain_record("BTCUSDT")
        for name, expected in EXPECTED_BTC_CHAIN.items():
            self.assertEqual(record[name], expected)
        self.assertEqual(record["completed_trade_count"], 1)
        self.assertEqual(record["analyst_trace_count"], 1)
        self.assertEqual(
            record["strategy_evidence"],
            "INSUFFICIENT_EVIDENCE",
        )
        self.assertTrue(record["replay_equal"])
        self.assertTrue(record["no_write"])

    def test_both_symbol_chains_are_deterministic_and_distinct(self):
        first, chains_one = _chain_set_sha256()
        second, chains_two = _chain_set_sha256()
        self.assertEqual(first, second)
        self.assertEqual(chains_one, chains_two)
        self.assertEqual(
            tuple(item["symbol"] for item in chains_one),
            ("BTCUSDT", "ETHUSDT"),
        )
        self.assertNotEqual(
            chains_one[0]["segmentation_sha256"],
            chains_one[1]["segmentation_sha256"],
        )

    def test_all_exact_scenario_outcomes_are_independently_checked(self):
        records = _records(self.matrix)
        _audit_records(records)
        for name, record in records.items():
            if name != "p7-009-index.json":
                _audit_exact_outcome(record)

    def test_changed_quality_outcome_fails_closed(self):
        records = _records(self.matrix)
        target = records["btcusdt-cross-symbol-linkage.json"]
        target["observed"]["diagnostics"][0]["code"] = "TIMELINE_GAP"
        with self.assertRaises(P7AuditError):
            _audit_exact_outcome(target)

    def test_profitability_fabrication_acceptance_fails_closed(self):
        records = _records(self.matrix)
        target = records["ethusdt-fabricated-profitability.json"]
        target["expected"]["fabricated_profitability_accepted"] = True
        with self.assertRaises(P7AuditError):
            _audit_exact_outcome(target)

    def test_evidence_upgrade_or_journal_write_escalation_fails_closed(self):
        records = _records(self.matrix)
        upgraded = records["btcusdt-evidence-label-upgrade.json"]
        upgraded["observed"]["strategy_evidence"] = "QUALIFIED_FOR_P4_RESEARCH"
        with self.assertRaises(P7AuditError):
            _audit_exact_outcome(upgraded)

        mutation = records["ethusdt-journal-mutation.json"]
        mutation["observed"]["no_write"] = False
        with self.assertRaises(P7AuditError):
            _audit_exact_outcome(mutation)

    def test_tampering_and_noncanonical_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analytics_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-schema-smuggling.json"
            target.write_text(
                target.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            with self.assertRaises(P7AuditError):
                _read_evidence(evidence)

    def test_missing_extra_and_symlink_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analytics_matrix(self.matrix, evidence)
            target = evidence / "ethusdt-future-timestamp.json"
            original = target.read_bytes()
            target.unlink()
            with self.assertRaises(P7AuditError):
                _read_evidence(evidence)
            target.write_bytes(original)

            extra = evidence / "extra.json"
            extra.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P7AuditError):
                _read_evidence(evidence)
            extra.unlink()

            target.unlink()
            target.symlink_to(evidence / "p7-009-index.json")
            with self.assertRaises(P7AuditError):
                _read_evidence(evidence)

    def test_changed_frozen_replay_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analytics_matrix(self.matrix, evidence)
            with patch(
                "yatl.analytics.audit.EXPECTED_INDEX_SHA256",
                "0" * 64,
            ):
                with self.assertRaises(P7AuditError):
                    audit_p7(evidence)

    def test_changed_frozen_policy_or_btc_chain_fails_closed(self):
        with patch(
            "yatl.analytics.audit.EXPECTED_POLICY_SHA256",
            "0" * 64,
        ):
            with self.assertRaises(P7AuditError):
                _policy_sha256()
        with patch.dict(
            "yatl.analytics.audit.EXPECTED_BTC_CHAIN",
            {"metrics_sha256": "0" * 64},
        ):
            with self.assertRaises(P7AuditError):
                _chain_record("BTCUSDT")

    def test_index_tamper_or_upstream_identity_drift_fails_closed(self):
        records = _records(self.matrix)
        records["p7-009-index.json"]["trade_permission"] = True
        with self.assertRaises(P7AuditError):
            _audit_records(records)

        records = _records(self.matrix)
        records["p7-009-index.json"][
            "accepted_upstream_identities"
        ]["p6_policy_sha256"] = "0" * 64
        with self.assertRaises(P7AuditError):
            _audit_records(records)

    def test_file_digest_mismatch_fails_closed(self):
        records = _records(self.matrix)
        records["p7-009-index.json"]["runs"][0]["sha256"] = "0" * 64
        with self.assertRaises(P7AuditError):
            _audit_records(records)

    def test_forbidden_material_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            write_adversarial_analytics_matrix(self.matrix, evidence)
            target = evidence / "btcusdt-upstream-tampering.json"
            record = json.loads(target.read_text(encoding="utf-8"))
            record["observed"]["database_path"] = "/private/source.sqlite3"
            target.write_text(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                ) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P7AuditError):
                _read_evidence(evidence)

    def test_accepted_upstream_identity_set_is_exact(self):
        self.assertEqual(
            set(EXPECTED_UPSTREAM_IDENTITIES),
            {
                "p3_index_sha256",
                "p4_index_sha256",
                "p4_policy_sha256",
                "p5_index_sha256",
                "p5_policy_sha256",
                "p6_index_sha256",
                "p6_policy_sha256",
                "p6_evidence_sha256",
            },
        )

    def test_source_safety_is_independently_checked(self):
        self.assertTrue(_audit_source_safety())


if __name__ == "__main__":
    unittest.main()
