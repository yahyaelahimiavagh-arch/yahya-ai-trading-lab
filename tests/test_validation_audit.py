import hashlib
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.validation.audit import (
    EXPECTED_CANDIDATE_SHA256,
    EXPECTED_CRITERIA,
    EXPECTED_EVIDENCE_FILES,
    EXPECTED_GATE_REGISTRY_SHA256,
    EXPECTED_WINDOW_SHA256,
    P10AuditError,
    P10AuditResult,
    _audit_evidence,
    _audit_source_safety,
    _candidate_gate_window,
    _disposition_flags,
    _read_evidence,
    audit_p10,
)
from yatl.validation.cli import _pipeline, snapshot_json
from yatl.validation.forward_store import ForwardCandleStore
from yatl.validation.paper_runner_runtime import build_mock_forward_runner_fixture
from yatl.validation.scenarios import (
    SCENARIOS,
    accepted_validation_fixture,
    run_adversarial_validation_matrix,
    validation_matrix_sha256,
    write_adversarial_validation_matrix,
)


EXPECTED_PAPER_RUN_SHA256 = (
    "de65b7cbd63f495542c59df19b51c3ab9fc4b6f06ce57206e7c5e9110a00850a"
)
EXPECTED_ECONOMICS_SHA256 = (
    "36f3e1dcb35d002b286c81b1b192056789e8294777ecc49f5d03d9affe469c4e"
)
EXPECTED_GATE_SHA256 = (
    "a7761f5ee0b9c6a61626dae15dc93bc430c0f96387189e8d39e85f22cb0bdd2b"
)
EXPECTED_AUDIT_SHA256 = (
    "1c11ea83affa5dd8d55644a573e765bb83435d0be6e39135384c9d79dda16be8"
)
EXPECTED_MATRIX_SHA256 = (
    "e9b36b749519c4793b94913e3d40c56aaf3aa60a82d42138cc17683568528b93"
)


class P10IndependentFinalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        store, cls.snapshot, cls.client = build_mock_forward_runner_fixture(cls.root)
        cls.database = cls.root / "p10-forward.sqlite3"
        store.close()

        cls.snapshot_path = cls.root / "snapshot.json"
        cls.snapshot_path.write_text(
            snapshot_json(cls.snapshot),
            encoding="utf-8",
        )
        cls.bundle = _pipeline(cls.database, cls.snapshot_path)
        cls.fixture = accepted_validation_fixture(cls.bundle)
        cls.matrix = run_adversarial_validation_matrix(cls.fixture)
        cls.evidence = cls.root / "p10-009-evidence"
        write_adversarial_validation_matrix(cls.matrix, cls.evidence)
        cls.database_sha = hashlib.sha256(cls.database.read_bytes()).hexdigest()

        cls.evidence_before = {
            path.name: path.read_bytes()
            for path in sorted(cls.evidence.iterdir(), key=lambda item: item.name)
        }
        with ForwardCandleStore(cls.database) as accepted_store:
            cls.result = audit_p10(
                accepted_store,
                cls.snapshot,
                cls.database_sha,
                cls.evidence,
            )
        cls.evidence_after = {
            path.name: path.read_bytes()
            for path in sorted(cls.evidence.iterdir(), key=lambda item: item.name)
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_mocked_final_disposition_is_insufficient(self):
        self.assertEqual(self.result.disposition, "INSUFFICIENT_DATA")
        self.assertTrue(self.result.continue_forward_observation)
        self.assertFalse(self.result.research_restart_required)
        self.assertFalse(self.result.economic_candidate_accepted)
        self.assertFalse(self.result.p11_consideration_allowed)

    def test_final_audit_never_unlocks_live_authority(self):
        self.assertFalse(self.result.p11_unlocked)
        self.assertFalse(self.result.live_authorized)
        self.assertEqual(
            self.result.strategy_evidence,
            "INSUFFICIENT_EVIDENCE",
        )

    def test_database_snapshot_digest_is_independently_bound(self):
        self.assertEqual(
            self.result.database_snapshot_sha256,
            self.database_sha,
        )

    def test_frozen_candidate_gate_window_digests_are_exact(self):
        self.assertEqual(
            self.result.candidate_sha256,
            EXPECTED_CANDIDATE_SHA256,
        )
        self.assertEqual(
            self.result.gate_registry_sha256,
            EXPECTED_GATE_REGISTRY_SHA256,
        )
        self.assertEqual(
            self.result.window_sha256,
            EXPECTED_WINDOW_SHA256,
        )
        candidate, gates, window = _candidate_gate_window()
        self.assertEqual(candidate.candidate_sha256, EXPECTED_CANDIDATE_SHA256)
        self.assertEqual(gates.registry_sha256, EXPECTED_GATE_REGISTRY_SHA256)
        self.assertEqual(window.window_sha256, EXPECTED_WINDOW_SHA256)

    def test_mocked_chain_digests_match_accepted_recomputation(self):
        self.assertEqual(self.result.paper_run_sha256, EXPECTED_PAPER_RUN_SHA256)
        self.assertEqual(self.result.economics_sha256, EXPECTED_ECONOMICS_SHA256)
        self.assertEqual(self.result.gate_sha256, EXPECTED_GATE_SHA256)
        self.assertEqual(self.result.audit_sha256, EXPECTED_AUDIT_SHA256)
        self.assertEqual(
            self.result.adversarial_matrix_sha256,
            EXPECTED_MATRIX_SHA256,
        )

    def test_matrix_digest_matches_direct_recomputation(self):
        self.assertEqual(
            validation_matrix_sha256(self.matrix),
            EXPECTED_MATRIX_SHA256,
        )

    def test_final_audit_exact_counts(self):
        self.assertEqual(self.result.criteria, len(EXPECTED_CRITERIA))
        self.assertEqual(self.result.scenarios, len(SCENARIOS))
        self.assertEqual(self.result.evidence_files, EXPECTED_EVIDENCE_FILES)
        self.assertEqual((self.result.criteria, self.result.scenarios), (7, 11))

    def test_all_final_acceptance_booleans_are_true(self):
        for name in (
            "exact_outcomes",
            "replay_equal",
            "chain_recomputed",
            "data_quality_recomputed",
            "adversarial_recomputed",
            "evidence_verified",
            "candidate_unchanged",
            "thresholds_unchanged",
            "no_write",
            "source_safe",
        ):
            with self.subTest(name=name):
                self.assertTrue(getattr(self.result, name))

    def test_final_audit_does_not_mutate_p10_009_evidence(self):
        self.assertEqual(self.evidence_before, self.evidence_after)

    def test_store_content_digest_is_valid(self):
        self.assertEqual(len(self.result.store_content_sha256), 64)
        int(self.result.store_content_sha256, 16)

    def test_read_evidence_has_exact_files(self):
        payloads = _read_evidence(self.evidence)
        self.assertEqual(len(payloads), EXPECTED_EVIDENCE_FILES)
        self.assertEqual(
            set(payloads),
            {"p10-009-index.json"} | {
                f"{name.lower().replace('_', '-')}.json"
                for name in SCENARIOS
            },
        )

    def test_adversarial_evidence_recomputes_exactly(self):
        payloads = _audit_evidence(self.matrix, self.evidence)
        self.assertEqual(payloads, _read_evidence(self.evidence))

    def test_missing_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            next(
                path for path in target.iterdir()
                if path.name != "p10-009-index.json"
            ).unlink()
            with self.assertRaises(P10AuditError):
                _read_evidence(target)

    def test_extra_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            (target / "extra.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P10AuditError):
                _read_evidence(target)

    def test_noncanonical_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p10-009-index.json"
            index.write_bytes(index.read_bytes() + b" ")
            with self.assertRaises(P10AuditError):
                _read_evidence(target)

    def test_tampered_evidence_differs_from_recomputed_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            index = target / "p10-009-index.json"
            record = json.loads(index.read_text(encoding="utf-8"))
            record["p11_unlocked"] = True
            index.write_text(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(P10AuditError):
                _audit_evidence(self.matrix, target)

    def test_evidence_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evidence"
            shutil.copytree(self.evidence, target)
            victim = target / "p10-009-index.json"
            source = target / "saved-index.json"
            victim.rename(source)
            victim.symlink_to(source)
            with self.assertRaises(P10AuditError):
                _read_evidence(target)

    def test_invalid_database_digest_fails_before_audit(self):
        with self.assertRaises(P10AuditError):
            audit_p10(None, self.snapshot, "bad", self.evidence)

    def test_disposition_flag_contract_is_exact(self):
        self.assertEqual(
            _disposition_flags("INSUFFICIENT_DATA"),
            {
                "continue_forward_observation": True,
                "research_restart_required": False,
                "economic_candidate_accepted": False,
                "p11_consideration_allowed": False,
            },
        )
        self.assertEqual(
            _disposition_flags("FAIL"),
            {
                "continue_forward_observation": False,
                "research_restart_required": True,
                "economic_candidate_accepted": False,
                "p11_consideration_allowed": False,
            },
        )
        self.assertEqual(
            _disposition_flags("PASS_CANDIDATE"),
            {
                "continue_forward_observation": False,
                "research_restart_required": False,
                "economic_candidate_accepted": True,
                "p11_consideration_allowed": True,
            },
        )

    def test_pass_candidate_allows_consideration_but_not_unlock(self):
        candidate = replace(
            self.result,
            disposition="PASS_CANDIDATE",
            continue_forward_observation=False,
            research_restart_required=False,
            economic_candidate_accepted=True,
            p11_consideration_allowed=True,
        )
        self.assertTrue(candidate.p11_consideration_allowed)
        self.assertTrue(candidate.economic_candidate_accepted)
        self.assertFalse(candidate.p11_unlocked)
        self.assertFalse(candidate.live_authorized)

    def test_fail_requires_new_research_and_keeps_p11_locked(self):
        failed = replace(
            self.result,
            disposition="FAIL",
            continue_forward_observation=False,
            research_restart_required=True,
            economic_candidate_accepted=False,
            p11_consideration_allowed=False,
        )
        self.assertTrue(failed.research_restart_required)
        self.assertFalse(failed.p11_unlocked)
        self.assertFalse(failed.live_authorized)

    def test_result_rejects_illegal_p11_unlock(self):
        with self.assertRaises(P10AuditError):
            replace(self.result, p11_unlocked=True)

    def test_result_rejects_live_authorization(self):
        with self.assertRaises(P10AuditError):
            replace(self.result, live_authorized=True)

    def test_result_rejects_wrong_frozen_digest(self):
        with self.assertRaises(P10AuditError):
            replace(self.result, candidate_sha256="a" * 64)

    def test_source_safety_recomputes_true(self):
        self.assertTrue(_audit_source_safety())


if __name__ == "__main__":
    unittest.main()
