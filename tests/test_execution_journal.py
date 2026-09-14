import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check, main
from yatl.execution import (
    ExecutionIntentJournal,
    ExecutionJournalError,
    IntentConflict,
    LocalPaperIntentRecord,
    RecoveryReadiness,
    RecoveryReason,
    RecoveryStatus,
    assess_local_paper_authorization,
)


def _accepted_decision(character="a"):
    _, _, decision, _ = _paper_execution_contract_runtime_check()
    if character == "a":
        return decision
    readiness = RecoveryReadiness(
        RecoveryStatus.READY,
        RecoveryReason.RECONCILIATION_PASSED,
        character * 64,
    )
    return assess_local_paper_authorization(
        decision.authorization,
        readiness,
    )


class ExecutionIntentJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "intents.sqlite3"

    def tearDown(self):
        self.temporary.cleanup()

    def test_accepted_intent_is_canonical_and_bound_to_authorization(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path) as journal:
            record = journal.record(decision)
            self.assertEqual(record.authorization_sha256, decision.authorization_sha256)
            self.assertEqual(record.effect_sha256, decision.authorization_sha256)
            self.assertEqual(record.decision_sha256, decision.decision_sha256)
            self.assertEqual(record.approved_quantity, decision.approved_quantity)
            self.assertEqual(journal.count(), 1)

    def test_duplicate_delivery_returns_existing_without_second_effect(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path) as journal:
            first = journal.record(decision)
            second = journal.record(decision)
            self.assertEqual(first, second)
            self.assertIsNot(first, second)
            self.assertEqual(journal.count(), 1)

    def test_same_authorization_with_changed_evidence_conflicts_atomically(self):
        first = _accepted_decision("a")
        changed = _accepted_decision("b")
        self.assertEqual(first.authorization_sha256, changed.authorization_sha256)
        self.assertNotEqual(first.decision_sha256, changed.decision_sha256)
        with ExecutionIntentJournal(self.path) as journal:
            original = journal.record(first)
            with self.assertRaises(IntentConflict):
                journal.record(changed)
            self.assertEqual(journal.count(), 1)
            self.assertEqual(journal.get(first.authorization_sha256), original)

    def test_insert_failure_rolls_back_complete_transaction(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path) as journal:
            original_insert = journal._insert

            def insert_then_fail(record):
                original_insert(record)
                raise ExecutionJournalError("injected failure")

            with patch.object(journal, "_insert", side_effect=insert_then_fail):
                with self.assertRaises(ExecutionJournalError):
                    journal.record(decision)
            self.assertEqual(journal.count(), 0)
            self.assertIsNone(journal.get(decision.authorization_sha256))

    def test_reopen_preserves_verified_record_and_schema(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path) as journal:
            expected = journal.record(decision)
        with ExecutionIntentJournal(self.path) as reopened:
            self.assertEqual(reopened.schema_version(), 1)
            self.assertEqual(reopened.count(), 1)
            self.assertEqual(reopened.get(decision.authorization_sha256), expected)

    def test_canonical_export_is_sorted_stable_and_path_free(self):
        first = _accepted_decision("a")
        second = _paper_execution_contract_runtime_check()[3]
        with ExecutionIntentJournal(self.path) as journal:
            journal.record(first)
            journal.record(second)
            exported = journal.canonical_json()
            self.assertEqual(exported, journal.canonical_json())
        payload = json.loads(exported)
        identities = [item["authorization_sha256"] for item in payload["intents"]]
        self.assertEqual(identities, sorted(identities))
        self.assertEqual(payload["schema_version"], 1)
        self.assertNotIn(str(self.path), exported)
        self.assertTrue(exported.endswith("\n"))

    def test_concurrent_duplicate_attempts_commit_one_effect(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path):
            pass
        barrier = threading.Barrier(4)
        results = []
        errors = []
        lock = threading.Lock()

        def attempt():
            try:
                barrier.wait()
                with ExecutionIntentJournal(self.path) as journal:
                    result = journal.record(decision)
                with lock:
                    results.append(result)
            except Exception as exc:  # captured and asserted in the main thread
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=attempt) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(errors)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result == results[0] for result in results))
        with ExecutionIntentJournal(self.path) as journal:
            self.assertEqual(journal.count(), 1)

    def test_blocked_and_nondecision_inputs_fail_without_writes(self):
        startup, candidate, _, _ = _paper_execution_contract_runtime_check()
        with ExecutionIntentJournal(self.path) as journal:
            for invalid in (startup, candidate, object(), None):
                with self.subTest(invalid=type(invalid)), self.assertRaises(
                    ExecutionJournalError
                ):
                    journal.record(invalid)
            self.assertEqual(journal.count(), 0)

    def test_tampered_row_fails_closed_on_read_and_export(self):
        decision = _accepted_decision()
        with ExecutionIntentJournal(self.path) as journal:
            journal.record(decision)
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_intents SET approved_quantity = ?",
                ("999",),
            )
        connection.close()
        with ExecutionIntentJournal(self.path) as journal:
            with self.assertRaises(ExecutionJournalError):
                journal.get(decision.authorization_sha256)
            with self.assertRaises(ExecutionJournalError):
                journal.canonical_json()

    def test_newer_schema_and_memory_database_fail_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "CREATE TABLE execution_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO execution_schema_migrations(version) VALUES (2)"
            )
        connection.close()
        with self.assertRaises(ExecutionJournalError):
            ExecutionIntentJournal(self.path)
        with self.assertRaises(ExecutionJournalError):
            ExecutionIntentJournal(":memory:")

    def test_record_constructor_detects_material_tampering(self):
        record = LocalPaperIntentRecord.from_decision(_accepted_decision())
        values = record.as_record()
        values["approved_quantity"] = "999"
        with self.assertRaises(ExecutionJournalError):
            LocalPaperIntentRecord(
                *(values[name] for name in (
                    "authorization_sha256",
                    "effect_sha256",
                    "decision_sha256",
                    "readiness_sha256",
                    "action",
                    "approved_quantity",
                    "policy_id",
                    "intent_sha256",
                ))
            )

    @patch("sys.argv", ["yatl", "paper-execution-journal-check"])
    def test_cli_reports_transactional_safe_replay(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P5 transactional local Paper intent journal", text)
        self.assertIn("effects=1 replay_equal=true reopen_equal=true", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
