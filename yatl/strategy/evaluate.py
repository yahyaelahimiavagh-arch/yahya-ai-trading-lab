"""Pre-registered, deterministic P3 evidence protocol; no strategy tuning."""

import hashlib
import json
import re
from dataclasses import dataclass, fields, replace
from decimal import Decimal, localcontext
from enum import Enum

from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.data import Candle, DATA_SOURCE, SYMBOLS

from .breakout import CONFIGURATION as BREAKOUT_CONFIGURATION
from .contracts import StrategyContractError, StrategyIdentity
from .trend import CONFIGURATION as TREND_CONFIGURATION


PROTOCOL_VERSION = "P3_EVAL_V1"
DAY_MS = 86_400_000
MIN_EVALUATION_DAYS = 180
MIN_TRADES_PER_SYMBOL = 30
MIN_TOTAL_TRADES = 60
SEGMENT_COUNT = 3
MAX_DRAWDOWN = Decimal("0.25")
MAX_SEGMENT_LOSS = Decimal("0.10")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SIGNED_DECIMAL_PATTERN = re.compile(
    r"-?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?")
LOCKED_CONFIGURATIONS = {
    TREND_CONFIGURATION.definition.identity: TREND_CONFIGURATION.sha256,
    BREAKOUT_CONFIGURATION.definition.identity: BREAKOUT_CONFIGURATION.sha256,
}


class EvaluationError(Exception):
    """Evaluation inputs violate the pre-registered research protocol."""


class EvidenceLabel(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"
    QUALIFIED_FOR_P4_RESEARCH = "QUALIFIED_FOR_P4_RESEARCH"


class EvidenceReason(str, Enum):
    EVALUATION_WINDOW_TOO_SHORT = "EVALUATION_WINDOW_TOO_SHORT"
    MINIMUM_TRADES_NOT_MET = "MINIMUM_TRADES_NOT_MET"
    SOFTWARE_EVIDENCE_FAILED = "SOFTWARE_EVIDENCE_FAILED"
    NO_TRADE_BASELINE_NOT_BEATEN = "NO_TRADE_BASELINE_NOT_BEATEN"
    BUY_HOLD_NOT_BEATEN = "BUY_HOLD_NOT_BEATEN"
    DRAWDOWN_GATE_FAILED = "DRAWDOWN_GATE_FAILED"
    SEGMENT_STABILITY_FAILED = "SEGMENT_STABILITY_FAILED"
    ALL_GATES_PASSED = "ALL_GATES_PASSED"


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256(value, field):
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise EvaluationError(f"{field} must be a lowercase SHA-256")
    return value


def _number(value, field, *, nonnegative=False, unit=False):
    if type(value) is not str or SIGNED_DECIMAL_PATTERN.fullmatch(value) is None:
        raise EvaluationError(f"{field} must be a plain decimal string")
    number = Decimal(value)
    if (not number.is_finite() or (nonnegative and number < 0)
            or (unit and not 0 <= number <= 1)):
        raise EvaluationError(f"{field} is outside the allowed range")
    return number


def _plain(value):
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def evaluation_input_sha256(candles, symbol, evaluation_end_ms):
    """Hash only closed market data legally visible before the frozen cutoff."""
    if (type(candles) is not tuple or not candles or len(candles) > 1_000_000
            or symbol not in SYMBOLS or type(evaluation_end_ms) is not int
            or evaluation_end_ms <= 0
            or any(type(item) is not Candle or item.source != DATA_SOURCE
                   or item.symbol != symbol for item in candles)):
        raise EvaluationError("Evaluation input identity is invalid")
    visible = tuple(item for item in candles
                    if item.close_time_ms < evaluation_end_ms)
    keys = tuple((item.interval, item.open_time_ms) for item in visible)
    if (not visible or any(not item.is_closed for item in visible)
            or len(set(keys)) != len(keys)):
        raise EvaluationError("Visible evaluation input is incomplete or duplicated")
    records = [item.as_record() for item in sorted(
        visible, key=lambda item: (item.interval, item.open_time_ms))]
    return _digest(records)


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    identity: StrategyIdentity
    configuration_sha256: str
    training_start_ms: int
    training_end_ms: int
    evaluation_start_ms: int
    evaluation_end_ms: int
    symbols: tuple[str, ...] = SYMBOLS
    segment_count: int = SEGMENT_COUNT
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self):
        try:
            replace(self.identity)
        except (StrategyContractError, TypeError, ValueError):
            raise EvaluationError("Evaluation strategy identity is invalid") from None
        expected_digest = LOCKED_CONFIGURATIONS.get(self.identity)
        if (expected_digest is None
                or _sha256(self.configuration_sha256, "configuration_sha256")
                != expected_digest
                or type(self.training_start_ms) is not int
                or type(self.training_end_ms) is not int
                or type(self.evaluation_start_ms) is not int
                or type(self.evaluation_end_ms) is not int
                or min(self.training_start_ms, self.training_end_ms,
                       self.evaluation_start_ms, self.evaluation_end_ms) <= 0
                or any(value % DAY_MS for value in (
                    self.training_start_ms, self.training_end_ms,
                    self.evaluation_start_ms, self.evaluation_end_ms))
                or not self.training_start_ms < self.training_end_ms
                or self.training_end_ms > self.evaluation_start_ms
                or self.evaluation_start_ms >= self.evaluation_end_ms
                or self.symbols != SYMBOLS
                or self.segment_count != SEGMENT_COUNT
                or self.protocol_version != PROTOCOL_VERSION):
            raise EvaluationError("Evaluation plan is not a valid frozen protocol")

    def to_record(self):
        replace(self)
        return {
            "protocol_version": self.protocol_version,
            "strategy_id": self.identity.strategy_id,
            "strategy_version": self.identity.version,
            "configuration_sha256": self.configuration_sha256,
            "training_start_ms": self.training_start_ms,
            "training_end_ms": self.training_end_ms,
            "evaluation_start_ms": self.evaluation_start_ms,
            "evaluation_end_ms": self.evaluation_end_ms,
            "symbols": list(self.symbols),
            "segment_count": self.segment_count,
            "paper_only": True,
            "live_master_lock": "OFF",
        }

    @property
    def sha256(self):
        return _digest(self.to_record())

    @property
    def evaluation_days(self):
        return (self.evaluation_end_ms - self.evaluation_start_ms) // DAY_MS


@dataclass(frozen=True, slots=True)
class SymbolEvidence:
    symbol: str
    plan_sha256: str
    configuration_sha256: str
    evaluation_start_ms: int
    evaluation_end_ms: int
    dataset_sha256: str
    trade_count: int
    total_return: str
    maximum_drawdown: str
    total_cost_quote: str
    buy_hold_return: str
    buy_hold_maximum_drawdown: str
    segment_returns: tuple[str, ...]
    replay_equal: bool
    point_in_time_verified: bool
    future_isolation_verified: bool

    def __post_init__(self):
        if (self.symbol not in SYMBOLS
                or type(self.evaluation_start_ms) is not int
                or type(self.evaluation_end_ms) is not int
                or self.evaluation_start_ms >= self.evaluation_end_ms
                or type(self.trade_count) is not int
                or not 0 <= self.trade_count <= 1_000_000
                or type(self.segment_returns) is not tuple
                or len(self.segment_returns) != SEGMENT_COUNT
                or type(self.replay_equal) is not bool
                or type(self.point_in_time_verified) is not bool
                or type(self.future_isolation_verified) is not bool):
            raise EvaluationError("Symbol evidence identity is invalid")
        _sha256(self.plan_sha256, "plan_sha256")
        _sha256(self.configuration_sha256, "configuration_sha256")
        _sha256(self.dataset_sha256, "dataset_sha256")
        normalized = {
            "total_return": _plain(_number(self.total_return, "total_return")),
            "maximum_drawdown": _plain(_number(
                self.maximum_drawdown, "maximum_drawdown", unit=True)),
            "total_cost_quote": _plain(_number(
                self.total_cost_quote, "total_cost_quote", nonnegative=True)),
            "buy_hold_return": _plain(_number(
                self.buy_hold_return, "buy_hold_return")),
            "buy_hold_maximum_drawdown": _plain(_number(
                self.buy_hold_maximum_drawdown,
                "buy_hold_maximum_drawdown", unit=True)),
        }
        for name, value in normalized.items():
            object.__setattr__(self, name, value)
        object.__setattr__(
            self, "segment_returns",
            tuple(_plain(_number(value, "segment_return"))
                  for value in self.segment_returns))

    def to_record(self):
        replace(self)
        result = {item.name: getattr(self, item.name) for item in fields(self)}
        result["segment_returns"] = list(self.segment_returns)
        return result

    @property
    def sha256(self):
        return _digest(self.to_record())


def _assessment(plan, runs):
    if (type(plan) is not EvaluationPlan or type(runs) is not tuple
            or len(runs) != len(SYMBOLS)
            or any(type(run) is not SymbolEvidence for run in runs)):
        raise EvaluationError("Evaluation requires one immutable run per symbol")
    replace(plan)
    ordered = tuple(sorted((replace(run) for run in runs),
                           key=lambda run: run.symbol))
    if tuple(run.symbol for run in ordered) != tuple(sorted(SYMBOLS)):
        raise EvaluationError("Evaluation symbol evidence is incomplete or duplicated")
    for run in ordered:
        if (run.plan_sha256 != plan.sha256
                or run.configuration_sha256 != plan.configuration_sha256
                or run.evaluation_start_ms != plan.evaluation_start_ms
                or run.evaluation_end_ms != plan.evaluation_end_ms):
            raise EvaluationError("Evidence does not match the frozen evaluation plan")

    total_trades = sum(run.trade_count for run in ordered)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        mean_return = sum((_number(run.total_return, "total_return")
                           for run in ordered), Decimal(0)) / len(ordered)
        mean_buy_hold = sum((_number(run.buy_hold_return, "buy_hold_return")
                             for run in ordered), Decimal(0)) / len(ordered)
        total_cost = sum((_number(run.total_cost_quote, "total_cost_quote",
                                  nonnegative=True) for run in ordered), Decimal(0))

    insufficient = []
    if plan.evaluation_days < MIN_EVALUATION_DAYS:
        insufficient.append(EvidenceReason.EVALUATION_WINDOW_TOO_SHORT)
    if (total_trades < MIN_TOTAL_TRADES
            or any(run.trade_count < MIN_TRADES_PER_SYMBOL for run in ordered)):
        insufficient.append(EvidenceReason.MINIMUM_TRADES_NOT_MET)
    if insufficient:
        return (ordered, EvidenceLabel.INSUFFICIENT_EVIDENCE,
                tuple(insufficient), total_trades, mean_return,
                mean_buy_hold, total_cost)

    rejected = []
    if any(not (run.replay_equal and run.point_in_time_verified
                and run.future_isolation_verified) for run in ordered):
        rejected.append(EvidenceReason.SOFTWARE_EVIDENCE_FAILED)
    if any(_number(run.total_return, "total_return") <= 0 for run in ordered):
        rejected.append(EvidenceReason.NO_TRADE_BASELINE_NOT_BEATEN)
    if any(_number(run.total_return, "total_return")
           <= _number(run.buy_hold_return, "buy_hold_return") for run in ordered):
        rejected.append(EvidenceReason.BUY_HOLD_NOT_BEATEN)
    if any(_number(run.maximum_drawdown, "maximum_drawdown", unit=True)
           > min(MAX_DRAWDOWN,
                 _number(run.buy_hold_maximum_drawdown,
                         "buy_hold_maximum_drawdown", unit=True))
           for run in ordered):
        rejected.append(EvidenceReason.DRAWDOWN_GATE_FAILED)
    if any(sum(_number(value, "segment_return") > 0
               for value in run.segment_returns) < 2
           or min(_number(value, "segment_return")
                  for value in run.segment_returns) < -MAX_SEGMENT_LOSS
           for run in ordered):
        rejected.append(EvidenceReason.SEGMENT_STABILITY_FAILED)
    if rejected:
        return (ordered, EvidenceLabel.REJECTED, tuple(rejected), total_trades,
                mean_return, mean_buy_hold, total_cost)
    return (ordered, EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
            (EvidenceReason.ALL_GATES_PASSED,), total_trades,
            mean_return, mean_buy_hold, total_cost)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    plan: EvaluationPlan
    runs: tuple[SymbolEvidence, ...]
    label: EvidenceLabel
    reasons: tuple[EvidenceReason, ...]
    total_trades: int
    mean_total_return: Decimal
    mean_buy_hold_return: Decimal
    total_cost_quote: Decimal

    def __post_init__(self):
        expected = _assessment(self.plan, self.runs)
        actual = (self.runs, self.label, self.reasons, self.total_trades,
                  self.mean_total_return, self.mean_buy_hold_return,
                  self.total_cost_quote)
        if actual != expected:
            raise EvaluationError("Evaluation report is inconsistent")

    def to_record(self):
        replace(self)
        return {
            "schema_version": 1,
            "plan": self.plan.to_record(),
            "plan_sha256": self.plan.sha256,
            "runs": [run.to_record() for run in self.runs],
            "label": self.label.value,
            "reasons": [reason.value for reason in self.reasons],
            "pooled": {
                "total_trades": self.total_trades,
                "mean_total_return": _plain(self.mean_total_return),
                "mean_buy_hold_return": _plain(self.mean_buy_hold_return),
                "total_cost_quote": _plain(self.total_cost_quote),
                "no_trade_return": "0",
            },
            "qualification_is_not_trading_approval": True,
        }

    @property
    def sha256(self):
        return _digest(self.to_record())


def assess_evidence(plan, runs):
    values = _assessment(plan, runs)
    return EvaluationReport(plan, *values)
