"""Deterministic Decimal performance metrics for completed P2 paper runs."""

from dataclasses import dataclass, fields
from decimal import Decimal, localcontext

from .costs import DECIMAL_PRECISION
from .portfolio import PortfolioSnapshot


class MetricsError(Exception):
    """An equity curve or derived metric violates the P2 metric contract."""


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time_ms: int
    portfolio: PortfolioSnapshot

    def __post_init__(self):
        if type(self.time_ms) is not int or self.time_ms < 0:
            raise MetricsError("Equity point time is invalid")
        if not isinstance(self.portfolio, PortfolioSnapshot):
            raise MetricsError("Equity point requires a valid portfolio snapshot")


@dataclass(frozen=True, slots=True)
class _MetricValues:
    initial_equity_quote: Decimal
    final_equity_quote: Decimal
    total_return: Decimal
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal | None
    gross_pnl_quote: Decimal
    net_pnl_quote: Decimal
    total_fee_quote: Decimal
    total_slippage_quote: Decimal
    total_cost_quote: Decimal
    maximum_drawdown_quote: Decimal
    maximum_drawdown: Decimal
    mean_period_return: Decimal | None
    sample_period_volatility: Decimal | None
    downside_deviation: Decimal | None
    mean_over_volatility: Decimal | None
    mean_over_downside: Decimal | None


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    points: tuple[EquityPoint, ...]
    initial_equity_quote: Decimal
    final_equity_quote: Decimal
    total_return: Decimal
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal | None
    gross_pnl_quote: Decimal
    net_pnl_quote: Decimal
    total_fee_quote: Decimal
    total_slippage_quote: Decimal
    total_cost_quote: Decimal
    maximum_drawdown_quote: Decimal
    maximum_drawdown: Decimal
    mean_period_return: Decimal | None
    sample_period_volatility: Decimal | None
    downside_deviation: Decimal | None
    mean_over_volatility: Decimal | None
    mean_over_downside: Decimal | None

    def __post_init__(self):
        expected = _calculate(self.points)
        actual = tuple(getattr(self, item.name) for item in fields(_MetricValues))
        reference = tuple(getattr(expected, item.name) for item in fields(_MetricValues))
        if actual != reference:
            raise MetricsError("Performance report arithmetic is inconsistent")


def _validate_curve(points):
    if not isinstance(points, tuple) or not points:
        raise MetricsError("Equity curve must be a non-empty tuple")
    if any(not isinstance(point, EquityPoint) for point in points):
        raise MetricsError("Equity curve contains an invalid point")
    first = points[0].portfolio
    if (first.asset_quantity != 0 or first.equity_quote <= 0
            or first.closed_trades != 0 or first.realized_pnl_quote != 0
            or first.total_fee_quote != 0 or first.total_slippage_quote != 0):
        raise MetricsError("Equity curve must begin at a clean flat portfolio")
    previous = points[0]
    for point in points[1:]:
        current = point.portfolio
        prior = previous.portfolio
        trade_delta = current.closed_trades - prior.closed_trades
        if (point.time_ms <= previous.time_ms or current.symbol != first.symbol
                or current.equity_quote <= 0
                or current.total_fee_quote < prior.total_fee_quote
                or current.total_slippage_quote < prior.total_slippage_quote
                or trade_delta not in (0, 1)
                or (trade_delta == 0
                    and current.realized_pnl_quote != prior.realized_pnl_quote)):
            raise MetricsError("Equity curve lifecycle is inconsistent")
        previous = point
    if points[-1].portfolio.asset_quantity != 0:
        raise MetricsError("Final performance metrics require a flat portfolio")


def _sqrt(value):
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return value.sqrt()


def _calculate(points):
    _validate_curve(points)
    first = points[0].portfolio
    final = points[-1].portfolio
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        net_pnl = final.equity_quote - first.equity_quote
        total_fee = final.total_fee_quote
        total_slippage = final.total_slippage_quote
        total_cost = total_fee + total_slippage
        gross_pnl = net_pnl + total_cost
        total_return = net_pnl / first.equity_quote

        peak = first.equity_quote
        max_drawdown_quote = Decimal(0)
        max_drawdown = Decimal(0)
        period_returns = []
        trade_pnls = []
        previous = points[0]
        for point in points[1:]:
            equity = point.portfolio.equity_quote
            period_returns.append(equity / previous.portfolio.equity_quote - Decimal(1))
            if equity > peak:
                peak = equity
            drawdown_quote = peak - equity
            drawdown = drawdown_quote / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_quote = drawdown_quote
            if point.portfolio.closed_trades > previous.portfolio.closed_trades:
                trade_pnls.append(point.portfolio.realized_pnl_quote
                                  - previous.portfolio.realized_pnl_quote)
            previous = point

        wins = sum(pnl > 0 for pnl in trade_pnls)
        losses = sum(pnl < 0 for pnl in trade_pnls)
        breakeven = sum(pnl == 0 for pnl in trade_pnls)
        trade_count = final.closed_trades
        win_rate = (Decimal(wins) / Decimal(trade_count) if trade_count else None)

        mean = None
        volatility = None
        downside = None
        mean_over_volatility = None
        mean_over_downside = None
        if period_returns:
            mean = sum(period_returns, Decimal(0)) / Decimal(len(period_returns))
            negative_squares = [value * value for value in period_returns if value < 0]
            if negative_squares:
                downside = _sqrt(sum(negative_squares, Decimal(0))
                                 / Decimal(len(period_returns)))
                if downside != 0:
                    mean_over_downside = mean / downside
            if len(period_returns) >= 2:
                variance = (sum((value - mean) ** 2 for value in period_returns)
                            / Decimal(len(period_returns) - 1))
                volatility = _sqrt(variance)
                if volatility != 0:
                    mean_over_volatility = mean / volatility

    return _MetricValues(
        initial_equity_quote=first.equity_quote,
        final_equity_quote=final.equity_quote,
        total_return=total_return,
        trade_count=trade_count,
        winning_trades=wins,
        losing_trades=losses,
        breakeven_trades=breakeven,
        win_rate=win_rate,
        gross_pnl_quote=gross_pnl,
        net_pnl_quote=net_pnl,
        total_fee_quote=total_fee,
        total_slippage_quote=total_slippage,
        total_cost_quote=total_cost,
        maximum_drawdown_quote=max_drawdown_quote,
        maximum_drawdown=max_drawdown,
        mean_period_return=mean,
        sample_period_volatility=volatility,
        downside_deviation=downside,
        mean_over_volatility=mean_over_volatility,
        mean_over_downside=mean_over_downside,
    )


def calculate_metrics(points):
    values = _calculate(points)
    return PerformanceReport(points, **{
        item.name: getattr(values, item.name) for item in fields(_MetricValues)
    })
