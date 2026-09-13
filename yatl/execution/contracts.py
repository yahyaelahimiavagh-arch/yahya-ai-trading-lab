"""Immutable P5 local Paper contracts with no external execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum

from yatl.backtest import IntentAction
from yatl.risk import (
    RiskAdapterError,
    RiskAuthorization,
    RiskDisposition,
)
from yatl.strategy import StrategyAction


EXECUTION_POLICY_ID = "P5_LOCAL_PAPER_V1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ExecutionContractError(ValueError):
    """A P5 local Paper request violates the frozen execution boundary."""


class RecoveryStatus(str, Enum):
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    READY = "READY"


class RecoveryReason(str, Enum):
    FAIL_CLOSED_STARTUP = "FAIL_CLOSED_STARTUP"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    RECONCILIATION_PASSED = "RECONCILIATION_PASSED"


@dataclass(frozen=True, slots=True)
class LocalPaperExecutionPolicy:
    """Frozen P5 boundary; it can authorize only an in-process Paper effect."""

    policy_id: str = EXECUTION_POLICY_ID
    execution_mode: str = "LOCAL_PAPER"
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    long_only: bool = True
    allow_external_transport: bool = False
    allow_credentials: bool = False
    allow_order_endpoint: bool = False
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_ai_direct_execution: bool = False

    def __post_init__(self):
        fixed = (
            self.policy_id == EXECUTION_POLICY_ID
            and self.execution_mode == "LOCAL_PAPER"
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.long_only is True
            and self.allow_external_transport is False
            and self.allow_credentials is False
            and self.allow_order_endpoint is False
            and self.allow_leverage is False
            and self.allow_withdrawal is False
            and self.allow_ai_direct_execution is False
        )
        if not fixed:
            raise ExecutionContractError(
                "Execution policy differs from the frozen local Paper policy"
            )


@dataclass(frozen=True, slots=True)
class RecoveryReadiness:
    """Evidence that startup reconciliation has, or has not, made P5 ready."""

    status: RecoveryStatus = RecoveryStatus.RECOVERY_REQUIRED
    reason: RecoveryReason = RecoveryReason.FAIL_CLOSED_STARTUP
    reconciliation_sha256: str | None = None

    def __post_init__(self):
        if not isinstance(self.status, RecoveryStatus) or not isinstance(
            self.reason, RecoveryReason
        ):
            raise ExecutionContractError("Recovery readiness identity is invalid")
        digest_valid = (
            isinstance(self.reconciliation_sha256, str)
            and SHA256_PATTERN.fullmatch(self.reconciliation_sha256) is not None
        )
        valid = (
            self.status is RecoveryStatus.RECOVERY_REQUIRED
            and self.reason is RecoveryReason.FAIL_CLOSED_STARTUP
            and self.reconciliation_sha256 is None
        ) or (
            self.status is RecoveryStatus.RECOVERY_REQUIRED
            and self.reason is RecoveryReason.RECONCILIATION_FAILED
            and digest_valid
        ) or (
            self.status is RecoveryStatus.READY
            and self.reason is RecoveryReason.RECONCILIATION_PASSED
            and digest_valid
        )
        if not valid:
            raise ExecutionContractError(
                "Recovery status, reason and reconciliation evidence disagree"
            )

    @property
    def readiness_sha256(self):
        payload = {
            "schema_version": 1,
            "status": self.status.value,
            "reason": self.reason.value,
            "reconciliation_sha256": self.reconciliation_sha256,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExecutionDisposition(str, Enum):
    NO_ACTION = "NO_ACTION"
    BLOCKED = "BLOCKED"
    ACCEPT_LOCAL_PAPER = "ACCEPT_LOCAL_PAPER"


class ExecutionReason(str, Enum):
    NO_STRATEGY_ACTION = "NO_STRATEGY_ACTION"
    RISK_NOT_APPROVED = "RISK_NOT_APPROVED"
    RECOVERY_NOT_READY = "RECOVERY_NOT_READY"
    LOCAL_PAPER_AUTHORIZED = "LOCAL_PAPER_AUTHORIZED"


def _validate_authorization(authorization):
    if not isinstance(authorization, RiskAuthorization):
        raise ExecutionContractError("Complete P4 authorization is required")
    try:
        reconstructed = RiskAuthorization(
            authorization.request,
            authorization.managed_state,
            authorization.kill_switch_state,
            authorization.circuit_assessment,
            authorization.protective_assessment,
            authorization.decision,
        )
    except (RiskAdapterError, TypeError, ValueError):
        raise ExecutionContractError(
            "P4 authorization failed deterministic reconstruction"
        ) from None
    if (
        reconstructed != authorization
        or reconstructed.authorization_sha256 != authorization.authorization_sha256
    ):
        raise ExecutionContractError("P4 authorization identity changed")


def _expected_execution(authorization, readiness):
    decision = authorization.decision
    strategy_action = decision.request.strategy_decision.action
    if decision.disposition is RiskDisposition.NO_ACTION:
        return (
            ExecutionDisposition.NO_ACTION,
            ExecutionReason.NO_STRATEGY_ACTION,
            IntentAction.HOLD,
            None,
        )
    if decision.disposition is RiskDisposition.REJECT:
        return (
            ExecutionDisposition.BLOCKED,
            ExecutionReason.RISK_NOT_APPROVED,
            IntentAction.HOLD,
            None,
        )
    if readiness.status is not RecoveryStatus.READY:
        return (
            ExecutionDisposition.BLOCKED,
            ExecutionReason.RECOVERY_NOT_READY,
            IntentAction.HOLD,
            None,
        )
    action = {
        StrategyAction.ENTER_LONG: IntentAction.ENTER_LONG,
        StrategyAction.EXIT_LONG: IntentAction.EXIT_LONG,
    }.get(strategy_action)
    if action is None or decision.approved_quantity is None:
        raise ExecutionContractError("P4 approval has no valid local Paper action")
    return (
        ExecutionDisposition.ACCEPT_LOCAL_PAPER,
        ExecutionReason.LOCAL_PAPER_AUTHORIZED,
        action,
        decision.approved_quantity,
    )


@dataclass(frozen=True, slots=True)
class LocalPaperExecutionDecision:
    """P5 routing result; acceptance is local-only and performs no effect."""

    authorization: RiskAuthorization
    readiness: RecoveryReadiness
    disposition: ExecutionDisposition
    reason: ExecutionReason
    action: IntentAction
    approved_quantity: str | None = None
    policy: LocalPaperExecutionPolicy = field(
        default_factory=LocalPaperExecutionPolicy
    )

    def __post_init__(self):
        _validate_authorization(self.authorization)
        try:
            reconstructed_readiness = RecoveryReadiness(
                self.readiness.status,
                self.readiness.reason,
                self.readiness.reconciliation_sha256,
            )
            reconstructed_policy = LocalPaperExecutionPolicy(
                **{
                    name: getattr(self.policy, name)
                    for name in self.policy.__dataclass_fields__
                }
            )
        except (AttributeError, ExecutionContractError, TypeError, ValueError):
            raise ExecutionContractError(
                "Recovery readiness or local Paper policy failed reconstruction"
            ) from None
        if (
            not isinstance(self.readiness, RecoveryReadiness)
            or not isinstance(self.disposition, ExecutionDisposition)
            or not isinstance(self.reason, ExecutionReason)
            or not isinstance(self.action, IntentAction)
            or not isinstance(self.policy, LocalPaperExecutionPolicy)
            or reconstructed_readiness != self.readiness
            or reconstructed_policy != self.policy
        ):
            raise ExecutionContractError("Local Paper decision identity is invalid")
        expected = _expected_execution(self.authorization, self.readiness)
        actual = (
            self.disposition,
            self.reason,
            self.action,
            self.approved_quantity,
        )
        if actual != expected:
            raise ExecutionContractError(
                "Execution disposition, reason, action and quantity disagree"
            )

    @property
    def authorization_sha256(self):
        return self.authorization.authorization_sha256

    @property
    def decision_sha256(self):
        payload = {
            "schema_version": 1,
            "authorization_sha256": self.authorization_sha256,
            "readiness_sha256": self.readiness.readiness_sha256,
            "policy": {
                name: getattr(self.policy, name)
                for name in self.policy.__dataclass_fields__
            },
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "action": self.action.value,
            "approved_quantity": self.approved_quantity,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assess_local_paper_authorization(
    authorization,
    readiness=None,
    policy=None,
):
    """Assess complete P4 evidence without executing or persisting anything."""

    _validate_authorization(authorization)
    if readiness is None:
        readiness = RecoveryReadiness()
    if policy is None:
        policy = LocalPaperExecutionPolicy()
    if not isinstance(readiness, RecoveryReadiness) or not isinstance(
        policy, LocalPaperExecutionPolicy
    ):
        raise ExecutionContractError("Recovery readiness or policy is invalid")
    disposition, reason, action, quantity = _expected_execution(
        authorization, readiness
    )
    return LocalPaperExecutionDecision(
        authorization,
        readiness,
        disposition,
        reason,
        action,
        quantity,
        policy,
    )
