"""P9-004 deterministic delivery guard, deduplication and bounded retry."""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum

from .contracts import NotificationMessage
from .formatter import FormattedNotification, format_notification
from .transport import (
    TELEGRAM_TRANSPORT_ID,
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportError,
    TelegramTransportErrorCode,
    TelegramTransportPolicy,
    send_formatted_notification,
)


DELIVERY_SCHEMA_VERSION = 1
DELIVERY_GUARD_ID = "P9_DELIVERY_GUARD_V1"
MAX_DELIVERY_RECORDS = 256
MAX_ATTEMPTS = 3
NETWORK_BACKOFF_SECONDS = (1, 2)
MAX_RATE_LIMIT_WAIT_SECONDS = 30
MAX_TOTAL_WAIT_SECONDS = 60

_HEX = frozenset("0123456789abcdef")


def _sha256(value):
    material = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _expect_keys(record, expected, label):
    if not isinstance(record, dict) or tuple(sorted(record)) != tuple(sorted(expected)):
        raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID, label=label)


class DeliveryGuardErrorCode(str, Enum):
    INVALID_REQUEST = "DELIVERY_INVALID_REQUEST"
    STATE_INVALID = "DELIVERY_STATE_INVALID"
    STATE_FULL = "DELIVERY_STATE_FULL"
    WAIT_BOUND_EXCEEDED = "DELIVERY_WAIT_BOUND_EXCEEDED"
    RETRY_EXHAUSTED = "DELIVERY_RETRY_EXHAUSTED"
    TRANSPORT_REJECTED = "DELIVERY_TRANSPORT_REJECTED"
    RECEIPT_INVALID = "DELIVERY_RECEIPT_INVALID"


class DeliveryGuardError(RuntimeError):
    """Stable redacted delivery failure with no provider or credential material."""

    def __init__(self, code, *, label=None):
        if not isinstance(code, DeliveryGuardErrorCode):
            raise TypeError("Delivery guard error code is invalid")
        self.code = code
        self.label = label if isinstance(label, str) else None
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class DeliveryGuardPolicy:
    """Frozen bounded retry and deduplication policy for P9-004."""

    guard_id: str = DELIVERY_GUARD_ID
    delivery_schema_version: int = DELIVERY_SCHEMA_VERSION
    max_delivery_records: int = MAX_DELIVERY_RECORDS
    max_attempts: int = MAX_ATTEMPTS
    network_backoff_seconds: tuple[int, int] = NETWORK_BACKOFF_SECONDS
    max_rate_limit_wait_seconds: int = MAX_RATE_LIMIT_WAIT_SECONDS
    max_total_wait_seconds: int = MAX_TOTAL_WAIT_SECONDS
    retry_network_error: bool = True
    retry_rate_limit: bool = True
    retry_http_status: bool = False
    retry_api_rejected: bool = False
    retry_invalid_response: bool = False
    persistent_storage: bool = False
    caller_managed_snapshot: bool = True
    upstream_mutation: bool = False
    control_loop: bool = False
    trade_permission: bool = False
    order_endpoint: bool = False
    ai_direct_execution: bool = False

    def __post_init__(self):
        if (
            self.guard_id != DELIVERY_GUARD_ID
            or self.delivery_schema_version != DELIVERY_SCHEMA_VERSION
            or self.max_delivery_records != MAX_DELIVERY_RECORDS
            or self.max_attempts != MAX_ATTEMPTS
            or self.network_backoff_seconds != NETWORK_BACKOFF_SECONDS
            or self.max_rate_limit_wait_seconds != MAX_RATE_LIMIT_WAIT_SECONDS
            or self.max_total_wait_seconds != MAX_TOTAL_WAIT_SECONDS
            or self.retry_network_error is not True
            or self.retry_rate_limit is not True
            or self.retry_http_status is not False
            or self.retry_api_rejected is not False
            or self.retry_invalid_response is not False
            or self.persistent_storage is not False
            or self.caller_managed_snapshot is not True
            or self.upstream_mutation is not False
            or self.control_loop is not False
            or self.trade_permission is not False
            or self.order_endpoint is not False
            or self.ai_direct_execution is not False
        ):
            raise DeliveryGuardError(DeliveryGuardErrorCode.INVALID_REQUEST)

    def as_record(self):
        return {
            "guard_id": self.guard_id,
            "delivery_schema_version": self.delivery_schema_version,
            "max_delivery_records": self.max_delivery_records,
            "max_attempts": self.max_attempts,
            "network_backoff_seconds": list(self.network_backoff_seconds),
            "max_rate_limit_wait_seconds": self.max_rate_limit_wait_seconds,
            "max_total_wait_seconds": self.max_total_wait_seconds,
            "retry_network_error": self.retry_network_error,
            "retry_rate_limit": self.retry_rate_limit,
            "retry_http_status": self.retry_http_status,
            "retry_api_rejected": self.retry_api_rejected,
            "retry_invalid_response": self.retry_invalid_response,
            "persistent_storage": self.persistent_storage,
            "caller_managed_snapshot": self.caller_managed_snapshot,
            "upstream_mutation": self.upstream_mutation,
            "control_loop": self.control_loop,
            "trade_permission": self.trade_permission,
            "order_endpoint": self.order_endpoint,
            "ai_direct_execution": self.ai_direct_execution,
        }

    @property
    def policy_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """Secret-free record of one successfully acknowledged notification."""

    delivery_id: str
    notification_sha256: str
    formatted_sha256: str
    receipt_sha256: str
    telegram_message_id: int
    attempts: int
    total_wait_seconds: int

    def __post_init__(self):
        if (
            not _valid_sha(self.delivery_id)
            or not _valid_sha(self.notification_sha256)
            or not _valid_sha(self.formatted_sha256)
            or not _valid_sha(self.receipt_sha256)
            or type(self.telegram_message_id) is not int
            or self.telegram_message_id <= 0
            or type(self.attempts) is not int
            or not 1 <= self.attempts <= MAX_ATTEMPTS
            or type(self.total_wait_seconds) is not int
            or not 0 <= self.total_wait_seconds <= MAX_TOTAL_WAIT_SECONDS
        ):
            raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)

    def as_record(self):
        return {
            "delivery_id": self.delivery_id,
            "notification_sha256": self.notification_sha256,
            "formatted_sha256": self.formatted_sha256,
            "receipt_sha256": self.receipt_sha256,
            "telegram_message_id": self.telegram_message_id,
            "attempts": self.attempts,
            "total_wait_seconds": self.total_wait_seconds,
        }


@dataclass(frozen=True, slots=True)
class DeliveryState:
    """Bounded caller-managed canonical dedupe snapshot; no file persistence here."""

    records: tuple[DeliveryRecord, ...] = ()
    schema_version: int = DELIVERY_SCHEMA_VERSION

    def __post_init__(self):
        if (
            type(self.records) is not tuple
            or len(self.records) > MAX_DELIVERY_RECORDS
            or any(not isinstance(item, DeliveryRecord) for item in self.records)
            or self.schema_version != DELIVERY_SCHEMA_VERSION
        ):
            raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)
        identities = tuple(item.delivery_id for item in self.records)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "records": [item.as_record() for item in self.records],
        }

    @property
    def state_sha256(self):
        return _sha256(self.as_record())

    def find(self, delivery_id):
        if not _valid_sha(delivery_id):
            raise DeliveryGuardError(DeliveryGuardErrorCode.INVALID_REQUEST)
        for record in self.records:
            if record.delivery_id == delivery_id:
                return record
        return None


class DeliveryStatus(str, Enum):
    DELIVERED = "DELIVERED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"


@dataclass(frozen=True, slots=True)
class GuardedDeliveryResult:
    """Successful or duplicate-suppressed outcome; failures use stable exceptions."""

    status: DeliveryStatus
    delivery_id: str
    notification_sha256: str
    formatted_sha256: str
    receipt_sha256: str
    telegram_message_id: int
    attempts: int
    wait_seconds: tuple[int, ...]
    state: DeliveryState
    policy_sha256: str = field(default_factory=lambda: DeliveryGuardPolicy().policy_sha256)

    def __post_init__(self):
        if (
            not isinstance(self.status, DeliveryStatus)
            or not _valid_sha(self.delivery_id)
            or not _valid_sha(self.notification_sha256)
            or not _valid_sha(self.formatted_sha256)
            or not _valid_sha(self.receipt_sha256)
            or type(self.telegram_message_id) is not int
            or self.telegram_message_id <= 0
            or type(self.attempts) is not int
            or self.attempts < 0
            or type(self.wait_seconds) is not tuple
            or any(type(item) is not int or item < 0 for item in self.wait_seconds)
            or sum(self.wait_seconds) > MAX_TOTAL_WAIT_SECONDS
            or not isinstance(self.state, DeliveryState)
            or not _valid_sha(self.policy_sha256)
        ):
            raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)
        if self.status is DeliveryStatus.DELIVERED:
            if not 1 <= self.attempts <= MAX_ATTEMPTS:
                raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)
        elif self.attempts != 0 or self.wait_seconds:
            raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)


def delivery_identity(message, formatted):
    if (
        not isinstance(message, NotificationMessage)
        or not isinstance(formatted, FormattedNotification)
        or formatted != format_notification(message)
    ):
        raise DeliveryGuardError(DeliveryGuardErrorCode.INVALID_REQUEST)
    return _sha256({
        "schema_version": DELIVERY_SCHEMA_VERSION,
        "transport_id": TELEGRAM_TRANSPORT_ID,
        "notification_sha256": message.message_sha256,
        "formatted_sha256": formatted.formatted_sha256,
    })


def delivery_state_from_record(record):
    _expect_keys(record, ("schema_version", "records"), "delivery_state")
    if record["schema_version"] != DELIVERY_SCHEMA_VERSION:
        raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)
    items = record["records"]
    if not isinstance(items, list) or len(items) > MAX_DELIVERY_RECORDS:
        raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_INVALID)
    records = []
    expected = (
        "delivery_id",
        "notification_sha256",
        "formatted_sha256",
        "receipt_sha256",
        "telegram_message_id",
        "attempts",
        "total_wait_seconds",
    )
    for item in items:
        _expect_keys(item, expected, "delivery_record")
        records.append(DeliveryRecord(**item))
    return DeliveryState(tuple(records))


def _validate_receipt(receipt, message, formatted):
    if not isinstance(receipt, TelegramDeliveryReceipt):
        raise DeliveryGuardError(DeliveryGuardErrorCode.RECEIPT_INVALID)
    if (
        receipt.notification_sha256 != message.message_sha256
        or receipt.formatted_sha256 != formatted.formatted_sha256
        or receipt.policy_sha256 != TelegramTransportPolicy().policy_sha256
    ):
        raise DeliveryGuardError(DeliveryGuardErrorCode.RECEIPT_INVALID)
    return receipt


def _append_record(state, record):
    if len(state.records) >= MAX_DELIVERY_RECORDS:
        raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_FULL)
    return DeliveryState(tuple(sorted(
        (*state.records, record),
        key=lambda item: item.delivery_id,
    )))


def _guard_error_for_transport(error):
    if not isinstance(error, TelegramTransportError):
        raise TypeError("Transport error is invalid")
    if error.code in (
        TelegramTransportErrorCode.HTTP_STATUS,
        TelegramTransportErrorCode.NETWORK_AMBIGUOUS,
        TelegramTransportErrorCode.RESPONSE_TOO_LARGE,
        TelegramTransportErrorCode.RESPONSE_INVALID,
        TelegramTransportErrorCode.API_REJECTED,
        TelegramTransportErrorCode.CONFIG_MISSING,
        TelegramTransportErrorCode.CONFIG_INVALID,
        TelegramTransportErrorCode.REQUEST_INVALID,
    ):
        return DeliveryGuardErrorCode.TRANSPORT_REJECTED
    return None


def guarded_send(
    message,
    formatted,
    credentials,
    *,
    state=None,
    sender=send_formatted_notification,
    sleep_fn=time.sleep,
):
    """Deliver once with deterministic dedupe and bounded retries only."""

    if (
        not isinstance(message, NotificationMessage)
        or not isinstance(formatted, FormattedNotification)
        or formatted != format_notification(message)
        or not isinstance(credentials, TelegramCredentials)
        or not isinstance(state if state is not None else DeliveryState(), DeliveryState)
        or not callable(sender)
        or not callable(sleep_fn)
    ):
        raise DeliveryGuardError(DeliveryGuardErrorCode.INVALID_REQUEST)

    policy = DeliveryGuardPolicy()
    current = DeliveryState() if state is None else state
    identity = delivery_identity(message, formatted)
    existing = current.find(identity)
    if existing is not None:
        return GuardedDeliveryResult(
            status=DeliveryStatus.DUPLICATE_SUPPRESSED,
            delivery_id=existing.delivery_id,
            notification_sha256=existing.notification_sha256,
            formatted_sha256=existing.formatted_sha256,
            receipt_sha256=existing.receipt_sha256,
            telegram_message_id=existing.telegram_message_id,
            attempts=0,
            wait_seconds=(),
            state=current,
            policy_sha256=policy.policy_sha256,
        )
    if len(current.records) >= policy.max_delivery_records:
        raise DeliveryGuardError(DeliveryGuardErrorCode.STATE_FULL)

    waits = []
    for attempt in range(1, policy.max_attempts + 1):
        try:
            receipt = sender(message, formatted, credentials)
        except TelegramTransportError as error:
            rejected = _guard_error_for_transport(error)
            if rejected is not None:
                raise DeliveryGuardError(rejected) from None

            if error.code is TelegramTransportErrorCode.NETWORK_ERROR:
                if attempt >= policy.max_attempts:
                    raise DeliveryGuardError(
                        DeliveryGuardErrorCode.RETRY_EXHAUSTED
                    ) from None
                wait_seconds = policy.network_backoff_seconds[attempt - 1]
            elif error.code is TelegramTransportErrorCode.RATE_LIMITED:
                if (
                    attempt >= policy.max_attempts
                    or type(error.retry_after_seconds) is not int
                    or error.retry_after_seconds > policy.max_rate_limit_wait_seconds
                ):
                    raise DeliveryGuardError(
                        DeliveryGuardErrorCode.WAIT_BOUND_EXCEEDED
                        if (
                            type(error.retry_after_seconds) is int
                            and error.retry_after_seconds
                            > policy.max_rate_limit_wait_seconds
                        )
                        else DeliveryGuardErrorCode.RETRY_EXHAUSTED
                    ) from None
                wait_seconds = error.retry_after_seconds
            else:
                raise DeliveryGuardError(
                    DeliveryGuardErrorCode.TRANSPORT_REJECTED
                ) from None

            if sum(waits) + wait_seconds > policy.max_total_wait_seconds:
                raise DeliveryGuardError(
                    DeliveryGuardErrorCode.WAIT_BOUND_EXCEEDED
                ) from None
            sleep_fn(wait_seconds)
            waits.append(wait_seconds)
            continue

        receipt = _validate_receipt(receipt, message, formatted)
        record = DeliveryRecord(
            delivery_id=identity,
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            receipt_sha256=receipt.receipt_sha256,
            telegram_message_id=receipt.telegram_message_id,
            attempts=attempt,
            total_wait_seconds=sum(waits),
        )
        updated = _append_record(current, record)
        return GuardedDeliveryResult(
            status=DeliveryStatus.DELIVERED,
            delivery_id=identity,
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            receipt_sha256=receipt.receipt_sha256,
            telegram_message_id=receipt.telegram_message_id,
            attempts=attempt,
            wait_seconds=tuple(waits),
            state=updated,
            policy_sha256=policy.policy_sha256,
        )

    raise DeliveryGuardError(DeliveryGuardErrorCode.RETRY_EXHAUSTED)
