"""P10-001 preregistration-only forward/Paper validation contracts."""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum


VALIDATION_POLICY_ID = "P10_VALIDATION_V1"
VALIDATION_SCHEMA_VERSION = 1

P4_RISK_PER_TRADE_FRACTION = "0.01"
P4_MAX_SESSION_LOSS_FRACTION = "0.02"
P4_MAX_DRAWDOWN_FRACTION = "0.10"
P4_MAX_CONSECUTIVE_LOSSES = 3

_HEX = frozenset("0123456789abcdef")


class ValidationContractError(ValueError):
    """P10 preregistration material violates the frozen validation boundary."""


class ValidationCriterion(str, Enum):
    NET_PNL_AFTER_COSTS = "NET_PNL_AFTER_COSTS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    SAMPLE_SIZE = "SAMPLE_SIZE"
    CONSISTENCY = "CONSISTENCY"
    REGIME_STABILITY = "REGIME_STABILITY"
    FAILURE_RECOVERY = "FAILURE_RECOVERY"
    RISK_CONTROLS = "RISK_CONTROLS"


VALIDATION_CRITERIA = (
    ValidationCriterion.NET_PNL_AFTER_COSTS,
    ValidationCriterion.MAX_DRAWDOWN,
    ValidationCriterion.SAMPLE_SIZE,
    ValidationCriterion.CONSISTENCY,
    ValidationCriterion.REGIME_STABILITY,
    ValidationCriterion.FAILURE_RECOVERY,
    ValidationCriterion.RISK_CONTROLS,
)


class ValidationEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RegistrationState(str, Enum):
    PREREGISTRATION_ONLY = "PREREGISTRATION_ONLY"


class CandidateState(str, Enum):
    UNFROZEN_PENDING_P10_002 = "UNFROZEN_PENDING_P10_002"


class ThresholdState(str, Enum):
    UNREGISTERED_PENDING_P10_002 = "UNREGISTERED_PENDING_P10_002"


class WindowState(str, Enum):
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


def _strict_keys(record, expected, label):
    if (
        not isinstance(record, dict)
        or tuple(sorted(record)) != tuple(sorted(expected))
    ):
        raise ValidationContractError(f"{label} fields are invalid")


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """Frozen P10-001 charter boundary before candidate/gate/window registration."""

    policy_id: str = VALIDATION_POLICY_ID
    mode: str = "PREREGISTRATION_ONLY"
    criteria: tuple[ValidationCriterion, ...] = VALIDATION_CRITERIA

    forward_only: bool = True
    new_data_only: bool = True
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    long_only: bool = True

    net_pnl_after_fee_slippage_required: bool = True
    risk_adjusted_persistence_required: bool = True
    point_in_time_only: bool = True
    no_lookahead_required: bool = True
    no_post_open_tuning: bool = True

    threshold_registration_required_before_window: bool = True
    candidate_freeze_required_before_window: bool = True
    window_seal_required_before_data: bool = True

    thresholds_registered: bool = False
    candidate_frozen: bool = False
    validation_window_open: bool = False
    forward_data_collection_allowed: bool = False
    economic_evaluation_allowed: bool = False
    strategy_evidence_upgrade_allowed: bool = False

    inherited_risk_per_trade_fraction: str = P4_RISK_PER_TRADE_FRACTION
    inherited_max_session_loss_fraction: str = P4_MAX_SESSION_LOSS_FRACTION
    inherited_max_drawdown_fraction: str = P4_MAX_DRAWDOWN_FRACTION
    inherited_max_consecutive_losses: int = P4_MAX_CONSECUTIVE_LOSSES

    allow_short: bool = False
    allow_margin: bool = False
    allow_futures: bool = False
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_credentials: bool = False
    allow_network_transport: bool = False
    allow_upstream_mutation: bool = False
    allow_execution_import: bool = False
    allow_risk_authorization_mutation: bool = False
    allow_quantity_authority: bool = False
    allow_trade_permission: bool = False
    allow_order_endpoint: bool = False
    allow_ai_direct_execution: bool = False
    allow_live_candidate: bool = False

    schema_version: int = VALIDATION_SCHEMA_VERSION

    def __post_init__(self):
        fixed = (
            self.policy_id == VALIDATION_POLICY_ID
            and self.mode == "PREREGISTRATION_ONLY"
            and self.criteria == VALIDATION_CRITERIA
            and self.forward_only is True
            and self.new_data_only is True
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.long_only is True
            and self.net_pnl_after_fee_slippage_required is True
            and self.risk_adjusted_persistence_required is True
            and self.point_in_time_only is True
            and self.no_lookahead_required is True
            and self.no_post_open_tuning is True
            and self.threshold_registration_required_before_window is True
            and self.candidate_freeze_required_before_window is True
            and self.window_seal_required_before_data is True
            and self.thresholds_registered is False
            and self.candidate_frozen is False
            and self.validation_window_open is False
            and self.forward_data_collection_allowed is False
            and self.economic_evaluation_allowed is False
            and self.strategy_evidence_upgrade_allowed is False
            and self.inherited_risk_per_trade_fraction
            == P4_RISK_PER_TRADE_FRACTION
            and self.inherited_max_session_loss_fraction
            == P4_MAX_SESSION_LOSS_FRACTION
            and self.inherited_max_drawdown_fraction
            == P4_MAX_DRAWDOWN_FRACTION
            and type(self.inherited_max_consecutive_losses) is int
            and self.inherited_max_consecutive_losses
            == P4_MAX_CONSECUTIVE_LOSSES
            and self.allow_short is False
            and self.allow_margin is False
            and self.allow_futures is False
            and self.allow_leverage is False
            and self.allow_withdrawal is False
            and self.allow_credentials is False
            and self.allow_network_transport is False
            and self.allow_upstream_mutation is False
            and self.allow_execution_import is False
            and self.allow_risk_authorization_mutation is False
            and self.allow_quantity_authority is False
            and self.allow_trade_permission is False
            and self.allow_order_endpoint is False
            and self.allow_ai_direct_execution is False
            and self.allow_live_candidate is False
            and self.schema_version == VALIDATION_SCHEMA_VERSION
        )
        if not fixed:
            raise ValidationContractError(
                "Validation policy differs from frozen P10-001 preregistration"
            )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "criteria": [item.value for item in self.criteria],
            "validation_semantics": {
                "forward_only": self.forward_only,
                "new_data_only": self.new_data_only,
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "spot_only": self.spot_only,
                "long_only": self.long_only,
                "net_pnl_after_fee_slippage_required":
                    self.net_pnl_after_fee_slippage_required,
                "risk_adjusted_persistence_required":
                    self.risk_adjusted_persistence_required,
                "point_in_time_only": self.point_in_time_only,
                "no_lookahead_required": self.no_lookahead_required,
                "no_post_open_tuning": self.no_post_open_tuning,
            },
            "prerequisites": {
                "threshold_registration_required_before_window":
                    self.threshold_registration_required_before_window,
                "candidate_freeze_required_before_window":
                    self.candidate_freeze_required_before_window,
                "window_seal_required_before_data":
                    self.window_seal_required_before_data,
                "thresholds_registered": self.thresholds_registered,
                "candidate_frozen": self.candidate_frozen,
                "validation_window_open": self.validation_window_open,
                "forward_data_collection_allowed":
                    self.forward_data_collection_allowed,
                "economic_evaluation_allowed":
                    self.economic_evaluation_allowed,
                "strategy_evidence_upgrade_allowed":
                    self.strategy_evidence_upgrade_allowed,
            },
            "inherited_risk_limits": {
                "risk_per_trade_fraction":
                    self.inherited_risk_per_trade_fraction,
                "max_session_loss_fraction":
                    self.inherited_max_session_loss_fraction,
                "max_drawdown_fraction":
                    self.inherited_max_drawdown_fraction,
                "max_consecutive_losses":
                    self.inherited_max_consecutive_losses,
            },
            "safety": {
                "allow_short": self.allow_short,
                "allow_margin": self.allow_margin,
                "allow_futures": self.allow_futures,
                "allow_leverage": self.allow_leverage,
                "allow_withdrawal": self.allow_withdrawal,
                "allow_credentials": self.allow_credentials,
                "allow_network_transport": self.allow_network_transport,
                "allow_upstream_mutation": self.allow_upstream_mutation,
                "allow_execution_import": self.allow_execution_import,
                "allow_risk_authorization_mutation":
                    self.allow_risk_authorization_mutation,
                "allow_quantity_authority": self.allow_quantity_authority,
                "allow_trade_permission": self.allow_trade_permission,
                "allow_order_endpoint": self.allow_order_endpoint,
                "allow_ai_direct_execution": self.allow_ai_direct_execution,
                "allow_live_candidate": self.allow_live_candidate,
            },
        }

    @property
    def policy_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class ValidationCharter:
    """Canonical P10-001 proof that validation has not started yet."""

    registration_id: str
    registered_at_ms: int
    policy: ValidationPolicy = field(default_factory=ValidationPolicy)
    registration_state: RegistrationState = RegistrationState.PREREGISTRATION_ONLY
    candidate_state: CandidateState = CandidateState.UNFROZEN_PENDING_P10_002
    threshold_state: ThresholdState = (
        ThresholdState.UNREGISTERED_PENDING_P10_002
    )
    window_state: WindowState = WindowState.NOT_OPEN
    forward_data_state: ForwardDataState = ForwardDataState.NOT_COLLECTED
    economic_evaluation_state: EconomicEvaluationState = (
        EconomicEvaluationState.NOT_EVALUATED
    )
    strategy_evidence: ValidationEvidenceState = (
        ValidationEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = VALIDATION_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != VALIDATION_SCHEMA_VERSION
            or not isinstance(self.registration_id, str)
            or not 1 <= len(self.registration_id) <= 96
            or not self.registration_id.startswith("P10-REG-")
            or type(self.registered_at_ms) is not int
            or self.registered_at_ms < 0
            or not isinstance(self.policy, ValidationPolicy)
            or self.registration_state
            is not RegistrationState.PREREGISTRATION_ONLY
            or self.candidate_state
            is not CandidateState.UNFROZEN_PENDING_P10_002
            or self.threshold_state
            is not ThresholdState.UNREGISTERED_PENDING_P10_002
            or self.window_state is not WindowState.NOT_OPEN
            or self.forward_data_state is not ForwardDataState.NOT_COLLECTED
            or self.economic_evaluation_state
            is not EconomicEvaluationState.NOT_EVALUATED
            or self.strategy_evidence
            is not ValidationEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise ValidationContractError(
                "Validation charter violates P10-001 preregistration state"
            )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "registration_id": self.registration_id,
            "registered_at_ms": self.registered_at_ms,
            "policy_sha256": self.policy.policy_sha256,
            "registration_state": self.registration_state.value,
            "candidate_state": self.candidate_state.value,
            "threshold_state": self.threshold_state.value,
            "window_state": self.window_state.value,
            "forward_data_state": self.forward_data_state.value,
            "economic_evaluation_state": self.economic_evaluation_state.value,
            "strategy_evidence": self.strategy_evidence.value,
            "criteria": [item.value for item in self.policy.criteria],
            "paper_only": self.policy.paper_only,
            "live_master_lock": self.policy.live_master_lock,
            "forward_only": self.policy.forward_only,
            "new_data_only": self.policy.new_data_only,
            "trade_permission": self.policy.allow_trade_permission,
            "order_endpoint": self.policy.allow_order_endpoint,
            "ai_direct_execution": self.policy.allow_ai_direct_execution,
            "live_candidate": self.policy.allow_live_candidate,
        }

    @property
    def charter_sha256(self):
        return _sha256(self.as_record())


def validation_policy_from_record(record):
    """Strictly reconstruct the only valid P10-001 policy record."""

    expected = (
        "schema_version",
        "policy_id",
        "mode",
        "criteria",
        "validation_semantics",
        "prerequisites",
        "inherited_risk_limits",
        "safety",
    )
    _strict_keys(record, expected, "Validation policy")
    policy = ValidationPolicy()
    if policy.as_record() != record:
        raise ValidationContractError("Validation policy record differs from frozen policy")
    return policy


def validation_charter_from_record(record):
    """Strictly reconstruct a P10-001 charter without accepting authority smuggling."""

    expected = (
        "schema_version",
        "registration_id",
        "registered_at_ms",
        "policy_sha256",
        "registration_state",
        "candidate_state",
        "threshold_state",
        "window_state",
        "forward_data_state",
        "economic_evaluation_state",
        "strategy_evidence",
        "criteria",
        "paper_only",
        "live_master_lock",
        "forward_only",
        "new_data_only",
        "trade_permission",
        "order_endpoint",
        "ai_direct_execution",
        "live_candidate",
    )
    _strict_keys(record, expected, "Validation charter")
    try:
        charter = ValidationCharter(
            registration_id=record["registration_id"],
            registered_at_ms=record["registered_at_ms"],
            policy=ValidationPolicy(),
            registration_state=RegistrationState(record["registration_state"]),
            candidate_state=CandidateState(record["candidate_state"]),
            threshold_state=ThresholdState(record["threshold_state"]),
            window_state=WindowState(record["window_state"]),
            forward_data_state=ForwardDataState(record["forward_data_state"]),
            economic_evaluation_state=EconomicEvaluationState(
                record["economic_evaluation_state"]
            ),
            strategy_evidence=ValidationEvidenceState(record["strategy_evidence"]),
            schema_version=record["schema_version"],
        )
    except (ValueError, TypeError):
        raise ValidationContractError("Validation charter record is invalid") from None

    if charter.as_record() != record:
        raise ValidationContractError("Validation charter record is inconsistent")
    return charter
