"""Deterministic descriptive P7 metrics over reconstructed completed Paper trades."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from .contracts import StrategyEvidenceState
from .trades import (
    DECIMAL_PRECISION,
    CompletedPaperTrade,
    PaperTradeReconstruction,
    TradeReconstructionError,
)


METRICS_SCHEMA_VERSION = 1
MAX_COMPLETED_TRADES = 4096


class PerformanceMetricsError(TradeReconstructionError):
    """Reconstructed trade material cannot form conservative descriptive metrics."""


class PerformanceMetricsStatus(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DESCRIPTIVE = "DESCRIPTIVE"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decimal(value, label):
    if not isinstance(value, str) or not value:
        raise PerformanceMetricsError(f"{label} is invalid")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise PerformanceMetricsError(f"{label} is invalid") from None
    if not number.is_finite():
        raise PerformanceMetricsError(f"{label} is not finite")
    return number


def _format(value):
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class TradePerformanceMetric:
    """Derived metrics for one already-reconstructed completed Paper trade."""

    trade_index: int
    trade_sha256: str
    realized_pnl_quote: str
    gross_return: str
    net_return: str
    total_fee_quote: str
    total_slippage_quote: str
    holding_time_ms: int

    def __post_init__(self):
        if (
            type(self.trade_index) is not int
            or self.trade_index < 0
            or not isinstance(self.trade_sha256, str)
            or len(self.trade_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.trade_sha256)
            or type(self.holding_time_ms) is not int
            or self.holding_time_ms < 0
        ):
            raise PerformanceMetricsError("Trade metric identity is invalid")
        for value, label in (
            (self.realized_pnl_quote, "Trade realized PnL"),
            (self.gross_return, "Trade gross return"),
            (self.net_return, "Trade net return"),
            (self.total_fee_quote, "Trade fee"),
            (self.total_slippage_quote, "Trade slippage"),
        ):
            _decimal(value, label)
        if (
            _decimal(self.total_fee_quote, "Trade fee") < 0
            or _decimal(self.total_slippage_quote, "Trade slippage") < 0
        ):
            raise PerformanceMetricsError("Trade metric costs are negative")

    def as_record(self):
        return {
            "trade_index": self.trade_index,
            "trade_sha256": self.trade_sha256,
            "realized_pnl_quote": self.realized_pnl_quote,
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "total_fee_quote": self.total_fee_quote,
            "total_slippage_quote": self.total_slippage_quote,
            "holding_time_ms": self.holding_time_ms,
        }


@dataclass(frozen=True, slots=True)
class _AggregateValues:
    completed_trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    realized_pnl_quote: str
    gross_pnl_quote: str
    total_fee_quote: str
    total_slippage_quote: str
    total_cost_quote: str
    gross_return: str | None
    net_return: str | None
    win_rate: str | None
    maximum_realized_drawdown_quote: str
    total_holding_time_ms: int
    minimum_holding_time_ms: int | None
    maximum_holding_time_ms: int | None
    average_holding_time_ms: str | None
    best_trade_pnl_quote: str | None
    worst_trade_pnl_quote: str | None


@dataclass(frozen=True, slots=True)
class PerformanceMetricsReport:
    """Canonical completed-trade-only descriptive analytics for future P8 consumption."""

    reconstruction_sha256: str
    timeline_sha256: str
    symbol: str
    status: PerformanceMetricsStatus
    open_trade_present: bool
    trades: tuple[TradePerformanceMetric, ...]
    completed_trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    realized_pnl_quote: str
    gross_pnl_quote: str
    total_fee_quote: str
    total_slippage_quote: str
    total_cost_quote: str
    gross_return: str | None
    net_return: str | None
    win_rate: str | None
    maximum_realized_drawdown_quote: str
    total_holding_time_ms: int
    minimum_holding_time_ms: int | None
    maximum_holding_time_ms: int | None
    average_holding_time_ms: str | None
    best_trade_pnl_quote: str | None
    worst_trade_pnl_quote: str | None
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = METRICS_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != METRICS_SCHEMA_VERSION
            or not isinstance(self.reconstruction_sha256, str)
            or len(self.reconstruction_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.reconstruction_sha256)
            or not isinstance(self.timeline_sha256, str)
            or len(self.timeline_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.timeline_sha256)
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not isinstance(self.status, PerformanceMetricsStatus)
            or type(self.open_trade_present) is not bool
            or type(self.trades) is not tuple
            or len(self.trades) > MAX_COMPLETED_TRADES
            or any(not isinstance(item, TradePerformanceMetric) for item in self.trades)
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise PerformanceMetricsError("Performance metrics report identity is invalid")

        indexes = tuple(item.trade_index for item in self.trades)
        if indexes != tuple(range(len(self.trades))):
            raise PerformanceMetricsError("Trade metric indexes are noncanonical")
        identities = tuple(item.trade_sha256 for item in self.trades)
        if len(set(identities)) != len(identities):
            raise PerformanceMetricsError("Trade metrics contain duplicate identities")

        expected = _aggregate(self.trades)
        actual = (
            self.completed_trade_count,
            self.winning_trades,
            self.losing_trades,
            self.breakeven_trades,
            self.realized_pnl_quote,
            self.gross_pnl_quote,
            self.total_fee_quote,
            self.total_slippage_quote,
            self.total_cost_quote,
            self.gross_return,
            self.net_return,
            self.win_rate,
            self.maximum_realized_drawdown_quote,
            self.total_holding_time_ms,
            self.minimum_holding_time_ms,
            self.maximum_holding_time_ms,
            self.average_holding_time_ms,
            self.best_trade_pnl_quote,
            self.worst_trade_pnl_quote,
        )
        reference = tuple(
            getattr(expected, field)
            for field in _AggregateValues.__dataclass_fields__
        )
        if actual != reference:
            raise PerformanceMetricsError("Performance metrics arithmetic is inconsistent")

        expected_status = (
            PerformanceMetricsStatus.DESCRIPTIVE
            if self.trades
            else PerformanceMetricsStatus.INSUFFICIENT_DATA
        )
        if self.status is not expected_status:
            raise PerformanceMetricsError("Performance metrics status is inconsistent")

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "reconstruction_sha256": self.reconstruction_sha256,
            "timeline_sha256": self.timeline_sha256,
            "symbol": self.symbol,
            "status": self.status.value,
            "open_trade_present": self.open_trade_present,
            "completed_trade_count": self.completed_trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "realized_pnl_quote": self.realized_pnl_quote,
            "gross_pnl_quote": self.gross_pnl_quote,
            "total_fee_quote": self.total_fee_quote,
            "total_slippage_quote": self.total_slippage_quote,
            "total_cost_quote": self.total_cost_quote,
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "win_rate": self.win_rate,
            "maximum_realized_drawdown_quote": self.maximum_realized_drawdown_quote,
            "total_holding_time_ms": self.total_holding_time_ms,
            "minimum_holding_time_ms": self.minimum_holding_time_ms,
            "maximum_holding_time_ms": self.maximum_holding_time_ms,
            "average_holding_time_ms": self.average_holding_time_ms,
            "best_trade_pnl_quote": self.best_trade_pnl_quote,
            "worst_trade_pnl_quote": self.worst_trade_pnl_quote,
            "trades": [item.as_record() for item in self.trades],
            "strategy_evidence": self.strategy_evidence.value,
            "definitions": {
                "gross_return": (
                    "(sum accepted exit gross_quote - sum accepted entry gross_quote) "
                    "/ sum accepted entry gross_quote; execution-gross, before fees"
                ),
                "net_return": (
                    "sum accepted completed-trade realized cash PnL "
                    "/ sum absolute accepted entry cash_delta"
                ),
                "maximum_realized_drawdown_quote": (
                    "maximum peak-to-trough decline of cumulative completed-trade "
                    "realized PnL starting from zero"
                ),
                "scope": "COMPLETED_PAPER_TRADES_ONLY",
                "annualized": False,
                "forecast": False,
            },
            "safety": {
                "descriptive_only": True,
                "read_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "strategy_evidence_upgrade": False,
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
        }

    @property
    def metrics_sha256(self):
        return _digest(self.as_record())

    @property
    def canonical_json(self):
        return _json(self.as_record()) + "\n"


def _trade_metric(trade):
    if not isinstance(trade, CompletedPaperTrade):
        raise PerformanceMetricsError("Completed trade metric input is invalid")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        entry_gross = _decimal(trade.entry.gross_quote, "Entry gross quote")
        exit_gross = _decimal(trade.exit.gross_quote, "Exit gross quote")
        entry_cash_out = -_decimal(trade.entry.cash_delta, "Entry cash delta")
        realized = _decimal(trade.realized_pnl_quote, "Trade realized PnL")
        if entry_gross <= 0 or entry_cash_out <= 0:
            raise PerformanceMetricsError("Completed trade return denominator is invalid")
        gross_return = (exit_gross - entry_gross) / entry_gross
        net_return = realized / entry_cash_out
    return TradePerformanceMetric(
        trade.trade_index,
        trade.trade_sha256,
        trade.realized_pnl_quote,
        _format(gross_return),
        _format(net_return),
        trade.total_fee_quote,
        trade.total_slippage_quote,
        trade.holding_time_ms,
    )


def _aggregate(trades):
    if type(trades) is not tuple or len(trades) > MAX_COMPLETED_TRADES:
        raise PerformanceMetricsError("Completed trade metric collection is invalid")
    if any(not isinstance(item, TradePerformanceMetric) for item in trades):
        raise PerformanceMetricsError("Completed trade metric collection is invalid")

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        realized_values = [
            _decimal(item.realized_pnl_quote, "Trade realized PnL")
            for item in trades
        ]
        fee_values = [
            _decimal(item.total_fee_quote, "Trade fee")
            for item in trades
        ]
        slippage_values = [
            _decimal(item.total_slippage_quote, "Trade slippage")
            for item in trades
        ]

        realized = sum(realized_values, Decimal(0))
        fees = sum(fee_values, Decimal(0))
        slippage = sum(slippage_values, Decimal(0))
        costs = fees + slippage
        wins = sum(value > 0 for value in realized_values)
        losses = sum(value < 0 for value in realized_values)
        breakeven = sum(value == 0 for value in realized_values)
        count = len(trades)

        gross_return = None
        net_return = None
        win_rate = None
        average_holding = None
        best = None
        worst = None
        gross_pnl = Decimal(0)

        if trades:
            gross_returns = [
                _decimal(item.gross_return, "Trade gross return")
                for item in trades
            ]
            net_returns = [
                _decimal(item.net_return, "Trade net return")
                for item in trades
            ]
            # Aggregate return is capital-weighted in calculate_performance_metrics.
            # Here these placeholders are replaced there before report construction.
            if any(not value.is_finite() for value in gross_returns + net_returns):
                raise PerformanceMetricsError("Trade return is not finite")
            win_rate = _format(Decimal(wins) / Decimal(count))
            total_holding = sum(item.holding_time_ms for item in trades)
            average_holding = _format(Decimal(total_holding) / Decimal(count))
            best = _format(max(realized_values))
            worst = _format(min(realized_values))
        else:
            total_holding = 0

        cumulative = Decimal(0)
        peak = Decimal(0)
        maximum_drawdown = Decimal(0)
        for value in realized_values:
            cumulative += value
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > maximum_drawdown:
                maximum_drawdown = drawdown

    return _AggregateValues(
        completed_trade_count=count,
        winning_trades=wins,
        losing_trades=losses,
        breakeven_trades=breakeven,
        realized_pnl_quote=_format(realized),
        gross_pnl_quote=_format(gross_pnl),
        total_fee_quote=_format(fees),
        total_slippage_quote=_format(slippage),
        total_cost_quote=_format(costs),
        gross_return=gross_return,
        net_return=net_return,
        win_rate=win_rate,
        maximum_realized_drawdown_quote=_format(maximum_drawdown),
        total_holding_time_ms=total_holding,
        minimum_holding_time_ms=(
            min(item.holding_time_ms for item in trades) if trades else None
        ),
        maximum_holding_time_ms=(
            max(item.holding_time_ms for item in trades) if trades else None
        ),
        average_holding_time_ms=average_holding,
        best_trade_pnl_quote=best,
        worst_trade_pnl_quote=worst,
    )


def calculate_performance_metrics(reconstruction):
    """Calculate bounded descriptive metrics without extrapolation or new economics."""

    if not isinstance(reconstruction, PaperTradeReconstruction):
        raise PerformanceMetricsError("Performance metrics require P7 trade reconstruction")
    if len(reconstruction.completed) > MAX_COMPLETED_TRADES:
        raise PerformanceMetricsError("Completed trade count exceeds analytics bound")

    trade_metrics = tuple(_trade_metric(item) for item in reconstruction.completed)
    base = _aggregate(trade_metrics)

    gross_pnl = Decimal(0)
    gross_entry = Decimal(0)
    net_entry_cash = Decimal(0)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for trade in reconstruction.completed:
            entry_gross = _decimal(trade.entry.gross_quote, "Entry gross quote")
            exit_gross = _decimal(trade.exit.gross_quote, "Exit gross quote")
            entry_cash = -_decimal(trade.entry.cash_delta, "Entry cash delta")
            if entry_gross <= 0 or entry_cash <= 0:
                raise PerformanceMetricsError(
                    "Completed trade return denominator is invalid"
                )
            gross_entry += entry_gross
            gross_pnl += exit_gross - entry_gross
            net_entry_cash += entry_cash

        gross_return = (
            None if not reconstruction.completed
            else _format(gross_pnl / gross_entry)
        )
        net_return = (
            None if not reconstruction.completed
            else _format(
                _decimal(base.realized_pnl_quote, "Aggregate realized PnL")
                / net_entry_cash
            )
        )

    values = _AggregateValues(
        completed_trade_count=base.completed_trade_count,
        winning_trades=base.winning_trades,
        losing_trades=base.losing_trades,
        breakeven_trades=base.breakeven_trades,
        realized_pnl_quote=base.realized_pnl_quote,
        gross_pnl_quote=_format(gross_pnl),
        total_fee_quote=base.total_fee_quote,
        total_slippage_quote=base.total_slippage_quote,
        total_cost_quote=base.total_cost_quote,
        gross_return=gross_return,
        net_return=net_return,
        win_rate=base.win_rate,
        maximum_realized_drawdown_quote=base.maximum_realized_drawdown_quote,
        total_holding_time_ms=base.total_holding_time_ms,
        minimum_holding_time_ms=base.minimum_holding_time_ms,
        maximum_holding_time_ms=base.maximum_holding_time_ms,
        average_holding_time_ms=base.average_holding_time_ms,
        best_trade_pnl_quote=base.best_trade_pnl_quote,
        worst_trade_pnl_quote=base.worst_trade_pnl_quote,
    )

    status = (
        PerformanceMetricsStatus.DESCRIPTIVE
        if trade_metrics
        else PerformanceMetricsStatus.INSUFFICIENT_DATA
    )
    return PerformanceMetricsReport(
        reconstruction.reconstruction_sha256,
        reconstruction.timeline_sha256,
        reconstruction.symbol,
        status,
        reconstruction.open_trade is not None,
        trade_metrics,
        **{
            name: getattr(values, name)
            for name in _AggregateValues.__dataclass_fields__
        },
    )
