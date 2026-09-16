"""Atomic durable P5 fill events and accepted P2 portfolio projection."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from yatl.backtest import (
    BacktestSpec,
    CostedFill,
    CostModelError,
    FillModelError,
    FillReason,
    FillReference,
    IntentAction,
    PortfolioError,
    PortfolioLedger,
    PortfolioSnapshot,
    apply_costs,
)

from .fills import LocalPaperFillError, LocalPaperFillStep, _fill_record
from .journal import ExecutionJournalError, INTENT_COLUMNS, LocalPaperIntentRecord
from .state import (
    STATE_COLUMNS,
    LocalOrderError,
    LocalOrderReason,
    LocalOrderStatus,
    LocalPaperOrderState,
)


PORTFOLIO_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class LocalPaperPortfolioError(Exception):
    """A durable fill or portfolio projection is unsafe or inconsistent."""


class DuplicateLocalPaperFill(LocalPaperPortfolioError):
    """A durable fill identity was submitted more than once."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_digest(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _spec_record(spec):
    return {
        "symbol": spec.symbol,
        "start_time_ms": spec.start_time_ms,
        "end_time_ms": spec.end_time_ms,
        "initial_cash": spec.initial_cash,
        "fee_bps": spec.fee_bps,
        "slippage_bps": spec.slippage_bps,
        "seed": spec.seed,
        "paper_only": spec.paper_only,
        "live_master_lock": spec.live_master_lock,
        "spot_only": spec.spot_only,
        "allow_short": spec.allow_short,
        "allow_leverage": spec.allow_leverage,
        "execution_price_policy": spec.execution_price_policy,
    }


def _snapshot_record(snapshot):
    return {
        "symbol": snapshot.symbol,
        "cash": format(snapshot.cash, "f"),
        "asset_quantity": format(snapshot.asset_quantity, "f"),
        "cost_basis_quote": format(snapshot.cost_basis_quote, "f"),
        "liquidation_value_quote": format(snapshot.liquidation_value_quote, "f"),
        "realized_pnl_quote": format(snapshot.realized_pnl_quote, "f"),
        "unrealized_pnl_quote": format(snapshot.unrealized_pnl_quote, "f"),
        "equity_quote": format(snapshot.equity_quote, "f"),
        "total_fee_quote": format(snapshot.total_fee_quote, "f"),
        "total_slippage_quote": format(snapshot.total_slippage_quote, "f"),
        "closed_trades": snapshot.closed_trades,
    }


def _snapshot_from_record(record):
    try:
        return PortfolioSnapshot(
            record["symbol"],
            Decimal(record["cash"]),
            Decimal(record["asset_quantity"]),
            Decimal(record["cost_basis_quote"]),
            Decimal(record["liquidation_value_quote"]),
            Decimal(record["realized_pnl_quote"]),
            Decimal(record["unrealized_pnl_quote"]),
            Decimal(record["equity_quote"]),
            Decimal(record["total_fee_quote"]),
            Decimal(record["total_slippage_quote"]),
            record["closed_trades"],
        )
    except (KeyError, PortfolioError, TypeError, ValueError):
        raise LocalPaperPortfolioError("Stored portfolio snapshot is invalid") from None


@dataclass(frozen=True, slots=True)
class LocalPaperFillEvent:
    """One order-bound durable identity for an accepted P5-004 costed fill."""

    sequence: int
    authorization_sha256: str
    intent_sha256: str
    order_state_sha256: str
    fill_step_sha256: str
    fill_index: int
    fill: CostedFill

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise LocalPaperPortfolioError("Durable fill sequence is invalid")
        if type(self.fill_index) is not int or self.fill_index < 0:
            raise LocalPaperPortfolioError("Durable fill index is invalid")
        if any(not _valid_digest(value) for value in (
            self.authorization_sha256,
            self.intent_sha256,
            self.order_state_sha256,
            self.fill_step_sha256,
        )):
            raise LocalPaperPortfolioError("Durable fill identity digest is invalid")
        if not isinstance(self.fill, CostedFill):
            raise LocalPaperPortfolioError("Durable costed fill is invalid") from None

    def _material(self):
        return {
            "schema_version": 1,
            "sequence": self.sequence,
            "authorization_sha256": self.authorization_sha256,
            "intent_sha256": self.intent_sha256,
            "order_state_sha256": self.order_state_sha256,
            "fill_step_sha256": self.fill_step_sha256,
            "fill_index": self.fill_index,
            "fill": _fill_record(self.fill),
        }

    def as_record(self):
        return {**self._material(), "fill_event_sha256": self.fill_event_sha256}

    @property
    def fill_event_sha256(self):
        return _digest(self._material())


@dataclass(frozen=True, slots=True)
class LocalPaperPortfolioProjection:
    """Materialized durable view produced only by the accepted P2 ledger."""

    spec_sha256: str
    fill_count: int
    last_fill_event_sha256: str
    mark_price: str
    snapshot: PortfolioSnapshot

    def __post_init__(self):
        if (
            not _valid_digest(self.spec_sha256)
            or not _valid_digest(self.last_fill_event_sha256)
            or type(self.fill_count) is not int
            or self.fill_count <= 0
            or not isinstance(self.mark_price, str)
            or not isinstance(self.snapshot, PortfolioSnapshot)
        ):
            raise LocalPaperPortfolioError("Portfolio projection identity is invalid")

    def _material(self):
        return {
            "schema_version": 1,
            "spec_sha256": self.spec_sha256,
            "fill_count": self.fill_count,
            "last_fill_event_sha256": self.last_fill_event_sha256,
            "mark_price": self.mark_price,
            "position": "LONG" if self.snapshot.asset_quantity > 0 else "FLAT",
            "portfolio": _snapshot_record(self.snapshot),
        }

    def as_record(self):
        return {**self._material(), "projection_sha256": self.projection_sha256}

    @property
    def projection_sha256(self):
        return _digest(self._material())


@dataclass(frozen=True, slots=True)
class LocalPaperPortfolioApplication:
    events: tuple[LocalPaperFillEvent, ...]
    projection: LocalPaperPortfolioProjection

    def __post_init__(self):
        if (
            type(self.events) is not tuple
            or not self.events
            or any(not isinstance(event, LocalPaperFillEvent) for event in self.events)
            or not isinstance(self.projection, LocalPaperPortfolioProjection)
            or self.projection.last_fill_event_sha256
            != self.events[-1].fill_event_sha256
        ):
            raise LocalPaperPortfolioError("Portfolio application evidence is invalid")


class LocalPaperPortfolioStore:
    """Replay-verified fill log and portfolio projection in one SQLite transaction."""

    def __init__(self, path, accepted_spec):
        if (
            not isinstance(path, (str, Path))
            or not str(path)
            or path == ":memory:"
            or not isinstance(accepted_spec, BacktestSpec)
        ):
            raise LocalPaperPortfolioError("A persistent store and accepted P2 spec are required")
        target = Path(path)
        if not target.is_file():
            raise LocalPaperPortfolioError("An initialized execution database is required")
        self.spec = accepted_spec
        self.spec_sha256 = _digest(_spec_record(accepted_spec))
        self._connection = None
        try:
            self._connection = sqlite3.connect(str(target), timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._migrate()
        except LocalPaperPortfolioError:
            if self._connection is not None:
                self._connection.close()
            raise
        except sqlite3.Error:
            if self._connection is not None:
                self._connection.close()
            raise LocalPaperPortfolioError("Cannot open or migrate portfolio state") from None

    def _migrate(self):
        required = {"local_paper_intents", "local_paper_order_states"}
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        if not required.issubset({row["name"] for row in rows}):
            raise LocalPaperPortfolioError("Accepted intent or order schema is missing")
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS portfolio_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            current = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM portfolio_schema_migrations"
            ).fetchone()[0]
            if current > PORTFOLIO_SCHEMA_VERSION:
                raise LocalPaperPortfolioError(
                    "Portfolio schema is newer than this application"
                )
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE local_paper_fill_events (
                        fill_event_sha256 TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        authorization_sha256 TEXT NOT NULL,
                        intent_sha256 TEXT NOT NULL,
                        order_state_sha256 TEXT NOT NULL,
                        fill_step_sha256 TEXT NOT NULL,
                        fill_index INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        UNIQUE(symbol, sequence),
                        UNIQUE(fill_step_sha256, fill_index),
                        FOREIGN KEY (authorization_sha256)
                            REFERENCES local_paper_intents(authorization_sha256),
                        FOREIGN KEY (order_state_sha256)
                            REFERENCES local_paper_order_states(state_sha256)
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE local_paper_portfolios (
                        symbol TEXT PRIMARY KEY,
                        spec_sha256 TEXT NOT NULL,
                        fill_count INTEGER NOT NULL,
                        last_fill_event_sha256 TEXT NOT NULL,
                        mark_price TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        projection_sha256 TEXT NOT NULL UNIQUE,
                        FOREIGN KEY (last_fill_event_sha256)
                            REFERENCES local_paper_fill_events(fill_event_sha256)
                    )
                    """
                )
                self._connection.execute(
                    "INSERT INTO portfolio_schema_migrations(version) VALUES (1)"
                )

    def _intent(self, authorization_sha256):
        columns = ", ".join(INTENT_COLUMNS)
        row = self._connection.execute(
            f"SELECT {columns} FROM local_paper_intents WHERE authorization_sha256 = ?",
            (authorization_sha256,),
        ).fetchone()
        if row is None:
            raise LocalPaperPortfolioError("Fill has no durable accepted intent")
        try:
            return LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS))
        except (ExecutionJournalError, TypeError, ValueError):
            raise LocalPaperPortfolioError("Stored fill intent is invalid") from None

    def _active_order(self, authorization_sha256):
        columns = ", ".join(STATE_COLUMNS)
        row = self._connection.execute(
            f"SELECT {columns} FROM local_paper_order_states "
            "WHERE authorization_sha256 = ?",
            (authorization_sha256,),
        ).fetchone()
        if row is None:
            raise LocalPaperPortfolioError("Fill has no durable local order state")
        try:
            state = LocalPaperOrderState(
                row["authorization_sha256"], row["intent_sha256"],
                row["sequence"], row["updated_time_ms"],
                LocalOrderStatus(row["status"]), LocalOrderReason(row["reason"]),
                row["previous_state_sha256"], row["event_sha256"],
            )
        except (LocalOrderError, TypeError, ValueError):
            raise LocalPaperPortfolioError("Stored local order state is invalid") from None
        if state.state_sha256 != row["state_sha256"]:
            raise LocalPaperPortfolioError("Stored local order state digest changed")
        return state

    def _event_from_row(self, row):
        try:
            payload = json.loads(row["payload_json"])
            reference = FillReference(
                IntentAction(payload["action"]), payload["symbol"],
                payload["decision_time_ms"], payload["fill_time_ms"],
                payload["quantity"], payload["reference_price"],
                FillReason(payload["reason"]),
            )
            fill = apply_costs(reference, self.spec)
            if _fill_record(fill) != payload:
                raise LocalPaperPortfolioError("Stored fill differs from accepted P2 costs")
            event = LocalPaperFillEvent(
                row["sequence"], row["authorization_sha256"],
                row["intent_sha256"], row["order_state_sha256"],
                row["fill_step_sha256"], row["fill_index"], fill,
            )
        except LocalPaperPortfolioError:
            raise
        except (CostModelError, FillModelError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise LocalPaperPortfolioError("Stored durable fill event is invalid") from None
        if event.fill_event_sha256 != row["fill_event_sha256"]:
            raise LocalPaperPortfolioError("Stored durable fill digest changed")
        return event

    def _projection_from_row(self, row):
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
            projection = LocalPaperPortfolioProjection(
                payload["spec_sha256"], payload["fill_count"],
                payload["last_fill_event_sha256"], payload["mark_price"],
                _snapshot_from_record(payload["portfolio"]),
            )
        except LocalPaperPortfolioError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise LocalPaperPortfolioError("Stored portfolio projection is invalid") from None
        if (
            projection.projection_sha256 != row["projection_sha256"]
            or projection.as_record() != payload
            or projection.spec_sha256 != row["spec_sha256"]
            or projection.fill_count != row["fill_count"]
            or projection.last_fill_event_sha256 != row["last_fill_event_sha256"]
            or projection.mark_price != row["mark_price"]
        ):
            raise LocalPaperPortfolioError("Stored portfolio projection digest changed")
        return projection

    def _load(self):
        rows = self._connection.execute(
            "SELECT * FROM local_paper_fill_events WHERE symbol = ? ORDER BY sequence",
            (self.spec.symbol,),
        ).fetchall()
        events = tuple(self._event_from_row(row) for row in rows)
        if tuple(event.sequence for event in events) != tuple(range(len(events))):
            raise LocalPaperPortfolioError("Durable fill sequence is incomplete")
        ledger = PortfolioLedger(self.spec)
        try:
            if events:
                ledger.apply_many(tuple(event.fill for event in events))
        except PortfolioError:
            raise LocalPaperPortfolioError("Durable fills fail accepted P2 replay") from None
        row = self._connection.execute(
            "SELECT * FROM local_paper_portfolios WHERE symbol = ?",
            (self.spec.symbol,),
        ).fetchone()
        projection = self._projection_from_row(row)
        if not events:
            if projection is not None:
                raise LocalPaperPortfolioError("Portfolio projection has no fill history")
        else:
            if (
                projection is None
                or projection.spec_sha256 != self.spec_sha256
                or projection.fill_count != len(events)
                or projection.last_fill_event_sha256 != events[-1].fill_event_sha256
                or projection.snapshot != ledger.snapshot(projection.mark_price)
            ):
                raise LocalPaperPortfolioError("Portfolio projection differs from P2 replay")
        return events, ledger, projection

    def _insert_fill(self, event):
        self._connection.execute(
            "INSERT INTO local_paper_fill_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.fill_event_sha256, self.spec.symbol, event.sequence,
                event.authorization_sha256, event.intent_sha256,
                event.order_state_sha256, event.fill_step_sha256,
                event.fill_index, _canonical_json(_fill_record(event.fill)),
            ),
        )

    def _write_projection(self, previous, current):
        values = (
            current.spec_sha256, current.fill_count,
            current.last_fill_event_sha256, current.mark_price,
            _canonical_json(current.as_record()), current.projection_sha256,
        )
        if previous is None:
            self._connection.execute(
                "INSERT INTO local_paper_portfolios VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.spec.symbol,) + values,
            )
        else:
            self._connection.execute(
                "UPDATE local_paper_portfolios SET spec_sha256 = ?, fill_count = ?, "
                "last_fill_event_sha256 = ?, mark_price = ?, payload_json = ?, "
                "projection_sha256 = ? WHERE symbol = ? AND projection_sha256 = ?",
                values + (self.spec.symbol, previous.projection_sha256),
            )
            if self._connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise LocalPaperPortfolioError("Portfolio projection changed concurrently")

    def apply(self, step, mark_price):
        """Commit every fill event and the complete P2 projection atomically."""
        if not isinstance(step, LocalPaperFillStep):
            raise LocalPaperPortfolioError("A canonical P5-004 fill step is required")
        try:
            reconstructed = LocalPaperFillStep(
                step.authorization_sha256, step.intent_sha256,
                step.order_state_sha256, step.p2_intent,
                step.references, step.fills,
            )
        except (LocalPaperFillError, TypeError, ValueError):
            raise LocalPaperPortfolioError("P5-004 fill step failed reconstruction") from None
        if reconstructed != step:
            raise LocalPaperPortfolioError("P5-004 fill step identity changed")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            intent = self._intent(step.authorization_sha256)
            order = self._active_order(step.authorization_sha256)
            if (
                intent.intent_sha256 != step.intent_sha256
                or intent.action != step.p2_intent.action.value
                or order.intent_sha256 != step.intent_sha256
                or order.state_sha256 != step.order_state_sha256
                or order.status is not LocalOrderStatus.ACTIVE_LOCAL
                or any(fill.reference.fill_time_ms <= order.updated_time_ms for fill in step.fills)
            ):
                raise LocalPaperPortfolioError("Fill step differs from durable intent or order")
            stored, ledger, previous = self._load()
            events = tuple(
                LocalPaperFillEvent(
                    len(stored) + index,
                    step.authorization_sha256,
                    step.intent_sha256,
                    step.order_state_sha256,
                    step.fill_step_sha256,
                    index,
                    fill,
                )
                for index, fill in enumerate(step.fills)
            )
            duplicate = self._connection.execute(
                "SELECT 1 FROM local_paper_fill_events WHERE fill_step_sha256 = ? LIMIT 1",
                (step.fill_step_sha256,),
            ).fetchone()
            if duplicate is not None:
                raise DuplicateLocalPaperFill("P5-004 fill step was already applied")
            try:
                ledger.apply_many(step.fills)
                snapshot = ledger.snapshot(mark_price)
            except PortfolioError:
                raise LocalPaperPortfolioError(
                    "Accepted P2 portfolio rejected the fill step"
                ) from None
            projection = LocalPaperPortfolioProjection(
                self.spec_sha256,
                len(stored) + len(events),
                events[-1].fill_event_sha256,
                mark_price,
                snapshot,
            )
            for event in events:
                self._insert_fill(event)
            self._write_projection(previous, projection)
            self._connection.commit()
            return LocalPaperPortfolioApplication(events, projection)
        except LocalPaperPortfolioError:
            self._connection.rollback()
            raise
        except sqlite3.IntegrityError:
            self._connection.rollback()
            raise DuplicateLocalPaperFill(
                "Durable fill identity conflicts with portfolio history"
            ) from None
        except sqlite3.Error:
            self._connection.rollback()
            raise LocalPaperPortfolioError(
                "Cannot transactionally apply fill and portfolio projection"
            ) from None

    def events(self):
        try:
            return self._load()[0]
        except LocalPaperPortfolioError:
            raise
        except sqlite3.Error:
            raise LocalPaperPortfolioError("Cannot read durable fill events") from None

    def get_projection(self):
        try:
            return self._load()[2]
        except LocalPaperPortfolioError:
            raise
        except sqlite3.Error:
            raise LocalPaperPortfolioError("Cannot read portfolio projection") from None

    def canonical_json(self):
        try:
            events, _, projection = self._load()
            return _canonical_json({
                "schema_version": PORTFOLIO_SCHEMA_VERSION,
                "spec": _spec_record(self.spec),
                "spec_sha256": self.spec_sha256,
                "fills": [event.as_record() for event in events],
                "projection": None if projection is None else projection.as_record(),
            }) + "\n"
        except LocalPaperPortfolioError:
            raise
        except sqlite3.Error:
            raise LocalPaperPortfolioError("Cannot export portfolio evidence") from None

    def schema_version(self):
        try:
            return self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM portfolio_schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise LocalPaperPortfolioError("Cannot read portfolio schema version") from None

    def close(self):
        try:
            self._connection.close()
        except sqlite3.Error:
            raise LocalPaperPortfolioError("Cannot close portfolio state") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
