import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check
from yatl.backtest import BacktestSpec
from yatl.execution import (
    ExecutionIntentJournal,
    LocalOrderEventType,
    LocalPaperOrderStore,
    LocalPaperPortfolioStore,
    RecoveryCode,
    RecoverySnapshotError,
    build_local_order_event,
    confirm_pending_snapshot,
    create_recovery_snapshot,
    recover_startup,
)


HOUR = 3_600_000


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class SnapshotRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.entry_decision, _ = _paper_execution_contract_runtime_check()
        cls.entry_time = (
            cls.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.path = root / "execution.sqlite3"
        self.snapshot_path = root / "execution.snapshot.json"
        self.spec = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.entry_time + 2 * HOUR,
            initial_cash="10000",
            fee_bps="10",
            slippage_bps="5",
        )
        with ExecutionIntentJournal(self.path):
            pass
        with LocalPaperOrderStore(self.path):
            pass
        with LocalPaperPortfolioStore(self.path, self.spec):
            pass

    def tearDown(self):
        self.temporary.cleanup()

    def _active_order(self):
        with ExecutionIntentJournal(self.path) as journal:
            intent = journal.record(self.entry_decision)
        decision_time = (
            self.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )
        with LocalPaperOrderStore(self.path) as store:
            created = store.apply(build_local_order_event(
                intent,
                0,
                decision_time - 2,
                LocalOrderEventType.CREATE,
            )).current
            active = store.apply(build_local_order_event(
                intent,
                1,
                decision_time - 1,
                LocalOrderEventType.ACTIVATE,
                created,
            )).current
        return intent, active

    def _rewrite_snapshot(self, **changes):
        record = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        record.pop("snapshot_sha256")
        record.update(changes)
        record["snapshot_sha256"] = hashlib.sha256(
            _canonical(record).encode("utf-8")
        ).hexdigest()
        self.snapshot_path.write_text(_canonical(record) + "\n", encoding="utf-8")

    def test_snapshot_creation_replay_and_idempotency(self):
        first = create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        second = create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertEqual(first, second)
        self.assertTrue(report.ready)
        self.assertEqual(report.code, RecoveryCode.MATCH)
        self.assertEqual(report.snapshot_sha256, first.snapshot_sha256)
        self.assertEqual(report, recover_startup(self.path, self.snapshot_path, self.spec))

    def test_deleted_snapshot_rebuilds_from_authoritative_journal(self):
        original = create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        self.snapshot_path.unlink()
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertTrue(report.ready)
        self.assertEqual(report.code, RecoveryCode.JOURNAL_REBUILD_READY)
        rebuilt = create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        self.assertEqual(original.snapshot_sha256, rebuilt.snapshot_sha256)

    def test_corrupt_and_truncated_snapshot_fail_closed(self):
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        self.snapshot_path.write_text("{", encoding="utf-8")
        corrupt = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(corrupt.ready)
        self.assertEqual(corrupt.code, RecoveryCode.SNAPSHOT_CORRUPT)
        self.snapshot_path.write_text("", encoding="utf-8")
        truncated = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(truncated.ready)
        self.assertEqual(truncated.code, RecoveryCode.SNAPSHOT_CORRUPT)

    def test_noncanonical_snapshot_fails_closed(self):
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        record = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.snapshot_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.SNAPSHOT_CORRUPT)

    def test_policy_drift_fails_closed_even_with_valid_snapshot_digest(self):
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        self._rewrite_snapshot(policy_sha256="0" * 64)
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.POLICY_DRIFT)

    def test_spec_drift_fails_closed(self):
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        changed = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.entry_time + 3 * HOUR,
            initial_cash="10000",
            fee_bps="10",
            slippage_bps="5",
        )
        report = recover_startup(self.path, self.snapshot_path, changed)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.SPEC_DRIFT)

    def test_valid_order_tail_is_replayed_from_snapshot_prefix(self):
        intent, active = self._active_order()
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        with LocalPaperOrderStore(self.path) as store:
            store.apply(build_local_order_event(
                intent,
                2,
                active.updated_time_ms + 1,
                LocalOrderEventType.CANCEL,
                active,
            ))
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertTrue(report.ready)
        self.assertEqual(report.code, RecoveryCode.TAIL_REPLAYED)
        self.assertEqual(report.tail_order_events, 1)
        self.assertEqual(report.tail_intents, 0)
        self.assertEqual(report.tail_fills, 0)

    def test_corrupt_tail_enters_recovery_required(self):
        intent, active = self._active_order()
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        with LocalPaperOrderStore(self.path) as store:
            store.apply(build_local_order_event(
                intent,
                2,
                active.updated_time_ms + 1,
                LocalOrderEventType.CANCEL,
                active,
            ))
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET event_sha256 = ? "
                "WHERE authorization_sha256 = ? AND sequence = 2",
                ("0" * 64, intent.authorization_sha256),
            )
        connection.close()
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.JOURNAL_RECONCILIATION_FAILED)

    def test_prefix_rewrite_is_never_treated_as_tail(self):
        intent, _ = self._active_order()
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET event_sha256 = ? "
                "WHERE authorization_sha256 = ? AND sequence = 1",
                ("0" * 64, intent.authorization_sha256),
            )
        connection.close()
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.SNAPSHOT_PREFIX_MISMATCH)

    def test_ambiguous_pending_commit_requires_exact_manual_confirmation(self):
        create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        pending = Path(f"{self.snapshot_path}.pending")
        shutil.copyfile(self.snapshot_path, pending)
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.AMBIGUOUS_COMMIT)
        self.assertIsNotNone(report.manual_confirmation_sha256)
        with self.assertRaises(RecoverySnapshotError):
            confirm_pending_snapshot(self.snapshot_path, "0" * 64)
        confirmed = confirm_pending_snapshot(
            self.snapshot_path,
            report.manual_confirmation_sha256,
        )
        self.assertEqual(confirmed, report.manual_confirmation_sha256)
        self.assertFalse(pending.exists())
        self.assertEqual(
            recover_startup(self.path, self.snapshot_path, self.spec).code,
            RecoveryCode.MATCH,
        )

    def test_crash_before_replace_leaves_no_guessed_repair(self):
        with patch("yatl.execution.recovery.os.replace", side_effect=OSError("crash")):
            with self.assertRaises(RecoverySnapshotError):
                create_recovery_snapshot(self.path, self.snapshot_path, self.spec)
        self.assertFalse(self.snapshot_path.exists())
        self.assertTrue(Path(f"{self.snapshot_path}.pending").exists())
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.AMBIGUOUS_COMMIT)

    def test_unreconciled_source_without_snapshot_stays_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute("DROP TABLE local_paper_order_states")
        connection.close()
        report = recover_startup(self.path, self.snapshot_path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, RecoveryCode.JOURNAL_RECONCILIATION_FAILED)


if __name__ == "__main__":
    unittest.main()
