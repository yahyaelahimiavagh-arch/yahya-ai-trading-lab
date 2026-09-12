"""P3-009 deterministic accepted-data candidate and baseline matrix."""

import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import uuid4

from yatl.backtest import (AcceptedBacktestDataset, ArtifactError, BacktestClock,
                           BacktestClockError, BacktestSpec, CostModelError,
                           EquityPoint, FillReason, FillReference, IntentAction,
                           MetricsError, PerformanceReport, PortfolioError,
                           PortfolioLedger,
                           apply_costs, artifact_json, build_run_manifest,
                           calculate_metrics, load_accepted_dataset)
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.loader import BacktestLoadError
from yatl.data import Candle, INTERVAL_MILLISECONDS, SYMBOLS

from .adapter import (FIXED_RESEARCH_QUANTITY, ResearchSignalAdapter,
                      SignalAdapterError)
from .breakout import (CONFIGURATION as BREAKOUT_CONFIGURATION,
                       IDENTITY as BREAKOUT_IDENTITY, BreakoutStrategyError,
                       evaluate_breakout)
from .contracts import StrategyContext, StrategyContractError, StrategyIdentity
from .evaluate import (EvaluationError, EvaluationPlan, EvaluationReport,
                       SymbolEvidence, assess_evidence,
                       evaluation_input_sha256)
from .trend import (CONFIGURATION as TREND_CONFIGURATION,
                    IDENTITY as TREND_IDENTITY, TrendStrategyError,
                    evaluate_trend_pullback)


TRAINING_START_MS = 1_786_406_400_000  # 2026-08-11T00:00:00Z
EVALUATION_START_MS = 1_787_184_000_000  # 2026-08-20T00:00:00Z
EVALUATION_END_MS = 1_788_912_000_000  # 2026-09-09T00:00:00Z
MATRIX_KIND = "YATL_P3_ACCEPTED_DATA_CANDIDATE_MATRIX"
MATRIX_SCHEMA_VERSION = 1
MAX_EVIDENCE_FILES = 32
MAX_INDEX_BYTES = 2 * 1024 * 1024
CANDIDATES = (
    (TREND_IDENTITY, TREND_CONFIGURATION.sha256, evaluate_trend_pullback),
    (BREAKOUT_IDENTITY, BREAKOUT_CONFIGURATION.sha256, evaluate_breakout),
)


class CandidateRunError(Exception):
    """P3-009 evidence could not be produced without weakening a gate."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _plain(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _candidate(identity):
    for item in CANDIDATES:
        if item[0] == identity:
            return item
    raise CandidateRunError("Candidate identity is not pre-registered")


def evaluation_plan(identity):
    registered, digest, _ = _candidate(identity)
    return EvaluationPlan(
        registered, digest, TRAINING_START_MS, EVALUATION_START_MS,
        EVALUATION_START_MS, EVALUATION_END_MS,
    )


def _sealed(dataset):
    if not isinstance(dataset, AcceptedBacktestDataset):
        raise CandidateRunError("Candidate run requires an accepted dataset")
    cutoff = dataset.spec.end_time_ms

    def visible(candles):
        return tuple(item for item in candles if item.close_time_ms < cutoff)

    result = replace(dataset, primary=visible(dataset.primary),
                     context=visible(dataset.context), regime=visible(dataset.regime))
    if any(not values for values in (result.primary, result.context, result.regime)):
        raise CandidateRunError("Sealed candidate input is incomplete")
    return result


def _events(dataset):
    try:
        values = tuple(BacktestClock(dataset).events())
    except BacktestClockError:
        raise CandidateRunError("Candidate event clock failed safely") from None
    if len(values) < 2:
        raise CandidateRunError("Candidate evaluation window is too short")
    return values


def _fill_record(fill):
    reference = fill.reference
    return {
        "action": reference.action.value,
        "decision_time_ms": reference.decision_time_ms,
        "fill_time_ms": reference.fill_time_ms,
        "quantity": reference.quantity,
        "reference_price": reference.reference_price,
        "reason": reference.reason.value,
    }


def _candidate_execution(dataset, identity):
    sealed = _sealed(dataset)
    _, _, evaluator = _candidate(identity)
    events = _events(sealed)
    by_open = {item.open_time_ms: item for item in sealed.primary}
    if len(by_open) != len(sealed.primary):
        raise CandidateRunError("Candidate primary candles are duplicated")
    adapter = ResearchSignalAdapter(identity, sealed.spec.symbol)
    ledger = PortfolioLedger(sealed.spec)
    fills = []
    trace = []
    points = [EquityPoint(
        events[0].decision_time_ms,
        ledger.snapshot(events[0].snapshot.latest_primary.close),
    )]
    for index, event in enumerate(events):
        candle = by_open.get(event.eligible_fill_open_time_ms)
        if candle is None or not candle.is_closed:
            raise CandidateRunError("Candidate next-open candle is unavailable")
        context = StrategyContext(identity, event.snapshot)
        if any(item.close_time_ms >= event.decision_time_ms
               for values in (event.snapshot.primary, event.snapshot.context,
                              event.snapshot.regime) for item in values):
            raise CandidateRunError("Candidate snapshot contains future data")
        decision = evaluator(context, in_position=adapter.has_position,
                             active_setup=adapter.active_setup)
        step = adapter.process(event, decision, candle)
        costed = tuple(apply_costs(item, sealed.spec) for item in step.fills)
        if costed:
            ledger.apply_many(costed)
            fills.extend(costed)
        trace.append({
            "sequence": event.sequence,
            "decision_time_ms": event.decision_time_ms,
            "action": decision.action.value,
            "reason": decision.reason.value,
            "context_sha256": decision.context_sha256,
            "fills": [_fill_record(item) for item in costed],
        })
        if index:
            points.append(EquityPoint(event.decision_time_ms,
                                      ledger.snapshot(candle.open)))
    if adapter.has_position or ledger.has_position:
        raise CandidateRunError("Candidate ended with unresolved paper exposure")
    report = calculate_metrics(tuple(points))
    encoded = artifact_json(build_run_manifest(sealed, tuple(fills), report))
    trace_json = _json({
        "schema_version": 1,
        "artifact_kind": "YATL_P3_DECISION_TRACE",
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.version,
        "symbol": sealed.spec.symbol,
        "evaluation_start_ms": EVALUATION_START_MS,
        "evaluation_end_ms": EVALUATION_END_MS,
        "paper_only": True,
        "live_master_lock": "OFF",
        "decisions": trace,
    })
    return report, encoded, trace_json, tuple(fills)


def _baseline_execution(dataset, name):
    if name not in ("NO_TRADE", "BUY_AND_HOLD"):
        raise CandidateRunError("Baseline identity is invalid")
    sealed = _sealed(dataset)
    events = _events(sealed)
    by_open = {item.open_time_ms: item for item in sealed.primary}
    ledger = PortfolioLedger(sealed.spec)
    fills = []
    points = [EquityPoint(
        events[0].decision_time_ms,
        ledger.snapshot(events[0].snapshot.latest_primary.close),
    )]
    for index, event in enumerate(events):
        candle = by_open.get(event.eligible_fill_open_time_ms)
        if candle is None or not candle.is_closed:
            raise CandidateRunError("Baseline next-open candle is unavailable")
        reference = None
        if name == "BUY_AND_HOLD" and index == 0:
            reference = FillReference(
                IntentAction.ENTER_LONG, sealed.spec.symbol,
                event.decision_time_ms, event.eligible_fill_open_time_ms,
                FIXED_RESEARCH_QUANTITY, candle.open,
                FillReason.NEXT_PRIMARY_OPEN,
            )
        elif name == "BUY_AND_HOLD" and index == len(events) - 1:
            reference = FillReference(
                IntentAction.EXIT_LONG, sealed.spec.symbol,
                event.decision_time_ms, event.eligible_fill_open_time_ms,
                FIXED_RESEARCH_QUANTITY, candle.open,
                FillReason.SCRIPTED_EXIT,
            )
        if reference is not None:
            fill = apply_costs(reference, sealed.spec)
            ledger.apply(fill)
            fills.append(fill)
        if index:
            points.append(EquityPoint(event.decision_time_ms,
                                      ledger.snapshot(candle.open)))
    if ledger.has_position:
        raise CandidateRunError("Baseline ended with unresolved paper exposure")
    report = calculate_metrics(tuple(points))
    encoded = artifact_json(build_run_manifest(sealed, tuple(fills), report))
    return report, encoded


def _segment_returns(report):
    points = report.points
    transitions = len(points) - 1
    indexes = (0, transitions // 3, (2 * transitions) // 3, transitions)
    values = []
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        for start, end in zip(indexes, indexes[1:]):
            if start == end:
                raise CandidateRunError("Evaluation segment has no observations")
            values.append(_plain(
                points[end].portfolio.equity_quote
                / points[start].portfolio.equity_quote - Decimal(1)))
    return tuple(values)


def _future_mutation(dataset):
    changed = False

    def mutate(values):
        nonlocal changed
        result = []
        for item in values:
            if not changed and item.open_time_ms >= EVALUATION_END_MS:
                item = replace(item, trade_count=item.trade_count + 1)
                changed = True
            result.append(item)
        return tuple(result)

    result = replace(dataset, primary=mutate(dataset.primary),
                     context=mutate(dataset.context), regime=mutate(dataset.regime))
    if not changed:
        raise CandidateRunError("Accepted dataset lacks future-isolation material")
    return result


@dataclass(frozen=True, slots=True)
class CandidateSymbolResult:
    identity: StrategyIdentity
    configuration_sha256: str
    symbol: str
    dataset_sha256: str
    report: object
    zero_cost_report: object
    no_trade_report: object
    buy_hold_report: object
    candidate_artifact: str
    zero_cost_artifact: str
    no_trade_artifact: str
    buy_hold_artifact: str
    trace_json: str
    cost_drag_quote: Decimal

    def __post_init__(self):
        if (self.symbol not in SYMBOLS or self.identity != _candidate(self.identity)[0]
                or self.configuration_sha256 != _candidate(self.identity)[1]
                or len(self.dataset_sha256) != 64
                or any(character not in "0123456789abcdef"
                       for character in self.dataset_sha256)
                or any(not isinstance(value, PerformanceReport)
                       for value in (self.report, self.zero_cost_report,
                                     self.no_trade_report, self.buy_hold_report))
                or any(not isinstance(value, str) or not value.endswith("\n")
                       for value in (self.candidate_artifact,
                                     self.zero_cost_artifact,
                                     self.no_trade_artifact,
                                     self.buy_hold_artifact, self.trace_json))
                or type(self.cost_drag_quote) is not Decimal
                or self.cost_drag_quote < 0):
            raise CandidateRunError("Candidate symbol result is invalid")


@dataclass(frozen=True, slots=True)
class CandidateMatrixResult:
    runs: tuple[CandidateSymbolResult, ...]
    evaluations: tuple[EvaluationReport, ...]
    index_json: str

    def __post_init__(self):
        expected = {(identity, symbol) for identity, _, _ in CANDIDATES
                    for symbol in SYMBOLS}
        actual = {(item.identity, item.symbol) for item in self.runs}
        if (type(self.runs) is not tuple or actual != expected
                or len(actual) != len(self.runs)
                or type(self.evaluations) is not tuple
                or len(self.evaluations) != len(CANDIDATES)
                or any(not isinstance(item, EvaluationReport)
                       for item in self.evaluations)
                or not isinstance(self.index_json, str)
                or len(self.index_json.encode("utf-8")) > MAX_INDEX_BYTES):
            raise CandidateRunError("Candidate matrix result is incomplete")
        if (tuple(item.plan.identity for item in self.evaluations)
                != tuple(item[0] for item in CANDIDATES)):
            raise CandidateRunError("Candidate evaluations are out of order")


def _filename(result, suffix):
    strategy = result.identity.strategy_id.lower().replace("_", "-")
    return f"{strategy}-{result.identity.version}-{result.symbol.lower()}-{suffix}.json"


def _run_record(result):
    files = {
        "candidate_costed": _filename(result, "candidate-costed"),
        "candidate_zero_cost": _filename(result, "candidate-zero-cost"),
        "baseline_no_trade": _filename(result, "baseline-no-trade"),
        "baseline_buy_hold": _filename(result, "baseline-buy-hold"),
        "decision_trace": _filename(result, "decision-trace"),
    }
    payloads = {
        "candidate_costed": result.candidate_artifact,
        "candidate_zero_cost": result.zero_cost_artifact,
        "baseline_no_trade": result.no_trade_artifact,
        "baseline_buy_hold": result.buy_hold_artifact,
        "decision_trace": result.trace_json,
    }
    return {
        "strategy_id": result.identity.strategy_id,
        "strategy_version": result.identity.version,
        "configuration_sha256": result.configuration_sha256,
        "symbol": result.symbol,
        "dataset_sha256": result.dataset_sha256,
        "trades": result.report.trade_count,
        "total_return": _plain(result.report.total_return),
        "maximum_drawdown": _plain(result.report.maximum_drawdown),
        "total_cost_quote": _plain(result.report.total_cost_quote),
        "zero_cost_total_return": _plain(result.zero_cost_report.total_return),
        "cost_drag_quote": _plain(result.cost_drag_quote),
        "no_trade_return": _plain(result.no_trade_report.total_return),
        "buy_hold_return": _plain(result.buy_hold_report.total_return),
        "buy_hold_maximum_drawdown": _plain(
            result.buy_hold_report.maximum_drawdown),
        "segment_returns": list(_segment_returns(result.report)),
        "replay_equal": True,
        "point_in_time_verified": True,
        "future_isolation_verified": True,
        "artifacts": {name: {"file": files[name],
                              "sha256": _sha256(payloads[name])}
                      for name in sorted(files)},
    }


def run_accepted_candidate_matrix(database_path, manifest_path):
    loaded = {}
    baselines = {}
    for symbol in SYMBOLS:
        spec = BacktestSpec(symbol, EVALUATION_START_MS, EVALUATION_END_MS)
        try:
            dataset = load_accepted_dataset(database_path, manifest_path, spec)
        except BacktestLoadError:
            raise CandidateRunError("Accepted candidate dataset could not be loaded") from None
        loaded[symbol] = dataset
        baselines[symbol] = (
            _baseline_execution(dataset, "NO_TRADE"),
            _baseline_execution(dataset, "BUY_AND_HOLD"),
        )

    results = []
    evidence_by_identity = {identity: [] for identity, _, _ in CANDIDATES}
    for identity, configuration_sha256, _ in CANDIDATES:
        plan = evaluation_plan(identity)
        for symbol in SYMBOLS:
            dataset = loaded[symbol]
            report, encoded, trace, fills = _candidate_execution(dataset, identity)
            repeated = _candidate_execution(dataset, identity)
            if (report, encoded, trace, fills) != repeated:
                raise CandidateRunError("Candidate replay is not byte-identical")
            zero_dataset = replace(
                dataset, spec=replace(dataset.spec, fee_bps="0", slippage_bps="0"))
            zero_report, zero_encoded, zero_trace, zero_fills = _candidate_execution(
                zero_dataset, identity)
            if (trace != zero_trace
                    or tuple(item.reference for item in fills)
                    != tuple(item.reference for item in zero_fills)):
                raise CandidateRunError("Costs changed candidate decisions or references")
            drag = zero_report.net_pnl_quote - report.net_pnl_quote
            if ((report.trade_count and drag <= 0)
                    or (not report.trade_count and drag != 0)
                    or drag != report.total_cost_quote):
                raise CandidateRunError("Candidate cost drag is inconsistent")
            future = _candidate_execution(_future_mutation(dataset), identity)
            if (report, encoded, trace, fills) != future:
                raise CandidateRunError("Future data changed sealed candidate evidence")
            (no_trade_report, no_trade_artifact), (buy_hold_report, buy_hold_artifact) = (
                baselines[symbol])
            sealed = _sealed(dataset)
            data_sha = evaluation_input_sha256(
                sealed.primary + sealed.context + sealed.regime,
                symbol, EVALUATION_END_MS)
            result = CandidateSymbolResult(
                identity, configuration_sha256, symbol, data_sha,
                report, zero_report, no_trade_report, buy_hold_report,
                encoded, zero_encoded, no_trade_artifact, buy_hold_artifact,
                trace, drag,
            )
            results.append(result)
            evidence_by_identity[identity].append(SymbolEvidence(
                symbol=symbol, plan_sha256=plan.sha256,
                configuration_sha256=configuration_sha256,
                evaluation_start_ms=EVALUATION_START_MS,
                evaluation_end_ms=EVALUATION_END_MS,
                dataset_sha256=data_sha, trade_count=report.trade_count,
                total_return=_plain(report.total_return),
                maximum_drawdown=_plain(report.maximum_drawdown),
                total_cost_quote=_plain(report.total_cost_quote),
                buy_hold_return=_plain(buy_hold_report.total_return),
                buy_hold_maximum_drawdown=_plain(
                    buy_hold_report.maximum_drawdown),
                segment_returns=_segment_returns(report), replay_equal=True,
                point_in_time_verified=True, future_isolation_verified=True,
            ))
    evaluations = tuple(assess_evidence(
        evaluation_plan(identity), tuple(evidence_by_identity[identity]))
        for identity, _, _ in CANDIDATES)
    records = [_run_record(item) for item in results]
    index = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "training_start_ms": TRAINING_START_MS,
        "training_end_ms": EVALUATION_START_MS,
        "evaluation_start_ms": EVALUATION_START_MS,
        "evaluation_end_ms": EVALUATION_END_MS,
        "symbols": list(SYMBOLS),
        "fixed_research_quantity": FIXED_RESEARCH_QUANTITY,
        "paper_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_leverage": False,
        "qualification_is_not_trading_approval": True,
        "runs": records,
        "evaluations": [dict(item.to_record(), report_sha256=item.sha256)
                        for item in evaluations],
    }
    encoded_index = _json(index)
    return CandidateMatrixResult(tuple(results), evaluations, encoded_index)


def write_candidate_matrix(result, output_dir):
    if not isinstance(result, CandidateMatrixResult):
        raise CandidateRunError("Candidate matrix output is invalid")
    target = Path(output_dir) if isinstance(output_dir, (str, Path)) and str(output_dir) else None
    if target is None:
        raise CandidateRunError("Candidate evidence output directory is invalid")
    if target.exists():
        raise CandidateRunError("Existing evidence directory will not be overwritten")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir(parents=True)
        files = {"p3-009-index.json": result.index_json}
        for item in result.runs:
            files.update({
                _filename(item, "candidate-costed"): item.candidate_artifact,
                _filename(item, "candidate-zero-cost"): item.zero_cost_artifact,
                _filename(item, "baseline-no-trade"): item.no_trade_artifact,
                _filename(item, "baseline-buy-hold"): item.buy_hold_artifact,
                _filename(item, "decision-trace"): item.trace_json,
            })
        if not 1 <= len(files) <= MAX_EVIDENCE_FILES:
            raise CandidateRunError("Candidate evidence file count is invalid")
        for name, content in files.items():
            (temporary / name).write_text(content, encoding="utf-8", newline="\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except CandidateRunError:
        raise
    except OSError:
        raise CandidateRunError("Cannot publish candidate evidence atomically") from None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def candidate_matrix_sha256(result):
    if not isinstance(result, CandidateMatrixResult):
        raise CandidateRunError("Candidate matrix digest input is invalid")
    return _sha256(result.index_json)


def run_and_write_candidate_matrix(database_path, manifest_path, output_dir):
    try:
        result = run_accepted_candidate_matrix(database_path, manifest_path)
        write_candidate_matrix(result, output_dir)
        return result
    except CandidateRunError:
        raise
    except (ArtifactError, BacktestClockError, CostModelError, EvaluationError,
            MetricsError, PortfolioError, SignalAdapterError,
            StrategyContractError, TrendStrategyError, BreakoutStrategyError,
            TypeError, ValueError):
        raise CandidateRunError("Accepted candidate matrix failed safely") from None
