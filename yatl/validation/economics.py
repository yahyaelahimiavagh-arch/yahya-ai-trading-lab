"""P10-006 descriptive economics of reconciled forward Paper evidence.

No acceptance verdict, sizing, execution, clock, network or evidence promotion.
The accepted runner has independent 10,000-quote symbol portfolios: pooling
adds both capital bases, not just their profits. This is not a shared account.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Context, Decimal, DecimalException, localcontext

from yatl.backtest import BacktestSpec, IntentAction, PortfolioLedger, apply_costs
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.fills import FillReason, FillReference
from yatl.backtest.portfolio import PortfolioError

from .forward_store import ForwardStoreError
from .paper_runner import (
    ForwardPaperRunResult,
    ForwardPaperRunnerError,
    RUNNER_QUANTITY,
    _fill_record,
    _portfolio_record,
    run_forward_paper,
)
from .registration import CandidateFreeze, EconomicGateRegistry
from .window import ForwardWindowSeal


FORWARD_ECONOMICS_ID = "P10_FORWARD_ECONOMICS_V1"
DAY_MS = 86_400_000
ZERO = Decimal(0)


class ForwardEconomicsError(Exception):
    """Forward economics cannot reconcile the exact accepted input."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value):
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise ForwardEconomicsError("Economics requires finite Decimal arithmetic")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True, slots=True)
class ForwardEconomicsReport:
    """Canonical immutable payload; as_record returns a detached value."""

    canonical_json: str

    def as_record(self):
        return json.loads(self.canonical_json)

    @property
    def report_sha256(self):
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def _trade_statistics(trades):
    pnls = [Decimal(item["net_pnl_quote"]) for item in trades]
    wins = sum(value > 0 for value in pnls)
    losses = sum(value < 0 for value in pnls)
    positive = sum((value for value in pnls if value > 0), ZERO)
    negative = -sum((value for value in pnls if value < 0), ZERO)
    count = len(trades)
    return {
        "completed_trades": count,
        "winning_trades": wins,
        "losing_trades": losses,
        "breakeven_trades": count - wins - losses,
        "win_rate": _plain(Decimal(wins) / count if count else None),
        "profit_factor_after_costs": _plain(positive / negative if negative else None),
        "profit_factor_status": (
            "DEFINED" if negative else
            "UNDEFINED_NO_LOSSES" if count else "UNDEFINED_NO_COMPLETED_TRADES"
        ),
        "mean_completed_holding_ms": _plain(
            Decimal(sum(item["holding_ms"] for item in trades)) / count
            if count else None
        ),
        "maximum_completed_holding_ms": max(
            (item["holding_ms"] for item in trades), default=None
        ),
    }


def _drawdown(equities):
    peak = equities[0]
    maximum_quote = ZERO
    maximum_fraction = ZERO
    for equity in equities:
        if equity <= 0:
            raise ForwardEconomicsError("Non-positive economics equity")
        peak = max(peak, equity)
        loss = peak - equity
        maximum_quote = max(maximum_quote, loss)
        maximum_fraction = max(maximum_fraction, loss / peak)
    return {
        "maximum_drawdown_quote": _plain(maximum_quote),
        "maximum_drawdown_fraction": _plain(maximum_fraction),
    }


def _reconcile_symbol(item, final_mark):
    """Re-cost every fill and rebuild the accepted P2 portfolio, without rounding."""
    candidate = CandidateFreeze()
    spec = BacktestSpec(
        item.symbol, item.first_decision_time_ms, item.end_time_ms,
        initial_cash=candidate.initial_equity_quote,
        fee_bps=candidate.fee_bps, slippage_bps=candidate.slippage_bps,
    )
    ledger = PortfolioLedger(spec)
    entry = None
    trades = []
    realized_events = []
    for record in item.fills:
        if record["quantity"] != RUNNER_QUANTITY:
            raise ForwardEconomicsError("Forward quantity differs from frozen runner")
        reference = FillReference(
            IntentAction(record["action"]), item.symbol,
            record["decision_time_ms"], record["fill_time_ms"],
            record["quantity"], record["reference_price"], FillReason(record["reason"]),
        )
        if not item.first_decision_time_ms <= reference.fill_time_ms < item.end_time_ms:
            raise ForwardEconomicsError("Fill lies outside the accepted forward prefix")
        fill = apply_costs(reference, spec)
        if _json(_fill_record(fill)) != _json(record):
            raise ForwardEconomicsError("Forward fill cost evidence does not reconcile")
        ledger.apply(fill)
        if reference.action is IntentAction.ENTER_LONG:
            entry = fill
        else:
            if entry is None:
                raise ForwardEconomicsError("Forward exit has no entry")
            gross = Decimal(reference.quantity) * (
                Decimal(reference.reference_price) - Decimal(entry.reference.reference_price)
            )
            fees = entry.fee_quote + fill.fee_quote
            slippage = entry.slippage_quote + fill.slippage_quote
            net = entry.cash_delta + fill.cash_delta
            if net != gross - fees - slippage:
                raise ForwardEconomicsError("Completed trade costs do not reconcile")
            trades.append({
                "symbol": item.symbol,
                "entry_time_ms": entry.reference.fill_time_ms,
                "exit_time_ms": reference.fill_time_ms,
                "holding_ms": reference.fill_time_ms - entry.reference.fill_time_ms,
                "gross_pnl_quote": _plain(gross),
                "fee_quote": _plain(fees),
                "slippage_quote": _plain(slippage),
                "net_pnl_quote": _plain(net),
            })
            realized_events.append((reference.fill_time_ms, net))
            entry = None

    final = ledger.snapshot(final_mark)
    if _json(_portfolio_record(final)) != _json(item.final_portfolio):
        raise ForwardEconomicsError("Forward final portfolio does not reconcile")
    realized = sum((Decimal(t["net_pnl_quote"]) for t in trades), ZERO)
    if realized != final.realized_pnl_quote or len(trades) != final.closed_trades:
        raise ForwardEconomicsError("Forward completed trades do not reconcile")
    completed_gross = sum((Decimal(t["gross_pnl_quote"]) for t in trades), ZERO)
    completed_fee = sum((Decimal(t["fee_quote"]) for t in trades), ZERO)
    completed_slip = sum((Decimal(t["slippage_quote"]) for t in trades), ZERO)
    open_fee = entry.fee_quote if entry else ZERO
    open_slip = entry.slippage_quote if entry else ZERO
    if (completed_fee + open_fee != final.total_fee_quote
            or completed_slip + open_slip != final.total_slippage_quote):
        raise ForwardEconomicsError("Open and closed costs do not reconcile")

    initial = spec.cash_decimal
    net = final.equity_quote - initial
    if net != realized + final.unrealized_pnl_quote:
        raise ForwardEconomicsError("Forward equity and PnL do not reconcile")
    start = ForwardWindowSeal().forward_window_start_ms
    duration = item.end_time_ms - start
    open_holding = item.end_time_ms - entry.reference.fill_time_ms if entry else 0
    holding = sum(t["holding_ms"] for t in trades) + open_holding
    marks = [(start, initial)] + [
        (row["decision_time_ms"], Decimal(row["risk_state"]["equity_quote"]))
        for row in item.trace
    ] + [(item.end_time_ms, final.equity_quote)]
    exposures = [
        Decimal(row["risk_state"]["position_quantity"])
        * Decimal(row["risk_state"]["mark_price"])
        for row in item.trace
    ] + [final.asset_quantity * Decimal(final_mark)]
    realized_curve = [initial]
    for _, pnl in realized_events:
        realized_curve.append(realized_curve[-1] + pnl)
    report = {
        "symbol": item.symbol,
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(final.equity_quote),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net / initial),
        "realized_net_pnl_quote": _plain(realized),
        "unrealized_liquidation_net_pnl_quote": _plain(final.unrealized_pnl_quote),
        "completed_gross_pnl_quote": _plain(completed_gross),
        "completed_fee_quote": _plain(completed_fee),
        "completed_slippage_quote": _plain(completed_slip),
        "executed_fee_quote": _plain(final.total_fee_quote),
        "executed_slippage_quote": _plain(final.total_slippage_quote),
        "executed_total_cost_quote": _plain(final.total_fee_quote + final.total_slippage_quote),
        "open_entry_fee_quote": _plain(open_fee),
        "open_entry_slippage_quote": _plain(open_slip),
        "open_positions": int(entry is not None),
        "open_holding_ms": open_holding,
        "position_time_ms": holding,
        "position_time_fraction": _plain(Decimal(holding) / duration),
        "maximum_sampled_notional_quote": _plain(max(exposures)),
        "realized_drawdown": _drawdown(realized_curve),
        "sampled_liquidation_drawdown": _drawdown([equity for _, equity in marks]),
        "kill_switch_latched": item.kill_switch_latched,
        "entries_blocked": item.entries_blocked,
        "trades": trades,
        **_trade_statistics(trades),
    }
    return report, marks, realized_events


def _assemble(run, final_marks):
    """Internal arithmetic only; public entrypoint first reproduces the runner."""
    window = ForwardWindowSeal()
    gates = EconomicGateRegistry()
    if len({item.end_time_ms for item in run.symbols}) != 1:
        raise ForwardEconomicsError("Cannot pool different observation cutoffs")
    end = run.symbols[0].end_time_ms
    duration = end - window.forward_window_start_ms
    reports, curves, events = zip(*(
        _reconcile_symbol(item, final_marks[item.symbol]) for item in run.symbols
    ))
    if any([time for time, _ in curve] != [time for time, _ in curves[0]]
           for curve in curves[1:]):
        raise ForwardEconomicsError("Cannot pool unsynchronized equity observations")
    initial = sum((Decimal(r["initial_equity_quote"]) for r in reports), ZERO)
    net = sum((Decimal(r["net_pnl_after_costs_quote"]) for r in reports), ZERO)
    trades = sorted(
        (trade for report in reports for trade in report["trades"]),
        key=lambda t: (t["exit_time_ms"], t["symbol"], t["entry_time_ms"]),
    )
    # Simultaneous closes are one pooled event, not an arbitrary symbol ordering.
    by_time = {}
    for symbol_events in events:
        for time, pnl in symbol_events:
            by_time[time] = by_time.get(time, ZERO) + pnl
    realized_curve = [initial]
    for time in sorted(by_time):
        realized_curve.append(realized_curve[-1] + by_time[time])
    sampled_curve = [sum((point[1] for point in points), ZERO) for points in zip(*curves)]
    pooled = {
        "capital_basis": "SUM_OF_INDEPENDENT_P10_005_SYMBOL_PORTFOLIOS",
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(initial + net),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net / initial),
        "realized_drawdown": _drawdown(realized_curve),
        "sampled_liquidation_drawdown": _drawdown(sampled_curve),
        **_trade_statistics(trades),
    }
    for key in (
        "realized_net_pnl_quote", "unrealized_liquidation_net_pnl_quote",
        "completed_gross_pnl_quote", "completed_fee_quote", "completed_slippage_quote",
        "executed_fee_quote", "executed_slippage_quote", "executed_total_cost_quote",
        "open_entry_fee_quote", "open_entry_slippage_quote",
    ):
        pooled[key] = _plain(sum((Decimal(r[key]) for r in reports), ZERO))
    pooled["open_positions"] = sum(r["open_positions"] for r in reports)
    insufficient = []
    if duration < gates.minimum_validation_days * DAY_MS:
        insufficient.append("MINIMUM_DURATION_NOT_MET")
    if len(trades) < gates.minimum_total_completed_trades:
        insufficient.append("MINIMUM_POOLED_TRADES_NOT_MET")
    for report in reports:
        if report["completed_trades"] < gates.minimum_completed_trades_per_symbol:
            insufficient.append(report["symbol"] + "_MINIMUM_TRADES_NOT_MET")
    return ForwardEconomicsReport(_json({
        "economics_id": FORWARD_ECONOMICS_ID,
        "input_run_sha256": run.run_sha256,
        "ingestion_snapshot_sha256": run.ingestion_snapshot_sha256,
        "window_sha256": run.window_sha256,
        "candidate_sha256": run.candidate_sha256,
        "gate_registry_sha256": run.gate_registry_sha256,
        "observation_start_ms": window.forward_window_start_ms,
        "observation_end_ms": end,
        "observation_duration_ms": duration,
        "observed_days": _plain(Decimal(duration) / DAY_MS),
        "sample_status": "INSUFFICIENT_DATA" if insufficient else "MINIMUM_SAMPLE_MET_ONLY",
        "insufficiency_reasons": insufficient,
        "symbols": list(reports),
        "pooled": pooled,
        "semantics": {
            "net_pnl": "REALIZED_PLUS_P2_NET_LIQUIDATION_UNREALIZED",
            "gross_pnl": "COMPLETED_REFERENCE_PRICE_PNL_ONLY",
            "executed_costs": "INCLUDES_OPEN_ENTRY_EXCLUDES_HYPOTHETICAL_EXIT",
            "holding_time": "P2_FILL_TIMESTAMPS_NOT_INTRABAR_WALL_CLOCK",
            "drawdown": "REALIZED_AND_SAMPLED_LIQUIDATION_NOT_INTRABAR_MAXIMUM",
            "pooled_capital": "DESCRIPTIVE_NOT_A_SHARED_ACCOUNT_OR_GATE_VERDICT",
        },
        "safety": {
            **run.as_record()["safety"],
            "p11_unlocked": False,
            "economic_verdict": "NOT_EVALUATED",
        },
    }))


def calculate_forward_economics(store, snapshot, run):
    """Bind metrics to exact store/snapshot/frozen replay, rejecting invented fills.

    Ratios use P2's 256-digit Decimal precision. No annualization, infinite profit
    factor, inferred trades, acceptance verdict or pre-window warm-up is added.
    """
    try:
        if type(run) is not ForwardPaperRunResult:
            raise ForwardEconomicsError("Economics requires accepted Paper run evidence")
        # Reproduce P10-005's standard Python Decimal environment explicitly;
        # the caller's precision/rounding flags must not affect replay.
        with localcontext(Context(prec=28)):
            reproduced = run_forward_paper(store, snapshot)
        if _json(reproduced.as_record()) != _json(run.as_record()):
            raise ForwardEconomicsError("Paper evidence differs from exact forward replay")
        marks = {}
        for item in reproduced.symbols:
            candles = store.candles_between(
                item.symbol, "1h", ForwardWindowSeal().forward_window_start_ms,
                item.end_time_ms,
            )
            marks[item.symbol] = candles[-1].close
        with localcontext(Context(prec=DECIMAL_PRECISION)):
            return _assemble(reproduced, marks)
    except ForwardEconomicsError:
        raise
    except (ForwardPaperRunnerError, ForwardStoreError, PortfolioError,
            ValueError, TypeError, KeyError,
            IndexError, DecimalException) as exc:
        raise ForwardEconomicsError("Forward economics input failed reconciliation") from exc
