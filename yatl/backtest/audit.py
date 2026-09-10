"""Independent fail-closed acceptance audit for the complete P2 engine."""

import hashlib
import json
import re
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from yatl.data import (AuditError, INTERVAL_MILLISECONDS, SYMBOLS,
                       audit_p1_manifest)

from .artifacts import (ARTIFACT_KIND, ENGINE_VERSION, ArtifactError,
                        artifact_json)
from .config import BacktestConfigError, BacktestSpec
from .costs import DECIMAL_PRECISION, apply_costs
from .fills import FillModelError, FillReason, FillReference, IntentAction
from .metrics import PerformanceReport
from .scenarios import (SCENARIOS, ScenarioError, run_real_scenario_matrix)


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SIGNED_DECIMAL_PATTERN = re.compile(
    r"-?(?:0|[1-9][0-9]{0,255})(?:\.[0-9]{1,512})?"
)
EXPECTED_METRICS = {item.name for item in fields(PerformanceReport)} - {"points"}
TRADE_KEYS = {
    "entry_time_ms", "exit_time_ms", "quantity", "entry_reference_price",
    "entry_execution_price", "exit_reference_price", "exit_execution_price",
    "exit_reason", "gross_pnl_quote", "net_pnl_quote", "fee_quote",
    "slippage_quote",
}


class P2AuditError(Exception):
    """P2 acceptance evidence is incomplete, inconsistent or unsafe."""


@dataclass(frozen=True, slots=True)
class ArtifactAuditResult:
    symbol: str
    trades: int
    input_sha256: str


@dataclass(frozen=True, slots=True)
class P2AuditResult:
    symbols: int
    scenarios: int
    artifacts: int
    trades: int


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _decimal(value, field):
    if (not isinstance(value, str)
            or SIGNED_DECIMAL_PATTERN.fullmatch(value) is None):
        raise P2AuditError(f"{field} must be an exact decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise P2AuditError(f"{field} is invalid") from None
    if not number.is_finite():
        raise P2AuditError(f"{field} is not finite")
    return number


def _audit_data(data, spec):
    if (not isinstance(data, dict) or set(data) != {
            "source", "symbol", "manifest_generated_at_ms", "intervals"}
            or data["source"] != "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV"
            or data["symbol"] != spec.symbol
            or type(data["manifest_generated_at_ms"]) is not int
            or data["manifest_generated_at_ms"] <= 0
            or not isinstance(data["intervals"], dict)
            or set(data["intervals"]) != {"1h", "15m", "4h"}):
        raise P2AuditError("Artifact data identity is invalid")
    for interval, value in data["intervals"].items():
        duration = INTERVAL_MILLISECONDS[interval]
        if (not isinstance(value, dict) or set(value) != {
                "rows", "first_open_time_ms", "last_open_time_ms", "sha256"}
                or type(value["rows"]) is not int or value["rows"] <= 0
                or type(value["first_open_time_ms"]) is not int
                or type(value["last_open_time_ms"]) is not int
                or value["first_open_time_ms"] > value["last_open_time_ms"]
                or value["first_open_time_ms"] % duration
                or value["last_open_time_ms"] % duration
                or ((value["last_open_time_ms"] - value["first_open_time_ms"])
                    // duration + 1) != value["rows"]
                or not isinstance(value["sha256"], str)
                or SHA256_PATTERN.fullmatch(value["sha256"]) is None):
            raise P2AuditError("Artifact interval identity is invalid")


def _audit_trades(trades, spec):
    if not isinstance(trades, list) or len(trades) > 100_000:
        raise P2AuditError("Artifact trade list is invalid")
    fill_inputs = []
    totals = {name: Decimal(0) for name in ("gross", "net", "fee", "slippage")}
    wins = losses = breakeven = 0
    previous_exit = None
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for trade in trades:
            if not isinstance(trade, dict) or set(trade) != TRADE_KEYS:
                raise P2AuditError("Artifact trade schema is invalid")
            entry_time = trade["entry_time_ms"]
            exit_time = trade["exit_time_ms"]
            if (type(entry_time) is not int or type(exit_time) is not int
                    or not spec.start_time_ms <= entry_time < exit_time < spec.end_time_ms
                    or previous_exit is not None and entry_time <= previous_exit):
                raise P2AuditError("Artifact trade time order is invalid")
            try:
                exit_reason = FillReason(trade["exit_reason"])
                entry_reference = FillReference(
                    IntentAction.ENTER_LONG, spec.symbol, entry_time, entry_time,
                    trade["quantity"], trade["entry_reference_price"],
                    FillReason.NEXT_PRIMARY_OPEN,
                )
                exit_reference = FillReference(
                    IntentAction.EXIT_LONG, spec.symbol, exit_time, exit_time,
                    trade["quantity"], trade["exit_reference_price"], exit_reason,
                )
                entry = apply_costs(entry_reference, spec)
                exit_fill = apply_costs(exit_reference, spec)
            except (ValueError, FillModelError):
                raise P2AuditError("Artifact trade cannot be reconstructed") from None
            gross = ((Decimal(trade["exit_reference_price"])
                      - Decimal(trade["entry_reference_price"]))
                     * Decimal(trade["quantity"]))
            net = entry.cash_delta + exit_fill.cash_delta
            fee = entry.fee_quote + exit_fill.fee_quote
            slippage = entry.slippage_quote + exit_fill.slippage_quote
            expected = (format(entry.execution_price, "f"),
                        format(exit_fill.execution_price, "f"),
                        format(gross, "f"), format(net, "f"),
                        format(fee, "f"), format(slippage, "f"))
            actual = (trade["entry_execution_price"], trade["exit_execution_price"],
                      trade["gross_pnl_quote"], trade["net_pnl_quote"],
                      trade["fee_quote"], trade["slippage_quote"])
            if actual != expected:
                raise P2AuditError("Artifact trade arithmetic is inconsistent")
            totals["gross"] += gross
            totals["net"] += net
            totals["fee"] += fee
            totals["slippage"] += slippage
            wins += net > 0
            losses += net < 0
            breakeven += net == 0
            fill_inputs.extend((
                {"action": "ENTER_LONG", "decision_time_ms": entry_time,
                 "fill_time_ms": entry_time, "quantity": trade["quantity"],
                 "reference_price": trade["entry_reference_price"],
                 "reason": "NEXT_PRIMARY_OPEN"},
                {"action": "EXIT_LONG", "decision_time_ms": exit_time,
                 "fill_time_ms": exit_time, "quantity": trade["quantity"],
                 "reference_price": trade["exit_reference_price"],
                 "reason": trade["exit_reason"]},
            ))
            previous_exit = exit_time
    return fill_inputs, totals, (wins, losses, breakeven)


def audit_run_manifest(encoded):
    if not isinstance(encoded, str):
        raise P2AuditError("Artifact must be canonical JSON text")
    try:
        manifest = json.loads(encoded)
        if encoded != artifact_json(manifest):
            raise P2AuditError("Artifact JSON is not canonical")
        config = manifest["configuration"]
        spec = BacktestSpec(**config)
    except (json.JSONDecodeError, KeyError, TypeError, ArtifactError,
            BacktestConfigError):
        raise P2AuditError("Artifact identity or safety policy is invalid") from None
    _audit_data(manifest["data"], spec)
    fill_inputs, totals, outcomes = _audit_trades(manifest["trades"], spec)

    metrics = manifest["metrics"]
    curve = manifest["equity_curve"]
    count_fields = ("trade_count", "winning_trades", "losing_trades",
                    "breakeven_trades")
    if (not isinstance(metrics, dict) or set(metrics) != EXPECTED_METRICS
            or not isinstance(curve, dict) or set(curve) != {
                "points", "start_time_ms", "end_time_ms", "initial_equity_quote",
                "final_equity_quote", "minimum_equity_quote", "maximum_equity_quote"}
            or any(type(metrics[name]) is not int or metrics[name] < 0
                   for name in count_fields)
            or metrics["trade_count"] != len(manifest["trades"])
            or (metrics["winning_trades"], metrics["losing_trades"],
                metrics["breakeven_trades"]) != outcomes
            or type(curve["points"]) is not int or curve["points"] <= 0
            or type(curve["start_time_ms"]) is not int
            or type(curve["end_time_ms"]) is not int
            or not spec.start_time_ms <= curve["start_time_ms"] <= curve["end_time_ms"]
            < spec.end_time_ms):
        raise P2AuditError("Artifact metrics or equity summary is invalid")
    initial = _decimal(curve["initial_equity_quote"], "initial equity")
    final = _decimal(curve["final_equity_quote"], "final equity")
    minimum = _decimal(curve["minimum_equity_quote"], "minimum equity")
    maximum = _decimal(curve["maximum_equity_quote"], "maximum equity")
    net = _decimal(metrics["net_pnl_quote"], "net PnL")
    gross = _decimal(metrics["gross_pnl_quote"], "gross PnL")
    fee = _decimal(metrics["total_fee_quote"], "total fee")
    slippage = _decimal(metrics["total_slippage_quote"], "total slippage")
    cost = _decimal(metrics["total_cost_quote"], "total cost")
    metric_initial = _decimal(metrics["initial_equity_quote"], "metric initial equity")
    metric_final = _decimal(metrics["final_equity_quote"], "metric final equity")
    total_return = _decimal(metrics["total_return"], "total return")
    max_drawdown_quote = _decimal(metrics["maximum_drawdown_quote"],
                                  "maximum drawdown quote")
    max_drawdown = _decimal(metrics["maximum_drawdown"], "maximum drawdown")
    for name in ("mean_period_return", "sample_period_volatility",
                 "downside_deviation", "mean_over_volatility",
                 "mean_over_downside"):
        if metrics[name] is not None:
            _decimal(metrics[name], name)
    actual_win_rate = (None if metrics["win_rate"] is None
                       else _decimal(metrics["win_rate"], "win rate"))
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        expected_win_rate = (Decimal(outcomes[0]) / Decimal(len(manifest["trades"]))
                             if manifest["trades"] else None)
        if (initial != spec.cash_decimal or metric_initial != initial
                or metric_final != final or final - initial != net
                or gross != net + cost or cost != fee + slippage
                or total_return != net / initial
                or actual_win_rate != expected_win_rate
                or max_drawdown_quote < 0 or max_drawdown < 0 or max_drawdown >= 1
                or totals != {"gross": gross, "net": net,
                              "fee": fee, "slippage": slippage}
                or not minimum <= min(initial, final) <= max(initial, final) <= maximum):
            raise P2AuditError("Artifact aggregate accounting is inconsistent")
    input_material = {"configuration": config, "data": manifest["data"],
                      "fill_inputs": fill_inputs}
    digest = hashlib.sha256(_canonical(input_material).encode("utf-8")).hexdigest()
    result_material = dict(manifest)
    result_digest = result_material.pop("result_sha256", None)
    expected_result_digest = hashlib.sha256(
        _canonical(result_material).encode("utf-8")
    ).hexdigest()
    if (manifest["artifact_kind"] != ARTIFACT_KIND
            or manifest["engine_version"] != ENGINE_VERSION
            or manifest["input_sha256"] != digest
            or result_digest != expected_result_digest):
        raise P2AuditError("Artifact input or result digest is inconsistent")
    return ArtifactAuditResult(spec.symbol, len(manifest["trades"]), digest)


def _audit_source_safety():
    forbidden = ("/api/v3/" + "order", "create_" + "order(",
                 "place_" + "order(", "submit_" + "order(",
                 "futures" + "_create_order", "withdraw" + "(")
    try:
        for path in Path(__file__).parent.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(value in text for value in forbidden):
                raise P2AuditError("P2 source contains an execution endpoint")
    except OSError:
        raise P2AuditError("P2 source safety scan failed") from None


def audit_p2(database_path="data/p1/market.sqlite3",
             manifest_path="manifests/p1-market-data.json", *, hours=24):
    try:
        audit_p1_manifest(manifest_path)
        _audit_source_safety()
        results = run_real_scenario_matrix(database_path, manifest_path, hours=hours)
        expected = {(symbol, name) for symbol in SYMBOLS for name in SCENARIOS}
        if {(item.symbol, item.name) for item in results} != expected or len(results) != 6:
            raise P2AuditError("P2 scenario coverage is incomplete")
        audits = [audit_run_manifest(item.manifest_json) for item in results]
        if any(audit.symbol != item.symbol
               or audit.trades != item.report.trade_count
               for audit, item in zip(audits, results)):
            raise P2AuditError("P2 artifacts and scenario results disagree")
        expected_counts = {"NO_TRADE": 0, "SINGLE_ROUND_TRIP": 1,
                           "CONTROLLED_MULTI_TRADE": 3}
        if any(item.report.trade_count != expected_counts[item.name] for item in results):
            raise P2AuditError("P2 scenario trade counts are inconsistent")
        return P2AuditResult(len(SYMBOLS), len(results), len(audits),
                             sum(item.trades for item in audits))
    except P2AuditError:
        raise
    except (AuditError, ScenarioError, TypeError, ValueError):
        raise P2AuditError("P2 final acceptance audit failed safely") from None
