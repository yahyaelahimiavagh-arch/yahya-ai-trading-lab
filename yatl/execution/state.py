"""Durable local-only Paper order lifecycle with hash-chained events."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .journal import ExecutionJournalError, INTENT_COLUMNS, LocalPaperIntentRecord


ORDER_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class LocalOrderError(Exception):
    """A local Paper order record or operation is unsafe or inconsistent."""


class LocalOrderTransitionError(LocalOrderError):
    """A local Paper order transition is impossible or out of order."""


class LocalOrderEventType(str, Enum):
    CREATE = "CREATE"
    ACTIVATE = "ACTIVATE"
    CANCEL = "CANCEL"


class LocalOrderStatus(str, Enum):
    PENDING_LOCAL = "PENDING_LOCAL"
    ACTIVE_LOCAL = "ACTIVE_LOCAL"
    CANCELLED_LOCAL = "CANCELLED_LOCAL"


class LocalOrderReason(str, Enum):
    ACCEPTED_INTENT_RECORDED = "ACCEPTED_INTENT_RECORDED"
    LOCAL_ACTIVATION_CONFIRMED = "LOCAL_ACTIVATION_CONFIRMED"
    LOCAL_CANCELLATION_CONFIRMED = "LOCAL_CANCELLATION_CONFIRMED"


_EVENT_REASONS = {
    LocalOrderEventType.CREATE: LocalOrderReason.ACCEPTED_INTENT_RECORDED,
    LocalOrderEventType.ACTIVATE: LocalOrderReason.LOCAL_ACTIVATION_CONFIRMED,
    LocalOrderEventType.CANCEL: LocalOrderReason.LOCAL_CANCELLATION_CONFIRMED,
}
_EVENT_STATUSES = {
    LocalOrderEventType.CREATE: LocalOrderStatus.PENDING_LOCAL,
    LocalOrderEventType.ACTIVATE: LocalOrderStatus.ACTIVE_LOCAL,
    LocalOrderEventType.CANCEL: LocalOrderStatus.CANCELLED_LOCAL,
}
_STATE_REASONS = {
    LocalOrderStatus.PENDING_LOCAL: LocalOrderReason.ACCEPTED_INTENT_RECORDED,
    LocalOrderStatus.ACTIVE_LOCAL: LocalOrderReason.LOCAL_ACTIVATION_CONFIRMED,
    LocalOrderStatus.CANCELLED_LOCAL: LocalOrderReason.LOCAL_CANCELLATION_CONFIRMED,
}


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_digest(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _validate_intent(intent):
    if not isinstance(intent, LocalPaperIntentRecord):
        raise LocalOrderError("A canonical local Paper intent is required")
    try:
        reconstructed = LocalPaperIntentRecord(
            *(getattr(intent, name) for name in INTENT_COLUMNS)
        )
    except (AttributeError, ExecutionJournalError, TypeError, ValueError):
        raise LocalOrderError("Local Paper intent failed reconstruction") from None
    if reconstructed != intent:
        raise LocalOrderError("Local Paper intent identity changed")


@dataclass(frozen=True, slots=True)
class LocalPaperOrderEvent:
    """One explicit local lifecycle event; it has no venue transport semantics."""

    authorization_sha256: str
    intent_sha256: str
    sequence: int
    event_time_ms: int
    event_type: LocalOrderEventType
    reason: LocalOrderReason
    previous_event_sha256: str | None

    def __post_init__(self):
        if not _valid_digest(self.authorization_sha256) or not _valid_digest(
            self.intent_sha256
        ):
            raise LocalOrderError("Local order identity digest is invalid")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise LocalOrderError("Local order event sequence is invalid")
        if type(self.event_time_ms) is not int or self.event_time_ms < 0:
            raise LocalOrderError("Local order event time is invalid")
        if not isinstance(self.event_type, LocalOrderEventType) or not isinstance(
            self.reason, LocalOrderReason
        ):
            raise LocalOrderError("Local order event identity is invalid")
        if self.reason is not _EVENT_REASONS[self.event_type]:
            raise LocalOrderError("Local order event type and reason disagree")
        if self.sequence == 0:
            if self.previous_event_sha256 is not None:
                raise LocalOrderError("Initial local order event has a predecessor")
        elif not _valid_digest(self.previous_event_sha256):
            raise LocalOrderError("Local order event is missing predecessor evidence")

    def _material(self):
        return {
            "schema_version": 1,
            "authorization_sha256": self.authorization_sha256,
            "intent_sha256": self.intent_sha256,
            "sequence": self.sequence,
            "event_time_ms": self.event_time_ms,
            "event_type": self.event_type.value,
            "reason": self.reason.value,
            "previous_event_sha256": self.previous_event_sha256,
        }

    def as_record(self):
        return {**self._material(), "event_sha256": self.event_sha256}

    @property
    def event_sha256(self):
        return _digest(self._material())


@dataclass(frozen=True, slots=True)
class LocalPaperOrderState:
    """Current durable local Paper order projection."""

    authorization_sha256: str
    intent_sha256: str
    sequence: int
    updated_time_ms: int
    status: LocalOrderStatus
    reason: LocalOrderReason
    previous_state_sha256: str | None
    event_sha256: str

    def __post_init__(self):
        if not _valid_digest(self.authorization_sha256) or not _valid_digest(
            self.intent_sha256
        ):
            raise LocalOrderError("Local order state identity digest is invalid")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise LocalOrderError("Local order state sequence is invalid")
        if type(self.updated_time_ms) is not int or self.updated_time_ms < 0:
            raise LocalOrderError("Local order state time is invalid")
        if not isinstance(self.status, LocalOrderStatus) or not isinstance(
            self.reason, LocalOrderReason
        ):
            raise LocalOrderError("Local order state identity is invalid")
        if self.reason is not _STATE_REASONS[self.status]:
            raise LocalOrderError("Local order status and reason disagree")
        if self.sequence == 0:
            if self.previous_state_sha256 is not None:
                raise LocalOrderError("Initial local order state has a predecessor")
        elif not _valid_digest(self.previous_state_sha256):
            raise LocalOrderError("Local order state is missing predecessor evidence")
        if not _valid_digest(self.event_sha256):
            raise LocalOrderError("Local order state event digest is invalid")

    def _material(self):
        return {
            "schema_version": 1,
            "authorization_sha256": self.authorization_sha256,
            "intent_sha256": self.intent_sha256,
            "sequence": self.sequence,
            "updated_time_ms": self.updated_time_ms,
            "status": self.status.value,
            "reason": self.reason.value,
            "previous_state_sha256": self.previous_state_sha256,
            "event_sha256": self.event_sha256,
        }

    def as_record(self):
        return {**self._material(), "state_sha256": self.state_sha256}

    @property
    def state_sha256(self):
        return _digest(self._material())


def _next_state(intent, previous, event):
    _validate_intent(intent)
    if not isinstance(event, LocalPaperOrderEvent):
        raise LocalOrderTransitionError("A canonical local order event is required")
    if (
        event.authorization_sha256 != intent.authorization_sha256
        or event.intent_sha256 != intent.intent_sha256
    ):
        raise LocalOrderTransitionError("Local order event and intent disagree")
    if previous is None:
        if event.sequence != 0 or event.event_type is not LocalOrderEventType.CREATE:
            raise LocalOrderTransitionError(
                "Local order lifecycle must begin with sequence-zero CREATE"
            )
        previous_state_sha256 = None
    else:
        if not isinstance(previous, LocalPaperOrderState):
            raise LocalOrderTransitionError("Previous local order state is invalid")
        try:
            reconstructed = LocalPaperOrderState(
                previous.authorization_sha256,
                previous.intent_sha256,
                previous.sequence,
                previous.updated_time_ms,
                previous.status,
                previous.reason,
                previous.previous_state_sha256,
                previous.event_sha256,
            )
        except (LocalOrderError, TypeError, ValueError):
            raise LocalOrderTransitionError(
                "Previous local order state failed reconstruction"
            ) from None
        if reconstructed != previous:
            raise LocalOrderTransitionError("Previous local order state changed")
        if (
            previous.authorization_sha256 != intent.authorization_sha256
            or previous.intent_sha256 != intent.intent_sha256
        ):
            raise LocalOrderTransitionError("Local order state and intent disagree")
        if event.sequence != previous.sequence + 1:
            raise LocalOrderTransitionError(
                "Local order event sequence is duplicate, skipped or out of order"
            )
        if event.event_time_ms <= previous.updated_time_ms:
            raise LocalOrderTransitionError("Local order event time is stale")
        if event.previous_event_sha256 != previous.event_sha256:
            raise LocalOrderTransitionError("Local order event chain is broken")
        allowed = {
            (LocalOrderStatus.PENDING_LOCAL, LocalOrderEventType.ACTIVATE),
            (LocalOrderStatus.ACTIVE_LOCAL, LocalOrderEventType.CANCEL),
        }
        if (previous.status, event.event_type) not in allowed:
            raise LocalOrderTransitionError("Local order transition is impossible")
        previous_state_sha256 = previous.state_sha256
    return LocalPaperOrderState(
        event.authorization_sha256,
        event.intent_sha256,
        event.sequence,
        event.event_time_ms,
        _EVENT_STATUSES[event.event_type],
        event.reason,
        previous_state_sha256,
        event.event_sha256,
    )


@dataclass(frozen=True, slots=True)
class LocalPaperOrderTransition:
    """Tamper-evident proof of one deterministic local lifecycle transition."""

    intent: LocalPaperIntentRecord
    previous: LocalPaperOrderState | None
    event: LocalPaperOrderEvent
    current: LocalPaperOrderState

    def __post_init__(self):
        if self.current != _next_state(self.intent, self.previous, self.event):
            raise LocalOrderTransitionError(
                "Current local order state does not match transition"
            )


def apply_local_order_event(intent, previous, event):
    """Apply one local-only lifecycle event without external execution."""
    current = _next_state(intent, previous, event)
    return LocalPaperOrderTransition(intent, previous, event, current)


def build_local_order_event(intent, sequence, event_time_ms, event_type, previous=None):
    """Build an event with the frozen reason and predecessor identity."""
    _validate_intent(intent)
    if not isinstance(event_type, LocalOrderEventType):
        raise LocalOrderError("Local order event type is invalid")
    if previous is not None and not isinstance(previous, LocalPaperOrderState):
        raise LocalOrderError("Previous local order state is invalid")
    return LocalPaperOrderEvent(
        intent.authorization_sha256,
        intent.intent_sha256,
        sequence,
        event_time_ms,
        event_type,
        _EVENT_REASONS[event_type],
        None if previous is None else previous.event_sha256,
    )


EVENT_COLUMNS = (
    "authorization_sha256",
    "intent_sha256",
    "sequence",
    "event_time_ms",
    "event_type",
    "reason",
    "previous_event_sha256",
    "event_sha256",
)
STATE_COLUMNS = (
    "authorization_sha256",
    "intent_sha256",
    "sequence",
    "updated_time_ms",
    "status",
    "reason",
    "previous_state_sha256",
    "event_sha256",
    "state_sha256",
)


class LocalPaperOrderStore:
    """Atomic durable event log and current projection for local Paper orders."""

    def __init__(self, path):
        if not isinstance(path, (str, Path)) or not str(path) or path == ":memory:":
            raise LocalOrderError("A persistent local order store path is required")
        target = Path(path)
        if not target.is_file():
            raise LocalOrderError("An initialized execution journal is required")
        self._connection = None
        try:
            self._connection = sqlite3.connect(str(target), timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._migrate()
        except LocalOrderError:
            if self._connection is not None:
                self._connection.close()
            raise
        except sqlite3.Error:
            if self._connection is not None:
                self._connection.close()
            raise LocalOrderError("Cannot open or migrate local order state") from None

    def _migrate(self):
        base = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'local_paper_intents'"
        ).fetchone()
        if base is None:
            raise LocalOrderError("Execution journal intent schema is missing")
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS order_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM order_schema_migrations"
            ).fetchone()
            current = row["version"]
            if current > ORDER_SCHEMA_VERSION:
                raise LocalOrderError(
                    "Local order schema is newer than this application"
                )
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE local_paper_order_events (
                        authorization_sha256 TEXT NOT NULL,
                        intent_sha256 TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_time_ms INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        previous_event_sha256 TEXT,
                        event_sha256 TEXT NOT NULL UNIQUE,
                        PRIMARY KEY (authorization_sha256, sequence),
                        FOREIGN KEY (authorization_sha256)
                            REFERENCES local_paper_intents(authorization_sha256)
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE local_paper_order_states (
                        authorization_sha256 TEXT PRIMARY KEY,
                        intent_sha256 TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        updated_time_ms INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        previous_state_sha256 TEXT,
                        event_sha256 TEXT NOT NULL,
                        state_sha256 TEXT NOT NULL UNIQUE,
                        FOREIGN KEY (authorization_sha256)
                            REFERENCES local_paper_intents(authorization_sha256)
                    )
                    """
                )
                self._connection.execute(
                    "INSERT INTO order_schema_migrations(version) VALUES (?)",
                    (ORDER_SCHEMA_VERSION,),
                )

    def _get_intent(self, authorization_sha256):
        columns = ", ".join(INTENT_COLUMNS)
        row = self._connection.execute(
            f"SELECT {columns} FROM local_paper_intents "
            "WHERE authorization_sha256 = ?",
            (authorization_sha256,),
        ).fetchone()
        if row is None:
            raise LocalOrderTransitionError(
                "Local order event has no recorded accepted intent"
            )
        try:
            return LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS))
        except (ExecutionJournalError, TypeError, ValueError):
            raise LocalOrderError("Stored intent failed local order validation") from None

    @staticmethod
    def _event_from_row(row):
        try:
            event = LocalPaperOrderEvent(
                row["authorization_sha256"],
                row["intent_sha256"],
                row["sequence"],
                row["event_time_ms"],
                LocalOrderEventType(row["event_type"]),
                LocalOrderReason(row["reason"]),
                row["previous_event_sha256"],
            )
        except (KeyError, LocalOrderError, TypeError, ValueError):
            raise LocalOrderError("Stored local order event is invalid") from None
        if event.event_sha256 != row["event_sha256"]:
            raise LocalOrderError("Stored local order event digest changed")
        return event

    @staticmethod
    def _state_from_row(row):
        if row is None:
            return None
        try:
            state = LocalPaperOrderState(
                row["authorization_sha256"],
                row["intent_sha256"],
                row["sequence"],
                row["updated_time_ms"],
                LocalOrderStatus(row["status"]),
                LocalOrderReason(row["reason"]),
                row["previous_state_sha256"],
                row["event_sha256"],
            )
        except (KeyError, LocalOrderError, TypeError, ValueError):
            raise LocalOrderError("Stored local order state is invalid") from None
        if state.state_sha256 != row["state_sha256"]:
            raise LocalOrderError("Stored local order state digest changed")
        return state

    def _select_state(self, authorization_sha256):
        columns = ", ".join(STATE_COLUMNS)
        return self._connection.execute(
            f"SELECT {columns} FROM local_paper_order_states "
            "WHERE authorization_sha256 = ?",
            (authorization_sha256,),
        ).fetchone()

    def _insert_event(self, event):
        columns = ", ".join(EVENT_COLUMNS)
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        values = (
            event.authorization_sha256,
            event.intent_sha256,
            event.sequence,
            event.event_time_ms,
            event.event_type.value,
            event.reason.value,
            event.previous_event_sha256,
            event.event_sha256,
        )
        self._connection.execute(
            f"INSERT INTO local_paper_order_events ({columns}) "
            f"VALUES ({placeholders})",
            values,
        )

    def _write_state(self, previous, current):
        values = (
            current.authorization_sha256,
            current.intent_sha256,
            current.sequence,
            current.updated_time_ms,
            current.status.value,
            current.reason.value,
            current.previous_state_sha256,
            current.event_sha256,
            current.state_sha256,
        )
        if previous is None:
            columns = ", ".join(STATE_COLUMNS)
            placeholders = ", ".join("?" for _ in STATE_COLUMNS)
            self._connection.execute(
                f"INSERT INTO local_paper_order_states ({columns}) "
                f"VALUES ({placeholders})",
                values,
            )
        else:
            assignments = ", ".join(f"{name} = ?" for name in STATE_COLUMNS[1:])
            self._connection.execute(
                f"UPDATE local_paper_order_states SET {assignments} "
                "WHERE authorization_sha256 = ? AND state_sha256 = ?",
                values[1:] + (
                    current.authorization_sha256,
                    previous.state_sha256,
                ),
            )
            if self._connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise LocalOrderTransitionError("Local order state changed concurrently")

    def apply(self, event):
        if not isinstance(event, LocalPaperOrderEvent):
            raise LocalOrderTransitionError("A canonical local order event is required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            intent = self._get_intent(event.authorization_sha256)
            previous = self._state_from_row(
                self._select_state(event.authorization_sha256)
            )
            transition = apply_local_order_event(intent, previous, event)
            self._insert_event(event)
            self._write_state(previous, transition.current)
            self._connection.commit()
            return transition
        except LocalOrderError:
            self._connection.rollback()
            raise
        except sqlite3.IntegrityError:
            self._connection.rollback()
            raise LocalOrderTransitionError(
                "Local order event is duplicate or conflicts with durable state"
            ) from None
        except sqlite3.Error:
            self._connection.rollback()
            raise LocalOrderError(
                "Cannot transactionally apply the local order event"
            ) from None

    def _load_order(self, authorization_sha256):
        intent = self._get_intent(authorization_sha256)
        columns = ", ".join(EVENT_COLUMNS)
        rows = self._connection.execute(
            f"SELECT {columns} FROM local_paper_order_events "
            "WHERE authorization_sha256 = ? ORDER BY sequence",
            (authorization_sha256,),
        ).fetchall()
        previous = None
        events = []
        for row in rows:
            event = self._event_from_row(row)
            previous = apply_local_order_event(intent, previous, event).current
            events.append(event)
        stored = self._state_from_row(self._select_state(authorization_sha256))
        if previous != stored:
            raise LocalOrderError("Stored local order projection differs from replay")
        return tuple(events), stored

    def get_state(self, authorization_sha256):
        if not _valid_digest(authorization_sha256):
            raise LocalOrderError("Authorization digest is invalid")
        try:
            return self._load_order(authorization_sha256)[1]
        except LocalOrderError:
            raise
        except sqlite3.Error:
            raise LocalOrderError("Cannot read local order state") from None

    def events(self, authorization_sha256):
        if not _valid_digest(authorization_sha256):
            raise LocalOrderError("Authorization digest is invalid")
        try:
            return self._load_order(authorization_sha256)[0]
        except LocalOrderError:
            raise
        except sqlite3.Error:
            raise LocalOrderError("Cannot read local order events") from None

    def count(self):
        try:
            return self._connection.execute(
                "SELECT COUNT(*) FROM local_paper_order_states"
            ).fetchone()[0]
        except sqlite3.Error:
            raise LocalOrderError("Cannot count local orders") from None

    def canonical_json(self):
        try:
            rows = self._connection.execute(
                "SELECT authorization_sha256 FROM local_paper_order_states "
                "ORDER BY authorization_sha256"
            ).fetchall()
            orders = []
            for row in rows:
                events, state = self._load_order(row["authorization_sha256"])
                orders.append({
                    "authorization_sha256": row["authorization_sha256"],
                    "events": [event.as_record() for event in events],
                    "state": state.as_record(),
                })
            return _canonical_json({
                "schema_version": ORDER_SCHEMA_VERSION,
                "orders": orders,
            }) + "\n"
        except LocalOrderError:
            raise
        except sqlite3.Error:
            raise LocalOrderError("Cannot export local order evidence") from None

    def schema_version(self):
        try:
            return self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM order_schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise LocalOrderError("Cannot read local order schema version") from None

    def close(self):
        try:
            self._connection.close()
        except sqlite3.Error:
            raise LocalOrderError("Cannot close local order state") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
