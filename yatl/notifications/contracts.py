"""Immutable P9 read-only notification contracts with no transport or execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum


NOTIFICATION_POLICY_ID = "P9_NOTIFICATION_V1"
NOTIFICATION_SCHEMA_VERSION = 1
SYMBOLS = ("BTCUSDT", "ETHUSDT")
MAX_NOTIFICATIONS = 64
MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 1000
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")

_FORBIDDEN_TEXT_FRAGMENTS = (
    "api_key",
    "api secret",
    "api_secret",
    "bot token",
    "bot_token",
    "authorization:",
    "bearer ",
    "http://",
    "https://",
    "tg://",
    "/api/v3/order",
    "riskauthorization",
    "risk authorization",
    "approved_quantity",
    "quantity_authority",
    "order_endpoint",
    "trade_permission",
    "execution_command",
    "withdrawal",
)


class NotificationContractError(ValueError):
    """P9 notification material violates the frozen read-only boundary."""


class StrategyEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class NotificationSourcePhase(str, Enum):
    P5_PAPER_EXECUTION = "P5_PAPER_EXECUTION"
    P7_ANALYTICS = "P7_ANALYTICS"
    P8_DASHBOARD = "P8_DASHBOARD"
    P10_FORWARD_VALIDATION = "P10_FORWARD_VALIDATION"


class NotificationCategory(str, Enum):
    SYSTEM_STATUS = "SYSTEM_STATUS"
    DATA_QUALITY_ALERT = "DATA_QUALITY_ALERT"
    PAPER_TRADE_LIFECYCLE = "PAPER_TRADE_LIFECYCLE"
    PAPER_SIGNAL_CANDIDATE = "PAPER_SIGNAL_CANDIDATE"
    RISK_DRAWDOWN_ALERT = "RISK_DRAWDOWN_ALERT"
    PERIODIC_SUMMARY = "PERIODIC_SUMMARY"
    P10_VALIDATION_STATUS = "P10_VALIDATION_STATUS"


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _canonical_json(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _valid_id(value):
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _safe_text(value, maximum, *, allow_empty=False):
    if not isinstance(value, str):
        return False
    if not allow_empty and not value:
        return False
    if len(value) > maximum:
        return False
    if any(character < " " or character == "\x7f" for character in value):
        return False
    lowered = value.lower()
    return not any(fragment in lowered for fragment in _FORBIDDEN_TEXT_FRAGMENTS)


def _expect_record(record, expected_keys, label):
    if not isinstance(record, dict) or set(record) != set(expected_keys):
        raise NotificationContractError(
            f"{label} schema is invalid or contains unexpected fields"
        )


def _enum(enum_type, value, label):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise NotificationContractError(f"{label} value is invalid") from exc


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    """Frozen P9-001 boundary: outbound notification semantics, zero transport/control."""

    policy_id: str = NOTIFICATION_POLICY_ID
    mode: str = "READ_ONLY_NOTIFICATION_CONTRACTS"
    source_scope: str = "ACCEPTED_SANITIZED_UPSTREAM_STATUS_ALERTS_ONLY"
    transport_mode: str = "NONE"
    outbound_only: bool = True
    notification_only: bool = True
    read_only: bool = True
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_telegram_transport: bool = False
    allow_network_transport: bool = False
    allow_credentials: bool = False
    allow_bot_token: bool = False
    allow_chat_id: bool = False
    allow_inbound_updates: bool = False
    allow_inbound_commands: bool = False
    allow_callback_actions: bool = False
    allow_webhook_receiver: bool = False
    allow_polling_receiver: bool = False
    allow_execution_control: bool = False
    allow_live_control: bool = False
    allow_strategy_optimizer: bool = False
    allow_risk_authorization_controller: bool = False
    allow_api_key_surface: bool = False
    allow_source_write: bool = False
    allow_short: bool = False
    allow_margin: bool = False
    allow_futures: bool = False
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_trade_permission: bool = False
    allow_order_endpoint: bool = False
    allow_ai_command_execution: bool = False
    allow_strategy_evidence_upgrade: bool = False

    def __post_init__(self):
        expected_false = (
            self.allow_telegram_transport,
            self.allow_network_transport,
            self.allow_credentials,
            self.allow_bot_token,
            self.allow_chat_id,
            self.allow_inbound_updates,
            self.allow_inbound_commands,
            self.allow_callback_actions,
            self.allow_webhook_receiver,
            self.allow_polling_receiver,
            self.allow_execution_control,
            self.allow_live_control,
            self.allow_strategy_optimizer,
            self.allow_risk_authorization_controller,
            self.allow_api_key_surface,
            self.allow_source_write,
            self.allow_short,
            self.allow_margin,
            self.allow_futures,
            self.allow_leverage,
            self.allow_withdrawal,
            self.allow_trade_permission,
            self.allow_order_endpoint,
            self.allow_ai_command_execution,
            self.allow_strategy_evidence_upgrade,
        )
        if not (
            self.policy_id == NOTIFICATION_POLICY_ID
            and self.mode == "READ_ONLY_NOTIFICATION_CONTRACTS"
            and self.source_scope
            == "ACCEPTED_SANITIZED_UPSTREAM_STATUS_ALERTS_ONLY"
            and self.transport_mode == "NONE"
            and self.outbound_only is True
            and self.notification_only is True
            and self.read_only is True
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and all(value is False for value in expected_false)
        ):
            raise NotificationContractError(
                "Notification policy differs from the frozen P9-001 boundary"
            )

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }

    @property
    def policy_sha256(self):
        return _sha256(
            {
                "schema_version": NOTIFICATION_SCHEMA_VERSION,
                "policy": self.as_record(),
            }
        )


@dataclass(frozen=True, slots=True)
class NotificationSourceIdentity:
    """Provenance for one accepted/sanitized upstream status or alert record."""

    source_id: str
    source_phase: NotificationSourcePhase
    observed_at_ms: int
    payload_sha256: str
    symbol: str | None = None
    accepted: bool = True
    sanitized: bool = True
    read_only: bool = True
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if not (
            _valid_id(self.source_id)
            and isinstance(self.source_phase, NotificationSourcePhase)
            and type(self.observed_at_ms) is int
            and self.observed_at_ms >= 0
            and _valid_sha(self.payload_sha256)
            and (self.symbol is None or self.symbol in SYMBOLS)
            and self.accepted is True
            and self.sanitized is True
            and self.read_only is True
            and self.strategy_evidence
            is StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise NotificationContractError("Notification source identity is invalid")

    def as_record(self):
        return {
            "source_id": self.source_id,
            "source_phase": self.source_phase.value,
            "observed_at_ms": self.observed_at_ms,
            "payload_sha256": self.payload_sha256,
            "symbol": self.symbol,
            "accepted": self.accepted,
            "sanitized": self.sanitized,
            "read_only": self.read_only,
            "strategy_evidence": self.strategy_evidence.value,
        }

    @property
    def identity_sha256(self):
        return _sha256(
            {
                "schema_version": NOTIFICATION_SCHEMA_VERSION,
                "source": self.as_record(),
            }
        )


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """One information-only message. It carries no executable action or authority."""

    notification_id: str
    category: NotificationCategory
    severity: NotificationSeverity
    title: str
    body: str
    source: NotificationSourceIdentity
    event_time_ms: int
    symbol: str | None = None
    paper_label: str = "PAPER ONLY"
    live_lock_label: str = "LIVE_MASTER_LOCK=OFF"
    evidence_label: str = "INSUFFICIENT_EVIDENCE"
    actionability: str = "INFORMATION_ONLY"
    read_only: bool = True

    def __post_init__(self):
        symbol_ok = self.symbol is None or self.symbol in SYMBOLS
        source_symbol_ok = (
            self.symbol == self.source.symbol
            if self.source.symbol is not None
            else self.symbol is None
        )
        if not (
            _valid_id(self.notification_id)
            and isinstance(self.category, NotificationCategory)
            and isinstance(self.severity, NotificationSeverity)
            and _safe_text(self.title, MAX_TITLE_CHARS)
            and _safe_text(self.body, MAX_BODY_CHARS)
            and isinstance(self.source, NotificationSourceIdentity)
            and type(self.event_time_ms) is int
            and 0 <= self.event_time_ms <= self.source.observed_at_ms
            and symbol_ok
            and source_symbol_ok
            and self.paper_label == "PAPER ONLY"
            and self.live_lock_label == "LIVE_MASTER_LOCK=OFF"
            and self.evidence_label == "INSUFFICIENT_EVIDENCE"
            and self.actionability == "INFORMATION_ONLY"
            and self.read_only is True
        ):
            raise NotificationContractError("Notification message is invalid")

    def as_record(self):
        return {
            "notification_id": self.notification_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "body": self.body,
            "source": self.source.as_record(),
            "event_time_ms": self.event_time_ms,
            "symbol": self.symbol,
            "paper_label": self.paper_label,
            "live_lock_label": self.live_lock_label,
            "evidence_label": self.evidence_label,
            "actionability": self.actionability,
            "read_only": self.read_only,
        }

    @property
    def message_sha256(self):
        return _sha256(
            {
                "schema_version": NOTIFICATION_SCHEMA_VERSION,
                "notification": self.as_record(),
            }
        )


@dataclass(frozen=True, slots=True)
class NotificationBatch:
    """Canonical bounded batch for a future outbound-only Telegram transport."""

    notifications: tuple[NotificationMessage, ...]
    policy: NotificationPolicy = field(default_factory=NotificationPolicy)

    def __post_init__(self):
        if not isinstance(self.policy, NotificationPolicy):
            raise NotificationContractError("Notification policy is invalid")
        if (
            type(self.notifications) is not tuple
            or not self.notifications
            or len(self.notifications) > MAX_NOTIFICATIONS
            or any(
                not isinstance(item, NotificationMessage)
                for item in self.notifications
            )
        ):
            raise NotificationContractError("Notification batch is invalid")
        identities = tuple(item.notification_id for item in self.notifications)
        if len(set(identities)) != len(identities):
            raise NotificationContractError("Notification identities are duplicated")
        if identities != tuple(sorted(identities)):
            raise NotificationContractError("Notification identities are unordered")

    def as_record(self):
        return {
            "schema_version": NOTIFICATION_SCHEMA_VERSION,
            "notifications": [
                item.as_record()
                for item in self.notifications
            ],
            "policy": self.policy.as_record(),
        }

    @property
    def batch_sha256(self):
        return _sha256(self.as_record())


def build_notification_batch(*notifications):
    return NotificationBatch(tuple(notifications))


def _source_from_record(record):
    expected = (
        "source_id",
        "source_phase",
        "observed_at_ms",
        "payload_sha256",
        "symbol",
        "accepted",
        "sanitized",
        "read_only",
        "strategy_evidence",
    )
    _expect_record(record, expected, "Notification source")
    return NotificationSourceIdentity(
        source_id=record["source_id"],
        source_phase=_enum(
            NotificationSourcePhase,
            record["source_phase"],
            "Notification source phase",
        ),
        observed_at_ms=record["observed_at_ms"],
        payload_sha256=record["payload_sha256"],
        symbol=record["symbol"],
        accepted=record["accepted"],
        sanitized=record["sanitized"],
        read_only=record["read_only"],
        strategy_evidence=_enum(
            StrategyEvidenceState,
            record["strategy_evidence"],
            "Strategy evidence",
        ),
    )


def _message_from_record(record):
    expected = (
        "notification_id",
        "category",
        "severity",
        "title",
        "body",
        "source",
        "event_time_ms",
        "symbol",
        "paper_label",
        "live_lock_label",
        "evidence_label",
        "actionability",
        "read_only",
    )
    _expect_record(record, expected, "Notification message")
    return NotificationMessage(
        notification_id=record["notification_id"],
        category=_enum(
            NotificationCategory,
            record["category"],
            "Notification category",
        ),
        severity=_enum(
            NotificationSeverity,
            record["severity"],
            "Notification severity",
        ),
        title=record["title"],
        body=record["body"],
        source=_source_from_record(record["source"]),
        event_time_ms=record["event_time_ms"],
        symbol=record["symbol"],
        paper_label=record["paper_label"],
        live_lock_label=record["live_lock_label"],
        evidence_label=record["evidence_label"],
        actionability=record["actionability"],
        read_only=record["read_only"],
    )


def notification_batch_from_record(record):
    _expect_record(
        record,
        ("schema_version", "notifications", "policy"),
        "Notification batch",
    )
    if record["schema_version"] != NOTIFICATION_SCHEMA_VERSION:
        raise NotificationContractError("Notification schema version is unsupported")
    if not isinstance(record["notifications"], list):
        raise NotificationContractError("Notification collection is invalid")
    policy_record = record["policy"]
    expected_policy_keys = tuple(NotificationPolicy.__dataclass_fields__)
    _expect_record(policy_record, expected_policy_keys, "Notification policy")
    try:
        policy = NotificationPolicy(**policy_record)
    except TypeError as exc:
        raise NotificationContractError("Notification policy is invalid") from exc
    return NotificationBatch(
        tuple(
            _message_from_record(item)
            for item in record["notifications"]
        ),
        policy=policy,
    )
