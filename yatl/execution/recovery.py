"""Versioned snapshot accelerators and explicit fail-closed recovery for P5."""

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from yatl.backtest import BacktestSpec

from .contracts import LocalPaperExecutionPolicy, RecoveryReadiness, RecoveryReason, RecoveryStatus
from .journal import INTENT_COLUMNS, LocalPaperIntentRecord
from .portfolio import _spec_record
from .reconcile import ReconciliationCode, reconcile_startup
from .state import STATE_COLUMNS, LocalOrderReason, LocalOrderStatus, LocalPaperOrderState


RECOVERY_SNAPSHOT_SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
INTENT_RECORD_KEYS = set(INTENT_COLUMNS) | {"schema_version"}


class RecoverySnapshotError(Exception):
    """Snapshot or recovery evidence is incomplete, corrupt, or ambiguous."""


class RecoveryCode(str, Enum):
    MATCH = "MATCH"
    TAIL_REPLAYED = "TAIL_REPLAYED"
    JOURNAL_REBUILD_READY = "JOURNAL_REBUILD_READY"
    SNAPSHOT_CORRUPT = "SNAPSHOT_CORRUPT"
    POLICY_DRIFT = "POLICY_DRIFT"
    SPEC_DRIFT = "SPEC_DRIFT"
    SNAPSHOT_PREFIX_MISMATCH = "SNAPSHOT_PREFIX_MISMATCH"
    JOURNAL_RECONCILIATION_FAILED = "JOURNAL_RECONCILIATION_FAILED"
    AMBIGUOUS_COMMIT = "AMBIGUOUS_COMMIT"
    STORAGE_ERROR = "STORAGE_ERROR"


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_digest(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _policy_record(policy):
    if not isinstance(policy, LocalPaperExecutionPolicy):
        raise RecoverySnapshotError("A frozen local Paper policy is required")
    return {
        name: getattr(policy, name)
        for name in policy.__dataclass_fields__
    }


def _policy_sha256(policy):
    return _digest({"schema_version": 1, "policy": _policy_record(policy)})


def _spec_sha256(spec):
    if not isinstance(spec, BacktestSpec):
        raise RecoverySnapshotError("An accepted P2 spec is required")
    return _digest(_spec_record(spec))


def _pending_path(path):
    return Path(f"{Path(path)}.pending")


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    """Canonical cache of a previously reconciled durable execution prefix."""

    policy_sha256: str
    spec_sha256: str
    reconciliation_sha256: str
    journal_sha256: str
    orders_sha256: str
    portfolio_sha256: str
    intent_records: tuple
    order_anchors: tuple
    fill_anchors: tuple
    order_event_count: int

    def __post_init__(self):
        if any(not _valid_digest(value) for value in (
            self.policy_sha256,
            self.spec_sha256,
            self.reconciliation_sha256,
            self.journal_sha256,
            self.orders_sha256,
            self.portfolio_sha256,
        )):
            raise RecoverySnapshotError("Snapshot digest is invalid")
        if type(self.intent_records) is not tuple or type(self.order_anchors) is not tuple:
            raise RecoverySnapshotError("Snapshot anchors are invalid")
        if type(self.fill_anchors) is not tuple or type(self.order_event_count) is not int:
            raise RecoverySnapshotError("Snapshot fill or event anchors are invalid")
        if self.order_event_count < 0:
            raise RecoverySnapshotError("Snapshot event count is invalid")
        authorizations = []
        for record in self.intent_records:
            if not isinstance(record, dict) or set(record) != INTENT_RECORD_KEYS:
                raise RecoverySnapshotError("Snapshot intent anchor is invalid")
            try:
                rebuilt = LocalPaperIntentRecord(*(record[name] for name in INTENT_COLUMNS))
            except Exception:
                raise RecoverySnapshotError("Snapshot intent anchor failed reconstruction") from None
            if rebuilt.as_record() != record:
                raise RecoverySnapshotError("Snapshot intent anchor changed")
            authorizations.append(record["authorization_sha256"])
        if authorizations != sorted(authorizations) or len(authorizations) != len(set(authorizations)):
            raise RecoverySnapshotError("Snapshot intent anchors are not canonical")

        order_authorizations = []
        for anchor in self.order_anchors:
            expected = {
                "authorization_sha256",
                "sequence",
                "event_sha256",
                "state_sha256",
                "state",
            }
            if not isinstance(anchor, dict) or set(anchor) != expected:
                raise RecoverySnapshotError("Snapshot order anchor is invalid")
            if (
                anchor["authorization_sha256"] not in authorizations
                or type(anchor["sequence"]) is not int
                or anchor["sequence"] < 0
                or not _valid_digest(anchor["event_sha256"])
                or not _valid_digest(anchor["state_sha256"])
                or not isinstance(anchor["state"], dict)
            ):
                raise RecoverySnapshotError("Snapshot order anchor fields are invalid")
            state_record = anchor["state"]
            try:
                state = LocalPaperOrderState(
                    state_record["authorization_sha256"],
                    state_record["intent_sha256"],
                    state_record["sequence"],
                    state_record["updated_time_ms"],
                    LocalOrderStatus(state_record["status"]),
                    LocalOrderReason(state_record["reason"]),
                    state_record["previous_state_sha256"],
                    state_record["event_sha256"],
                )
            except Exception:
                raise RecoverySnapshotError("Snapshot order state failed reconstruction") from None
            if (
                state.as_record() != state_record
                or state.authorization_sha256 != anchor["authorization_sha256"]
                or state.sequence != anchor["sequence"]
                or state.event_sha256 != anchor["event_sha256"]
                or state.state_sha256 != anchor["state_sha256"]
            ):
                raise RecoverySnapshotError("Snapshot order state changed")
            order_authorizations.append(anchor["authorization_sha256"])
        if (
            order_authorizations != sorted(order_authorizations)
            or order_authorizations != authorizations
        ):
            raise RecoverySnapshotError("Snapshot order coverage is invalid")

        expected_sequences = list(range(len(self.fill_anchors)))
        actual_sequences = []
        for anchor in self.fill_anchors:
            if (
                not isinstance(anchor, dict)
                or set(anchor) != {"sequence", "fill_event_sha256"}
                or type(anchor["sequence"]) is not int
                or not _valid_digest(anchor["fill_event_sha256"])
            ):
                raise RecoverySnapshotError("Snapshot fill anchor is invalid")
            actual_sequences.append(anchor["sequence"])
        if actual_sequences != expected_sequences:
            raise RecoverySnapshotError("Snapshot fill anchors are not contiguous")
        minimum_events = sum(anchor["sequence"] + 1 for anchor in self.order_anchors)
        if self.order_event_count != minimum_events:
            raise RecoverySnapshotError("Snapshot order event count disagrees with anchors")

    @property
    def intent_count(self):
        return len(self.intent_records)

    @property
    def order_count(self):
        return len(self.order_anchors)

    @property
    def fill_count(self):
        return len(self.fill_anchors)

    def _material(self):
        return {
            "schema_version": RECOVERY_SNAPSHOT_SCHEMA_VERSION,
            "policy_sha256": self.policy_sha256,
            "spec_sha256": self.spec_sha256,
            "reconciliation_sha256": self.reconciliation_sha256,
            "journal_sha256": self.journal_sha256,
            "orders_sha256": self.orders_sha256,
            "portfolio_sha256": self.portfolio_sha256,
            "intent_records": list(self.intent_records),
            "order_anchors": list(self.order_anchors),
            "fill_anchors": list(self.fill_anchors),
            "order_event_count": self.order_event_count,
        }

    @property
    def snapshot_sha256(self):
        return _digest(self._material())

    def as_record(self):
        return {**self._material(), "snapshot_sha256": self.snapshot_sha256}


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """Deterministic startup recovery result; failures never become executable."""

    ready: bool
    code: RecoveryCode
    reconciliation_sha256: str | None = None
    snapshot_sha256: str | None = None
    tail_intents: int = 0
    tail_order_events: int = 0
    tail_fills: int = 0
    manual_confirmation_sha256: str | None = None

    def __post_init__(self):
        if type(self.ready) is not bool or not isinstance(self.code, RecoveryCode):
            raise RecoverySnapshotError("Recovery report status is invalid")
        if any(type(value) is not int or value < 0 for value in (
            self.tail_intents,
            self.tail_order_events,
            self.tail_fills,
        )):
            raise RecoverySnapshotError("Recovery tail counts are invalid")
        for value in (
            self.reconciliation_sha256,
            self.snapshot_sha256,
            self.manual_confirmation_sha256,
        ):
            if value is not None and not _valid_digest(value):
                raise RecoverySnapshotError("Recovery report digest is invalid")
        if self.ready and self.reconciliation_sha256 is None:
            raise RecoverySnapshotError("Ready recovery report lacks reconciliation evidence")
        if self.code is RecoveryCode.AMBIGUOUS_COMMIT:
            if self.manual_confirmation_sha256 is None or self.ready:
                raise RecoverySnapshotError("Ambiguous recovery requires manual confirmation")
        elif self.manual_confirmation_sha256 is not None:
            raise RecoverySnapshotError("Unexpected manual confirmation evidence")

    def _material(self):
        return {
            "schema_version": 1,
            "status": "READY" if self.ready else "RECOVERY_REQUIRED",
            "code": self.code.value,
            "reconciliation_sha256": self.reconciliation_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "tail_intents": self.tail_intents,
            "tail_order_events": self.tail_order_events,
            "tail_fills": self.tail_fills,
            "manual_confirmation_sha256": self.manual_confirmation_sha256,
        }

    @property
    def recovery_sha256(self):
        return _digest(self._material())

    @property
    def readiness(self):
        if self.ready:
            return RecoveryReadiness(
                RecoveryStatus.READY,
                RecoveryReason.RECONCILIATION_PASSED,
                self.reconciliation_sha256,
            )
        return RecoveryReadiness(
            RecoveryStatus.RECOVERY_REQUIRED,
            RecoveryReason.RECONCILIATION_FAILED,
            self.recovery_sha256,
        )

    def as_record(self):
        return {**self._material(), "recovery_sha256": self.recovery_sha256}


def _read_limited(path):
    target = Path(path)
    try:
        if not target.is_file():
            raise FileNotFoundError
        size = target.stat().st_size
        if size <= 0 or size > MAX_SNAPSHOT_BYTES:
            raise RecoverySnapshotError("Snapshot size is invalid")
        return target.read_text(encoding="utf-8")
    except RecoverySnapshotError:
        raise
    except (OSError, UnicodeError):
        raise RecoverySnapshotError("Snapshot cannot be read safely") from None


def _snapshot_from_text(text):
    try:
        record = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise RecoverySnapshotError("Snapshot JSON is invalid") from None
    expected = {
        "schema_version",
        "policy_sha256",
        "spec_sha256",
        "reconciliation_sha256",
        "journal_sha256",
        "orders_sha256",
        "portfolio_sha256",
        "intent_records",
        "order_anchors",
        "fill_anchors",
        "order_event_count",
        "snapshot_sha256",
    }
    if not isinstance(record, dict) or set(record) != expected:
        raise RecoverySnapshotError("Snapshot schema is invalid")
    if record["schema_version"] != RECOVERY_SNAPSHOT_SCHEMA_VERSION:
        raise RecoverySnapshotError("Snapshot version is unsupported")
    supplied_digest = record.pop("snapshot_sha256")
    if not _valid_digest(supplied_digest) or _digest(record) != supplied_digest:
        raise RecoverySnapshotError("Snapshot digest verification failed")
    snapshot = RecoverySnapshot(
        record["policy_sha256"],
        record["spec_sha256"],
        record["reconciliation_sha256"],
        record["journal_sha256"],
        record["orders_sha256"],
        record["portfolio_sha256"],
        tuple(record["intent_records"]),
        tuple(record["order_anchors"]),
        tuple(record["fill_anchors"]),
        record["order_event_count"],
    )
    canonical = _canonical_json(snapshot.as_record()) + "\n"
    if text != canonical or snapshot.snapshot_sha256 != supplied_digest:
        raise RecoverySnapshotError("Snapshot is not canonical")
    return snapshot


def load_recovery_snapshot(path):
    return _snapshot_from_text(_read_limited(path))


def _build_snapshot(path, spec, policy):
    report = reconcile_startup(path, spec)
    if not report.ready or report.code is not ReconciliationCode.MATCH:
        raise RecoverySnapshotError("Authoritative execution state is not reconciled")
    connection = None
    try:
        connection = sqlite3.connect(str(Path(path)), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        columns = ", ".join(INTENT_COLUMNS)
        intent_rows = connection.execute(
            f"SELECT {columns} FROM local_paper_intents ORDER BY authorization_sha256"
        ).fetchall()
        intent_records = tuple(
            LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS)).as_record()
            for row in intent_rows
        )
        state_columns = ", ".join(STATE_COLUMNS)
        state_rows = connection.execute(
            f"SELECT {state_columns} FROM local_paper_order_states ORDER BY authorization_sha256"
        ).fetchall()
        order_anchors = []
        for row in state_rows:
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
            order_anchors.append({
                "authorization_sha256": state.authorization_sha256,
                "sequence": state.sequence,
                "event_sha256": state.event_sha256,
                "state_sha256": state.state_sha256,
                "state": state.as_record(),
            })
        fill_rows = connection.execute(
            "SELECT sequence, fill_event_sha256 FROM local_paper_fill_events ORDER BY sequence"
        ).fetchall()
        fill_anchors = tuple({
            "sequence": row["sequence"],
            "fill_event_sha256": row["fill_event_sha256"],
        } for row in fill_rows)
        event_count = connection.execute(
            "SELECT COUNT(*) FROM local_paper_order_events"
        ).fetchone()[0]
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        raise RecoverySnapshotError("Cannot build snapshot anchors") from None
    finally:
        if connection is not None:
            connection.close()
    return RecoverySnapshot(
        _policy_sha256(policy),
        _spec_sha256(spec),
        report.reconciliation_sha256,
        report.journal_sha256,
        report.orders_sha256,
        report.portfolio_sha256,
        intent_records,
        tuple(order_anchors),
        fill_anchors,
        event_count,
    )


def create_recovery_snapshot(path, snapshot_path, spec, policy=None):
    """Atomically persist a canonical accelerator for already reconciled source state."""
    if policy is None:
        policy = LocalPaperExecutionPolicy()
    snapshot = _build_snapshot(path, spec, policy)
    target = Path(snapshot_path)
    pending = _pending_path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise RecoverySnapshotError("Cannot prepare snapshot directory") from None
    if pending.exists():
        raise RecoverySnapshotError("Pending snapshot commit requires explicit confirmation")
    if target.exists():
        existing = load_recovery_snapshot(target)
        if existing == snapshot:
            return existing
        raise RecoverySnapshotError("Existing snapshot differs from current reconciled state")
    payload = _canonical_json(snapshot.as_record()) + "\n"
    try:
        with pending.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, target)
    except FileExistsError:
        raise RecoverySnapshotError("Pending snapshot commit already exists") from None
    except OSError:
        raise RecoverySnapshotError("Snapshot commit outcome is ambiguous") from None
    return snapshot


def _pending_confirmation(snapshot_path):
    target = Path(snapshot_path)
    pending = _pending_path(target)
    try:
        pending_bytes = pending.read_bytes()
        if len(pending_bytes) > MAX_SNAPSHOT_BYTES:
            raise RecoverySnapshotError("Pending snapshot evidence is invalid")
        final_sha256 = None
        if target.is_file():
            final_bytes = target.read_bytes()
            if len(final_bytes) > MAX_SNAPSHOT_BYTES:
                raise RecoverySnapshotError("Final snapshot evidence is invalid")
            final_sha256 = hashlib.sha256(final_bytes).hexdigest()
    except RecoverySnapshotError:
        raise
    except OSError:
        raise RecoverySnapshotError("Pending snapshot evidence cannot be read") from None
    material = {
        "schema_version": 1,
        "action": "DISCARD_PENDING_ONLY",
        "pending_sha256": hashlib.sha256(pending_bytes).hexdigest(),
        "final_sha256": final_sha256,
    }
    return _digest(material)


def confirm_pending_snapshot(snapshot_path, confirmation_sha256):
    """Explicitly discard only an incomplete accelerator commit, never source state."""
    if not _valid_digest(confirmation_sha256):
        raise RecoverySnapshotError("Manual confirmation digest is invalid")
    expected = _pending_confirmation(snapshot_path)
    if confirmation_sha256 != expected:
        raise RecoverySnapshotError("Manual confirmation evidence changed")
    pending = _pending_path(snapshot_path)
    try:
        pending.unlink()
    except OSError:
        raise RecoverySnapshotError("Cannot discard pending snapshot") from None
    return expected


def _validate_snapshot_prefix(path, snapshot):
    connection = None
    try:
        connection = sqlite3.connect(str(Path(path)), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        columns = ", ".join(INTENT_COLUMNS)
        for record in snapshot.intent_records:
            row = connection.execute(
                f"SELECT {columns} FROM local_paper_intents WHERE authorization_sha256 = ?",
                (record["authorization_sha256"],),
            ).fetchone()
            if row is None:
                return None
            current = LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS)).as_record()
            if current != record:
                return None
        for anchor in snapshot.order_anchors:
            event = connection.execute(
                "SELECT event_sha256 FROM local_paper_order_events "
                "WHERE authorization_sha256 = ? AND sequence = ?",
                (anchor["authorization_sha256"], anchor["sequence"]),
            ).fetchone()
            state = connection.execute(
                "SELECT sequence, state_sha256 FROM local_paper_order_states "
                "WHERE authorization_sha256 = ?",
                (anchor["authorization_sha256"],),
            ).fetchone()
            if (
                event is None
                or event["event_sha256"] != anchor["event_sha256"]
                or state is None
                or state["sequence"] < anchor["sequence"]
                or (
                    state["sequence"] == anchor["sequence"]
                    and state["state_sha256"] != anchor["state_sha256"]
                )
            ):
                return None
        for anchor in snapshot.fill_anchors:
            row = connection.execute(
                "SELECT fill_event_sha256 FROM local_paper_fill_events WHERE sequence = ?",
                (anchor["sequence"],),
            ).fetchone()
            if row is None or row["fill_event_sha256"] != anchor["fill_event_sha256"]:
                return None
        counts = {
            "intents": connection.execute(
                "SELECT COUNT(*) FROM local_paper_intents"
            ).fetchone()[0],
            "orders": connection.execute(
                "SELECT COUNT(*) FROM local_paper_order_states"
            ).fetchone()[0],
            "order_events": connection.execute(
                "SELECT COUNT(*) FROM local_paper_order_events"
            ).fetchone()[0],
            "fills": connection.execute(
                "SELECT COUNT(*) FROM local_paper_fill_events"
            ).fetchone()[0],
        }
        return counts
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        return None
    finally:
        if connection is not None:
            connection.close()


def recover_startup(path, snapshot_path, spec, policy=None):
    """Validate a snapshot prefix, replay authoritative state, and fail closed on ambiguity."""
    if policy is None:
        policy = LocalPaperExecutionPolicy()
    try:
        expected_policy_sha256 = _policy_sha256(policy)
        expected_spec_sha256 = _spec_sha256(spec)
    except RecoverySnapshotError:
        return RecoveryReport(False, RecoveryCode.SPEC_DRIFT)
    target = Path(snapshot_path)
    pending = _pending_path(target)
    if pending.exists():
        try:
            confirmation = _pending_confirmation(target)
        except RecoverySnapshotError:
            return RecoveryReport(False, RecoveryCode.STORAGE_ERROR)
        return RecoveryReport(
            False,
            RecoveryCode.AMBIGUOUS_COMMIT,
            manual_confirmation_sha256=confirmation,
        )
    if not target.exists():
        source = reconcile_startup(path, spec)
        if source.ready:
            return RecoveryReport(
                True,
                RecoveryCode.JOURNAL_REBUILD_READY,
                source.reconciliation_sha256,
            )
        return RecoveryReport(
            False,
            RecoveryCode.JOURNAL_RECONCILIATION_FAILED,
            source.reconciliation_sha256,
        )
    try:
        snapshot = load_recovery_snapshot(target)
    except RecoverySnapshotError:
        return RecoveryReport(False, RecoveryCode.SNAPSHOT_CORRUPT)
    if snapshot.policy_sha256 != expected_policy_sha256:
        return RecoveryReport(
            False,
            RecoveryCode.POLICY_DRIFT,
            snapshot_sha256=snapshot.snapshot_sha256,
        )
    if snapshot.spec_sha256 != expected_spec_sha256:
        return RecoveryReport(
            False,
            RecoveryCode.SPEC_DRIFT,
            snapshot_sha256=snapshot.snapshot_sha256,
        )
    counts = _validate_snapshot_prefix(path, snapshot)
    if counts is None:
        return RecoveryReport(
            False,
            RecoveryCode.SNAPSHOT_PREFIX_MISMATCH,
            snapshot_sha256=snapshot.snapshot_sha256,
        )
    if (
        counts["intents"] < snapshot.intent_count
        or counts["orders"] < snapshot.order_count
        or counts["order_events"] < snapshot.order_event_count
        or counts["fills"] < snapshot.fill_count
    ):
        return RecoveryReport(
            False,
            RecoveryCode.SNAPSHOT_PREFIX_MISMATCH,
            snapshot_sha256=snapshot.snapshot_sha256,
        )
    source = reconcile_startup(path, spec)
    if not source.ready:
        return RecoveryReport(
            False,
            RecoveryCode.JOURNAL_RECONCILIATION_FAILED,
            source.reconciliation_sha256,
            snapshot.snapshot_sha256,
        )
    tail_intents = counts["intents"] - snapshot.intent_count
    tail_order_events = counts["order_events"] - snapshot.order_event_count
    tail_fills = counts["fills"] - snapshot.fill_count
    code = (
        RecoveryCode.TAIL_REPLAYED
        if any((tail_intents, tail_order_events, tail_fills))
        else RecoveryCode.MATCH
    )
    return RecoveryReport(
        True,
        code,
        source.reconciliation_sha256,
        snapshot.snapshot_sha256,
        tail_intents,
        tail_order_events,
        tail_fills,
    )
