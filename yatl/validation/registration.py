"""P10-002 exact candidate freeze and pre-registered economic gates."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

from .contracts import (
    VALIDATION_CRITERIA,
    ValidationCriterion,
    ValidationEvidenceState,
)


CANDIDATE_ID = "P10_BASELINE_TREND_PULLBACK_V1"
GATE_REGISTRY_ID = "P10_ECONOMIC_GATES_V1"
REGISTRATION_ID = "P10-CANDIDATE-GATES-001"
P10_001_POLICY_SHA256 = (
    "a85981d7ec835b584907bc89f3cff62b662a11d46c163900101ad46a213aa2c2"
)

TREND_CONFIGURATION_SHA256 = (
    "98301c6ee14e9ee01ffdbb1ca68cdce4c0ea0db6a504fc6e4e280bd9f027e20a"
)
P3_ACCEPTED_TREND_TRADES = 31
P3_ACCEPTED_BREAKOUT_TRADES = 4

CANDIDATE_SOURCE_BLOBS = (
    ("yatl/strategy/contracts.py", "d932e30c868cbe1385e70f9b5d20687b553433ab"),
    ("yatl/strategy/features.py", "d388f09be37df075efe86cc47ee7a88a0ed3f923"),
    ("yatl/strategy/regime.py", "845af1b843041226561fe4e537822681b9a460e1"),
    ("yatl/strategy/registry.py", "61d5f5384f72932c187c8d91ad832987b3eaab08"),
    ("yatl/strategy/trend.py", "5baacfe87c9256b0029ba817d04859f1d7e5503b"),
)

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_BLOB_SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
PLAIN_DECIMAL_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?"
)


class RegistrationError(ValueError):
    """P10-002 candidate or gate registry violates the frozen registration."""


class CandidateFreezeState(str, Enum):
    FROZEN = "FROZEN"


class GateRegistrationState(str, Enum):
    REGISTERED = "REGISTERED"


class ValidationWindowState(str, Enum):
    NOT_OPEN = "NOT_OPEN"


class ForwardDataState(str, Enum):
    NOT_COLLECTED = "NOT_COLLECTED"


class EconomicEvaluationState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"


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


def _decimal(value, name, *, maximum=None):
    if not isinstance(value, str) or PLAIN_DECIMAL_PATTERN.fullmatch(value) is None:
        raise RegistrationError(f"{name} must be a plain nonnegative decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise RegistrationError(f"{name} is invalid") from None
    if (
        not number.is_finite()
        or number < 0
        or (maximum is not None and number > Decimal(maximum))
    ):
        raise RegistrationError(f"{name} is outside the allowed range")
    return number


def _strict_keys(record, expected, label):
    if (
        not isinstance(record, dict)
        or tuple(sorted(record)) != tuple(sorted(expected))
    ):
        raise RegistrationError(f"{label} fields are invalid")


@dataclass(frozen=True, slots=True)
class SourceBlobIdentity:
    path: str
    git_blob_sha1: str

    def __post_init__(self):
        if (
            not isinstance(self.path, str)
            or not self.path.startswith("yatl/strategy/")
            or not self.path.endswith(".py")
            or not isinstance(self.git_blob_sha1, str)
            or GIT_BLOB_SHA1_PATTERN.fullmatch(self.git_blob_sha1) is None
        ):
            raise RegistrationError("Candidate source blob identity is invalid")

    def as_record(self):
        return {
            "path": self.path,
            "git_blob_sha1": self.git_blob_sha1,
        }


@dataclass(frozen=True, slots=True)
class CandidateFreeze:
    """One exact non-AI baseline candidate selected before forward data."""

    candidate_id: str = CANDIDATE_ID
    strategy_id: str = "TREND_PULLBACK"
    strategy_version: str = "1.0.0"
    configuration_sha256: str = TREND_CONFIGURATION_SHA256
    source_blobs: tuple[SourceBlobIdentity, ...] = field(
        default_factory=lambda: tuple(
            SourceBlobIdentity(path, digest)
            for path, digest in CANDIDATE_SOURCE_BLOBS
        )
    )

    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    primary_interval: str = "1h"
    context_interval: str = "15m"
    regime_interval: str = "4h"
    execution_price_policy: str = "NEXT_PRIMARY_OPEN"

    initial_equity_quote: str = "10000"
    fee_bps: str = "10"
    slippage_bps: str = "5"

    risk_policy_id: str = "P4_RISK_V1"
    risk_per_trade_fraction: str = "0.01"
    max_position_fraction: str = "0.25"
    max_gross_exposure_fraction: str = "0.25"
    max_session_loss_fraction: str = "0.02"
    max_risk_drawdown_fraction: str = "0.10"
    max_consecutive_losses: int = 3
    max_open_positions: int = 1

    selection_basis: str = "P3_ACCEPTED_SAMPLE_FEASIBILITY_ONLY"
    selection_uses_historical_return: bool = False
    accepted_p3_trend_trades: int = P3_ACCEPTED_TREND_TRADES
    accepted_p3_breakout_trades: int = P3_ACCEPTED_BREAKOUT_TRADES
    accepted_p3_evidence: str = "INSUFFICIENT_EVIDENCE"

    baseline_ai_enabled: bool = False
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    long_only: bool = True
    trade_permission: bool = False
    order_endpoint: bool = False
    ai_direct_execution: bool = False

    def __post_init__(self):
        expected_sources = tuple(
            SourceBlobIdentity(path, digest)
            for path, digest in CANDIDATE_SOURCE_BLOBS
        )
        fixed = (
            self.candidate_id == CANDIDATE_ID
            and self.strategy_id == "TREND_PULLBACK"
            and self.strategy_version == "1.0.0"
            and self.configuration_sha256 == TREND_CONFIGURATION_SHA256
            and SHA256_PATTERN.fullmatch(self.configuration_sha256) is not None
            and self.source_blobs == expected_sources
            and tuple(item.path for item in self.source_blobs)
            == tuple(sorted(item.path for item in self.source_blobs))
            and self.symbols == ("BTCUSDT", "ETHUSDT")
            and self.primary_interval == "1h"
            and self.context_interval == "15m"
            and self.regime_interval == "4h"
            and self.execution_price_policy == "NEXT_PRIMARY_OPEN"
            and self.initial_equity_quote == "10000"
            and self.fee_bps == "10"
            and self.slippage_bps == "5"
            and self.risk_policy_id == "P4_RISK_V1"
            and self.risk_per_trade_fraction == "0.01"
            and self.max_position_fraction == "0.25"
            and self.max_gross_exposure_fraction == "0.25"
            and self.max_session_loss_fraction == "0.02"
            and self.max_risk_drawdown_fraction == "0.10"
            and type(self.max_consecutive_losses) is int
            and self.max_consecutive_losses == 3
            and type(self.max_open_positions) is int
            and self.max_open_positions == 1
            and self.selection_basis == "P3_ACCEPTED_SAMPLE_FEASIBILITY_ONLY"
            and self.selection_uses_historical_return is False
            and self.accepted_p3_trend_trades == P3_ACCEPTED_TREND_TRADES
            and self.accepted_p3_breakout_trades == P3_ACCEPTED_BREAKOUT_TRADES
            and self.accepted_p3_evidence == "INSUFFICIENT_EVIDENCE"
            and self.baseline_ai_enabled is False
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.long_only is True
            and self.trade_permission is False
            and self.order_endpoint is False
            and self.ai_direct_execution is False
        )
        if not fixed:
            raise RegistrationError("Candidate differs from frozen P10-002 baseline")
        for name in (
            "initial_equity_quote",
            "fee_bps",
            "slippage_bps",
            "risk_per_trade_fraction",
            "max_position_fraction",
            "max_gross_exposure_fraction",
            "max_session_loss_fraction",
            "max_risk_drawdown_fraction",
        ):
            _decimal(getattr(self, name), name)

    def as_record(self):
        return {
            "candidate_id": self.candidate_id,
            "strategy": {
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "configuration_sha256": self.configuration_sha256,
                "source_blobs": [item.as_record() for item in self.source_blobs],
            },
            "market_scope": {
                "symbols": list(self.symbols),
                "primary_interval": self.primary_interval,
                "context_interval": self.context_interval,
                "regime_interval": self.regime_interval,
                "execution_price_policy": self.execution_price_policy,
            },
            "paper_economics": {
                "initial_equity_quote": self.initial_equity_quote,
                "fee_bps": self.fee_bps,
                "slippage_bps": self.slippage_bps,
            },
            "risk_policy": {
                "policy_id": self.risk_policy_id,
                "risk_per_trade_fraction": self.risk_per_trade_fraction,
                "max_position_fraction": self.max_position_fraction,
                "max_gross_exposure_fraction": self.max_gross_exposure_fraction,
                "max_session_loss_fraction": self.max_session_loss_fraction,
                "max_drawdown_fraction": self.max_risk_drawdown_fraction,
                "max_consecutive_losses": self.max_consecutive_losses,
                "max_open_positions": self.max_open_positions,
            },
            "selection_provenance": {
                "basis": self.selection_basis,
                "uses_historical_return": self.selection_uses_historical_return,
                "accepted_p3_trend_trades": self.accepted_p3_trend_trades,
                "accepted_p3_breakout_trades": self.accepted_p3_breakout_trades,
                "accepted_p3_evidence": self.accepted_p3_evidence,
            },
            "safety": {
                "baseline_ai_enabled": self.baseline_ai_enabled,
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "spot_only": self.spot_only,
                "long_only": self.long_only,
                "trade_permission": self.trade_permission,
                "order_endpoint": self.order_endpoint,
                "ai_direct_execution": self.ai_direct_execution,
            },
        }

    @property
    def candidate_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class EconomicGateRegistry:
    """Numeric/evaluable gates frozen before the P10 forward window opens."""

    registry_id: str = GATE_REGISTRY_ID
    p10_001_policy_sha256: str = P10_001_POLICY_SHA256
    candidate_sha256: str = field(
        default_factory=lambda: CandidateFreeze().candidate_sha256
    )
    criteria: tuple[ValidationCriterion, ...] = VALIDATION_CRITERIA

    minimum_validation_days: int = 90
    minimum_total_completed_trades: int = 60
    minimum_completed_trades_per_symbol: int = 20

    minimum_net_return_after_costs: str = "0.02"
    minimum_profit_factor_after_costs: str = "1.10"
    maximum_validation_drawdown_fraction: str = "0.08"

    segment_count: int = 3
    minimum_positive_segments: int = 2
    maximum_segment_loss_fraction: str = "0.04"
    positive_net_pnl_each_symbol_required: bool = True

    minimum_distinct_regimes_observed: int = 2
    allowed_entry_regimes: tuple[str, ...] = ("TREND_UP",)
    maximum_entries_outside_allowed_regimes: int = 0

    maximum_unresolved_data_quality_failures: int = 0
    maximum_unresolved_reconciliation_failures: int = 0
    maximum_safety_breaches: int = 0
    maximum_entries_while_kill_switch_active: int = 0
    recovery_requires_clear_observation_and_manual_reset: bool = True

    maximum_risk_policy_violations: int = 0
    maximum_order_endpoint_events: int = 0
    maximum_ai_direct_execution_events: int = 0

    fee_and_slippage_must_be_included: bool = True
    missing_metric_fails_closed: bool = True
    all_criteria_required: bool = True
    thresholds_mutable_after_window_open: bool = False
    future_data_used_for_registration: bool = False

    def __post_init__(self):
        fixed = (
            self.registry_id == GATE_REGISTRY_ID
            and self.p10_001_policy_sha256 == P10_001_POLICY_SHA256
            and SHA256_PATTERN.fullmatch(self.p10_001_policy_sha256) is not None
            and self.candidate_sha256 == CandidateFreeze().candidate_sha256
            and SHA256_PATTERN.fullmatch(self.candidate_sha256) is not None
            and self.criteria == VALIDATION_CRITERIA
            and self.minimum_validation_days == 90
            and self.minimum_total_completed_trades == 60
            and self.minimum_completed_trades_per_symbol == 20
            and self.minimum_net_return_after_costs == "0.02"
            and self.minimum_profit_factor_after_costs == "1.10"
            and self.maximum_validation_drawdown_fraction == "0.08"
            and self.segment_count == 3
            and self.minimum_positive_segments == 2
            and self.maximum_segment_loss_fraction == "0.04"
            and self.positive_net_pnl_each_symbol_required is True
            and self.minimum_distinct_regimes_observed == 2
            and self.allowed_entry_regimes == ("TREND_UP",)
            and self.maximum_entries_outside_allowed_regimes == 0
            and self.maximum_unresolved_data_quality_failures == 0
            and self.maximum_unresolved_reconciliation_failures == 0
            and self.maximum_safety_breaches == 0
            and self.maximum_entries_while_kill_switch_active == 0
            and self.recovery_requires_clear_observation_and_manual_reset is True
            and self.maximum_risk_policy_violations == 0
            and self.maximum_order_endpoint_events == 0
            and self.maximum_ai_direct_execution_events == 0
            and self.fee_and_slippage_must_be_included is True
            and self.missing_metric_fails_closed is True
            and self.all_criteria_required is True
            and self.thresholds_mutable_after_window_open is False
            and self.future_data_used_for_registration is False
        )
        if not fixed:
            raise RegistrationError(
                "Economic gates differ from frozen P10-002 registration"
            )

        net_return = _decimal(
            self.minimum_net_return_after_costs,
            "minimum_net_return_after_costs",
            maximum="1",
        )
        profit_factor = _decimal(
            self.minimum_profit_factor_after_costs,
            "minimum_profit_factor_after_costs",
        )
        drawdown = _decimal(
            self.maximum_validation_drawdown_fraction,
            "maximum_validation_drawdown_fraction",
            maximum="1",
        )
        segment_loss = _decimal(
            self.maximum_segment_loss_fraction,
            "maximum_segment_loss_fraction",
            maximum="1",
        )
        if (
            net_return <= 0
            or profit_factor <= 1
            or drawdown <= 0
            or drawdown > Decimal("0.10")
            or segment_loss <= 0
            or self.minimum_positive_segments > self.segment_count
            or self.minimum_total_completed_trades
            < 2 * self.minimum_completed_trades_per_symbol
        ):
            raise RegistrationError("Economic gate relationships are invalid")

    def as_record(self):
        return {
            "registry_id": self.registry_id,
            "p10_001_policy_sha256": self.p10_001_policy_sha256,
            "candidate_sha256": self.candidate_sha256,
            "criteria": [item.value for item in self.criteria],
            "net_pnl_after_costs": {
                "minimum_net_return_after_costs":
                    self.minimum_net_return_after_costs,
                "minimum_profit_factor_after_costs":
                    self.minimum_profit_factor_after_costs,
                "fee_and_slippage_must_be_included":
                    self.fee_and_slippage_must_be_included,
            },
            "max_drawdown": {
                "maximum_validation_drawdown_fraction":
                    self.maximum_validation_drawdown_fraction,
            },
            "sample_size": {
                "minimum_validation_days": self.minimum_validation_days,
                "minimum_total_completed_trades":
                    self.minimum_total_completed_trades,
                "minimum_completed_trades_per_symbol":
                    self.minimum_completed_trades_per_symbol,
            },
            "consistency": {
                "segment_count": self.segment_count,
                "minimum_positive_segments": self.minimum_positive_segments,
                "maximum_segment_loss_fraction":
                    self.maximum_segment_loss_fraction,
                "positive_net_pnl_each_symbol_required":
                    self.positive_net_pnl_each_symbol_required,
            },
            "regime_stability": {
                "minimum_distinct_regimes_observed":
                    self.minimum_distinct_regimes_observed,
                "allowed_entry_regimes": list(self.allowed_entry_regimes),
                "maximum_entries_outside_allowed_regimes":
                    self.maximum_entries_outside_allowed_regimes,
            },
            "failure_recovery": {
                "maximum_unresolved_data_quality_failures":
                    self.maximum_unresolved_data_quality_failures,
                "maximum_unresolved_reconciliation_failures":
                    self.maximum_unresolved_reconciliation_failures,
                "maximum_safety_breaches": self.maximum_safety_breaches,
                "maximum_entries_while_kill_switch_active":
                    self.maximum_entries_while_kill_switch_active,
                "recovery_requires_clear_observation_and_manual_reset":
                    self.recovery_requires_clear_observation_and_manual_reset,
            },
            "risk_controls": {
                "maximum_risk_policy_violations":
                    self.maximum_risk_policy_violations,
                "maximum_order_endpoint_events":
                    self.maximum_order_endpoint_events,
                "maximum_ai_direct_execution_events":
                    self.maximum_ai_direct_execution_events,
            },
            "registration_safety": {
                "missing_metric_fails_closed": self.missing_metric_fails_closed,
                "all_criteria_required": self.all_criteria_required,
                "thresholds_mutable_after_window_open":
                    self.thresholds_mutable_after_window_open,
                "future_data_used_for_registration":
                    self.future_data_used_for_registration,
            },
        }

    @property
    def registry_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class CandidateGateRegistration:
    """P10-002 frozen state. Window/data/evaluation remain unopened."""

    registration_id: str = REGISTRATION_ID
    p10_001_policy_sha256: str = P10_001_POLICY_SHA256
    candidate: CandidateFreeze = field(default_factory=CandidateFreeze)
    gates: EconomicGateRegistry = field(default_factory=EconomicGateRegistry)

    candidate_state: CandidateFreezeState = CandidateFreezeState.FROZEN
    gate_state: GateRegistrationState = GateRegistrationState.REGISTERED
    window_state: ValidationWindowState = ValidationWindowState.NOT_OPEN
    forward_data_state: ForwardDataState = ForwardDataState.NOT_COLLECTED
    economic_evaluation_state: EconomicEvaluationState = (
        EconomicEvaluationState.NOT_EVALUATED
    )
    strategy_evidence: ValidationEvidenceState = (
        ValidationEvidenceState.INSUFFICIENT_EVIDENCE
    )

    paper_only: bool = True
    live_master_lock: str = "OFF"
    p11_locked: bool = True
    live_candidate: bool = False
    trade_permission: bool = False
    order_endpoint: bool = False
    ai_direct_execution: bool = False

    def __post_init__(self):
        if (
            self.registration_id != REGISTRATION_ID
            or self.p10_001_policy_sha256 != P10_001_POLICY_SHA256
            or not isinstance(self.candidate, CandidateFreeze)
            or not isinstance(self.gates, EconomicGateRegistry)
            or self.gates.candidate_sha256 != self.candidate.candidate_sha256
            or self.gates.p10_001_policy_sha256 != self.p10_001_policy_sha256
            or self.candidate_state is not CandidateFreezeState.FROZEN
            or self.gate_state is not GateRegistrationState.REGISTERED
            or self.window_state is not ValidationWindowState.NOT_OPEN
            or self.forward_data_state is not ForwardDataState.NOT_COLLECTED
            or self.economic_evaluation_state
            is not EconomicEvaluationState.NOT_EVALUATED
            or self.strategy_evidence
            is not ValidationEvidenceState.INSUFFICIENT_EVIDENCE
            or self.paper_only is not True
            or self.live_master_lock != "OFF"
            or self.p11_locked is not True
            or self.live_candidate is not False
            or self.trade_permission is not False
            or self.order_endpoint is not False
            or self.ai_direct_execution is not False
        ):
            raise RegistrationError("P10-002 registration bundle is invalid")

    def as_record(self):
        return {
            "registration_id": self.registration_id,
            "p10_001_policy_sha256": self.p10_001_policy_sha256,
            "candidate": self.candidate.as_record(),
            "candidate_sha256": self.candidate.candidate_sha256,
            "gates": self.gates.as_record(),
            "gate_registry_sha256": self.gates.registry_sha256,
            "states": {
                "candidate_state": self.candidate_state.value,
                "gate_state": self.gate_state.value,
                "window_state": self.window_state.value,
                "forward_data_state": self.forward_data_state.value,
                "economic_evaluation_state":
                    self.economic_evaluation_state.value,
                "strategy_evidence": self.strategy_evidence.value,
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
    def registration_sha256(self):
        return _sha256(self.as_record())


def candidate_from_record(record):
    expected = (
        "candidate_id",
        "strategy",
        "market_scope",
        "paper_economics",
        "risk_policy",
        "selection_provenance",
        "safety",
    )
    _strict_keys(record, expected, "Candidate")
    candidate = CandidateFreeze()
    if candidate.as_record() != record:
        raise RegistrationError("Candidate record differs from frozen baseline")
    return candidate


def gate_registry_from_record(record):
    expected = (
        "registry_id",
        "p10_001_policy_sha256",
        "candidate_sha256",
        "criteria",
        "net_pnl_after_costs",
        "max_drawdown",
        "sample_size",
        "consistency",
        "regime_stability",
        "failure_recovery",
        "risk_controls",
        "registration_safety",
    )
    _strict_keys(record, expected, "Gate registry")
    gates = EconomicGateRegistry()
    if gates.as_record() != record:
        raise RegistrationError("Gate registry record differs from frozen gates")
    return gates


def registration_from_record(record):
    expected = (
        "registration_id",
        "p10_001_policy_sha256",
        "candidate",
        "candidate_sha256",
        "gates",
        "gate_registry_sha256",
        "states",
        "safety",
    )
    _strict_keys(record, expected, "Registration")
    candidate = candidate_from_record(record["candidate"])
    gates = gate_registry_from_record(record["gates"])
    registration = CandidateGateRegistration(candidate=candidate, gates=gates)
    if registration.as_record() != record:
        raise RegistrationError("Registration record is inconsistent")
    return registration
