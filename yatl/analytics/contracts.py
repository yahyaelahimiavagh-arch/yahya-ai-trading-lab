"""Immutable P7 read-only analytics contracts with no execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum


ANALYTICS_POLICY_ID = "P7_ANALYTICS_V1"
ANALYTICS_SCHEMA_VERSION = 1
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
FIELD_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}")
MAX_SOURCES = 32
MAX_EVENTS = 4096
MAX_DERIVED_FIELDS = 256


class AnalyticsContractError(ValueError):
    """P7 analytics material violates the frozen read-only boundary."""


class AnalyticsSourceKind(str, Enum):
    P5_EXECUTION_EVIDENCE = "P5_EXECUTION_EVIDENCE"
    P6_ANALYST_TRACE = "P6_ANALYST_TRACE"


class AnalyticsEventKind(str, Enum):
    P5_JOURNAL_EVENT = "P5_JOURNAL_EVENT"
    P6_ANALYST_EVENT = "P6_ANALYST_EVENT"


class AnalyticsOrigin(str, Enum):
    UPSTREAM = "UPSTREAM"
    DERIVED = "DERIVED"


class StrategyEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AnalyticsDisposition(str, Enum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnalyticsReason(str, Enum):
    ANALYTICS_ONLY = "ANALYTICS_ONLY"
    NO_USABLE_EVENTS = "NO_USABLE_EVENTS"


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class AnalyticsPolicy:
    """Frozen P7 boundary. Analytics can describe accepted evidence, never authority."""

    policy_id: str = ANALYTICS_POLICY_ID
    mode: str = "READ_ONLY_ANALYTICS"
    descriptive_only: bool = True
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_margin: bool = False
    allow_futures: bool = False
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_external_transport: bool = False
    allow_credentials: bool = False
    allow_upstream_mutation: bool = False
    allow_execution_import: bool = False
    allow_risk_authorization_mutation: bool = False
    allow_quantity_authority: bool = False
    allow_trade_permission: bool = False
    allow_order_endpoint: bool = False
    allow_ai_direct_execution: bool = False
    allow_strategy_evidence_upgrade: bool = False

    def __post_init__(self):
        if not (
            self.policy_id == ANALYTICS_POLICY_ID
            and self.mode == "READ_ONLY_ANALYTICS"
            and self.descriptive_only is True
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.allow_short is False
            and self.allow_margin is False
            and self.allow_futures is False
            and self.allow_leverage is False
            and self.allow_withdrawal is False
            and self.allow_external_transport is False
            and self.allow_credentials is False
            and self.allow_upstream_mutation is False
            and self.allow_execution_import is False
            and self.allow_risk_authorization_mutation is False
            and self.allow_quantity_authority is False
            and self.allow_trade_permission is False
            and self.allow_order_endpoint is False
            and self.allow_ai_direct_execution is False
            and self.allow_strategy_evidence_upgrade is False
        ):
            raise AnalyticsContractError(
                "Analytics policy differs from the frozen read-only policy"
            )

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }

    @property
    def policy_sha256(self):
        return _sha256({
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "policy": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class AnalyticsSourceIdentity:
    """Read-only identity for one accepted upstream evidence source."""

    source_id: str
    source_kind: AnalyticsSourceKind
    symbol: str
    schema_version: int
    observed_at_ms: int
    source_sha256: str
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    read_only: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.source_id, str)
            or ID_PATTERN.fullmatch(self.source_id) is None
            or not isinstance(self.source_kind, AnalyticsSourceKind)
            or self.symbol not in SYMBOLS
            or type(self.schema_version) is not int
            or not 1 <= self.schema_version <= 1_000_000
            or type(self.observed_at_ms) is not int
            or self.observed_at_ms < 0
            or not _valid_sha(self.source_sha256)
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
            or self.read_only is not True
        ):
            raise AnalyticsContractError("Analytics source identity is invalid")

    def as_record(self):
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "symbol": self.symbol,
            "schema_version": self.schema_version,
            "observed_at_ms": self.observed_at_ms,
            "source_sha256": self.source_sha256,
            "strategy_evidence": self.strategy_evidence.value,
            "read_only": self.read_only,
        }

    @property
    def identity_sha256(self):
        return _sha256({
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "source": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class AnalyticsJournalEvent:
    """One immutable upstream journal/trace event reference. It carries no payload."""

    event_id: str
    source: AnalyticsSourceIdentity
    event_kind: AnalyticsEventKind
    event_time_ms: int
    sequence: int
    event_sha256: str
    origin: AnalyticsOrigin = AnalyticsOrigin.UPSTREAM

    def __post_init__(self):
        if (
            not isinstance(self.event_id, str)
            or ID_PATTERN.fullmatch(self.event_id) is None
            or not isinstance(self.source, AnalyticsSourceIdentity)
            or not isinstance(self.event_kind, AnalyticsEventKind)
            or type(self.event_time_ms) is not int
            or self.event_time_ms < 0
            or self.event_time_ms > self.source.observed_at_ms
            or type(self.sequence) is not int
            or not 0 <= self.sequence <= 1_000_000_000
            or not _valid_sha(self.event_sha256)
            or self.origin is not AnalyticsOrigin.UPSTREAM
        ):
            raise AnalyticsContractError("Analytics journal event is invalid")
        expected_kind = {
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE:
                AnalyticsEventKind.P5_JOURNAL_EVENT,
            AnalyticsSourceKind.P6_ANALYST_TRACE:
                AnalyticsEventKind.P6_ANALYST_EVENT,
        }[self.source.source_kind]
        if self.event_kind is not expected_kind:
            raise AnalyticsContractError(
                "Analytics journal event does not match its upstream source kind"
            )

    def as_record(self):
        return {
            "event_id": self.event_id,
            "source_id": self.source.source_id,
            "source_identity_sha256": self.source.identity_sha256,
            "symbol": self.source.symbol,
            "event_kind": self.event_kind.value,
            "event_time_ms": self.event_time_ms,
            "sequence": self.sequence,
            "event_sha256": self.event_sha256,
            "origin": self.origin.value,
            "strategy_evidence": self.source.strategy_evidence.value,
        }

    @property
    def reference_sha256(self):
        return _sha256({
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "event": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class AnalyticsScope:
    """Canonical point-in-time analytics scope bound only to source identities."""

    scope_id: str
    symbol: str
    start_time_ms: int
    end_time_ms: int
    sources: tuple[AnalyticsSourceIdentity, ...]
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if (
            not isinstance(self.scope_id, str)
            or ID_PATTERN.fullmatch(self.scope_id) is None
            or self.symbol not in SYMBOLS
            or type(self.start_time_ms) is not int
            or type(self.end_time_ms) is not int
            or self.start_time_ms < 0
            or self.end_time_ms <= self.start_time_ms
            or type(self.sources) is not tuple
            or not 1 <= len(self.sources) <= MAX_SOURCES
            or any(
                not isinstance(item, AnalyticsSourceIdentity)
                for item in self.sources
            )
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise AnalyticsContractError("Analytics scope identity is invalid")
        source_ids = tuple(item.source_id for item in self.sources)
        if (
            len(set(source_ids)) != len(source_ids)
            or source_ids != tuple(sorted(source_ids))
            or any(item.symbol != self.symbol for item in self.sources)
            or any(item.observed_at_ms > self.end_time_ms for item in self.sources)
            or any(
                item.strategy_evidence
                is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
                for item in self.sources
            )
        ):
            raise AnalyticsContractError(
                "Analytics sources are duplicate, unordered, future-dated, "
                "cross-symbol or evidence-upgraded"
            )

    def as_record(self):
        return {
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "scope_id": self.scope_id,
            "symbol": self.symbol,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "strategy_evidence": self.strategy_evidence.value,
            "sources": [item.as_record() for item in self.sources],
        }

    @property
    def scope_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class DerivedAnalyticsField:
    """Identity of one P7-derived value, explicitly separate from upstream evidence."""

    field_id: str
    field_name: str
    source_ids: tuple[str, ...]
    value_sha256: str
    origin: AnalyticsOrigin = AnalyticsOrigin.DERIVED

    def __post_init__(self):
        if (
            not isinstance(self.field_id, str)
            or ID_PATTERN.fullmatch(self.field_id) is None
            or not isinstance(self.field_name, str)
            or FIELD_NAME_PATTERN.fullmatch(self.field_name) is None
            or type(self.source_ids) is not tuple
            or not self.source_ids
            or any(
                not isinstance(item, str)
                or ID_PATTERN.fullmatch(item) is None
                for item in self.source_ids
            )
            or len(set(self.source_ids)) != len(self.source_ids)
            or self.source_ids != tuple(sorted(self.source_ids))
            or not _valid_sha(self.value_sha256)
            or self.origin is not AnalyticsOrigin.DERIVED
        ):
            raise AnalyticsContractError("Derived analytics field is invalid")

    def as_record(self):
        return {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "source_ids": list(self.source_ids),
            "value_sha256": self.value_sha256,
            "origin": self.origin.value,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsReport:
    """Deterministic descriptive-only P7 report with no executable authority."""

    scope: AnalyticsScope
    events: tuple[AnalyticsJournalEvent, ...]
    derived_fields: tuple[DerivedAnalyticsField, ...]
    disposition: AnalyticsDisposition
    reason: AnalyticsReason
    policy: AnalyticsPolicy = field(default_factory=AnalyticsPolicy)

    def __post_init__(self):
        if (
            not isinstance(self.scope, AnalyticsScope)
            or type(self.events) is not tuple
            or len(self.events) > MAX_EVENTS
            or any(not isinstance(item, AnalyticsJournalEvent) for item in self.events)
            or type(self.derived_fields) is not tuple
            or len(self.derived_fields) > MAX_DERIVED_FIELDS
            or any(
                not isinstance(item, DerivedAnalyticsField)
                for item in self.derived_fields
            )
            or not isinstance(self.disposition, AnalyticsDisposition)
            or not isinstance(self.reason, AnalyticsReason)
            or not isinstance(self.policy, AnalyticsPolicy)
        ):
            raise AnalyticsContractError("Analytics report identity is invalid")

        try:
            reconstructed_scope = AnalyticsScope(
                self.scope.scope_id,
                self.scope.symbol,
                self.scope.start_time_ms,
                self.scope.end_time_ms,
                self.scope.sources,
                self.scope.strategy_evidence,
            )
            reconstructed_policy = AnalyticsPolicy(
                **{
                    name: getattr(self.policy, name)
                    for name in self.policy.__dataclass_fields__
                }
            )
        except (AnalyticsContractError, TypeError, ValueError):
            raise AnalyticsContractError(
                "Analytics scope or policy failed deterministic reconstruction"
            ) from None
        if reconstructed_scope != self.scope or reconstructed_policy != self.policy:
            raise AnalyticsContractError(
                "Analytics report reconstruction changed identity"
            )

        known_sources = {
            item.source_id: item
            for item in self.scope.sources
        }
        event_ids = tuple(item.event_id for item in self.events)
        event_order = tuple(
            (item.event_time_ms, item.sequence, item.event_id)
            for item in self.events
        )
        if (
            len(set(event_ids)) != len(event_ids)
            or event_order != tuple(sorted(event_order))
        ):
            raise AnalyticsContractError(
                "Analytics events are duplicate or unordered"
            )
        for event in self.events:
            accepted_source = known_sources.get(event.source.source_id)
            if (
                accepted_source != event.source
                or event.source.symbol != self.scope.symbol
                or not (
                    self.scope.start_time_ms
                    <= event.event_time_ms
                    < self.scope.end_time_ms
                )
            ):
                raise AnalyticsContractError(
                    "Analytics event is outside the accepted scope"
                )

        field_ids = tuple(item.field_id for item in self.derived_fields)
        if (
            len(set(field_ids)) != len(field_ids)
            or field_ids != tuple(sorted(field_ids))
        ):
            raise AnalyticsContractError(
                "Derived analytics fields are duplicate or unordered"
            )
        for item in self.derived_fields:
            if any(source_id not in known_sources for source_id in item.source_ids):
                raise AnalyticsContractError(
                    "Derived analytics field references an unknown source"
                )

        expected = (
            (
                AnalyticsDisposition.DESCRIPTIVE_ONLY,
                AnalyticsReason.ANALYTICS_ONLY,
            )
            if self.events
            else (
                AnalyticsDisposition.INSUFFICIENT_DATA,
                AnalyticsReason.NO_USABLE_EVENTS,
            )
        )
        if (self.disposition, self.reason) != expected:
            raise AnalyticsContractError(
                "Analytics disposition or reason is not conservative"
            )

    def as_record(self):
        return {
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "scope": self.scope.as_record(),
            "events": [item.as_record() for item in self.events],
            "derived_fields": [item.as_record() for item in self.derived_fields],
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "strategy_evidence": self.scope.strategy_evidence.value,
            "safety": {
                "descriptive_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
            "policy": self.policy.as_record(),
        }

    @property
    def report_sha256(self):
        return _sha256(self.as_record())


def build_analytics_report(scope, events=(), derived_fields=(), policy=None):
    """Build a conservative P7 report from already-identified upstream material."""

    if not isinstance(scope, AnalyticsScope):
        raise AnalyticsContractError("Analytics report requires a valid scope")
    if type(events) is not tuple or type(derived_fields) is not tuple:
        raise AnalyticsContractError("Analytics report collections must be tuples")
    if policy is None:
        policy = AnalyticsPolicy()
    disposition, reason = (
        (
            AnalyticsDisposition.DESCRIPTIVE_ONLY,
            AnalyticsReason.ANALYTICS_ONLY,
        )
        if events
        else (
            AnalyticsDisposition.INSUFFICIENT_DATA,
            AnalyticsReason.NO_USABLE_EVENTS,
        )
    )
    return AnalyticsReport(
        scope,
        events,
        derived_fields,
        disposition,
        reason,
        policy,
    )
