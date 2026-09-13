"""Deterministic P4 protective-stop, cost and worst-loss entry gate."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from .contracts import SIGNED_DECIMAL_PATTERN, UNSIGNED_DECIMAL_PATTERN
from .limits import EntryLimitAssessment, LimitStatus
from .sizing import BASIS_POINTS, FEE_BPS, SLIPPAGE_BPS


class ProtectiveGateError(ValueError):
    """Protective gate input or evidence is invalid or inconsistent."""


class ProtectiveStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


class ProtectiveReason(str, Enum):
    PROTECTIVE_GATE_PASSED = "PROTECTIVE_GATE_PASSED"
    PRIOR_LIMIT_REJECTED = "PRIOR_LIMIT_REJECTED"
    INVALID_PROTECTIVE_LEVELS = "INVALID_PROTECTIVE_LEVELS"
    NON_POSITIVE_POST_COST_REWARD = "NON_POSITIVE_POST_COST_REWARD"
    PLANNED_LOSS_EXCEEDS_BUDGET = "PLANNED_LOSS_EXCEEDS_BUDGET"


def _canonical(number):
    return format(number, "f")


def _values(limit_assessment):
    if not isinstance(limit_assessment, EntryLimitAssessment):
        raise ProtectiveGateError("Protective gate requires a valid limit assessment")
    size = limit_assessment.position_size
    setup = size.request.strategy_decision.setup
    if setup is None:
        raise ProtectiveGateError("Protective gate requires an entry setup")

    with localcontext() as context:
        context.prec = 256
        quantity = Decimal(size.quantity)
        entry_reference = Decimal(setup.reference_price)
        stop_reference = Decimal(setup.invalidation_price)
        target_reference = Decimal(setup.target_price)
        fee_rate = FEE_BPS / BASIS_POINTS
        slippage_rate = SLIPPAGE_BPS / BASIS_POINTS
        entry_execution = entry_reference * (Decimal(1) + slippage_rate)
        stop_execution = stop_reference * (Decimal(1) - slippage_rate)
        target_execution = target_reference * (Decimal(1) - slippage_rate)
        entry_fee = quantity * entry_execution * fee_rate
        stop_fee = quantity * stop_execution * fee_rate
        target_fee = quantity * target_execution * fee_rate
        worst_loss = (
            quantity * (entry_execution - stop_execution) + entry_fee + stop_fee
        )
        net_reward = (
            quantity * (target_execution - entry_execution) - entry_fee - target_fee
        )
        risk_budget = Decimal(size.risk_budget_quote)
        levels_valid = (
            stop_reference < entry_reference < target_reference
            and stop_execution > 0
            and stop_execution < entry_execution
        )
        if limit_assessment.status is not LimitStatus.PASS:
            status = ProtectiveStatus.REJECT
            reason = ProtectiveReason.PRIOR_LIMIT_REJECTED
        elif not levels_valid:
            status = ProtectiveStatus.REJECT
            reason = ProtectiveReason.INVALID_PROTECTIVE_LEVELS
        elif worst_loss > risk_budget:
            status = ProtectiveStatus.REJECT
            reason = ProtectiveReason.PLANNED_LOSS_EXCEEDS_BUDGET
        elif net_reward <= 0:
            status = ProtectiveStatus.REJECT
            reason = ProtectiveReason.NON_POSITIVE_POST_COST_REWARD
        else:
            status = ProtectiveStatus.PASS
            reason = ProtectiveReason.PROTECTIVE_GATE_PASSED

        return {
            "status": status,
            "reason": reason,
            "quantity": quantity,
            "reference_entry_price": entry_reference,
            "reference_stop_price": stop_reference,
            "reference_target_price": target_reference,
            "entry_execution_price": entry_execution,
            "stop_execution_price": stop_execution,
            "target_execution_price": target_execution,
            "entry_fee_quote": entry_fee,
            "stop_fee_quote": stop_fee,
            "target_fee_quote": target_fee,
            "worst_loss_quote": worst_loss,
            "risk_budget_quote": risk_budget,
            "net_reward_quote": net_reward,
        }


@dataclass(frozen=True, slots=True)
class ProtectiveAssessment:
    """Tamper-checked gate evidence; no approval or execution is emitted."""

    limit_assessment: EntryLimitAssessment
    status: ProtectiveStatus
    reason: ProtectiveReason
    quantity: str
    reference_entry_price: str
    reference_stop_price: str
    reference_target_price: str
    entry_execution_price: str
    stop_execution_price: str
    target_execution_price: str
    entry_fee_quote: str
    stop_fee_quote: str
    target_fee_quote: str
    worst_loss_quote: str
    risk_budget_quote: str
    net_reward_quote: str

    def __post_init__(self):
        expected = _values(self.limit_assessment)
        if self.status is not expected["status"] or self.reason is not expected["reason"]:
            raise ProtectiveGateError("Protective status or reason is inconsistent")
        unsigned = (
            "quantity",
            "reference_entry_price",
            "reference_stop_price",
            "reference_target_price",
            "entry_execution_price",
            "stop_execution_price",
            "target_execution_price",
            "entry_fee_quote",
            "stop_fee_quote",
            "target_fee_quote",
            "worst_loss_quote",
            "risk_budget_quote",
        )
        signed = ("net_reward_quote",)
        for name in unsigned + signed:
            value = getattr(self, name)
            pattern = SIGNED_DECIMAL_PATTERN if name in signed else UNSIGNED_DECIMAL_PATTERN
            if (
                not isinstance(value, str)
                or pattern.fullmatch(value) is None
                or value != _canonical(expected[name])
            ):
                raise ProtectiveGateError(
                    "Protective assessment is noncanonical or inconsistent"
                )
        if self.worst_loss_quote != self.limit_assessment.position_size.planned_loss_quote:
            raise ProtectiveGateError("Worst loss does not match accepted sizing")

    @property
    def request_sha256(self):
        return self.limit_assessment.request_sha256

    @property
    def gate_sha256(self):
        payload = {
            "schema_version": 1,
            "request_sha256": self.request_sha256,
            "limit_status": self.limit_assessment.status.value,
            "limit_reason": self.limit_assessment.reason.value,
            **{
                name: (
                    getattr(self, name).value
                    if isinstance(getattr(self, name), Enum)
                    else getattr(self, name)
                )
                for name in self.__dataclass_fields__
                if name != "limit_assessment"
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assess_protective_entry(limit_assessment):
    """Validate stop, post-cost reward and worst loss without granting approval."""
    values = _values(limit_assessment)
    return ProtectiveAssessment(
        limit_assessment=limit_assessment,
        status=values.pop("status"),
        reason=values.pop("reason"),
        **{name: _canonical(value) for name, value in values.items()},
    )
