"""Exact adverse slippage and quote-fee accounting for P2 fill references."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .config import BacktestSpec, MAX_COST_BPS
from .fills import FillReference, IntentAction


BASIS_POINTS = Decimal("10000")
DECIMAL_PRECISION = 256


class CostModelError(Exception):
    """A cost input or computed fill violates the exact P2 accounting model."""


def _rate(value, field):
    if (type(value) is not Decimal or not value.is_finite()
            or value < 0 or value > MAX_COST_BPS):
        raise CostModelError(f"{field} is invalid")
    return value


def _components(reference, fee_bps, slippage_bps):
    if not isinstance(reference, FillReference):
        raise CostModelError("Cost model requires a fill reference")
    fee_bps = _rate(fee_bps, "fee_bps")
    slippage_bps = _rate(slippage_bps, "slippage_bps")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        quantity = Decimal(reference.quantity)
        price = Decimal(reference.reference_price)
        slip_rate = slippage_bps / BASIS_POINTS
        fee_rate = fee_bps / BASIS_POINTS
        if reference.action is IntentAction.ENTER_LONG:
            execution_price = price * (Decimal(1) + slip_rate)
            asset_delta = quantity
            direction = Decimal(-1)
        else:
            execution_price = price * (Decimal(1) - slip_rate)
            asset_delta = -quantity
            direction = Decimal(1)
        gross_quote = quantity * execution_price
        fee_quote = gross_quote * fee_rate
        slippage_quote = quantity * abs(execution_price - price)
        cash_delta = direction * gross_quote - fee_quote
        return (execution_price, gross_quote, fee_quote, slippage_quote,
                cash_delta, asset_delta)


@dataclass(frozen=True, slots=True)
class CostedFill:
    reference: FillReference
    fee_bps: Decimal
    slippage_bps: Decimal
    execution_price: Decimal
    gross_quote: Decimal
    fee_quote: Decimal
    slippage_quote: Decimal
    cash_delta: Decimal
    asset_delta: Decimal

    def __post_init__(self):
        values = (self.execution_price, self.gross_quote, self.fee_quote,
                  self.slippage_quote, self.cash_delta, self.asset_delta)
        if any(type(value) is not Decimal or not value.is_finite() for value in values):
            raise CostModelError("Costed fill values must be finite Decimal values")
        expected = _components(self.reference, self.fee_bps, self.slippage_bps)
        if values != expected:
            raise CostModelError("Costed fill arithmetic is inconsistent")

    @property
    def total_cost_quote(self):
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return self.fee_quote + self.slippage_quote


def apply_costs(reference, spec):
    if not isinstance(spec, BacktestSpec) or not isinstance(reference, FillReference):
        raise CostModelError("Cost model inputs are invalid")
    if reference.symbol != spec.symbol:
        raise CostModelError("Fill and backtest symbols differ")
    fee_bps = spec.fee_bps_decimal
    slippage_bps = spec.slippage_bps_decimal
    values = _components(reference, fee_bps, slippage_bps)
    return CostedFill(reference, fee_bps, slippage_bps, *values)
