"""Fail-closed, hash-chained P4 Paper Kill Switch state machine."""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

from .circuit import CircuitAssessment, CircuitBreaker


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class KillSwitchError(ValueError):
    """A Kill Switch event, state or transition is unsafe or inconsistent."""


class KillSwitchMode(str, Enum):
    INACTIVE = "INACTIVE"
    TRIGGERED = "TRIGGERED"


class KillSwitchReason(str, Enum):
    FAIL_CLOSED_STARTUP = "FAIL_CLOSED_STARTUP"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    LATCHED_UNTIL_MANUAL_RESET = "LATCHED_UNTIL_MANUAL_RESET"
    CIRCUIT_CLEAR = "CIRCUIT_CLEAR"
    MANUAL_RESET = "MANUAL_RESET"


class KillSwitchEventType(str, Enum):
    STARTUP = "STARTUP"
    CIRCUIT_OBSERVATION = "CIRCUIT_OBSERVATION"
    MANUAL_RESET = "MANUAL_RESET"


_BREAKER_ORDER = tuple(CircuitBreaker)


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_digest(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class KillSwitchEvent:
    """One explicit local Paper event; manual reset requires clear evidence."""

    sequence: int
    event_time_ms: int
    event_type: KillSwitchEventType
    circuit_assessment: CircuitAssessment | None = None
    manual_confirmation: bool = False

    def __post_init__(self):
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise KillSwitchError("Kill Switch event sequence is invalid")
        if type(self.event_time_ms) is not int or self.event_time_ms < 0:
            raise KillSwitchError("Kill Switch event time is invalid")
        if not isinstance(self.event_type, KillSwitchEventType):
            raise KillSwitchError("Kill Switch event type is invalid")
        if type(self.manual_confirmation) is not bool:
            raise KillSwitchError("Manual confirmation must be boolean")
        if self.event_type is KillSwitchEventType.STARTUP:
            valid = (
                self.sequence == 0
                and self.circuit_assessment is None
                and self.manual_confirmation is False
            )
        elif self.event_type is KillSwitchEventType.CIRCUIT_OBSERVATION:
            valid = (
                isinstance(self.circuit_assessment, CircuitAssessment)
                and self.manual_confirmation is False
            )
        else:
            valid = (
                isinstance(self.circuit_assessment, CircuitAssessment)
                and self.manual_confirmation is True
            )
        if not valid:
            raise KillSwitchError("Kill Switch event fields are inconsistent")
        if (
            self.circuit_assessment is not None
            and self.circuit_assessment.managed_state.decision_time_ms
            > self.event_time_ms
        ):
            raise KillSwitchError("Kill Switch event cannot use future circuit state")

    @property
    def event_sha256(self):
        return _digest({
            "schema_version": 1,
            "sequence": self.sequence,
            "event_time_ms": self.event_time_ms,
            "event_type": self.event_type.value,
            "circuit_sha256": (
                None
                if self.circuit_assessment is None
                else self.circuit_assessment.circuit_sha256
            ),
            "manual_confirmation": self.manual_confirmation,
        })


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    """Canonical latched Paper safety state with no execution capability."""

    mode: KillSwitchMode
    reason: KillSwitchReason
    sequence: int
    event_time_ms: int
    triggered_breakers: tuple[CircuitBreaker, ...]
    last_circuit_time_ms: int | None
    last_circuit_sha256: str | None
    previous_state_sha256: str | None
    event_sha256: str

    def __post_init__(self):
        if not isinstance(self.mode, KillSwitchMode):
            raise KillSwitchError("Kill Switch mode is invalid")
        if not isinstance(self.reason, KillSwitchReason):
            raise KillSwitchError("Kill Switch reason is invalid")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise KillSwitchError("Kill Switch state sequence is invalid")
        if type(self.event_time_ms) is not int or self.event_time_ms < 0:
            raise KillSwitchError("Kill Switch state time is invalid")
        if (
            type(self.triggered_breakers) is not tuple
            or not all(isinstance(item, CircuitBreaker) for item in self.triggered_breakers)
            or self.triggered_breakers != tuple(
                item for item in _BREAKER_ORDER if item in self.triggered_breakers
            )
        ):
            raise KillSwitchError("Triggered breaker reasons are invalid or unordered")
        if self.mode is KillSwitchMode.INACTIVE:
            valid = (
                self.reason in {KillSwitchReason.CIRCUIT_CLEAR,
                                KillSwitchReason.MANUAL_RESET}
                and not self.triggered_breakers
            )
        elif self.reason is KillSwitchReason.FAIL_CLOSED_STARTUP:
            valid = self.sequence == 0 and not self.triggered_breakers
        elif self.reason is KillSwitchReason.CIRCUIT_BREAKER_TRIGGERED:
            valid = bool(self.triggered_breakers)
        else:
            valid = self.reason is KillSwitchReason.LATCHED_UNTIL_MANUAL_RESET
        if not valid:
            raise KillSwitchError("Kill Switch mode and reason are inconsistent")
        if (self.last_circuit_time_ms is None) != (self.last_circuit_sha256 is None):
            raise KillSwitchError("Last circuit time and digest must appear together")
        if self.last_circuit_time_ms is not None:
            if (
                type(self.last_circuit_time_ms) is not int
                or self.last_circuit_time_ms < 0
                or self.last_circuit_time_ms > self.event_time_ms
                or not _valid_digest(self.last_circuit_sha256)
            ):
                raise KillSwitchError("Last circuit evidence is invalid")
        if self.sequence == 0:
            if (
                self.mode is not KillSwitchMode.TRIGGERED
                or self.reason is not KillSwitchReason.FAIL_CLOSED_STARTUP
                or self.previous_state_sha256 is not None
                or self.last_circuit_time_ms is not None
                or self.triggered_breakers
            ):
                raise KillSwitchError("Initial Kill Switch state must fail closed")
        else:
            if not _valid_digest(self.previous_state_sha256):
                raise KillSwitchError("Kill Switch state is missing predecessor digest")
            if self.last_circuit_time_ms is None:
                raise KillSwitchError("Advanced Kill Switch state requires circuit evidence")
        if not _valid_digest(self.event_sha256):
            raise KillSwitchError("Kill Switch state event digest is invalid")

    @property
    def active(self):
        return self.mode is KillSwitchMode.TRIGGERED

    @property
    def state_sha256(self):
        return _digest({
            "schema_version": 1,
            "mode": self.mode.value,
            "reason": self.reason.value,
            "sequence": self.sequence,
            "event_time_ms": self.event_time_ms,
            "triggered_breakers": [item.value for item in self.triggered_breakers],
            "last_circuit_time_ms": self.last_circuit_time_ms,
            "last_circuit_sha256": self.last_circuit_sha256,
            "previous_state_sha256": self.previous_state_sha256,
            "event_sha256": self.event_sha256,
        })


def _merge_breakers(existing, observed):
    return tuple(
        breaker
        for breaker in _BREAKER_ORDER
        if breaker in existing or breaker in observed
    )


def _next_state(previous, event):
    if not isinstance(event, KillSwitchEvent):
        raise KillSwitchError("A valid Kill Switch event is required")
    if previous is None:
        if event.event_type is not KillSwitchEventType.STARTUP:
            raise KillSwitchError("Kill Switch must begin with fail-closed startup")
        return KillSwitchState(
            KillSwitchMode.TRIGGERED,
            KillSwitchReason.FAIL_CLOSED_STARTUP,
            event.sequence,
            event.event_time_ms,
            (),
            None,
            None,
            None,
            event.event_sha256,
        )
    if not isinstance(previous, KillSwitchState):
        raise KillSwitchError("Previous Kill Switch state is invalid")
    if event.event_type is KillSwitchEventType.STARTUP:
        raise KillSwitchError("Startup event cannot be repeated")
    if event.sequence != previous.sequence + 1:
        raise KillSwitchError("Kill Switch event sequence is duplicate or missing")
    if event.event_time_ms <= previous.event_time_ms:
        raise KillSwitchError("Kill Switch event time is stale or out of order")

    assessment = event.circuit_assessment
    circuit_time = assessment.managed_state.decision_time_ms
    if (
        previous.last_circuit_time_ms is not None
        and circuit_time <= previous.last_circuit_time_ms
    ):
        raise KillSwitchError("Circuit evidence is stale or already consumed")
    circuit_sha = assessment.circuit_sha256

    if event.event_type is KillSwitchEventType.MANUAL_RESET:
        if previous.mode is not KillSwitchMode.TRIGGERED:
            raise KillSwitchError("Only a triggered Kill Switch can be reset")
        if assessment.triggered_breakers:
            raise KillSwitchError("Manual reset requires current clear circuit evidence")
        mode = KillSwitchMode.INACTIVE
        reason = KillSwitchReason.MANUAL_RESET
        breakers = ()
    elif assessment.triggered_breakers:
        mode = KillSwitchMode.TRIGGERED
        reason = KillSwitchReason.CIRCUIT_BREAKER_TRIGGERED
        breakers = _merge_breakers(
            previous.triggered_breakers,
            assessment.triggered_breakers,
        )
    elif previous.mode is KillSwitchMode.TRIGGERED:
        mode = KillSwitchMode.TRIGGERED
        reason = KillSwitchReason.LATCHED_UNTIL_MANUAL_RESET
        breakers = previous.triggered_breakers
    else:
        mode = KillSwitchMode.INACTIVE
        reason = KillSwitchReason.CIRCUIT_CLEAR
        breakers = ()

    return KillSwitchState(
        mode=mode,
        reason=reason,
        sequence=event.sequence,
        event_time_ms=event.event_time_ms,
        triggered_breakers=breakers,
        last_circuit_time_ms=circuit_time,
        last_circuit_sha256=circuit_sha,
        previous_state_sha256=previous.state_sha256,
        event_sha256=event.event_sha256,
    )


@dataclass(frozen=True, slots=True)
class KillSwitchTransition:
    """Tamper-evident proof of one deterministic Kill Switch transition."""

    previous: KillSwitchState | None
    event: KillSwitchEvent
    current: KillSwitchState

    def __post_init__(self):
        if self.current != _next_state(self.previous, self.event):
            raise KillSwitchError("Current Kill Switch state does not match transition")


def apply_kill_switch_event(previous, event):
    """Apply one explicit Paper safety event without automatic reset or I/O."""
    current = _next_state(previous, event)
    return KillSwitchTransition(previous, event, current)
