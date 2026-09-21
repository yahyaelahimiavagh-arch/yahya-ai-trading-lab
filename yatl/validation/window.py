"""P10-003 sealed forward-data window and no-peek admission boundary."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum

from .contracts import ValidationEvidenceState
from .registration import CandidateGateRegistration


WINDOW_ID = "P10_FORWARD_WINDOW_V1"
P10_002_CHECKPOINT = "e327e2b99a0883fc096941db18b27e572561a7d1"

ACCEPTED_SOURCE_ID = "BINANCE_SPOT_PUBLIC"
ACCEPTED_SOURCE_MANIFEST_PATH = "manifests/p1-market-data.json"
ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1 = (
    "d86ce9d2344ef3ece54c27d3271aebb2f28399c8"
)
ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS = 1_788_971_310_603

P3_DEVELOPMENT_EVIDENCE_END_MS = 1_788_912_000_000
ACCEPTED_HISTORICAL_SOURCE_END_MS = 1_788_970_500_000

SEALED_AT_MS = 1_789_978_020_000
FORWARD_WINDOW_START_MS = 1_790_035_200_000
MINIMUM_EVALUATION_NOT_BEFORE_MS = 1_797_811_200_000
MINIMUM_VALIDATION_DAYS = 90

SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVAL_MILLISECONDS = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}
INTERVALS = ("15m", "1h", "4h")
PRIMARY_INTERVAL = "1h"
CONTEXT_INTERVAL = "15m"
REGIME_INTERVAL = "4h"
TIME_BASIS = "UTC_UNIX_MILLISECONDS"
WINDOW_RANGE_SEMANTICS = "[START,OBSERVATION_CUTOFF)"
DAY_MS = 86_400_000

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_BLOB_SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")


class WindowSealError(ValueError):
    """P10-003 window material violates the frozen no-peek boundary."""


class WindowSealState(str, Enum):
    SEALED = "SEALED"


class ForwardCollectionState(str, Enum):
    NOT_COLLECTED = "NOT_COLLECTED"


class EconomicEvaluationState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"


class WindowEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _strict_keys(record, expected, label):
    if (
        not isinstance(record, dict)
        or tuple(sorted(record)) != tuple(sorted(expected))
    ):
        raise WindowSealError(f"{label} fields are invalid")


def _registration():
    registration = CandidateGateRegistration()
    if (
        SHA256_PATTERN.fullmatch(registration.candidate.candidate_sha256) is None
        or SHA256_PATTERN.fullmatch(registration.gates.registry_sha256) is None
        or SHA256_PATTERN.fullmatch(registration.registration_sha256) is None
    ):
        raise WindowSealError("Accepted P10-002 registration identity is invalid")
    return registration


@dataclass(frozen=True, slots=True)
class ForwardWindowSeal:
    """Exact future-only P10 window identity frozen before any forward data."""

    window_id: str = WINDOW_ID
    p10_002_checkpoint: str = P10_002_CHECKPOINT
    p10_002_registration_sha256: str = field(
        default_factory=lambda: _registration().registration_sha256
    )
    candidate_sha256: str = field(
        default_factory=lambda: _registration().candidate.candidate_sha256
    )
    gate_registry_sha256: str = field(
        default_factory=lambda: _registration().gates.registry_sha256
    )

    accepted_source_id: str = ACCEPTED_SOURCE_ID
    accepted_source_manifest_path: str = ACCEPTED_SOURCE_MANIFEST_PATH
    accepted_source_manifest_git_blob_sha1: str = (
        ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1
    )
    accepted_source_manifest_generated_at_ms: int = (
        ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS
    )

    p3_development_evidence_end_ms: int = P3_DEVELOPMENT_EVIDENCE_END_MS
    accepted_historical_source_end_ms: int = ACCEPTED_HISTORICAL_SOURCE_END_MS
    sealed_at_ms: int = SEALED_AT_MS
    forward_window_start_ms: int = FORWARD_WINDOW_START_MS
    minimum_evaluation_not_before_ms: int = MINIMUM_EVALUATION_NOT_BEFORE_MS
    minimum_validation_days: int = MINIMUM_VALIDATION_DAYS

    symbols: tuple[str, ...] = SYMBOLS
    intervals: tuple[str, ...] = INTERVALS
    primary_interval: str = PRIMARY_INTERVAL
    context_interval: str = CONTEXT_INTERVAL
    regime_interval: str = REGIME_INTERVAL
    time_basis: str = TIME_BASIS
    range_semantics: str = WINDOW_RANGE_SEMANTICS

    window_state: WindowSealState = WindowSealState.SEALED
    forward_collection_state: ForwardCollectionState = (
        ForwardCollectionState.NOT_COLLECTED
    )
    economic_evaluation_state: EconomicEvaluationState = (
        EconomicEvaluationState.NOT_EVALUATED
    )
    strategy_evidence: WindowEvidenceState = WindowEvidenceState.INSUFFICIENT_EVIDENCE

    future_only: bool = True
    reject_pre_window_data: bool = True
    reject_historical_backfill_as_forward: bool = True
    require_closed_observations: bool = True
    require_exact_source: bool = True
    require_exact_symbol_interval_scope: bool = True
    candidate_mutation_allowed: bool = False
    gate_mutation_allowed: bool = False
    source_substitution_allowed: bool = False
    lookahead_allowed: bool = False
    forward_data_admission_authorized: bool = True
    economic_evaluation_allowed: bool = False
    evaluation_may_extend_for_sample_gate: bool = True

    paper_only: bool = True
    live_master_lock: str = "OFF"
    p11_locked: bool = True
    live_candidate: bool = False
    trade_permission: bool = False
    order_endpoint: bool = False
    ai_direct_execution: bool = False

    def __post_init__(self):
        registration = _registration()
        expected_minimum_end = (
            self.forward_window_start_ms
            + self.minimum_validation_days * DAY_MS
        )
        aligned = all(
            self.forward_window_start_ms % INTERVAL_MILLISECONDS[item] == 0
            for item in self.intervals
        )
        fixed = (
            self.window_id == WINDOW_ID
            and self.p10_002_checkpoint == P10_002_CHECKPOINT
            and GIT_BLOB_SHA1_PATTERN.fullmatch(self.p10_002_checkpoint)
            is not None
            and self.p10_002_registration_sha256
            == registration.registration_sha256
            and self.candidate_sha256 == registration.candidate.candidate_sha256
            and self.gate_registry_sha256 == registration.gates.registry_sha256
            and self.accepted_source_id == ACCEPTED_SOURCE_ID
            and self.accepted_source_manifest_path
            == ACCEPTED_SOURCE_MANIFEST_PATH
            and self.accepted_source_manifest_git_blob_sha1
            == ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1
            and GIT_BLOB_SHA1_PATTERN.fullmatch(
                self.accepted_source_manifest_git_blob_sha1
            )
            is not None
            and self.accepted_source_manifest_generated_at_ms
            == ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS
            and self.p3_development_evidence_end_ms
            == P3_DEVELOPMENT_EVIDENCE_END_MS
            and self.accepted_historical_source_end_ms
            == ACCEPTED_HISTORICAL_SOURCE_END_MS
            and self.sealed_at_ms == SEALED_AT_MS
            and self.forward_window_start_ms == FORWARD_WINDOW_START_MS
            and self.minimum_evaluation_not_before_ms
            == MINIMUM_EVALUATION_NOT_BEFORE_MS
            and self.minimum_validation_days == MINIMUM_VALIDATION_DAYS
            and self.minimum_evaluation_not_before_ms == expected_minimum_end
            and self.p3_development_evidence_end_ms
            < self.accepted_historical_source_end_ms
            < self.sealed_at_ms
            < self.forward_window_start_ms
            and aligned
            and self.symbols == SYMBOLS
            and self.intervals == INTERVALS
            and self.primary_interval == PRIMARY_INTERVAL
            and self.context_interval == CONTEXT_INTERVAL
            and self.regime_interval == REGIME_INTERVAL
            and self.time_basis == TIME_BASIS
            and self.range_semantics == WINDOW_RANGE_SEMANTICS
            and self.window_state is WindowSealState.SEALED
            and self.forward_collection_state
            is ForwardCollectionState.NOT_COLLECTED
            and self.economic_evaluation_state
            is EconomicEvaluationState.NOT_EVALUATED
            and self.strategy_evidence
            is WindowEvidenceState.INSUFFICIENT_EVIDENCE
            and self.future_only is True
            and self.reject_pre_window_data is True
            and self.reject_historical_backfill_as_forward is True
            and self.require_closed_observations is True
            and self.require_exact_source is True
            and self.require_exact_symbol_interval_scope is True
            and self.candidate_mutation_allowed is False
            and self.gate_mutation_allowed is False
            and self.source_substitution_allowed is False
            and self.lookahead_allowed is False
            and self.forward_data_admission_authorized is True
            and self.economic_evaluation_allowed is False
            and self.evaluation_may_extend_for_sample_gate is True
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.p11_locked is True
            and self.live_candidate is False
            and self.trade_permission is False
            and self.order_endpoint is False
            and self.ai_direct_execution is False
        )
        if not fixed:
            raise WindowSealError(
                "Forward window differs from frozen P10-003 no-peek boundary"
            )

    def as_record(self):
        return {
            "window_id": self.window_id,
            "p10_002": {
                "checkpoint": self.p10_002_checkpoint,
                "registration_sha256": self.p10_002_registration_sha256,
                "candidate_sha256": self.candidate_sha256,
                "gate_registry_sha256": self.gate_registry_sha256,
            },
            "accepted_source": {
                "source_id": self.accepted_source_id,
                "manifest_path": self.accepted_source_manifest_path,
                "manifest_git_blob_sha1":
                    self.accepted_source_manifest_git_blob_sha1,
                "manifest_generated_at_ms":
                    self.accepted_source_manifest_generated_at_ms,
            },
            "cutoffs": {
                "p3_development_evidence_end_ms":
                    self.p3_development_evidence_end_ms,
                "accepted_historical_source_end_ms":
                    self.accepted_historical_source_end_ms,
                "sealed_at_ms": self.sealed_at_ms,
                "forward_window_start_ms": self.forward_window_start_ms,
                "minimum_evaluation_not_before_ms":
                    self.minimum_evaluation_not_before_ms,
                "minimum_validation_days": self.minimum_validation_days,
            },
            "scope": {
                "symbols": list(self.symbols),
                "intervals": list(self.intervals),
                "primary_interval": self.primary_interval,
                "context_interval": self.context_interval,
                "regime_interval": self.regime_interval,
                "time_basis": self.time_basis,
                "range_semantics": self.range_semantics,
            },
            "states": {
                "window_state": self.window_state.value,
                "forward_collection_state": self.forward_collection_state.value,
                "economic_evaluation_state":
                    self.economic_evaluation_state.value,
                "strategy_evidence": self.strategy_evidence.value,
            },
            "no_peek": {
                "future_only": self.future_only,
                "reject_pre_window_data": self.reject_pre_window_data,
                "reject_historical_backfill_as_forward":
                    self.reject_historical_backfill_as_forward,
                "require_closed_observations":
                    self.require_closed_observations,
                "require_exact_source": self.require_exact_source,
                "require_exact_symbol_interval_scope":
                    self.require_exact_symbol_interval_scope,
                "candidate_mutation_allowed":
                    self.candidate_mutation_allowed,
                "gate_mutation_allowed": self.gate_mutation_allowed,
                "source_substitution_allowed":
                    self.source_substitution_allowed,
                "lookahead_allowed": self.lookahead_allowed,
                "forward_data_admission_authorized":
                    self.forward_data_admission_authorized,
                "economic_evaluation_allowed":
                    self.economic_evaluation_allowed,
                "evaluation_may_extend_for_sample_gate":
                    self.evaluation_may_extend_for_sample_gate,
            },
            "safety": {
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "p11_locked": self.p11_locked,
                "live_candidate": self.live_candidate,
                "trade_permission": self.trade_permission,
                "order_endpoint": self.order_endpoint,
                "ai_direct_execution": self.ai_direct_execution,
            },
        }

    @property
    def window_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class ForwardObservationIdentity:
    """Identity-only admission check; carries no OHLCV or economic result."""

    source_id: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    is_closed: bool
    window_sha256: str = field(
        default_factory=lambda: ForwardWindowSeal().window_sha256
    )

    def __post_init__(self):
        window = ForwardWindowSeal()
        duration = INTERVAL_MILLISECONDS.get(self.interval)
        if (
            self.source_id != window.accepted_source_id
            or self.symbol not in window.symbols
            or self.interval not in window.intervals
            or type(self.open_time_ms) is not int
            or type(self.close_time_ms) is not int
            or type(self.is_closed) is not bool
            or self.is_closed is not True
            or duration is None
            or self.open_time_ms < window.forward_window_start_ms
            or self.open_time_ms % duration
            or self.close_time_ms != self.open_time_ms + duration - 1
            or self.window_sha256 != window.window_sha256
        ):
            raise WindowSealError(
                "Forward observation identity violates sealed P10 window"
            )

    def as_record(self):
        return {
            "source_id": self.source_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "is_closed": self.is_closed,
            "window_sha256": self.window_sha256,
        }

    @property
    def identity_sha256(self):
        return _sha256(self.as_record())


def window_from_record(record):
    expected = (
        "window_id",
        "p10_002",
        "accepted_source",
        "cutoffs",
        "scope",
        "states",
        "no_peek",
        "safety",
    )
    _strict_keys(record, expected, "Forward window")
    window = ForwardWindowSeal()
    if window.as_record() != record:
        raise WindowSealError("Forward window record differs from frozen seal")
    return window


def observation_identity_from_record(record):
    expected = (
        "source_id",
        "symbol",
        "interval",
        "open_time_ms",
        "close_time_ms",
        "is_closed",
        "window_sha256",
    )
    _strict_keys(record, expected, "Forward observation identity")
    try:
        identity = ForwardObservationIdentity(
            source_id=record["source_id"],
            symbol=record["symbol"],
            interval=record["interval"],
            open_time_ms=record["open_time_ms"],
            close_time_ms=record["close_time_ms"],
            is_closed=record["is_closed"],
            window_sha256=record["window_sha256"],
        )
    except (TypeError, ValueError):
        raise WindowSealError("Forward observation identity is invalid") from None
    if identity.as_record() != record:
        raise WindowSealError("Forward observation identity is inconsistent")
    return identity
