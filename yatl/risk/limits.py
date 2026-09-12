"""Deterministic P4 cash, notional and gross-exposure entry limits."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from .contracts import UNSIGNED_DECIMAL_PATTERN
from .sizing import BASIS_POINTS, FEE_BPS, PositionSize


class RiskLimitError(ValueError):
    """A P4 limit input or assessment is invalid or inconsistent."""


class LimitStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


class LimitReason(str, Enum):
    WITHIN_LIMITS = "WITHIN_LIMITS"
    CASH_INSUFFICIENT = "CASH_INSUFFICIENT"
    NOTIONAL_OR_EXPOSURE_LIMIT = "NOTIONAL_OR_EXPOSURE_LIMIT"


def _values(position_size):
    if not isinstance(position_size, PositionSize):
        raise RiskLimitError("Limits require a valid position-size result")
    request = position_size.request
    state = request.portfolio
    policy = request.policy
    if state.open_positions != 0 or Decimal(state.position_quantity) != 0:
        raise RiskLimitError("Entry limit assessment requires a flat portfolio")

    with localcontext() as context:
        context.prec = 256
        quantity = Decimal(position_size.quantity)
        entry_execution = Decimal(position_size.entry_execution_price)
        equity = Decimal(state.equity_quote)
        cash = Decimal(state.cash_quote)
        entry_notional = quantity * entry_execution
        entry_fee = entry_notional * FEE_BPS / BASIS_POINTS
        cash_required = entry_notional + entry_fee
        position_limit = equity * Decimal(policy.max_position_fraction)
        gross_before = Decimal(state.position_quantity) * Decimal(state.mark_price)
        gross_after = gross_before + entry_notional
        gross_limit = equity * Decimal(policy.max_gross_exposure_fraction)

        if entry_notional > position_limit or gross_after > gross_limit:
            status = LimitStatus.REJECT
            reason = LimitReason.NOTIONAL_OR_EXPOSURE_LIMIT
        elif cash_required > cash:
            status = LimitStatus.REJECT
            reason = LimitReason.CASH_INSUFFICIENT
        else:
            status = LimitStatus.PASS
            reason = LimitReason.WITHIN_LIMITS
        return {
            "status": status,
            "reason": reason,
            "entry_notional_quote": entry_notional,
            "entry_fee_quote": entry_fee,
            "cash_required_quote": cash_required,
            "position_limit_quote": position_limit,
            "gross_exposure_before_quote": gross_before,
            "gross_exposure_after_quote": gross_after,
            "gross_exposure_limit_quote": gross_limit,
        }


def _canonical(number):
    return format(number, "f")


@dataclass(frozen=True, slots=True)
class EntryLimitAssessment:
    """Immutable limit evidence; final approval remains a later P4 responsibility."""

    position_size: PositionSize
    status: LimitStatus
    reason: LimitReason
    entry_notional_quote: str
    entry_fee_quote: str
    cash_required_quote: str
    position_limit_quote: str
    gross_exposure_before_quote: str
    gross_exposure_after_quote: str
    gross_exposure_limit_quote: str

    def __post_init__(self):
        expected = _values(self.position_size)
        if self.status is not expected["status"] or self.reason is not expected["reason"]:
            raise RiskLimitError("Limit status or reason is inconsistent")
        fields = (
            "entry_notional_quote",
            "entry_fee_quote",
            "cash_required_quote",
            "position_limit_quote",
            "gross_exposure_before_quote",
            "gross_exposure_after_quote",
            "gross_exposure_limit_quote",
        )
        for name in fields:
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or UNSIGNED_DECIMAL_PATTERN.fullmatch(value) is None
                or value != _canonical(expected[name])
            ):
                raise RiskLimitError("Limit assessment is noncanonical or inconsistent")

    @property
    def request_sha256(self):
        return self.position_size.request_sha256


def assess_entry_limits(position_size):
    """Check cash and both frozen 25% caps without emitting an approval."""
    values = _values(position_size)
    return EntryLimitAssessment(
        position_size=position_size,
        status=values.pop("status"),
        reason=values.pop("reason"),
        **{name: _canonical(value) for name, value in values.items()},
    )
