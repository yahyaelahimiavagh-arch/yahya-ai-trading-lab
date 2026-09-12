"""Exact, cost-aware P4 paper position sizing from a frozen loss budget."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, localcontext

from yatl.strategy import EvidenceLabel, StrategyAction

from .contracts import RiskRequest, UNSIGNED_DECIMAL_PATTERN


FEE_BPS = Decimal("10")
SLIPPAGE_BPS = Decimal("5")
QUANTITY_STEP = Decimal("0.000001")
BASIS_POINTS = Decimal("10000")


class RiskSizingError(ValueError):
    """A P4 entry cannot be sized safely under the frozen research policy."""


def _entry_values(request):
    if not isinstance(request, RiskRequest):
        raise RiskSizingError("Sizing requires a valid risk request")
    decision = request.strategy_decision
    if (
        decision.action is not StrategyAction.ENTER_LONG
        or decision.setup is None
        or request.evidence_label is not EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH
        or request.portfolio.kill_switch_active
        or request.portfolio.open_positions != 0
    ):
        raise RiskSizingError("Entry request is not eligible for sizing")

    with localcontext() as context:
        context.prec = 256
        equity = Decimal(request.portfolio.equity_quote)
        entry = Decimal(decision.setup.reference_price)
        stop = Decimal(decision.setup.invalidation_price)
        risk_fraction = Decimal(request.policy.risk_per_trade_fraction)
        fee_rate = FEE_BPS / BASIS_POINTS
        slippage_rate = SLIPPAGE_BPS / BASIS_POINTS

        risk_budget = equity * risk_fraction
        entry_execution = entry * (Decimal(1) + slippage_rate)
        stop_execution = stop * (Decimal(1) - slippage_rate)
        if stop_execution <= 0 or stop_execution >= entry_execution:
            raise RiskSizingError("Cost-adjusted entry and stop are invalid")
        fee_per_unit = (entry_execution + stop_execution) * fee_rate
        slippage_per_unit = (entry + stop) * slippage_rate
        loss_per_unit = entry_execution - stop_execution + fee_per_unit
        if risk_budget <= 0 or loss_per_unit <= 0:
            raise RiskSizingError("Risk budget or loss per unit is invalid")

        steps = (risk_budget / loss_per_unit / QUANTITY_STEP).to_integral_value(
            rounding=ROUND_FLOOR
        )
        quantity = steps * QUANTITY_STEP
        if quantity <= 0:
            raise RiskSizingError("Risk budget is below the minimum quantity step")
        planned_loss = quantity * loss_per_unit
        total_fee = quantity * fee_per_unit
        total_slippage = quantity * slippage_per_unit
        if planned_loss > risk_budget:
            raise RiskSizingError("Rounded quantity exceeds the loss budget")
        return {
            "quantity": quantity,
            "risk_budget_quote": risk_budget,
            "entry_execution_price": entry_execution,
            "stop_execution_price": stop_execution,
            "loss_per_unit_quote": loss_per_unit,
            "planned_loss_quote": planned_loss,
            "fee_quote": total_fee,
            "slippage_quote": total_slippage,
        }


def _canonical(number):
    return format(number, "f")


@dataclass(frozen=True, slots=True)
class PositionSize:
    """A reproducible sizing result; exposure approval belongs to P4-003."""

    request: RiskRequest
    quantity: str
    risk_budget_quote: str
    entry_execution_price: str
    stop_execution_price: str
    loss_per_unit_quote: str
    planned_loss_quote: str
    fee_quote: str
    slippage_quote: str

    def __post_init__(self):
        expected = _entry_values(self.request)
        actual = {
            "quantity": self.quantity,
            "risk_budget_quote": self.risk_budget_quote,
            "entry_execution_price": self.entry_execution_price,
            "stop_execution_price": self.stop_execution_price,
            "loss_per_unit_quote": self.loss_per_unit_quote,
            "planned_loss_quote": self.planned_loss_quote,
            "fee_quote": self.fee_quote,
            "slippage_quote": self.slippage_quote,
        }
        if any(
            not isinstance(value, str)
            or UNSIGNED_DECIMAL_PATTERN.fullmatch(value) is None
            or value != _canonical(expected[name])
            for name, value in actual.items()
        ):
            raise RiskSizingError("Position-size result is noncanonical or inconsistent")
        with localcontext() as context:
            context.prec = 256
            if Decimal(self.planned_loss_quote) > Decimal(self.risk_budget_quote):
                raise RiskSizingError("Position-size result exceeds its loss budget")
            next_loss = (
                (Decimal(self.quantity) + QUANTITY_STEP)
                * Decimal(self.loss_per_unit_quote)
            )
            if next_loss <= Decimal(self.risk_budget_quote):
                raise RiskSizingError(
                    "Position size was not rounded to the maximum safe step"
                )

    @property
    def request_sha256(self):
        return self.request.request_sha256


def size_entry(request):
    """Return the maximum stepped quantity within the cost-aware 1% budget."""
    values = _entry_values(request)
    return PositionSize(
        request=request,
        **{name: _canonical(value) for name, value in values.items()},
    )
