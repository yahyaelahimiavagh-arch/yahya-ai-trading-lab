"""Exact long-only Spot portfolio ledger for deterministic P2 simulations."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from yatl.data import SYMBOLS

from .config import BacktestSpec, DECIMAL_PATTERN
from .costs import BASIS_POINTS, DECIMAL_PRECISION, CostedFill
from .fills import IntentAction


MAX_LEDGER_BATCH = 100_000


class PortfolioError(Exception):
    """A fill or valuation would violate a portfolio accounting invariant."""


def _mark(value):
    if not isinstance(value, str) or DECIMAL_PATTERN.fullmatch(value) is None:
        raise PortfolioError("Mark price must be a plain positive decimal string")
    number = Decimal(value)
    if not number.is_finite() or number <= 0:
        raise PortfolioError("Mark price must be positive")
    return number


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    symbol: str
    cash: Decimal
    asset_quantity: Decimal
    cost_basis_quote: Decimal
    liquidation_value_quote: Decimal
    realized_pnl_quote: Decimal
    unrealized_pnl_quote: Decimal
    equity_quote: Decimal
    total_fee_quote: Decimal
    total_slippage_quote: Decimal
    closed_trades: int

    def __post_init__(self):
        decimals = (self.cash, self.asset_quantity, self.cost_basis_quote,
                    self.liquidation_value_quote, self.realized_pnl_quote,
                    self.unrealized_pnl_quote, self.equity_quote,
                    self.total_fee_quote, self.total_slippage_quote)
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            equity_is_valid = self.equity_quote == self.cash + self.liquidation_value_quote
            unrealized_is_valid = (self.unrealized_pnl_quote
                                   == self.liquidation_value_quote - self.cost_basis_quote)
        if (self.symbol not in SYMBOLS
                or any(type(value) is not Decimal or not value.is_finite() for value in decimals)
                or self.cash < 0 or self.asset_quantity < 0
                or self.cost_basis_quote < 0 or self.liquidation_value_quote < 0
                or self.total_fee_quote < 0 or self.total_slippage_quote < 0
                or type(self.closed_trades) is not int or self.closed_trades < 0
                or not equity_is_valid or not unrealized_is_valid
                or (self.asset_quantity == 0
                    and (self.cost_basis_quote != 0 or self.liquidation_value_quote != 0))):
            raise PortfolioError("Portfolio snapshot arithmetic is inconsistent")


class PortfolioLedger:
    def __init__(self, spec):
        if not isinstance(spec, BacktestSpec):
            raise PortfolioError("Portfolio requires a valid backtest specification")
        self.spec = spec
        self.cash = spec.cash_decimal
        self.asset_quantity = Decimal(0)
        self.cost_basis_quote = Decimal(0)
        self.realized_pnl_quote = Decimal(0)
        self.total_fee_quote = Decimal(0)
        self.total_slippage_quote = Decimal(0)
        self.closed_trades = 0
        self._last_fill_time_ms = None
        self._applied = set()

    @property
    def has_position(self):
        return self.asset_quantity > 0

    def _state(self):
        return (self.cash, self.asset_quantity, self.cost_basis_quote,
                self.realized_pnl_quote, self.total_fee_quote,
                self.total_slippage_quote, self.closed_trades,
                self._last_fill_time_ms, set(self._applied))

    def _restore(self, state):
        (self.cash, self.asset_quantity, self.cost_basis_quote,
         self.realized_pnl_quote, self.total_fee_quote,
         self.total_slippage_quote, self.closed_trades,
         self._last_fill_time_ms, applied) = state
        self._applied = applied

    def _apply(self, fill):
        if not isinstance(fill, CostedFill) or fill.reference.symbol != self.spec.symbol:
            raise PortfolioError("Costed fill does not belong to this portfolio")
        if (fill.fee_bps != self.spec.fee_bps_decimal
                or fill.slippage_bps != self.spec.slippage_bps_decimal):
            raise PortfolioError("Costed fill uses a different cost policy")
        if fill in self._applied:
            raise PortfolioError("Costed fill was already applied")
        if (self._last_fill_time_ms is not None
                and fill.reference.fill_time_ms < self._last_fill_time_ms):
            raise PortfolioError("Costed fills are out of time order")
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            if fill.reference.action is IntentAction.ENTER_LONG:
                if self.has_position:
                    raise PortfolioError("Overlapping portfolio positions are forbidden")
                new_cash = self.cash + fill.cash_delta
                if new_cash < 0:
                    raise PortfolioError("Portfolio has insufficient cash")
                self.cash = new_cash
                self.asset_quantity = fill.asset_delta
                self.cost_basis_quote = fill.cash_delta.copy_negate()
            else:
                if (not self.has_position
                        or fill.asset_delta.copy_negate() != self.asset_quantity):
                    raise PortfolioError("Exit must close the full long position")
                proceeds = fill.cash_delta
                self.cash += proceeds
                self.realized_pnl_quote += proceeds - self.cost_basis_quote
                self.asset_quantity = Decimal(0)
                self.cost_basis_quote = Decimal(0)
                self.closed_trades += 1
            self.total_fee_quote += fill.fee_quote
            self.total_slippage_quote += fill.slippage_quote
        if self.cash < 0 or self.asset_quantity < 0:
            raise PortfolioError("Portfolio balance became negative")
        self._last_fill_time_ms = fill.reference.fill_time_ms
        self._applied.add(fill)

    def apply(self, fill):
        state = self._state()
        try:
            self._apply(fill)
        except PortfolioError:
            self._restore(state)
            raise

    def apply_many(self, fills):
        if not isinstance(fills, (tuple, list)) or not 1 <= len(fills) <= MAX_LEDGER_BATCH:
            raise PortfolioError("Portfolio fill batch size is invalid")
        state = self._state()
        try:
            for fill in fills:
                self._apply(fill)
        except PortfolioError:
            self._restore(state)
            raise

    def snapshot(self, mark_price):
        price = _mark(mark_price)
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            if self.has_position:
                slipped = price * (Decimal(1) - self.spec.slippage_bps_decimal / BASIS_POINTS)
                gross = self.asset_quantity * slipped
                liquidation = gross * (Decimal(1) - self.spec.fee_bps_decimal / BASIS_POINTS)
            else:
                liquidation = Decimal(0)
            unrealized = liquidation - self.cost_basis_quote
            equity = self.cash + liquidation
        return PortfolioSnapshot(
            symbol=self.spec.symbol, cash=self.cash,
            asset_quantity=self.asset_quantity,
            cost_basis_quote=self.cost_basis_quote,
            liquidation_value_quote=liquidation,
            realized_pnl_quote=self.realized_pnl_quote,
            unrealized_pnl_quote=unrealized, equity_quote=equity,
            total_fee_quote=self.total_fee_quote,
            total_slippage_quote=self.total_slippage_quote,
            closed_trades=self.closed_trades,
        )
