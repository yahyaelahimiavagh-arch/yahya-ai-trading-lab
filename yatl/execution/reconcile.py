"""Independent fail-closed startup reconciliation for local Paper execution."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from yatl.backtest import (
    BacktestSpec,
    CostModelError,
    FillModelError,
    FillReason,
    FillReference,
    IntentAction,
    PortfolioError,
    PortfolioLedger,
    apply_costs,
)

from .contracts import RecoveryReadiness, RecoveryReason, RecoveryStatus
from .fills import _fill_record
from .journal import (
    INTENT_COLUMNS,
    JOURNAL_SCHEMA_VERSION,
    ExecutionJournalError,
    LocalPaperIntentRecord,
)
from .portfolio import (
    PORTFOLIO_SCHEMA_VERSION,
    LocalPaperFillEvent,
    LocalPaperPortfolioError,
    LocalPaperPortfolioProjection,
    _snapshot_from_record,
    _spec_record,
)
from .state import (
    EVENT_COLUMNS,
    ORDER_SCHEMA_VERSION,
    STATE_COLUMNS,
    LocalOrderError,
    LocalOrderEventType,
    LocalOrderReason,
    LocalOrderStatus,
    LocalPaperOrderEvent,
    LocalPaperOrderState,
    apply_local_order_event,
)


RECONCILIATION_SCHEMA_VERSION = 1


class ReconciliationCode(str, Enum):
    MATCH = "MATCH"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    MISSING_SCHEMA = "MISSING_SCHEMA"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    INTENT_INVALID = "INTENT_INVALID"
    ORDER_COVERAGE_MISMATCH = "ORDER_COVERAGE_MISMATCH"
    ORDER_EVENT_INVALID = "ORDER_EVENT_INVALID"
    ORDER_STATE_INVALID = "ORDER_STATE_INVALID"
    ORDER_REPLAY_MISMATCH = "ORDER_REPLAY_MISMATCH"
    FILL_INVALID = "FILL_INVALID"
    FILL_ORDER_MISMATCH = "FILL_ORDER_MISMATCH"
    PORTFOLIO_INVALID = "PORTFOLIO_INVALID"
    PORTFOLIO_REPLAY_MISMATCH = "PORTFOLIO_REPLAY_MISMATCH"
    STORAGE_ERROR = "STORAGE_ERROR"


class StartupReconciliationError(Exception):
    """Internal deterministic reconciliation failure with a stable reason code."""

    def __init__(self, code):
        if not isinstance(code, ReconciliationCode) or code is ReconciliationCode.MATCH:
            raise ValueError("A non-success reconciliation code is required")
        self.code = code
        super().__init__(code.value)


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload):
    encoded = _canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_digest(payload):
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class StartupReconciliationReport:
    """Canonical evidence that startup is ready or remains fail closed."""

    ready: bool
    code: ReconciliationCode
    spec_sha256: str | None
    intent_count: int = 0
    order_count: int = 0
    fill_count: int = 0
    journal_sha256: str | None = None
    orders_sha256: str | None = None
    portfolio_sha256: str | None = None

    def __post_init__(self):
        if type(self.ready) is not bool or not isinstance(self.code, ReconciliationCode):
            raise ValueError("Reconciliation report status is invalid")
        if any(type(value) is not int or value < 0 for value in (
            self.intent_count,
            self.order_count,
            self.fill_count,
        )):
            raise ValueError("Reconciliation report counts are invalid")
        digests = (
            self.spec_sha256,
            self.journal_sha256,
            self.orders_sha256,
            self.portfolio_sha256,
        )
        if any(value is not None and (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ) for value in digests):
            raise ValueError("Reconciliation report digest is invalid")
        if self.ready:
            if (
                self.code is not ReconciliationCode.MATCH
                or any(value is None for value in digests)
            ):
                raise ValueError("Ready reconciliation evidence is incomplete")
        elif self.code is ReconciliationCode.MATCH:
            raise ValueError("Failed reconciliation cannot use MATCH")

    def _material(self):
        return {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "status": "READY" if self.ready else "RECOVERY_REQUIRED",
            "code": self.code.value,
            "spec_sha256": self.spec_sha256,
            "intent_count": self.intent_count,
            "order_count": self.order_count,
            "fill_count": self.fill_count,
            "journal_sha256": self.journal_sha256,
            "orders_sha256": self.orders_sha256,
            "portfolio_sha256": self.portfolio_sha256,
        }

    @property
    def reconciliation_sha256(self):
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
            self.reconciliation_sha256,
        )

    def as_record(self):
        return {
            **self._material(),
            "reconciliation_sha256": self.reconciliation_sha256,
            "readiness_sha256": self.readiness.readiness_sha256,
        }


def _failure(code, spec_sha256=None):
    return StartupReconciliationReport(False, code, spec_sha256)


def _require_schema(connection):
    required = {
        "execution_schema_migrations",
        "local_paper_intents",
        "order_schema_migrations",
        "local_paper_order_events",
        "local_paper_order_states",
        "portfolio_schema_migrations",
        "local_paper_fill_events",
        "local_paper_portfolios",
    }
    names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if not required.issubset(names):
        raise StartupReconciliationError(ReconciliationCode.MISSING_SCHEMA)
    expected = (
        ("execution_schema_migrations", JOURNAL_SCHEMA_VERSION),
        ("order_schema_migrations", ORDER_SCHEMA_VERSION),
        ("portfolio_schema_migrations", PORTFOLIO_SCHEMA_VERSION),
    )
    for table, version in expected:
        current = connection.execute(
            f"SELECT COALESCE(MAX(version), 0) FROM {table}"
        ).fetchone()[0]
        if current != version:
            raise StartupReconciliationError(ReconciliationCode.UNSUPPORTED_SCHEMA)


def _load_intents(connection):
    columns = ", ".join(INTENT_COLUMNS)
    rows = connection.execute(
        f"SELECT {columns} FROM local_paper_intents ORDER BY authorization_sha256"
    ).fetchall()
    intents = {}
    records = []
    try:
        for row in rows:
            record = LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS))
            intents[record.authorization_sha256] = record
            records.append(record.as_record())
    except (ExecutionJournalError, KeyError, TypeError, ValueError):
        raise StartupReconciliationError(ReconciliationCode.INTENT_INVALID) from None
    if len(intents) != len(records):
        raise StartupReconciliationError(ReconciliationCode.INTENT_INVALID)
    payload = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "intents": records,
    }
    return intents, payload


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
        raise StartupReconciliationError(ReconciliationCode.ORDER_EVENT_INVALID) from None
    if event.event_sha256 != row["event_sha256"]:
        raise StartupReconciliationError(ReconciliationCode.ORDER_EVENT_INVALID)
    return event


def _state_from_row(row):
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
        raise StartupReconciliationError(ReconciliationCode.ORDER_STATE_INVALID) from None
    if state.state_sha256 != row["state_sha256"]:
        raise StartupReconciliationError(ReconciliationCode.ORDER_STATE_INVALID)
    return state


def _load_orders(connection, intents):
    state_columns = ", ".join(STATE_COLUMNS)
    event_columns = ", ".join(EVENT_COLUMNS)
    state_rows = connection.execute(
        f"SELECT {state_columns} FROM local_paper_order_states "
        "ORDER BY authorization_sha256"
    ).fetchall()
    event_rows = connection.execute(
        f"SELECT {event_columns} FROM local_paper_order_events "
        "ORDER BY authorization_sha256, sequence"
    ).fetchall()
    state_auths = {row["authorization_sha256"] for row in state_rows}
    event_auths = {row["authorization_sha256"] for row in event_rows}
    intent_auths = set(intents)
    if state_auths != intent_auths or event_auths != intent_auths:
        if intent_auths or state_auths or event_auths:
            raise StartupReconciliationError(
                ReconciliationCode.ORDER_COVERAGE_MISMATCH
            )
    rows_by_auth = {authorization: [] for authorization in intents}
    for row in event_rows:
        rows_by_auth.setdefault(row["authorization_sha256"], []).append(row)
    states = {}
    orders = []
    for row in state_rows:
        authorization = row["authorization_sha256"]
        intent = intents.get(authorization)
        if intent is None:
            raise StartupReconciliationError(
                ReconciliationCode.ORDER_COVERAGE_MISMATCH
            )
        previous = None
        events = []
        try:
            for event_row in rows_by_auth[authorization]:
                event = _event_from_row(event_row)
                previous = apply_local_order_event(intent, previous, event).current
                events.append(event)
        except StartupReconciliationError:
            raise
        except (LocalOrderError, TypeError, ValueError):
            raise StartupReconciliationError(
                ReconciliationCode.ORDER_EVENT_INVALID
            ) from None
        stored = _state_from_row(row)
        if previous != stored:
            raise StartupReconciliationError(
                ReconciliationCode.ORDER_REPLAY_MISMATCH
            )
        states[authorization] = stored
        orders.append({
            "authorization_sha256": authorization,
            "events": [event.as_record() for event in events],
            "state": stored.as_record(),
        })
    payload = {
        "schema_version": ORDER_SCHEMA_VERSION,
        "orders": orders,
    }
    return states, payload


def _fill_event_from_row(row, spec):
    try:
        payload = json.loads(row["payload_json"])
        reference = FillReference(
            IntentAction(payload["action"]),
            payload["symbol"],
            payload["decision_time_ms"],
            payload["fill_time_ms"],
            payload["quantity"],
            payload["reference_price"],
            FillReason(payload["reason"]),
        )
        fill = apply_costs(reference, spec)
        if _fill_record(fill) != payload:
            raise StartupReconciliationError(ReconciliationCode.FILL_INVALID)
        event = LocalPaperFillEvent(
            row["sequence"],
            row["authorization_sha256"],
            row["intent_sha256"],
            row["order_state_sha256"],
            row["fill_step_sha256"],
            row["fill_index"],
            fill,
        )
    except StartupReconciliationError:
        raise
    except (
        CostModelError,
        FillModelError,
        KeyError,
        LocalPaperPortfolioError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        raise StartupReconciliationError(ReconciliationCode.FILL_INVALID) from None
    if event.fill_event_sha256 != row["fill_event_sha256"]:
        raise StartupReconciliationError(ReconciliationCode.FILL_INVALID)
    return event


def _load_portfolio(connection, spec, spec_sha256, intents, states):
    rows = connection.execute(
        "SELECT * FROM local_paper_fill_events ORDER BY sequence"
    ).fetchall()
    if any(row["symbol"] != spec.symbol for row in rows):
        raise StartupReconciliationError(ReconciliationCode.FILL_INVALID)
    events = tuple(_fill_event_from_row(row, spec) for row in rows)
    if tuple(event.sequence for event in events) != tuple(range(len(events))):
        raise StartupReconciliationError(ReconciliationCode.FILL_INVALID)
    for event in events:
        intent = intents.get(event.authorization_sha256)
        state = states.get(event.authorization_sha256)
        if (
            intent is None
            or state is None
            or event.intent_sha256 != intent.intent_sha256
            or event.order_state_sha256 != state.state_sha256
            or state.status is not LocalOrderStatus.ACTIVE_LOCAL
            or event.fill.reference.fill_time_ms <= state.updated_time_ms
        ):
            raise StartupReconciliationError(
                ReconciliationCode.FILL_ORDER_MISMATCH
            )
    try:
        ledger = PortfolioLedger(spec)
        if events:
            ledger.apply_many(tuple(event.fill for event in events))
    except PortfolioError:
        raise StartupReconciliationError(ReconciliationCode.FILL_INVALID) from None

    portfolio_rows = connection.execute(
        "SELECT * FROM local_paper_portfolios ORDER BY symbol"
    ).fetchall()
    projection = None
    if not events:
        if portfolio_rows:
            raise StartupReconciliationError(ReconciliationCode.PORTFOLIO_INVALID)
    else:
        if len(portfolio_rows) != 1 or portfolio_rows[0]["symbol"] != spec.symbol:
            raise StartupReconciliationError(ReconciliationCode.PORTFOLIO_INVALID)
        row = portfolio_rows[0]
        try:
            payload = json.loads(row["payload_json"])
            projection = LocalPaperPortfolioProjection(
                payload["spec_sha256"],
                payload["fill_count"],
                payload["last_fill_event_sha256"],
                payload["mark_price"],
                _snapshot_from_record(payload["portfolio"]),
            )
        except LocalPaperPortfolioError:
            raise StartupReconciliationError(
                ReconciliationCode.PORTFOLIO_INVALID
            ) from None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise StartupReconciliationError(
                ReconciliationCode.PORTFOLIO_INVALID
            ) from None
        if (
            projection.projection_sha256 != row["projection_sha256"]
            or projection.as_record() != payload
            or projection.spec_sha256 != row["spec_sha256"]
            or projection.fill_count != row["fill_count"]
            or projection.last_fill_event_sha256 != row["last_fill_event_sha256"]
            or projection.mark_price != row["mark_price"]
            or projection.spec_sha256 != spec_sha256
            or projection.fill_count != len(events)
            or projection.last_fill_event_sha256 != events[-1].fill_event_sha256
        ):
            raise StartupReconciliationError(
                ReconciliationCode.PORTFOLIO_INVALID
            )
        try:
            expected = ledger.snapshot(projection.mark_price)
        except PortfolioError:
            raise StartupReconciliationError(
                ReconciliationCode.PORTFOLIO_INVALID
            ) from None
        if projection.snapshot != expected:
            raise StartupReconciliationError(
                ReconciliationCode.PORTFOLIO_REPLAY_MISMATCH
            )

    payload = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "spec": _spec_record(spec),
        "spec_sha256": spec_sha256,
        "fills": [event.as_record() for event in events],
        "projection": None if projection is None else projection.as_record(),
    }
    return events, payload


def reconcile_startup(path, accepted_spec):
    """Rebuild durable local state and return READY only after exact reconciliation."""
    if not isinstance(accepted_spec, BacktestSpec):
        return _failure(ReconciliationCode.PORTFOLIO_INVALID)
    spec_sha256 = _digest(_spec_record(accepted_spec))
    if not isinstance(path, (str, Path)) or not str(path) or path == ":memory:":
        return _failure(ReconciliationCode.DATABASE_UNAVAILABLE, spec_sha256)
    target = Path(path)
    if not target.is_file():
        return _failure(ReconciliationCode.DATABASE_UNAVAILABLE, spec_sha256)
    connection = None
    try:
        connection = sqlite3.connect(str(target), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        _require_schema(connection)
        intents, journal_payload = _load_intents(connection)
        states, orders_payload = _load_orders(connection, intents)
        events, portfolio_payload = _load_portfolio(
            connection,
            accepted_spec,
            spec_sha256,
            intents,
            states,
        )
        return StartupReconciliationReport(
            True,
            ReconciliationCode.MATCH,
            spec_sha256,
            len(intents),
            len(states),
            len(events),
            _canonical_digest(journal_payload),
            _canonical_digest(orders_payload),
            _canonical_digest(portfolio_payload),
        )
    except StartupReconciliationError as exc:
        return _failure(exc.code, spec_sha256)
    except sqlite3.Error:
        return _failure(ReconciliationCode.STORAGE_ERROR, spec_sha256)
    finally:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass
