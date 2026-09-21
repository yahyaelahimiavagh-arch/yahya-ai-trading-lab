"""P10-005 deterministic frozen-baseline forward Paper replay runner."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from yatl.backtest import (
    AcceptedBacktestDataset,
    BacktestClock,
    BacktestSpec,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.backtest.costs import BASIS_POINTS, DECIMAL_PRECISION
from yatl.data import INTERVAL_MILLISECONDS
from yatl.execution import LocalPaperExecutionPolicy
from yatl.risk import RiskPolicy
from yatl.strategy import (
    StrategyAction,
    StrategyContext,
    TREND_PULLBACK_IDENTITY,
    evaluate_trend_pullback,
)
from yatl.strategy.adapter import FIXED_RESEARCH_QUANTITY

from .forward_store import ForwardCandleStore
from .ingestion import ForwardIngestionSnapshot
from .registration import CandidateFreeze, CandidateGateRegistration
from .window import ForwardWindowSeal


FORWARD_PAPER_RUNNER_ID = "P10_FORWARD_PAPER_V1"
P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1 = "53500425684a9e0b4078a047eedbad4ae8176460"
REGIME_WARMUP_BARS = 51
RUNNER_QUANTITY = "0.001"
UTC_DAY_MS = 86_400_000


class ForwardPaperRunnerError(Exception):
    """The P10 forward Paper replay violated a frozen boundary."""


class EntryVetoReason(str, Enum):
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    SESSION_LOSS_LIMIT = "SESSION_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    CONSECUTIVE_LOSS_LIMIT = "CONSECUTIVE_LOSS_LIMIT"
    OPEN_POSITION_LIMIT = "OPEN_POSITION_LIMIT"
    CASH_INSUFFICIENT = "CASH_INSUFFICIENT"
    POSITION_LIMIT = "POSITION_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    PLANNED_LOSS_LIMIT = "PLANNED_LOSS_LIMIT"
    INVALID_PROTECTIVE_LEVELS = "INVALID_PROTECTIVE_LEVELS"
    NON_POSITIVE_POST_COST_REWARD = "NON_POSITIVE_POST_COST_REWARD"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _plain(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ForwardPaperRunnerError("Paper arithmetic is not finite")
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _dataset_digest(candles):
    return _sha256([item.as_record() for item in candles])


def _portfolio_record(snapshot):
    return {
        "symbol": snapshot.symbol,
        "cash": _plain(snapshot.cash),
        "asset_quantity": _plain(snapshot.asset_quantity),
        "cost_basis_quote": _plain(snapshot.cost_basis_quote),
        "liquidation_value_quote": _plain(snapshot.liquidation_value_quote),
        "realized_pnl_quote": _plain(snapshot.realized_pnl_quote),
        "unrealized_pnl_quote": _plain(snapshot.unrealized_pnl_quote),
        "equity_quote": _plain(snapshot.equity_quote),
        "total_fee_quote": _plain(snapshot.total_fee_quote),
        "total_slippage_quote": _plain(snapshot.total_slippage_quote),
        "closed_trades": snapshot.closed_trades,
    }


def _fill_record(fill):
    reference = fill.reference
    return {
        "action": reference.action.value,
        "decision_time_ms": reference.decision_time_ms,
        "fill_time_ms": reference.fill_time_ms,
        "quantity": reference.quantity,
        "reference_price": reference.reference_price,
        "reason": reference.reason.value,
        "execution_price": _plain(fill.execution_price),
        "gross_quote": _plain(fill.gross_quote),
        "fee_quote": _plain(fill.fee_quote),
        "slippage_quote": _plain(fill.slippage_quote),
        "cash_delta": _plain(fill.cash_delta),
        "asset_delta": _plain(fill.asset_delta),
        "total_cost_quote": _plain(fill.total_cost_quote),
    }


@dataclass(frozen=True, slots=True)
class ValidationRiskState:
    symbol: str
    equity_quote: str
    cash_quote: str
    position_quantity: str
    mark_price: str
    peak_equity_quote: str
    session_start_time_ms: int
    session_start_equity_quote: str
    session_realized_pnl_quote: str
    consecutive_losses: int
    open_positions: int
    kill_switch_active: bool

    def as_record(self):
        return {
            name: (
                getattr(self, name).value
                if isinstance(getattr(self, name), Enum)
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class EntrySafetyVeto:
    allowed: bool
    reasons: tuple[EntryVetoReason, ...]
    quantity: str
    risk_budget_quote: str
    planned_loss_quote: str
    entry_notional_quote: str
    cash_required_quote: str
    position_limit_quote: str
    gross_exposure_after_quote: str
    gross_exposure_limit_quote: str
    net_reward_quote: str

    def __post_init__(self):
        if (
            type(self.allowed) is not bool
            or type(self.reasons) is not tuple
            or any(not isinstance(item, EntryVetoReason) for item in self.reasons)
            or self.allowed != (not self.reasons)
            or self.quantity != RUNNER_QUANTITY
        ):
            raise ForwardPaperRunnerError("P10 entry-veto evidence is inconsistent")

    def as_record(self):
        return {
            "allowed": self.allowed,
            "reasons": [item.value for item in self.reasons],
            "quantity": self.quantity,
            "risk_budget_quote": self.risk_budget_quote,
            "planned_loss_quote": self.planned_loss_quote,
            "entry_notional_quote": self.entry_notional_quote,
            "cash_required_quote": self.cash_required_quote,
            "position_limit_quote": self.position_limit_quote,
            "gross_exposure_after_quote": self.gross_exposure_after_quote,
            "gross_exposure_limit_quote": self.gross_exposure_limit_quote,
            "net_reward_quote": self.net_reward_quote,
        }


def assess_fixed_quantity_entry(decision, risk_state, policy=None):
    """Veto the frozen P3 research quantity using the accepted P4 numeric envelope.

    This function never approves a new quantity and never creates a P4 authorization object.
    """
    if policy is None:
        policy = RiskPolicy()
    if (
        decision.action is not StrategyAction.ENTER_LONG
        or decision.setup is None
        or not isinstance(risk_state, ValidationRiskState)
        or not isinstance(policy, RiskPolicy)
        or RUNNER_QUANTITY != FIXED_RESEARCH_QUANTITY
    ):
        raise ForwardPaperRunnerError("P10 entry-veto input is invalid")

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        quantity = Decimal(RUNNER_QUANTITY)
        equity = Decimal(risk_state.equity_quote)
        cash = Decimal(risk_state.cash_quote)
        mark = Decimal(risk_state.mark_price)
        peak = Decimal(risk_state.peak_equity_quote)
        session_start = Decimal(risk_state.session_start_equity_quote)
        session_pnl = Decimal(risk_state.session_realized_pnl_quote)

        entry = Decimal(decision.setup.reference_price)
        stop = Decimal(decision.setup.invalidation_price)
        target = Decimal(decision.setup.target_price)
        fee_rate = Decimal("10") / BASIS_POINTS
        slippage_rate = Decimal("5") / BASIS_POINTS

        entry_execution = entry * (Decimal(1) + slippage_rate)
        stop_execution = stop * (Decimal(1) - slippage_rate)
        target_execution = target * (Decimal(1) - slippage_rate)

        entry_fee = quantity * entry_execution * fee_rate
        stop_fee = quantity * stop_execution * fee_rate
        target_fee = quantity * target_execution * fee_rate

        planned_loss = (
            quantity * (entry_execution - stop_execution) + entry_fee + stop_fee
        )
        risk_budget = equity * Decimal(policy.risk_per_trade_fraction)
        entry_notional = quantity * entry_execution
        cash_required = entry_notional + entry_fee
        position_limit = equity * Decimal(policy.max_position_fraction)
        gross_before = Decimal(risk_state.position_quantity) * mark
        gross_after = gross_before + entry_notional
        gross_limit = equity * Decimal(policy.max_gross_exposure_fraction)
        net_reward = (
            quantity * (target_execution - entry_execution) - entry_fee - target_fee
        )

        session_loss = max(-session_pnl, Decimal(0))
        session_limit = session_start * Decimal(policy.max_session_loss_fraction)
        drawdown = peak - equity
        drawdown_limit = peak * Decimal(policy.max_drawdown_fraction)

    reasons = []
    if risk_state.kill_switch_active:
        reasons.append(EntryVetoReason.KILL_SWITCH_ACTIVE)
    if session_loss >= session_limit:
        reasons.append(EntryVetoReason.SESSION_LOSS_LIMIT)
    if drawdown >= drawdown_limit:
        reasons.append(EntryVetoReason.DRAWDOWN_LIMIT)
    if risk_state.consecutive_losses >= policy.max_consecutive_losses:
        reasons.append(EntryVetoReason.CONSECUTIVE_LOSS_LIMIT)
    if risk_state.open_positions >= policy.max_open_positions:
        reasons.append(EntryVetoReason.OPEN_POSITION_LIMIT)
    if cash_required > cash:
        reasons.append(EntryVetoReason.CASH_INSUFFICIENT)
    if entry_notional > position_limit:
        reasons.append(EntryVetoReason.POSITION_LIMIT)
    if gross_after > gross_limit:
        reasons.append(EntryVetoReason.GROSS_EXPOSURE_LIMIT)
    if planned_loss > risk_budget:
        reasons.append(EntryVetoReason.PLANNED_LOSS_LIMIT)
    if not (Decimal(0) < stop_execution < entry_execution < target_execution):
        reasons.append(EntryVetoReason.INVALID_PROTECTIVE_LEVELS)
    if net_reward <= 0:
        reasons.append(EntryVetoReason.NON_POSITIVE_POST_COST_REWARD)

    ordered = tuple(reason for reason in EntryVetoReason if reason in reasons)
    return EntrySafetyVeto(
        allowed=not ordered,
        reasons=ordered,
        quantity=RUNNER_QUANTITY,
        risk_budget_quote=_plain(risk_budget),
        planned_loss_quote=_plain(planned_loss),
        entry_notional_quote=_plain(entry_notional),
        cash_required_quote=_plain(cash_required),
        position_limit_quote=_plain(position_limit),
        gross_exposure_after_quote=_plain(gross_after),
        gross_exposure_limit_quote=_plain(gross_limit),
        net_reward_quote=_plain(net_reward),
    )


class _RiskTracker:
    def __init__(self, symbol, initial_equity):
        self.symbol = symbol
        self.peak = Decimal(initial_equity)
        self.session_start_time_ms = None
        self.session_start_equity = None
        self.session_realized_pnl = Decimal(0)
        self.previous_realized_pnl = Decimal(0)
        self.previous_closed_trades = 0
        self.consecutive_losses = 0
        self.kill_switch_active = False

    def observe(self, event_time_ms, snapshot, mark_price):
        equity = snapshot.equity_quote
        realized = snapshot.realized_pnl_quote
        delta = realized - self.previous_realized_pnl
        closed_delta = snapshot.closed_trades - self.previous_closed_trades
        if closed_delta not in (0, 1):
            raise ForwardPaperRunnerError("Paper close count advanced unexpectedly")
        if closed_delta:
            if delta < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

        day_start = (event_time_ms // UTC_DAY_MS) * UTC_DAY_MS
        if self.session_start_time_ms is None:
            self.session_start_time_ms = day_start
            self.session_start_equity = equity
            self.session_realized_pnl = Decimal(0)
        elif day_start != self.session_start_time_ms:
            old_loss = max(-(self.session_realized_pnl + delta), Decimal(0))
            old_limit = (
                self.session_start_equity
                * Decimal(RiskPolicy().max_session_loss_fraction)
            )
            if old_loss >= old_limit:
                self.kill_switch_active = True
            self.session_start_time_ms = day_start
            self.session_start_equity = equity
            self.session_realized_pnl = Decimal(0)
            delta = Decimal(0)
        else:
            self.session_realized_pnl += delta

        self.peak = max(self.peak, equity)
        drawdown = self.peak - equity
        drawdown_limit = self.peak * Decimal(RiskPolicy().max_drawdown_fraction)
        session_loss = max(-self.session_realized_pnl, Decimal(0))
        session_limit = (
            self.session_start_equity
            * Decimal(RiskPolicy().max_session_loss_fraction)
        )
        if (
            drawdown >= drawdown_limit
            or session_loss >= session_limit
            or self.consecutive_losses >= RiskPolicy().max_consecutive_losses
        ):
            self.kill_switch_active = True

        self.previous_realized_pnl = realized
        self.previous_closed_trades = snapshot.closed_trades
        return ValidationRiskState(
            symbol=self.symbol,
            equity_quote=_plain(equity),
            cash_quote=_plain(snapshot.cash),
            position_quantity=_plain(snapshot.asset_quantity),
            mark_price=mark_price,
            peak_equity_quote=_plain(self.peak),
            session_start_time_ms=self.session_start_time_ms,
            session_start_equity_quote=_plain(self.session_start_equity),
            session_realized_pnl_quote=_plain(self.session_realized_pnl),
            consecutive_losses=self.consecutive_losses,
            open_positions=1 if snapshot.asset_quantity > 0 else 0,
            kill_switch_active=self.kill_switch_active,
        )


@dataclass(frozen=True, slots=True)
class ForwardPaperSymbolResult:
    symbol: str
    spec_sha256: str
    input_snapshot_sha256: str
    input_dataset_sha256: str
    first_decision_time_ms: int
    end_time_ms: int
    event_count: int
    entry_signals: int
    entries_allowed: int
    entries_blocked: int
    exit_signals: int
    no_trade_signals: int
    kill_switch_latched: bool
    trace: tuple[dict, ...]
    fills: tuple[dict, ...]
    final_portfolio: dict
    point_in_time_verified: bool
    replay_from_start: bool

    def as_record(self):
        return {
            "symbol": self.symbol,
            "spec_sha256": self.spec_sha256,
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "input_dataset_sha256": self.input_dataset_sha256,
            "first_decision_time_ms": self.first_decision_time_ms,
            "end_time_ms": self.end_time_ms,
            "event_count": self.event_count,
            "entry_signals": self.entry_signals,
            "entries_allowed": self.entries_allowed,
            "entries_blocked": self.entries_blocked,
            "exit_signals": self.exit_signals,
            "no_trade_signals": self.no_trade_signals,
            "kill_switch_latched": self.kill_switch_latched,
            "trace": list(self.trace),
            "fills": list(self.fills),
            "final_portfolio": self.final_portfolio,
            "point_in_time_verified": self.point_in_time_verified,
            "replay_from_start": self.replay_from_start,
        }

    @property
    def result_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class ForwardPaperRunResult:
    runner_id: str
    ingestion_snapshot_sha256: str
    window_sha256: str
    candidate_sha256: str
    gate_registry_sha256: str
    execution_policy_id: str
    fixed_research_quantity: str
    p3_adapter_git_blob_sha1: str
    symbols: tuple[ForwardPaperSymbolResult, ...]
    paper_only: bool
    live_master_lock: str
    p3_qualification_fabricated: bool
    p4_risk_authorization_created: bool
    quantity_authority_created: bool
    external_transport_used: bool
    trade_permission: bool
    order_endpoint: bool
    ai_direct_execution: bool
    economic_evaluation_allowed: bool
    strategy_evidence: str

    def __post_init__(self):
        window = ForwardWindowSeal()
        candidate = CandidateFreeze()
        policy = LocalPaperExecutionPolicy()
        if (
            self.runner_id != FORWARD_PAPER_RUNNER_ID
            or self.window_sha256 != window.window_sha256
            or self.candidate_sha256 != candidate.candidate_sha256
            or self.gate_registry_sha256
            != CandidateGateRegistration().gates.registry_sha256
            or self.execution_policy_id != policy.policy_id
            or self.fixed_research_quantity != RUNNER_QUANTITY
            or self.fixed_research_quantity != FIXED_RESEARCH_QUANTITY
            or self.p3_adapter_git_blob_sha1
            != P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1
            or tuple(item.symbol for item in self.symbols)
            != window.symbols
            or self.paper_only is not True
            or self.live_master_lock != "OFF"
            or self.p3_qualification_fabricated is not False
            or self.p4_risk_authorization_created is not False
            or self.quantity_authority_created is not False
            or self.external_transport_used is not False
            or self.trade_permission is not False
            or self.order_endpoint is not False
            or self.ai_direct_execution is not False
            or self.economic_evaluation_allowed is not False
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
        ):
            raise ForwardPaperRunnerError("P10 forward runner result is inconsistent")

    def as_record(self):
        return {
            "runner_id": self.runner_id,
            "ingestion_snapshot_sha256": self.ingestion_snapshot_sha256,
            "window_sha256": self.window_sha256,
            "candidate_sha256": self.candidate_sha256,
            "gate_registry_sha256": self.gate_registry_sha256,
            "execution_policy_id": self.execution_policy_id,
            "fixed_research_quantity": self.fixed_research_quantity,
            "p3_adapter_git_blob_sha1": self.p3_adapter_git_blob_sha1,
            "symbols": [item.as_record() for item in self.symbols],
            "safety": {
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "p3_qualification_fabricated":
                    self.p3_qualification_fabricated,
                "p4_risk_authorization_created":
                    self.p4_risk_authorization_created,
                "quantity_authority_created": self.quantity_authority_created,
                "external_transport_used": self.external_transport_used,
                "trade_permission": self.trade_permission,
                "order_endpoint": self.order_endpoint,
                "ai_direct_execution": self.ai_direct_execution,
                "economic_evaluation_allowed":
                    self.economic_evaluation_allowed,
                "strategy_evidence": self.strategy_evidence,
            },
        }

    @property
    def run_sha256(self):
        return _sha256(self.as_record())


def _spec_sha256(spec):
    return _sha256({
        name: getattr(spec, name)
        for name in spec.__dataclass_fields__
    })


def _verify_snapshot_store(store, snapshot):
    if (
        not isinstance(store, ForwardCandleStore)
        or not isinstance(snapshot, ForwardIngestionSnapshot)
        or snapshot.quality_pass is not True
        or snapshot.window_sha256 != ForwardWindowSeal().window_sha256
        or snapshot.candidate_sha256 != CandidateFreeze().candidate_sha256
        or snapshot.gate_registry_sha256
        != CandidateGateRegistration().gates.registry_sha256
        or store.window_sha256 != snapshot.window_sha256
    ):
        raise ForwardPaperRunnerError("P10 runner input provenance is invalid")

    for evidence in snapshot.datasets:
        candles = store.candles_between(
            evidence.symbol,
            evidence.interval,
            evidence.requested_start_time_ms,
            evidence.requested_end_time_ms,
        )
        if (
            len(candles) != evidence.total_rows
            or _dataset_digest(candles) != evidence.dataset_sha256
        ):
            raise ForwardPaperRunnerError(
                "P10 runner store differs from accepted ingestion evidence"
            )


def _dataset_for_symbol(store, snapshot, symbol):
    window = ForwardWindowSeal()
    evidence = {
        item.interval: item
        for item in snapshot.datasets
        if item.symbol == symbol
    }
    if set(evidence) != set(window.intervals):
        raise ForwardPaperRunnerError("P10 runner dataset scope is incomplete")
    common_end = min(item.requested_end_time_ms for item in evidence.values())
    first_decision = (
        window.forward_window_start_ms
        + REGIME_WARMUP_BARS * INTERVAL_MILLISECONDS["4h"]
    )
    if common_end <= first_decision:
        raise ForwardPaperRunnerError(
            "Forward prefix does not yet contain the frozen strategy warmup"
        )

    candidate = CandidateFreeze()
    spec = BacktestSpec(
        symbol,
        first_decision,
        common_end,
        initial_cash=candidate.initial_equity_quote,
        fee_bps=candidate.fee_bps,
        slippage_bps=candidate.slippage_bps,
    )
    values = {
        interval: store.candles_between(
            symbol,
            interval,
            window.forward_window_start_ms,
            common_end,
        )
        for interval in window.intervals
    }
    dataset = AcceptedBacktestDataset(
        spec=spec,
        manifest_generated_at_ms=snapshot.generated_at_ms,
        primary=values["1h"],
        context=values["15m"],
        regime=values["4h"],
    )
    input_sha = _sha256(
        [
            item.as_record()
            for interval in ("15m", "1h", "4h")
            for item in values[interval]
        ]
    )
    return dataset, input_sha


def _run_symbol(store, snapshot, symbol):
    dataset, input_sha = _dataset_for_symbol(store, snapshot, symbol)
    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise ForwardPaperRunnerError("Forward Paper runner has no legal event")
    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise ForwardPaperRunnerError("Forward primary candles are duplicated")

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    risk_tracker = _RiskTracker(symbol, CandidateFreeze().initial_equity_quote)
    active_setup = None
    trace = []
    fills = []
    counts = {
        "entry": 0,
        "allowed": 0,
        "blocked": 0,
        "exit": 0,
        "no_trade": 0,
    }

    for event in events:
        fill_candle = by_open.get(event.eligible_fill_open_time_ms)
        if fill_candle is None or not fill_candle.is_closed:
            raise ForwardPaperRunnerError(
                "Forward next-open candle is missing or not closed"
            )
        if any(
            candle.close_time_ms >= event.decision_time_ms
            for series in (
                event.snapshot.primary,
                event.snapshot.context,
                event.snapshot.regime,
            )
            for candle in series
        ):
            raise ForwardPaperRunnerError("Forward decision contains future data")

        pre = ledger.snapshot(event.snapshot.latest_primary.close)
        risk_state = risk_tracker.observe(
            event.decision_time_ms,
            pre,
            event.snapshot.latest_primary.close,
        )
        context = StrategyContext(TREND_PULLBACK_IDENTITY, event.snapshot)
        decision = evaluate_trend_pullback(
            context,
            in_position=fill_engine.has_position,
            active_setup=active_setup,
        )

        veto = None
        if decision.action is StrategyAction.ENTER_LONG:
            counts["entry"] += 1
            veto = assess_fixed_quantity_entry(decision, risk_state)
            if veto.allowed:
                counts["allowed"] += 1
                intent = PaperIntent(
                    IntentAction.ENTER_LONG,
                    event.decision_time_ms,
                    RUNNER_QUANTITY,
                    decision.setup.invalidation_price,
                    decision.setup.target_price,
                )
            else:
                counts["blocked"] += 1
                intent = PaperIntent(IntentAction.HOLD, event.decision_time_ms)
        elif decision.action is StrategyAction.EXIT_LONG:
            counts["exit"] += 1
            intent = PaperIntent(IntentAction.EXIT_LONG, event.decision_time_ms)
        else:
            counts["no_trade"] += 1
            intent = PaperIntent(IntentAction.HOLD, event.decision_time_ms)

        references = fill_engine.process(event, intent, fill_candle)
        costed = tuple(apply_costs(item, dataset.spec) for item in references)
        if costed:
            ledger.apply_many(costed)
            fills.extend(_fill_record(item) for item in costed)

        if fill_engine.has_position:
            if intent.action is IntentAction.ENTER_LONG:
                active_setup = decision.setup
            elif active_setup is None:
                raise ForwardPaperRunnerError(
                    "Forward Paper position lost its frozen setup"
                )
        else:
            active_setup = None

        trace.append({
            "sequence": event.sequence,
            "decision_time_ms": event.decision_time_ms,
            "context_sha256": decision.context_sha256,
            "strategy_action": decision.action.value,
            "strategy_reason": decision.reason.value,
            "effective_intent": intent.action.value,
            "entry_veto": None if veto is None else veto.as_record(),
            "risk_state": risk_state.as_record(),
            "fill_count": len(costed),
        })

    final_mark = dataset.primary[-1].close
    final_portfolio = ledger.snapshot(final_mark)
    return ForwardPaperSymbolResult(
        symbol=symbol,
        spec_sha256=_spec_sha256(dataset.spec),
        input_snapshot_sha256=snapshot.snapshot_sha256,
        input_dataset_sha256=input_sha,
        first_decision_time_ms=dataset.spec.start_time_ms,
        end_time_ms=dataset.spec.end_time_ms,
        event_count=len(events),
        entry_signals=counts["entry"],
        entries_allowed=counts["allowed"],
        entries_blocked=counts["blocked"],
        exit_signals=counts["exit"],
        no_trade_signals=counts["no_trade"],
        kill_switch_latched=risk_tracker.kill_switch_active,
        trace=tuple(trace),
        fills=tuple(fills),
        final_portfolio=_portfolio_record(final_portfolio),
        point_in_time_verified=True,
        replay_from_start=True,
    )


def run_forward_paper(store, snapshot):
    """Replay the exact frozen P10 baseline from the sealed forward start."""
    _verify_snapshot_store(store, snapshot)
    if (
        CandidateFreeze().strategy_id != "TREND_PULLBACK"
        or CandidateFreeze().strategy_version != "1.0.0"
        or RUNNER_QUANTITY != FIXED_RESEARCH_QUANTITY
    ):
        raise ForwardPaperRunnerError("Frozen P10 execution baseline changed")

    first = tuple(
        _run_symbol(store, snapshot, symbol)
        for symbol in ForwardWindowSeal().symbols
    )
    second = tuple(
        _run_symbol(store, snapshot, symbol)
        for symbol in ForwardWindowSeal().symbols
    )
    if tuple(item.as_record() for item in first) != tuple(
        item.as_record() for item in second
    ):
        raise ForwardPaperRunnerError("Forward Paper replay is not deterministic")

    policy = LocalPaperExecutionPolicy()
    return ForwardPaperRunResult(
        runner_id=FORWARD_PAPER_RUNNER_ID,
        ingestion_snapshot_sha256=snapshot.snapshot_sha256,
        window_sha256=ForwardWindowSeal().window_sha256,
        candidate_sha256=CandidateFreeze().candidate_sha256,
        gate_registry_sha256=CandidateGateRegistration().gates.registry_sha256,
        execution_policy_id=policy.policy_id,
        fixed_research_quantity=RUNNER_QUANTITY,
        p3_adapter_git_blob_sha1=P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1,
        symbols=first,
        paper_only=True,
        live_master_lock="OFF",
        p3_qualification_fabricated=False,
        p4_risk_authorization_created=False,
        quantity_authority_created=False,
        external_transport_used=False,
        trade_permission=False,
        order_endpoint=False,
        ai_direct_execution=False,
        economic_evaluation_allowed=False,
        strategy_evidence="INSUFFICIENT_EVIDENCE",
    )
