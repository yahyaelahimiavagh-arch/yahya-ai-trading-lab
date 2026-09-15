import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check, main
from yatl.execution import (
    ExecutionIntentJournal,
    LocalOrderError,
    LocalOrderEventType,
    LocalOrderReason,
    LocalOrderStatus,
    LocalOrderTransitionError,
    LocalPaperOrderEvent,
    LocalPaperOrderStore,
    apply_local_order_event,
    build_local_order_event,
)


START = 1_700_000_000_000


class LocalPaperOrderStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "execution.sqlite3"
        self.decision = _paper_execution_contract_runtime_check()[2]
        with ExecutionIntentJournal(self.path) as journal:
            self.intent = journal.record(self.decision)

    def tearDown(self):
        self.temporary.cleanup()

    def _create(self, store):
        event = build_local_order_event(
            self.intent, 0, START, LocalOrderEventType.CREATE,
        )
        return store.apply(event)

    def _activate(self, store, previous):
        event = build_local_order_event(
            self.intent, 1, START + 1, LocalOrderEventType.ACTIVATE, previous,
        )
        return store.apply(event)

    def _cancel(self, store, previous):
        event = build_local_order_event(
            self.intent, 2, START + 2, LocalOrderEventType.CANCEL, previous,
        )
        return store.apply(event)

    def test_exact_local_transition_table_and_immutable_reasons(self):
        with LocalPaperOrderStore(self.path) as store:
            created = self._create(store)
            active = self._activate(store, created.current)
            cancelled = self._cancel(store, active.current)
            self.assertEqual(created.current.status, LocalOrderStatus.PENDING_LOCAL)
            self.assertEqual(
                created.current.reason,
                LocalOrderReason.ACCEPTED_INTENT_RECORDED,
            )
            self.assertEqual(active.current.status, LocalOrderStatus.ACTIVE_LOCAL)
            self.assertEqual(
                active.current.reason,
                LocalOrderReason.LOCAL_ACTIVATION_CONFIRMED,
            )
            self.assertEqual(
                cancelled.current.status,
                LocalOrderStatus.CANCELLED_LOCAL,
            )
            self.assertEqual(
                cancelled.current.reason,
                LocalOrderReason.LOCAL_CANCELLATION_CONFIRMED,
            )

    def test_events_and_states_are_deterministic_hash_chains(self):
        create = build_local_order_event(
            self.intent, 0, START, LocalOrderEventType.CREATE,
        )
        first = apply_local_order_event(self.intent, None, create)
        replay = apply_local_order_event(self.intent, None, create)
        activate = build_local_order_event(
            self.intent, 1, START + 1, LocalOrderEventType.ACTIVATE, first.current,
        )
        second = apply_local_order_event(self.intent, first.current, activate)
        self.assertEqual(first, replay)
        self.assertEqual(
            activate.previous_event_sha256,
            first.event.event_sha256,
        )
        self.assertEqual(
            second.current.previous_state_sha256,
            first.current.state_sha256,
        )
        self.assertNotEqual(first.current.state_sha256, second.current.state_sha256)

    def test_unrecorded_intent_cannot_create_durable_order(self):
        other = Path(self.temporary.name) / "empty.sqlite3"
        with ExecutionIntentJournal(other):
            pass
        event = build_local_order_event(
            self.intent, 0, START, LocalOrderEventType.CREATE,
        )
        with LocalPaperOrderStore(other) as store:
            with self.assertRaises(LocalOrderTransitionError):
                store.apply(event)
            self.assertEqual(store.count(), 0)

    def test_lifecycle_cannot_start_with_activation_or_cancel(self):
        with LocalPaperOrderStore(self.path) as store:
            for event_type in (
                LocalOrderEventType.ACTIVATE,
                LocalOrderEventType.CANCEL,
            ):
                event = build_local_order_event(
                    self.intent, 0, START, event_type,
                )
                with self.subTest(event_type=event_type), self.assertRaises(
                    LocalOrderTransitionError
                ):
                    store.apply(event)
            self.assertEqual(store.count(), 0)

    def test_duplicate_and_skipped_sequences_fail_without_mutation(self):
        with LocalPaperOrderStore(self.path) as store:
            created = self._create(store)
            duplicate = created.event
            skipped = build_local_order_event(
                self.intent,
                2,
                START + 2,
                LocalOrderEventType.ACTIVATE,
                created.current,
            )
            for event in (duplicate, skipped):
                with self.subTest(event=event.sequence), self.assertRaises(
                    LocalOrderTransitionError
                ):
                    store.apply(event)
            self.assertEqual(store.events(self.intent.authorization_sha256), (duplicate,))
            self.assertEqual(
                store.get_state(self.intent.authorization_sha256),
                created.current,
            )

    def test_stale_time_and_broken_event_chain_fail_without_mutation(self):
        with LocalPaperOrderStore(self.path) as store:
            created = self._create(store)
            stale = build_local_order_event(
                self.intent,
                1,
                START,
                LocalOrderEventType.ACTIVATE,
                created.current,
            )
            broken = LocalPaperOrderEvent(
                self.intent.authorization_sha256,
                self.intent.intent_sha256,
                1,
                START + 1,
                LocalOrderEventType.ACTIVATE,
                LocalOrderReason.LOCAL_ACTIVATION_CONFIRMED,
                "f" * 64,
            )
            for event in (stale, broken):
                with self.subTest(event=event.event_time_ms), self.assertRaises(
                    LocalOrderTransitionError
                ):
                    store.apply(event)
            self.assertEqual(store.get_state(self.intent.authorization_sha256), created.current)

    def test_terminal_cancelled_state_rejects_every_transition(self):
        with LocalPaperOrderStore(self.path) as store:
            created = self._create(store)
            active = self._activate(store, created.current)
            cancelled = self._cancel(store, active.current)
            for event_type in LocalOrderEventType:
                event = build_local_order_event(
                    self.intent,
                    3,
                    START + 3,
                    event_type,
                    cancelled.current,
                )
                with self.subTest(event_type=event_type), self.assertRaises(
                    LocalOrderTransitionError
                ):
                    store.apply(event)
            self.assertEqual(store.events(self.intent.authorization_sha256), (
                created.event, active.event, cancelled.event,
            ))

    def test_event_intent_identity_mismatch_fails_closed(self):
        event = LocalPaperOrderEvent(
            self.intent.authorization_sha256,
            "f" * 64,
            0,
            START,
            LocalOrderEventType.CREATE,
            LocalOrderReason.ACCEPTED_INTENT_RECORDED,
            None,
        )
        with LocalPaperOrderStore(self.path) as store:
            with self.assertRaises(LocalOrderTransitionError):
                store.apply(event)

    def test_event_reason_mismatch_and_invalid_fields_fail_closed(self):
        with self.assertRaises(LocalOrderError):
            LocalPaperOrderEvent(
                self.intent.authorization_sha256,
                self.intent.intent_sha256,
                0,
                START,
                LocalOrderEventType.CREATE,
                LocalOrderReason.LOCAL_ACTIVATION_CONFIRMED,
                None,
            )
        for invalid in (-1, True, "0"):
            with self.subTest(invalid=invalid), self.assertRaises(LocalOrderError):
                build_local_order_event(
                    self.intent, invalid, START, LocalOrderEventType.CREATE,
                )

    def test_state_write_failure_rolls_back_event_and_projection(self):
        event = build_local_order_event(
            self.intent, 0, START, LocalOrderEventType.CREATE,
        )
        with LocalPaperOrderStore(self.path) as store:
            with patch.object(
                store,
                "_write_state",
                side_effect=LocalOrderError("injected failure"),
            ):
                with self.assertRaises(LocalOrderError):
                    store.apply(event)
            self.assertEqual(store.count(), 0)
            self.assertEqual(
                store._connection.execute(
                    "SELECT COUNT(*) FROM local_paper_order_events"
                ).fetchone()[0],
                0,
            )

    def test_reopen_and_canonical_export_replay_complete_chain(self):
        with LocalPaperOrderStore(self.path) as store:
            created = self._create(store)
            active = self._activate(store, created.current)
            cancelled = self._cancel(store, active.current)
            exported = store.canonical_json()
        with LocalPaperOrderStore(self.path) as reopened:
            self.assertEqual(reopened.schema_version(), 1)
            self.assertEqual(reopened.count(), 1)
            self.assertEqual(reopened.canonical_json(), exported)
            self.assertEqual(
                reopened.get_state(self.intent.authorization_sha256),
                cancelled.current,
            )
        payload = json.loads(exported)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(len(payload["orders"][0]["events"]), 3)
        self.assertNotIn(str(self.path), exported)

    def test_tampered_event_or_projection_fails_replay(self):
        with LocalPaperOrderStore(self.path) as store:
            self._create(store)
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET event_time_ms = ?",
                (START + 99,),
            )
        connection.close()
        with LocalPaperOrderStore(self.path) as store:
            with self.assertRaises(LocalOrderError):
                store.get_state(self.intent.authorization_sha256)
            with self.assertRaises(LocalOrderError):
                store.canonical_json()

    def test_newer_schema_and_uninitialized_database_fail_closed(self):
        newer = Path(self.temporary.name) / "newer.sqlite3"
        with ExecutionIntentJournal(newer):
            pass
        connection = sqlite3.connect(newer)
        with connection:
            connection.execute(
                "CREATE TABLE order_schema_migrations (version INTEGER PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO order_schema_migrations(version) VALUES (2)"
            )
        connection.close()
        with self.assertRaises(LocalOrderError):
            LocalPaperOrderStore(newer)
        missing = Path(self.temporary.name) / "missing.sqlite3"
        missing.touch()
        with self.assertRaises(LocalOrderError):
            LocalPaperOrderStore(missing)

    @patch("sys.argv", ["yatl", "paper-order-state-check"])
    def test_cli_reports_safe_deterministic_lifecycle(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P5 local Paper order state machine", text)
        self.assertIn("PENDING_LOCAL/ACTIVE_LOCAL/CANCELLED_LOCAL", text)
        self.assertIn("events=3", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
