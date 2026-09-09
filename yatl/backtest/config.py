"""Immutable P2 backtest policy and safety boundaries."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from yatl.data import INTERVAL_MILLISECONDS, SYMBOLS


PRIMARY_INTERVAL = "1h"
REGIME_INTERVAL = "4h"
CONTEXT_INTERVAL = "15m"
EXECUTION_PRICE_POLICY = "NEXT_PRIMARY_OPEN"
MAX_COST_BPS = Decimal("1000")
MAX_INITIAL_CASH = Decimal("1000000000000000")
MAX_PRIMARY_CANDLES = 100_000
DECIMAL_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?")


class BacktestConfigError(ValueError):
    """Backtest configuration violates the fixed P2 policy."""


def _bounded_decimal(value, field, *, positive=False, maximum=None):
    if not isinstance(value, str) or DECIMAL_PATTERN.fullmatch(value) is None:
        raise BacktestConfigError(f"{field} must be a plain decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise BacktestConfigError(f"{field} is invalid") from None
    if (not number.is_finite() or number < 0 or (positive and number == 0)
            or (maximum is not None and number > maximum)):
        raise BacktestConfigError(f"{field} is outside the allowed range")
    return number


@dataclass(frozen=True, slots=True)
class BacktestSpec:
    """One deterministic, local, long-only Spot simulation specification."""

    symbol: str
    start_time_ms: int
    end_time_ms: int
    initial_cash: str = "10000"
    fee_bps: str = "10"
    slippage_bps: str = "5"
    seed: int = 0
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_leverage: bool = False
    execution_price_policy: str = EXECUTION_PRICE_POLICY

    def __post_init__(self):
        if self.symbol not in SYMBOLS:
            raise BacktestConfigError("Backtest symbol is not approved")
        if (type(self.start_time_ms) is not int or type(self.end_time_ms) is not int
                or self.start_time_ms < 0 or self.end_time_ms <= self.start_time_ms
                or self.start_time_ms % INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
                or self.end_time_ms % INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
                or ((self.end_time_ms - self.start_time_ms)
                    // INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]) > MAX_PRIMARY_CANDLES):
            raise BacktestConfigError("Backtest range must be a non-empty aligned 1h range")
        _bounded_decimal(self.initial_cash, "initial_cash", positive=True,
                         maximum=MAX_INITIAL_CASH)
        _bounded_decimal(self.fee_bps, "fee_bps", maximum=MAX_COST_BPS)
        _bounded_decimal(self.slippage_bps, "slippage_bps", maximum=MAX_COST_BPS)
        if type(self.seed) is not int or self.seed < 0 or self.seed > 2**32 - 1:
            raise BacktestConfigError("Backtest seed is invalid")
        if (self.paper_only is not True or self.live_master_lock != "OFF"
                or self.spot_only is not True or self.allow_short is not False
                or self.allow_leverage is not False
                or self.execution_price_policy != EXECUTION_PRICE_POLICY):
            raise BacktestConfigError("Backtest safety policy is invalid")

    @property
    def cash_decimal(self):
        return Decimal(self.initial_cash)

    @property
    def fee_bps_decimal(self):
        return Decimal(self.fee_bps)

    @property
    def slippage_bps_decimal(self):
        return Decimal(self.slippage_bps)
