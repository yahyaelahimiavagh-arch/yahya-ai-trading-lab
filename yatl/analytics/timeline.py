"""Canonical read-only P7 point-in-time timeline over accepted P5/P6 evidence."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from .contracts import (
    AnalyticsSourceKind,
    StrategyEvidenceState,
)
from .ingestion import (
    AnalyticsIngestionError,
    MAX_RECORDS,
    P5_COLUMNS,
    UpstreamSourceSpec,
    _connect_readonly,
    _decode_canonical,
    _p5_canonical,
    _p6_canonical,
    _safe_stat,
    _schema_version,
    _sha256_file,
    _table_columns,
    _valid_sha,
    ingest_readonly_sources,
)


TIMELINE_SCHEMA_VERSION = 1
MAX_TIMELINE_ENTRIES = 16_384
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

ORDER_EVENT_COLUMNS = (
    "authorization_sha256",
    "intent_sha256",
    "sequence",
    "event_time_ms",
    "event_type",
    "reason",
    "previous_event_sha256",
    "event_sha256",
)
ORDER_STATE_COLUMNS = (
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
FILL_COLUMNS = (
    "fill_event_sha256",
    "symbol",
    "sequence",
    "authorization_sha256",
    "intent_sha256",
    "order_state_sha256",
    "fill_step_sha256",
    "fill_index",
    "payload_json",
)
PORTFOLIO_COLUMNS = (
    "symbol",
    "spec_sha256",
    "fill_count",
    "last_fill_event_sha256",
    "mark_price",
    "payload_json",
    "projection_sha256",
)
FILL_PAYLOAD_KEYS = {
    "action",
    "symbol",
    "decision_time_ms",
    "fill_time_ms",
    "quantity",
    "reference_price",
    "reason",
    "fee_bps",
    "slippage_bps",
    "execution_price",
    "gross_quote",
    "fee_quote",
    "slippage_quote",
    "cash_delta",
    "asset_delta",
}
PORTFOLIO_PAYLOAD_KEYS = {
    "schema_version",
    "spec_sha256",
    "fill_count",
    "last_fill_event_sha256",
    "mark_price",
    "position",
    "portfolio",
    "projection_sha256",
}
PORTFOLIO_SNAPSHOT_KEYS = {
    "symbol",
    "cash",
    "asset_quantity",
    "cost_basis_quote",
    "liquidation_value_quote",
    "realized_pnl_quote",
    "unrealized_pnl_quote",
    "equity_quote",
    "total_fee_quote",
    "total_slippage_quote",
    "closed_trades",
}
EVENT_REASON = {
    "CREATE": "ACCEPTED_INTENT_RECORDED",
    "ACTIVATE": "LOCAL_ACTIVATION_CONFIRMED",
    "CANCEL": "LOCAL_CANCELLATION_CONFIRMED",
}
EVENT_STATUS = {
    "CREATE": "PENDING_LOCAL",
    "ACTIVATE": "ACTIVE_LOCAL",
    "CANCEL": "CANCELLED_LOCAL",
}


class TimelineError(AnalyticsIngestionError):
    """Accepted source material cannot form a coherent point-in-time timeline."""


class TimelineKind(str, Enum):
    P5_INTENT_BINDING = "P5_INTENT_BINDING"
    P5_ORDER_EVENT = "P5_ORDER_EVENT"
    P5_FILL_EVENT = "P5_FILL_EVENT"
    P5_PORTFOLIO_PROJECTION = "P5_PORTFOLIO_PROJECTION"
    P6_ANALYST_TRACE = "P6_ANALYST_TRACE"


class TimelineTimeBasis(str, Enum):
    RELATED_ORDER_TIME = "RELATED_ORDER_TIME"
    UPSTREAM_EVENT_TIME = "UPSTREAM_EVENT_TIME"
    UPSTREAM_FILL_TIME = "UPSTREAM_FILL_TIME"
    LAST_FILL_TIME = "LAST_FILL_TIME"
    SOURCE_OBSERVED_AT = "SOURCE_OBSERVED_AT"


class RelationshipKind(str, Enum):
    AUTHORIZATION = "AUTHORIZATION"
    INTENT = "INTENT"
    DECISION = "DECISION"
    READINESS = "READINESS"
    PREVIOUS_EVENT = "PREVIOUS_EVENT"
    ORDER_STATE = "ORDER_STATE"
    FILL_STEP = "FILL_STEP"
    LAST_FILL = "LAST_FILL"
    SPEC = "SPEC"
    REQUEST = "REQUEST"
    RESPONSE_VALIDATION = "RESPONSE_VALIDATION"
    BUNDLE = "BUNDLE"
    GROUNDING = "GROUNDING"
    ANALYST_INPUT = "ANALYST_INPUT"
    ANALYST_REPORT = "ANALYST_REPORT"


_KIND_RANK = {
    TimelineKind.P5_INTENT_BINDING: 0,
    TimelineKind.P5_ORDER_EVENT: 1,
    TimelineKind.P5_FILL_EVENT: 2,
    TimelineKind.P5_PORTFOLIO_PROJECTION: 3,
    TimelineKind.P6_ANALYST_TRACE: 4,
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_sha(value, label):
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise TimelineError(f"{label} digest is invalid")
    return value


@dataclass(frozen=True, slots=True)
class TimelineRelationship:
    kind: RelationshipKind
    sha256: str

    def __post_init__(self):
        if not isinstance(self.kind, RelationshipKind):
            raise TimelineError("Timeline relationship kind is invalid")
        _require_sha(self.sha256, "Timeline relationship")

    def as_record(self):
        return {"kind": self.kind.value, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    sequence: int
    time_ms: int
    time_basis: TimelineTimeBasis
    kind: TimelineKind
    symbol: str
    source_id: str
    primary_sha256: str
    relationships: tuple[TimelineRelationship, ...]

    def __post_init__(self):
        if (
            type(self.sequence) is not int
            or self.sequence < 0
            or type(self.time_ms) is not int
            or self.time_ms < 0
            or not isinstance(self.time_basis, TimelineTimeBasis)
            or not isinstance(self.kind, TimelineKind)
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not isinstance(self.source_id, str)
            or not self.source_id
            or not _valid_sha(self.primary_sha256)
            or type(self.relationships) is not tuple
            or any(
                not isinstance(item, TimelineRelationship)
                for item in self.relationships
            )
        ):
            raise TimelineError("Timeline entry identity is invalid")
        keys = tuple((item.kind.value, item.sha256) for item in self.relationships)
        if len(set(keys)) != len(keys) or keys != tuple(sorted(keys)):
            raise TimelineError(
                "Timeline relationships are duplicate or noncanonical"
            )

    def as_record(self):
        return {
            "sequence": self.sequence,
            "time_ms": self.time_ms,
            "time_basis": self.time_basis.value,
            "kind": self.kind.value,
            "symbol": self.symbol,
            "source_id": self.source_id,
            "primary_sha256": self.primary_sha256,
            "relationships": [item.as_record() for item in self.relationships],
        }

    @property
    def entry_sha256(self):
        return _digest({
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "entry": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class UnifiedTimeline:
    snapshot_time_ms: int
    symbol: str
    ingestion_manifest_sha256: str
    entries: tuple[TimelineEntry, ...]
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = TIMELINE_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != TIMELINE_SCHEMA_VERSION
            or type(self.snapshot_time_ms) is not int
            or self.snapshot_time_ms < 0
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not _valid_sha(self.ingestion_manifest_sha256)
            or type(self.entries) is not tuple
            or not 1 <= len(self.entries) <= MAX_TIMELINE_ENTRIES
            or any(not isinstance(item, TimelineEntry) for item in self.entries)
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise TimelineError("Unified timeline identity is invalid")

        sequences = tuple(item.sequence for item in self.entries)
        if sequences != tuple(range(len(self.entries))):
            raise TimelineError("Unified timeline sequence is not contiguous")
        if any(
            item.symbol != self.symbol
            or item.time_ms > self.snapshot_time_ms
            for item in self.entries
        ):
            raise TimelineError("Unified timeline contains cross-symbol or future data")

        identities = tuple(
            (item.kind.value, item.primary_sha256)
            for item in self.entries
        )
        if len(set(identities)) != len(identities):
            raise TimelineError("Unified timeline contains duplicate identities")

        order = tuple(
            (
                item.time_ms,
                _KIND_RANK[item.kind],
                item.primary_sha256,
            )
            for item in self.entries
        )
        if order != tuple(sorted(order)):
            raise TimelineError("Unified timeline order is noncanonical")

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "snapshot_time_ms": self.snapshot_time_ms,
            "symbol": self.symbol,
            "ingestion_manifest_sha256": self.ingestion_manifest_sha256,
            "strategy_evidence": self.strategy_evidence.value,
            "entries": [item.as_record() for item in self.entries],
            "safety": {
                "read_only": True,
                "descriptive_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "upstream_mutation": False,
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
        }

    @property
    def timeline_sha256(self):
        return _digest(self.as_record())

    @property
    def canonical_json(self):
        return _json(self.as_record()) + "\n"


def _relationships(*pairs):
    items = tuple(
        TimelineRelationship(kind, sha)
        for kind, sha in pairs
        if sha is not None
    )
    return tuple(sorted(items, key=lambda item: (item.kind.value, item.sha256)))


def _require_tables(connection, expected):
    for table, columns in expected.items():
        if _table_columns(connection, table) != columns:
            raise TimelineError(f"Required P5 {table} schema is unsupported")


def _read_rows(connection, query, label):
    try:
        rows = connection.execute(query).fetchall()
    except sqlite3.Error:
        raise TimelineError(f"{label} cannot be read") from None
    if len(rows) > MAX_RECORDS:
        raise TimelineError(f"{label} exceeds the record bound")
    return rows


def _intent_records(connection):
    encoded, _ = _p5_canonical(connection)
    payload = json.loads(encoded)
    intents = {
        item["authorization_sha256"]: item
        for item in payload["intents"]
    }
    if len(intents) != len(payload["intents"]):
        raise TimelineError("P5 intent identities are duplicate")
    return intents


def _validate_order_material(connection, intents, symbol, snapshot_time_ms):
    if _schema_version(connection, "order_schema_migrations") != 1:
        raise TimelineError("P5 order schema version is unsupported")
    _require_tables(
        connection,
        {
            "local_paper_order_events": ORDER_EVENT_COLUMNS,
            "local_paper_order_states": ORDER_STATE_COLUMNS,
        },
    )
    rows = _read_rows(
        connection,
        "SELECT " + ", ".join(ORDER_EVENT_COLUMNS)
        + " FROM local_paper_order_events "
        "ORDER BY authorization_sha256, sequence",
        "P5 order events",
    )

    grouped = {}
    all_states = {}
    validated = []
    for row in rows:
        item = {name: row[name] for name in ORDER_EVENT_COLUMNS}
        auth = _require_sha(item["authorization_sha256"], "P5 authorization")
        intent_sha = _require_sha(item["intent_sha256"], "P5 intent")
        event_sha = _require_sha(item["event_sha256"], "P5 order event")
        intent = intents.get(auth)
        if intent is None or intent["intent_sha256"] != intent_sha:
            raise TimelineError("P5 order event has no accepted intent")
        if (
            type(item["sequence"]) is not int
            or item["sequence"] < 0
            or type(item["event_time_ms"]) is not int
            or item["event_time_ms"] < 0
            or item["event_time_ms"] > snapshot_time_ms
            or item["event_type"] not in EVENT_REASON
            or item["reason"] != EVENT_REASON[item["event_type"]]
        ):
            raise TimelineError("P5 order event fields are invalid")
        if item["sequence"] == 0:
            if item["previous_event_sha256"] is not None:
                raise TimelineError("Initial P5 order event has a predecessor")
        else:
            _require_sha(item["previous_event_sha256"], "P5 previous order event")

        material = {
            "schema_version": 1,
            "authorization_sha256": auth,
            "intent_sha256": intent_sha,
            "sequence": item["sequence"],
            "event_time_ms": item["event_time_ms"],
            "event_type": item["event_type"],
            "reason": item["reason"],
            "previous_event_sha256": item["previous_event_sha256"],
        }
        if _digest(material) != event_sha:
            raise TimelineError("P5 order event digest verification failed")
        grouped.setdefault(auth, []).append(item)
        validated.append(item)

    if set(grouped) != set(intents):
        raise TimelineError("P5 accepted intent is orphaned from its order lifecycle")

    current_by_auth = {}
    for auth, events in grouped.items():
        previous_event_sha = None
        previous_state_sha = None
        previous_time = None
        expected_type = ("CREATE", "ACTIVATE", "CANCEL")
        for index, item in enumerate(events):
            if (
                item["sequence"] != index
                or index >= len(expected_type)
                or item["event_type"] != expected_type[index]
                or item["previous_event_sha256"] != previous_event_sha
                or (
                    previous_time is not None
                    and item["event_time_ms"] <= previous_time
                )
            ):
                raise TimelineError(
                    "P5 order lifecycle is skipped, broken or out of order"
                )
            status = EVENT_STATUS[item["event_type"]]
            state_material = {
                "schema_version": 1,
                "authorization_sha256": auth,
                "intent_sha256": item["intent_sha256"],
                "sequence": index,
                "updated_time_ms": item["event_time_ms"],
                "status": status,
                "reason": item["reason"],
                "previous_state_sha256": previous_state_sha,
                "event_sha256": item["event_sha256"],
            }
            state_sha = _digest(state_material)
            state = {
                **state_material,
                "state_sha256": state_sha,
            }
            all_states[state_sha] = state
            previous_event_sha = item["event_sha256"]
            previous_state_sha = state_sha
            previous_time = item["event_time_ms"]
        current_by_auth[auth] = all_states[previous_state_sha]

    state_rows = _read_rows(
        connection,
        "SELECT " + ", ".join(ORDER_STATE_COLUMNS)
        + " FROM local_paper_order_states ORDER BY authorization_sha256",
        "P5 order states",
    )
    if len(state_rows) != len(current_by_auth):
        raise TimelineError("P5 current order-state coverage is incomplete")
    for row in state_rows:
        item = {name: row[name] for name in ORDER_STATE_COLUMNS}
        expected = current_by_auth.get(item["authorization_sha256"])
        if expected is None or item != {
            name: expected[name] for name in ORDER_STATE_COLUMNS
        }:
            raise TimelineError("P5 current order state differs from replay")

    return tuple(validated), grouped, all_states


def _validate_fill_material(
    connection,
    intents,
    all_states,
    symbol,
    snapshot_time_ms,
):
    if _schema_version(connection, "portfolio_schema_migrations") != 1:
        raise TimelineError("P5 portfolio schema version is unsupported")
    _require_tables(
        connection,
        {
            "local_paper_fill_events": FILL_COLUMNS,
            "local_paper_portfolios": PORTFOLIO_COLUMNS,
        },
    )
    rows = _read_rows(
        connection,
        "SELECT " + ", ".join(FILL_COLUMNS)
        + " FROM local_paper_fill_events ORDER BY sequence",
        "P5 fill events",
    )

    fills = []
    fill_steps = {}
    for expected_sequence, row in enumerate(rows):
        item = {name: row[name] for name in FILL_COLUMNS}
        if (
            item["symbol"] != symbol
            or item["sequence"] != expected_sequence
            or type(item["fill_index"]) is not int
            or item["fill_index"] < 0
        ):
            raise TimelineError("P5 fill identity is cross-symbol or out of order")
        for name in (
            "fill_event_sha256",
            "authorization_sha256",
            "intent_sha256",
            "order_state_sha256",
            "fill_step_sha256",
        ):
            _require_sha(item[name], f"P5 fill {name}")

        intent = intents.get(item["authorization_sha256"])
        state = all_states.get(item["order_state_sha256"])
        if (
            intent is None
            or intent["intent_sha256"] != item["intent_sha256"]
            or state is None
            or state["authorization_sha256"] != item["authorization_sha256"]
            or state["intent_sha256"] != item["intent_sha256"]
            or state["status"] != "ACTIVE_LOCAL"
        ):
            raise TimelineError("P5 fill is orphaned from intent/order state")

        payload = _decode_canonical(item["payload_json"], "P5 fill payload")
        if (
            not isinstance(payload, dict)
            or set(payload) != FILL_PAYLOAD_KEYS
            or payload["symbol"] != symbol
            or payload["action"] != intent["action"]
            or payload["quantity"] != intent["approved_quantity"]
            or type(payload["decision_time_ms"]) is not int
            or type(payload["fill_time_ms"]) is not int
            or payload["decision_time_ms"] < state["updated_time_ms"]
            or payload["fill_time_ms"] < payload["decision_time_ms"]
            or payload["fill_time_ms"] > snapshot_time_ms
        ):
            raise TimelineError("P5 fill payload violates point-in-time relationships")
        for name in (
            "quantity",
            "reference_price",
            "reason",
            "fee_bps",
            "slippage_bps",
            "execution_price",
            "gross_quote",
            "fee_quote",
            "slippage_quote",
            "cash_delta",
            "asset_delta",
        ):
            if not isinstance(payload[name], str) or not payload[name]:
                raise TimelineError("P5 fill payload contains invalid scalar material")

        material = {
            "schema_version": 1,
            "sequence": item["sequence"],
            "authorization_sha256": item["authorization_sha256"],
            "intent_sha256": item["intent_sha256"],
            "order_state_sha256": item["order_state_sha256"],
            "fill_step_sha256": item["fill_step_sha256"],
            "fill_index": item["fill_index"],
            "fill": payload,
        }
        if _digest(material) != item["fill_event_sha256"]:
            raise TimelineError("P5 fill event digest verification failed")
        fill_steps.setdefault(item["fill_step_sha256"], []).append(item["fill_index"])
        fills.append({**item, "payload": payload})

    for indexes in fill_steps.values():
        if indexes != list(range(len(indexes))):
            raise TimelineError("P5 fill-step indexes are incomplete or out of order")

    portfolio_rows = _read_rows(
        connection,
        "SELECT " + ", ".join(PORTFOLIO_COLUMNS)
        + " FROM local_paper_portfolios ORDER BY symbol",
        "P5 portfolio projections",
    )
    projection = None
    if not fills:
        if portfolio_rows:
            raise TimelineError("P5 portfolio projection has no fill history")
        return tuple(fills), projection

    if len(portfolio_rows) != 1:
        raise TimelineError("P5 fill history requires exactly one portfolio projection")
    row = portfolio_rows[0]
    values = {name: row[name] for name in PORTFOLIO_COLUMNS}
    if (
        values["symbol"] != symbol
        or not _valid_sha(values["spec_sha256"])
        or not _valid_sha(values["last_fill_event_sha256"])
        or not _valid_sha(values["projection_sha256"])
        or type(values["fill_count"]) is not int
        or values["fill_count"] != len(fills)
        or values["last_fill_event_sha256"] != fills[-1]["fill_event_sha256"]
        or not isinstance(values["mark_price"], str)
        or not values["mark_price"]
    ):
        raise TimelineError("P5 portfolio row relationships are invalid")

    payload = _decode_canonical(values["payload_json"], "P5 portfolio payload")
    if (
        not isinstance(payload, dict)
        or set(payload) != PORTFOLIO_PAYLOAD_KEYS
        or payload["schema_version"] != 1
        or payload["spec_sha256"] != values["spec_sha256"]
        or payload["fill_count"] != values["fill_count"]
        or payload["last_fill_event_sha256"] != values["last_fill_event_sha256"]
        or payload["mark_price"] != values["mark_price"]
        or payload["projection_sha256"] != values["projection_sha256"]
        or payload["position"] not in ("LONG", "FLAT")
        or not isinstance(payload["portfolio"], dict)
        or set(payload["portfolio"]) != PORTFOLIO_SNAPSHOT_KEYS
        or payload["portfolio"]["symbol"] != symbol
    ):
        raise TimelineError("P5 portfolio payload differs from durable row")
    for name in PORTFOLIO_SNAPSHOT_KEYS - {"symbol", "closed_trades"}:
        if (
            not isinstance(payload["portfolio"][name], str)
            or not payload["portfolio"][name]
        ):
            raise TimelineError("P5 portfolio snapshot scalar is invalid")
    if (
        type(payload["portfolio"]["closed_trades"]) is not int
        or payload["portfolio"]["closed_trades"] < 0
    ):
        raise TimelineError("P5 portfolio closed-trade count is invalid")
    try:
        quantity = Decimal(payload["portfolio"]["asset_quantity"])
    except (InvalidOperation, ValueError):
        raise TimelineError("P5 portfolio quantity is invalid") from None
    if (
        quantity < 0
        or (payload["position"] == "LONG") is not (quantity > 0)
    ):
        raise TimelineError("P5 portfolio position and quantity disagree")

    material = {key: payload[key] for key in payload if key != "projection_sha256"}
    if _digest(material) != values["projection_sha256"]:
        raise TimelineError("P5 portfolio projection digest verification failed")
    projection = {**values, "payload": payload}
    return tuple(fills), projection


def _p5_entries(spec, snapshot_time_ms):
    before_stat = _safe_stat(spec.database_path)
    before_sha = _sha256_file(spec.database_path)
    if before_sha != spec.expected_database_sha256:
        raise TimelineError("P5 database identity changed before timeline read")
    connection = _connect_readonly(spec.database_path)
    try:
        intents = _intent_records(connection)
        order_events, grouped, all_states = _validate_order_material(
            connection,
            intents,
            spec.symbol,
            snapshot_time_ms,
        )
        fills, projection = _validate_fill_material(
            connection,
            intents,
            all_states,
            spec.symbol,
            snapshot_time_ms,
        )
    finally:
        connection.close()
    after_stat = _safe_stat(spec.database_path)
    after_sha = _sha256_file(spec.database_path)
    if before_stat != after_stat or before_sha != after_sha:
        raise TimelineError("P5 database changed during timeline read")

    entries = []
    for auth, intent in intents.items():
        first_order = grouped[auth][0]
        entries.append({
            "time_ms": first_order["event_time_ms"],
            "time_basis": TimelineTimeBasis.RELATED_ORDER_TIME,
            "kind": TimelineKind.P5_INTENT_BINDING,
            "primary_sha256": intent["intent_sha256"],
            "relationships": _relationships(
                (RelationshipKind.AUTHORIZATION, auth),
                (RelationshipKind.DECISION, intent["decision_sha256"]),
                (RelationshipKind.READINESS, intent["readiness_sha256"]),
            ),
        })

    for event in order_events:
        entries.append({
            "time_ms": event["event_time_ms"],
            "time_basis": TimelineTimeBasis.UPSTREAM_EVENT_TIME,
            "kind": TimelineKind.P5_ORDER_EVENT,
            "primary_sha256": event["event_sha256"],
            "relationships": _relationships(
                (RelationshipKind.AUTHORIZATION, event["authorization_sha256"]),
                (RelationshipKind.INTENT, event["intent_sha256"]),
                (
                    RelationshipKind.PREVIOUS_EVENT,
                    event["previous_event_sha256"],
                ),
            ),
        })

    for fill in fills:
        entries.append({
            "time_ms": fill["payload"]["fill_time_ms"],
            "time_basis": TimelineTimeBasis.UPSTREAM_FILL_TIME,
            "kind": TimelineKind.P5_FILL_EVENT,
            "primary_sha256": fill["fill_event_sha256"],
            "relationships": _relationships(
                (RelationshipKind.AUTHORIZATION, fill["authorization_sha256"]),
                (RelationshipKind.INTENT, fill["intent_sha256"]),
                (RelationshipKind.ORDER_STATE, fill["order_state_sha256"]),
                (RelationshipKind.FILL_STEP, fill["fill_step_sha256"]),
            ),
        })

    if projection is not None:
        entries.append({
            "time_ms": fills[-1]["payload"]["fill_time_ms"],
            "time_basis": TimelineTimeBasis.LAST_FILL_TIME,
            "kind": TimelineKind.P5_PORTFOLIO_PROJECTION,
            "primary_sha256": projection["projection_sha256"],
            "relationships": _relationships(
                (
                    RelationshipKind.LAST_FILL,
                    projection["last_fill_event_sha256"],
                ),
                (RelationshipKind.SPEC, projection["spec_sha256"]),
            ),
        })
    return entries


def _p6_entries(spec, snapshot_time_ms):
    before_stat = _safe_stat(spec.database_path)
    before_sha = _sha256_file(spec.database_path)
    if before_sha != spec.expected_database_sha256:
        raise TimelineError("P6 database identity changed before timeline read")
    connection = _connect_readonly(spec.database_path)
    try:
        encoded, _ = _p6_canonical(connection)
    finally:
        connection.close()
    after_stat = _safe_stat(spec.database_path)
    after_sha = _sha256_file(spec.database_path)
    if before_stat != after_stat or before_sha != after_sha:
        raise TimelineError("P6 database changed during timeline read")
    if spec.observed_at_ms > snapshot_time_ms:
        raise TimelineError("P6 analyst source is future-dated")

    traces = json.loads(encoded)["traces"]
    entries = []
    for trace in traces:
        entries.append({
            "time_ms": spec.observed_at_ms,
            "time_basis": TimelineTimeBasis.SOURCE_OBSERVED_AT,
            "kind": TimelineKind.P6_ANALYST_TRACE,
            "primary_sha256": trace["trace_sha256"],
            "relationships": _relationships(
                (RelationshipKind.REQUEST, trace["request_sha256"]),
                (
                    RelationshipKind.RESPONSE_VALIDATION,
                    trace["response_validation_sha256"],
                ),
                (RelationshipKind.BUNDLE, trace["bundle_sha256"]),
                (RelationshipKind.GROUNDING, trace["grounding_sha256"]),
                (RelationshipKind.ANALYST_INPUT, trace["input_sha256"]),
                (RelationshipKind.ANALYST_REPORT, trace["report_sha256"]),
            ),
        })
    return entries


def build_unified_timeline(snapshot_time_ms, specs):
    """Build a stable point-in-time timeline from exactly one P5 and one P6 source."""

    if type(snapshot_time_ms) is not int or snapshot_time_ms < 0:
        raise TimelineError("Timeline snapshot time is invalid")
    if type(specs) is not tuple or len(specs) != 2:
        raise TimelineError("Timeline requires exactly two upstream source specs")
    if any(not isinstance(item, UpstreamSourceSpec) for item in specs):
        raise TimelineError("Timeline source specification is invalid")

    try:
        manifest = ingest_readonly_sources(snapshot_time_ms, specs)
    except AnalyticsIngestionError:
        raise TimelineError(
            "Timeline upstream ingestion failed closed"
        ) from None
    by_kind = {item.source_kind: item for item in specs}
    if set(by_kind) != {
        AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
        AnalyticsSourceKind.P6_ANALYST_TRACE,
    }:
        raise TimelineError("Timeline source coverage is incomplete")
    p5 = by_kind[AnalyticsSourceKind.P5_EXECUTION_EVIDENCE]
    p6 = by_kind[AnalyticsSourceKind.P6_ANALYST_TRACE]
    if p5.symbol != p6.symbol:
        raise TimelineError("Timeline sources are cross-symbol")

    raw = []
    raw.extend(_p5_entries(p5, snapshot_time_ms))
    raw.extend(_p6_entries(p6, snapshot_time_ms))
    if not raw or len(raw) > MAX_TIMELINE_ENTRIES:
        raise TimelineError("Timeline entry count is invalid")

    source_ids = {
        AnalyticsSourceKind.P5_EXECUTION_EVIDENCE: p5.source_id,
        AnalyticsSourceKind.P6_ANALYST_TRACE: p6.source_id,
    }
    ordered = sorted(
        raw,
        key=lambda item: (
            item["time_ms"],
            _KIND_RANK[item["kind"]],
            item["primary_sha256"],
        ),
    )
    entries = tuple(
        TimelineEntry(
            index,
            item["time_ms"],
            item["time_basis"],
            item["kind"],
            p5.symbol,
            (
                source_ids[AnalyticsSourceKind.P6_ANALYST_TRACE]
                if item["kind"] is TimelineKind.P6_ANALYST_TRACE
                else source_ids[AnalyticsSourceKind.P5_EXECUTION_EVIDENCE]
            ),
            item["primary_sha256"],
            item["relationships"],
        )
        for index, item in enumerate(ordered)
    )
    return UnifiedTimeline(
        snapshot_time_ms,
        p5.symbol,
        manifest.manifest_sha256,
        entries,
    )
