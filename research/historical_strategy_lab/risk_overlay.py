"""HSL-002 deterministic research-only risk-overlay comparison.

This checkpoint compares the accepted P4-style latched entry veto with one
preregistered recovery/cooldown challenger. It reuses the exact HSL-001
strategies, folds, Spot paper quantity, fee/slippage and point-in-time market
history. It never mutates P4, P10, P11 or any live/execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    BacktestClock,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.risk import RiskPolicy
from yatl.strategy import StrategyAction, StrategyContext
from yatl.validation.paper_runner import (
    RUNNER_QUANTITY,
    ValidationRiskState,
    _RiskTracker,
    assess_fixed_quantity_entry,
)
from yatl.validation.registration import CandidateFreeze

from research.crisis_lab import acquisition as acq
from research.crisis_lab import controls, replay

from . import walk_forward as hsl1


IMPLEMENTATION_ID = "HSL-002-RISK-OVERLAY/0.1.0"
SCHEMA_VERSION = "0.1.0"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/historical-strategy-lab/"
    "HSL-002-RISK-OVERLAY-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
REFERENCE_ARM_ID = "HSL-RISK-P4-LATCHED"
CHALLENGER_ARM_ID = "HSL-RISK-RECOVERY-COOLDOWN"
UTC_DAY_MS = 86_400_000


class HSLRiskOverlayError(RuntimeError):
    """HSL-002 violated a frozen research or safety boundary."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (_json(value) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _number(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise HSLRiskOverlayError(f"{label} is not numeric") from None
    if not result.is_finite():
        raise HSLRiskOverlayError(f"{label} is not finite")
    return result


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise HSLRiskOverlayError("HSL-002 arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _load_protocol_payload(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise HSLRiskOverlayError(str(exc)) from None
    if target.is_symlink():
        raise HSLRiskOverlayError("symlink HSL-002 protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise HSLRiskOverlayError("cannot read HSL-002 protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise HSLRiskOverlayError("HSL-002 protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HSLRiskOverlayError(
            "HSL-002 protocol is not canonical UTF-8 JSON"
        ) from None
    if not isinstance(protocol, dict):
        raise HSLRiskOverlayError("HSL-002 protocol must be an object")
    return protocol, payload


def load_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    protocol, payload = _load_protocol_payload(path)
    if (
        protocol.get("schema") != "YATL_HSL_RISK_OVERLAY_PROTOCOL"
        or protocol.get("version") != SCHEMA_VERSION
        or protocol.get("status")
        != "REGISTERED_BEFORE_HSL002_OUTCOME_REPLAY"
        or protocol.get("research_only") is not True
        or protocol.get("paper_only") is not True
        or protocol.get("p10_untouched") is not True
        or protocol.get("p11_locked") is not True
        or protocol.get("live_master_lock") != "OFF"
        or protocol.get("trade_permission") is not False
        or protocol.get("order_endpoint") is not False
        or protocol.get("ai_direct_execution") is not False
        or protocol.get("parent_protocol")
        != "HSL-001-WALK-FORWARD/0.1.0"
    ):
        raise HSLRiskOverlayError("HSL-002 protocol invariants are invalid")

    parent, _ = hsl1.load_protocol()
    arms = protocol.get("arms")
    invariants = protocol.get("invariants")
    reporting = protocol.get("reporting")
    comparison_gate = protocol.get("comparison_gate")
    if (
        not isinstance(arms, list)
        or len(arms) != 2
        or not isinstance(invariants, dict)
        or not isinstance(reporting, list)
        or not isinstance(comparison_gate, dict)
    ):
        raise HSLRiskOverlayError("HSL-002 protocol scope is incomplete")

    by_arm = {
        item.get("arm_id"): item
        for item in arms
        if isinstance(item, dict)
    }
    if set(by_arm) != {REFERENCE_ARM_ID, CHALLENGER_ARM_ID}:
        raise HSLRiskOverlayError("HSL-002 risk arms are not frozen")

    policy = RiskPolicy()
    expected_thresholds = {
        "max_session_loss_fraction": policy.max_session_loss_fraction,
        "max_drawdown_fraction": policy.max_drawdown_fraction,
        "max_consecutive_losses": policy.max_consecutive_losses,
    }
    for arm_id in (REFERENCE_ARM_ID, CHALLENGER_ARM_ID):
        arm = by_arm[arm_id]
        if arm.get("thresholds") != expected_thresholds:
            raise HSLRiskOverlayError(
                "HSL-002 thresholds differ from frozen P4"
            )

    challenger = by_arm[CHALLENGER_ARM_ID]
    if (
        challenger.get("cooldown_primary_decisions") != 24
        or challenger.get("hard_latch_breakers")
        != ["DRAWDOWN_LIMIT"]
        or challenger.get("recoverable_breakers")
        != ["SESSION_LOSS_LIMIT", "CONSECUTIVE_LOSS_LIMIT"]
    ):
        raise HSLRiskOverlayError(
            "HSL-002 cooldown recovery policy is not frozen"
        )

    strategies = [
        f"{item['strategy_id']}/{item['strategy_version']}"
        for item in parent["candidates"]
    ]
    methodology = parent["methodology"]
    if (
        invariants.get("strategies") != strategies
        or invariants.get("symbols") != list(acq.ALLOWED_SYMBOLS)
        or invariants.get("folds") != "EXACT_HSL001_F001_TO_F005"
        or invariants.get("fixed_quantity") != RUNNER_QUANTITY
        or invariants.get("fee_bps") != methodology["fee_bps"]
        or invariants.get("slippage_bps") != methodology["slippage_bps"]
        or invariants.get("execution") != methodology["execution"]
        or invariants.get("parameter_search") is not False
        or invariants.get("strategy_selection_from_hsl001_outcomes")
        is not False
        or invariants.get("point_in_time_market_history") is not True
        or invariants.get("drawdown_hard_latch_auto_reset") is not False
        or invariants.get("p4_policy_mutated") is not False
    ):
        raise HSLRiskOverlayError(
            "HSL-002 execution differs from HSL-001 registration"
        )

    if (
        comparison_gate.get("research_only") is not True
        or comparison_gate.get("minimum_completed_trades_total") != 30
        or comparison_gate.get("maximum_drawdown_fraction")
        != policy.max_drawdown_fraction
        or comparison_gate.get("require_positive_total_net_pnl")
        is not True
        or comparison_gate.get("require_positive_expectancy") is not True
        or comparison_gate.get("minimum_profit_factor") != "1.05"
        or comparison_gate.get("require_net_pnl_above_control") is not True
        or comparison_gate.get("hard_latch_bypass_allowed") is not False
        or comparison_gate.get("automatic_promotion_to_p10_p11_live")
        is not False
    ):
        raise HSLRiskOverlayError(
            "HSL-002 comparison gate is invalid"
        )

    return protocol, _sha256(payload)


def _threshold_reasons(state: ValidationRiskState) -> tuple[str, ...]:
    policy = RiskPolicy()
    equity = Decimal(state.equity_quote)
    peak = Decimal(state.peak_equity_quote)
    session_start = Decimal(state.session_start_equity_quote)
    session_pnl = Decimal(state.session_realized_pnl_quote)
    reasons: list[str] = []
    if max(-session_pnl, Decimal(0)) >= (
        session_start * Decimal(policy.max_session_loss_fraction)
    ):
        reasons.append("SESSION_LOSS_LIMIT")
    if (peak - equity) >= (
        peak * Decimal(policy.max_drawdown_fraction)
    ):
        reasons.append("DRAWDOWN_LIMIT")
    if state.consecutive_losses >= policy.max_consecutive_losses:
        reasons.append("CONSECUTIVE_LOSS_LIMIT")
    return tuple(reasons)


class _ReferenceRiskTracker:
    """Exact accepted P10 latched tracker, wrapped only for HSL telemetry."""

    def __init__(self, symbol: str, initial_equity: str):
        self._tracker = _RiskTracker(symbol, initial_equity)
        self.kill_switch_trigger_count = 0
        self.hard_latch_trigger_count = 0
        self.session_release_count = 0
        self.cooldown_release_count = 0
        self.cooldown_blocked_decision_count = 0
        self.observed_consecutive_losses_peak = 0
        self._hard_latched = False

    @property
    def hard_latched(self) -> bool:
        return self._hard_latched

    def observe(self, event_time_ms, snapshot, mark_price):
        was_active = self._tracker.kill_switch_active
        state = self._tracker.observe(
            event_time_ms, snapshot, mark_price
        )
        self.observed_consecutive_losses_peak = max(
            self.observed_consecutive_losses_peak,
            state.consecutive_losses,
        )
        if state.kill_switch_active and not was_active:
            self.kill_switch_trigger_count += 1
            if "DRAWDOWN_LIMIT" in _threshold_reasons(state):
                self.hard_latch_trigger_count += 1
                self._hard_latched = True
        return state

    def summary(self) -> dict[str, object]:
        return {
            "kill_switch_trigger_count": self.kill_switch_trigger_count,
            "hard_latch_trigger_count": self.hard_latch_trigger_count,
            "session_release_count": self.session_release_count,
            "cooldown_release_count": self.cooldown_release_count,
            "cooldown_blocked_decision_count": (
                self.cooldown_blocked_decision_count
            ),
            "observed_consecutive_losses_peak": (
                self.observed_consecutive_losses_peak
            ),
            "hard_latched_at_end": self.hard_latched,
            "hard_latch_bypass_count": 0,
        }


class _RecoveryCooldownRiskTracker:
    """Research-only recovery state; frozen P4 numeric limits remain unchanged."""

    def __init__(
        self,
        symbol: str,
        initial_equity: str,
        *,
        cooldown_primary_decisions: int,
    ):
        if cooldown_primary_decisions != 24:
            raise HSLRiskOverlayError(
                "HSL-002 cooldown differs from preregistration"
            )
        self.symbol = symbol
        self.peak = Decimal(initial_equity)
        self.session_start_time_ms: int | None = None
        self.session_start_equity: Decimal | None = None
        self.session_realized_pnl = Decimal(0)
        self.previous_realized_pnl = Decimal(0)
        self.previous_closed_trades = 0

        self.observed_consecutive_losses = 0
        self.entry_eligibility_consecutive_losses = 0
        self.observed_consecutive_losses_peak = 0

        self.hard_latched = False
        self.session_block_active = False
        self.cooldown_primary_decisions = cooldown_primary_decisions
        self.cooldown_remaining = 0
        self.cooldown_release_pending = False

        self.kill_switch_trigger_count = 0
        self.hard_latch_trigger_count = 0
        self.session_trigger_count = 0
        self.loss_streak_trigger_count = 0
        self.session_release_count = 0
        self.cooldown_release_count = 0
        self.cooldown_blocked_decision_count = 0

    def _risk_state(
        self,
        *,
        snapshot,
        mark_price,
        kill_switch_active: bool,
    ) -> ValidationRiskState:
        if self.session_start_time_ms is None:
            raise HSLRiskOverlayError(
                "HSL-002 recovery tracker has no session"
            )
        if self.session_start_equity is None:
            raise HSLRiskOverlayError(
                "HSL-002 recovery tracker has no session equity"
            )
        return ValidationRiskState(
            symbol=self.symbol,
            equity_quote=_plain(snapshot.equity_quote),
            cash_quote=_plain(snapshot.cash),
            position_quantity=_plain(snapshot.asset_quantity),
            mark_price=str(mark_price),
            peak_equity_quote=_plain(self.peak),
            session_start_time_ms=self.session_start_time_ms,
            session_start_equity_quote=_plain(
                self.session_start_equity
            ),
            session_realized_pnl_quote=_plain(
                self.session_realized_pnl
            ),
            consecutive_losses=(
                self.entry_eligibility_consecutive_losses
            ),
            open_positions=1 if snapshot.asset_quantity > 0 else 0,
            kill_switch_active=kill_switch_active,
        )

    def observe(self, event_time_ms, snapshot, mark_price):
        policy = RiskPolicy()
        equity = snapshot.equity_quote
        realized = snapshot.realized_pnl_quote
        delta = realized - self.previous_realized_pnl
        closed_delta = (
            snapshot.closed_trades - self.previous_closed_trades
        )
        if closed_delta not in (0, 1):
            raise HSLRiskOverlayError(
                "HSL-002 close count advanced unexpectedly"
            )

        if closed_delta:
            if delta < 0:
                self.observed_consecutive_losses += 1
                self.entry_eligibility_consecutive_losses += 1
            else:
                self.observed_consecutive_losses = 0
                self.entry_eligibility_consecutive_losses = 0
        self.observed_consecutive_losses_peak = max(
            self.observed_consecutive_losses_peak,
            self.observed_consecutive_losses,
        )

        day_start = (event_time_ms // UTC_DAY_MS) * UTC_DAY_MS
        if self.session_start_time_ms is None:
            self.session_start_time_ms = day_start
            self.session_start_equity = equity
            self.session_realized_pnl = Decimal(0)
        elif day_start != self.session_start_time_ms:
            if self.session_block_active:
                self.session_block_active = False
                self.session_release_count += 1
            self.session_start_time_ms = day_start
            self.session_start_equity = equity
            self.session_realized_pnl = Decimal(0)
            delta = Decimal(0)
        else:
            self.session_realized_pnl += delta

        self.peak = max(self.peak, equity)
        drawdown = self.peak - equity
        drawdown_limit = (
            self.peak * Decimal(policy.max_drawdown_fraction)
        )
        session_loss = max(
            -self.session_realized_pnl, Decimal(0)
        )
        session_limit = (
            self.session_start_equity
            * Decimal(policy.max_session_loss_fraction)
        )

        if drawdown >= drawdown_limit and not self.hard_latched:
            self.hard_latched = True
            self.hard_latch_trigger_count += 1
            self.kill_switch_trigger_count += 1

        if session_loss >= session_limit:
            if not self.session_block_active:
                self.session_trigger_count += 1
                self.kill_switch_trigger_count += 1
            self.session_block_active = True

        cooldown_active_this_decision = (
            self.cooldown_remaining > 0
        )
        new_cooldown = False

        if (
            self.cooldown_release_pending
            and snapshot.asset_quantity == 0
            and not self.hard_latched
            and not self.session_block_active
        ):
            self.entry_eligibility_consecutive_losses = 0
            self.cooldown_release_pending = False
            self.cooldown_release_count += 1

        if (
            not cooldown_active_this_decision
            and not self.cooldown_release_pending
            and self.entry_eligibility_consecutive_losses
            >= policy.max_consecutive_losses
        ):
            self.cooldown_remaining = (
                self.cooldown_primary_decisions
            )
            cooldown_active_this_decision = True
            new_cooldown = True
            self.loss_streak_trigger_count += 1
            self.kill_switch_trigger_count += 1

        kill_switch_active = (
            self.hard_latched
            or self.session_block_active
            or cooldown_active_this_decision
        )
        state = self._risk_state(
            snapshot=snapshot,
            mark_price=mark_price,
            kill_switch_active=kill_switch_active,
        )

        if cooldown_active_this_decision and not new_cooldown:
            self.cooldown_blocked_decision_count += 1
            self.cooldown_remaining -= 1
            if self.cooldown_remaining < 0:
                raise HSLRiskOverlayError(
                    "HSL-002 cooldown underflowed"
                )
            if self.cooldown_remaining == 0:
                self.cooldown_release_pending = True

        self.previous_realized_pnl = realized
        self.previous_closed_trades = snapshot.closed_trades
        return state

    def summary(self) -> dict[str, object]:
        return {
            "kill_switch_trigger_count": self.kill_switch_trigger_count,
            "hard_latch_trigger_count": self.hard_latch_trigger_count,
            "session_trigger_count": self.session_trigger_count,
            "loss_streak_trigger_count": self.loss_streak_trigger_count,
            "session_release_count": self.session_release_count,
            "cooldown_release_count": self.cooldown_release_count,
            "cooldown_blocked_decision_count": (
                self.cooldown_blocked_decision_count
            ),
            "observed_consecutive_losses_peak": (
                self.observed_consecutive_losses_peak
            ),
            "hard_latched_at_end": self.hard_latched,
            "hard_latch_bypass_count": 0,
        }


def _tracker_for_arm(
    *,
    arm: Mapping[str, object],
    symbol: str,
):
    initial = CandidateFreeze().initial_equity_quote
    arm_id = arm["arm_id"]
    if arm_id == REFERENCE_ARM_ID:
        return _ReferenceRiskTracker(symbol, initial)
    if arm_id == CHALLENGER_ARM_ID:
        return _RecoveryCooldownRiskTracker(
            symbol,
            initial,
            cooldown_primary_decisions=int(
                arm["cooldown_primary_decisions"]
            ),
        )
    raise HSLRiskOverlayError("unknown HSL-002 risk arm")


def _run_cell(
    *,
    corpus: controls.AdmittedControlCorpus,
    fold: Mapping[str, object],
    candidate_record: Mapping[str, object],
    arm: Mapping[str, object],
) -> dict[str, object]:
    _, _, evaluation_start, evaluation_end = hsl1._fold_times(fold)
    strategy_id = candidate_record["strategy_id"]
    registry = hsl1._CANDIDATES.get(str(strategy_id))
    if registry is None:
        raise HSLRiskOverlayError(
            "HSL-002 candidate is not registered"
        )
    identity = registry["identity"]
    evaluator = registry["evaluator"]
    symbol = str(candidate_record["_symbol"])

    try:
        dataset, dataset_sha = hsl1._dataset(
            corpus=corpus,
            symbol=symbol,
            evaluation_start_ms=evaluation_start,
            evaluation_end_ms=evaluation_end,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLRiskOverlayError(str(exc)) from None

    by_open = {
        item.open_time_ms: item for item in dataset.primary
    }
    if len(by_open) != len(dataset.primary):
        raise HSLRiskOverlayError(
            "HSL-002 primary candles are duplicated"
        )

    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise HSLRiskOverlayError(
            "HSL-002 fold has no decision events"
        )
    analysis_primary = tuple(
        item
        for item in dataset.primary
        if evaluation_start
        <= item.open_time_ms
        < evaluation_end
    )
    if not analysis_primary:
        raise HSLRiskOverlayError(
            "HSL-002 fold has no analysis candles"
        )

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    tracker = _tracker_for_arm(
        arm=arm,
        symbol=symbol,
    )
    active_setup = None
    open_trade_cash_delta: Decimal | None = None
    trade_pnls: list[Decimal] = []

    counts = {
        "decision": 0,
        "missing_fill": 0,
        "stale_snapshot": 0,
        "entry_signal": 0,
        "entry_gap_rejected": 0,
        "risk_blocked_entry": 0,
        "entry_fill": 0,
        "exit_fill": 0,
    }
    veto_reason_counts: dict[str, int] = {}

    initial = Decimal(CandidateFreeze().initial_equity_quote)
    peak = initial
    maximum_drawdown_fraction = Decimal(0)

    for decision_event in events:
        fill_candle = by_open.get(
            decision_event.eligible_fill_open_time_ms
        )
        if fill_candle is None:
            counts["missing_fill"] += 1
            continue
        if not fill_candle.is_closed:
            raise HSLRiskOverlayError(
                "HSL-002 fill candle is not closed"
            )
        if any(
            candle.close_time_ms >= decision_event.decision_time_ms
            for series in (
                decision_event.snapshot.primary,
                decision_event.snapshot.context,
                decision_event.snapshot.regime,
            )
            for candle in series
        ):
            raise HSLRiskOverlayError(
                "HSL-002 decision contains future data"
            )

        counts["decision"] += 1
        pre = ledger.snapshot(
            decision_event.snapshot.latest_primary.close
        )
        risk_state = tracker.observe(
            decision_event.decision_time_ms,
            pre,
            decision_event.snapshot.latest_primary.close,
        )

        decision = None
        veto = None
        if not replay._snapshot_is_fresh(
            decision_event.snapshot
        ):
            counts["stale_snapshot"] += 1
            intent = PaperIntent(
                IntentAction.HOLD,
                decision_event.decision_time_ms,
            )
        else:
            context = StrategyContext(
                identity,
                decision_event.snapshot,
            )
            decision = evaluator(
                context,
                in_position=fill_engine.has_position,
                active_setup=active_setup,
            )
            if decision.action is StrategyAction.ENTER_LONG:
                counts["entry_signal"] += 1
                opened = Decimal(fill_candle.open)
                stop = Decimal(
                    decision.setup.invalidation_price
                )
                target = Decimal(
                    decision.setup.target_price
                )
                if not stop < opened < target:
                    counts["entry_gap_rejected"] += 1
                    intent = PaperIntent(
                        IntentAction.HOLD,
                        decision_event.decision_time_ms,
                    )
                else:
                    veto = assess_fixed_quantity_entry(
                        decision,
                        risk_state,
                    )
                    if veto.allowed:
                        if tracker.hard_latched:
                            raise HSLRiskOverlayError(
                                "hard drawdown latch was bypassed"
                            )
                        intent = PaperIntent(
                            IntentAction.ENTER_LONG,
                            decision_event.decision_time_ms,
                            RUNNER_QUANTITY,
                            decision.setup.invalidation_price,
                            decision.setup.target_price,
                        )
                    else:
                        counts["risk_blocked_entry"] += 1
                        for reason in veto.reasons:
                            key = reason.value
                            veto_reason_counts[key] = (
                                veto_reason_counts.get(key, 0) + 1
                            )
                        intent = PaperIntent(
                            IntentAction.HOLD,
                            decision_event.decision_time_ms,
                        )
            elif decision.action is StrategyAction.EXIT_LONG:
                intent = PaperIntent(
                    IntentAction.EXIT_LONG,
                    decision_event.decision_time_ms,
                )
            else:
                intent = PaperIntent(
                    IntentAction.HOLD,
                    decision_event.decision_time_ms,
                )

        references = fill_engine.process(
            decision_event,
            intent,
            fill_candle,
        )
        costed = tuple(
            apply_costs(item, dataset.spec)
            for item in references
        )
        if costed:
            ledger.apply_many(costed)

        for fill in costed:
            if fill.reference.action is IntentAction.ENTER_LONG:
                counts["entry_fill"] += 1
                if open_trade_cash_delta is not None:
                    raise HSLRiskOverlayError(
                        "HSL-002 overlapping trade accounting"
                    )
                open_trade_cash_delta = fill.cash_delta
            else:
                counts["exit_fill"] += 1
                if open_trade_cash_delta is None:
                    raise HSLRiskOverlayError(
                        "HSL-002 exit has no paired entry"
                    )
                with localcontext() as arithmetic:
                    arithmetic.prec = DECIMAL_PRECISION
                    pnl = (
                        open_trade_cash_delta
                        + fill.cash_delta
                    )
                trade_pnls.append(pnl)
                open_trade_cash_delta = None

        if fill_engine.has_position:
            if (
                intent.action is IntentAction.ENTER_LONG
                and decision is not None
            ):
                active_setup = decision.setup
            elif active_setup is None:
                raise HSLRiskOverlayError(
                    "HSL-002 open position lost setup state"
                )
        else:
            active_setup = None

        snapshot = ledger.snapshot(fill_candle.open)
        peak, maximum_drawdown_fraction = (
            hsl1._drawdown_update(
                snapshot.equity_quote,
                peak,
                maximum_drawdown_fraction,
            )
        )

    final_mark = analysis_primary[-1].close
    final_snapshot = ledger.snapshot(final_mark)
    peak, maximum_drawdown_fraction = hsl1._drawdown_update(
        final_snapshot.equity_quote,
        peak,
        maximum_drawdown_fraction,
    )

    realized = sum(trade_pnls, Decimal(0))
    if realized != final_snapshot.realized_pnl_quote:
        raise HSLRiskOverlayError(
            "HSL-002 closed-trade accounting disagrees with ledger"
        )

    wins = [item for item in trade_pnls if item > 0]
    losses = [item for item in trade_pnls if item < 0]
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    completed = len(trade_pnls)
    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        net = final_snapshot.equity_quote - initial
        net_return = net / initial
        expectancy = (
            realized / completed if completed else None
        )
        win_rate = (
            Decimal(len(wins)) / completed
            if completed
            else None
        )
        largest_positive = (
            max(wins) if wins else Decimal(0)
        )
        largest_share = (
            largest_positive / gross_profit
            if gross_profit > 0
            else None
        )
    profit_factor, profit_factor_infinite = (
        hsl1._profit_factor(gross_profit, gross_loss)
    )
    telemetry = tracker.summary()

    return {
        "fold_id": fold["fold_id"],
        "symbol": symbol,
        "candidate_id": candidate_record["candidate_id"],
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.version,
        "configuration_sha256": (
            registry["configuration"].sha256
        ),
        "risk_arm_id": arm["arm_id"],
        "risk_arm_role": arm["role"],
        "input_dataset_sha256": dataset_sha,
        "training_outcomes_used_for_configuration": False,
        "evaluation_start_ms": evaluation_start,
        "evaluation_end_exclusive_ms": evaluation_end,
        "decision_count": counts["decision"],
        "missing_fill_decision_count": counts["missing_fill"],
        "stale_snapshot_decision_count": (
            counts["stale_snapshot"]
        ),
        "entry_signal_count": counts["entry_signal"],
        "entry_gap_rejected_count": (
            counts["entry_gap_rejected"]
        ),
        "risk_blocked_entry_count": (
            counts["risk_blocked_entry"]
        ),
        "entry_fill_count": counts["entry_fill"],
        "exit_fill_count": counts["exit_fill"],
        "completed_trades": completed,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven_trades": (
            completed - len(wins) - len(losses)
        ),
        "win_rate": _plain(win_rate),
        "expectancy_quote": _plain(expectancy),
        "gross_profit_quote": _plain(gross_profit),
        "gross_loss_quote": _plain(gross_loss),
        "profit_factor": profit_factor,
        "profit_factor_infinite": (
            profit_factor_infinite
        ),
        "largest_positive_trade_quote": (
            _plain(largest_positive)
        ),
        "largest_trade_profit_share": (
            _plain(largest_share)
        ),
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(
            final_snapshot.equity_quote
        ),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net_return),
        "realized_closed_trade_pnl_quote": (
            _plain(realized)
        ),
        "unrealized_liquidation_net_pnl_quote": _plain(
            final_snapshot.unrealized_pnl_quote
        ),
        "executed_fee_quote": _plain(
            final_snapshot.total_fee_quote
        ),
        "executed_slippage_quote": _plain(
            final_snapshot.total_slippage_quote
        ),
        "executed_total_cost_quote": _plain(
            final_snapshot.total_fee_quote
            + final_snapshot.total_slippage_quote
        ),
        "maximum_drawdown_fraction": _plain(
            maximum_drawdown_fraction
        ),
        "open_position_at_fold_end": (
            fill_engine.has_position
        ),
        "terminal_position_forced_closed": False,
        "veto_reason_counts": dict(
            sorted(veto_reason_counts.items())
        ),
        "blocked_by_kill_switch_count": (
            veto_reason_counts.get(
                "KILL_SWITCH_ACTIVE", 0
            )
        ),
        "blocked_by_session_loss_count": (
            veto_reason_counts.get(
                "SESSION_LOSS_LIMIT", 0
            )
        ),
        "blocked_by_drawdown_count": (
            veto_reason_counts.get(
                "DRAWDOWN_LIMIT", 0
            )
        ),
        "blocked_by_loss_streak_count": (
            veto_reason_counts.get(
                "CONSECUTIVE_LOSS_LIMIT", 0
            )
        ),
        **telemetry,
        "point_in_time_verified": True,
    }


def _aggregate_arm_candidate(
    *,
    candidate_record: Mapping[str, object],
    arm: Mapping[str, object],
    cells: Sequence[Mapping[str, object]],
    parent_gate: Mapping[str, object],
) -> dict[str, object]:
    try:
        economic = hsl1._aggregate_candidate(
            candidate_record=candidate_record,
            cells=cells,
            gate=parent_gate,
        )
    except hsl1.HSLImplementationError as exc:
        raise HSLRiskOverlayError(str(exc)) from None

    fields = (
        "risk_blocked_entry_count",
        "blocked_by_kill_switch_count",
        "blocked_by_session_loss_count",
        "blocked_by_drawdown_count",
        "blocked_by_loss_streak_count",
        "kill_switch_trigger_count",
        "hard_latch_trigger_count",
        "session_release_count",
        "cooldown_release_count",
        "cooldown_blocked_decision_count",
        "hard_latch_bypass_count",
    )
    result = dict(economic)
    result["risk_arm_id"] = arm["arm_id"]
    result["risk_arm_role"] = arm["role"]
    for field in fields:
        result[field] = sum(
            int(item.get(field, 0)) for item in cells
        )
    result["observed_consecutive_losses_peak"] = max(
        int(item.get("observed_consecutive_losses_peak", 0))
        for item in cells
    )
    result["hard_latched_cell_count"] = sum(
        bool(item.get("hard_latched_at_end"))
        for item in cells
    )
    return result


def _profit_factor_meets(
    summary: Mapping[str, object],
    minimum: Decimal,
) -> bool:
    if summary.get("profit_factor_infinite") is True:
        return True
    value = summary.get("profit_factor")
    return (
        value is not None
        and _number(value, "profit factor") >= minimum
    )


def _comparison(
    *,
    candidate_id: str,
    reference: Mapping[str, object],
    challenger: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict[str, object]:
    reference_net = _number(
        reference["total_net_pnl_after_costs_quote"],
        "reference net pnl",
    )
    challenger_net = _number(
        challenger["total_net_pnl_after_costs_quote"],
        "challenger net pnl",
    )
    reference_expectancy = (
        None
        if reference["expectancy_quote"] is None
        else _number(
            reference["expectancy_quote"],
            "reference expectancy",
        )
    )
    challenger_expectancy = (
        None
        if challenger["expectancy_quote"] is None
        else _number(
            challenger["expectancy_quote"],
            "challenger expectancy",
        )
    )
    reference_dd = _number(
        reference["maximum_drawdown_fraction"],
        "reference drawdown",
    )
    challenger_dd = _number(
        challenger["maximum_drawdown_fraction"],
        "challenger drawdown",
    )

    failures: list[str] = []
    if int(challenger["completed_trades"]) < int(
        gate["minimum_completed_trades_total"]
    ):
        failures.append(
            "MINIMUM_COMPLETED_TRADES_TOTAL_NOT_MET"
        )
    if (
        gate.get("require_positive_total_net_pnl") is True
        and challenger_net <= 0
    ):
        failures.append("TOTAL_NET_PNL_NOT_POSITIVE")
    if (
        gate.get("require_positive_expectancy") is True
        and (
            challenger_expectancy is None
            or challenger_expectancy <= 0
        )
    ):
        failures.append("EXPECTANCY_NOT_POSITIVE")
    if not _profit_factor_meets(
        challenger,
        _number(
            gate["minimum_profit_factor"],
            "minimum profit factor",
        ),
    ):
        failures.append("PROFIT_FACTOR_GATE_FAILED")
    if challenger_dd > _number(
        gate["maximum_drawdown_fraction"],
        "maximum drawdown gate",
    ):
        failures.append("MAXIMUM_DRAWDOWN_GATE_FAILED")
    if (
        gate.get("require_net_pnl_above_control") is True
        and challenger_net <= reference_net
    ):
        failures.append("NET_PNL_DID_NOT_BEAT_CONTROL")
    if int(challenger["hard_latch_bypass_count"]) != 0:
        failures.append("HARD_LATCH_BYPASS_DETECTED")

    with localcontext() as arithmetic:
        arithmetic.prec = DECIMAL_PRECISION
        net_delta = challenger_net - reference_net
        dd_delta = challenger_dd - reference_dd
        expectancy_delta = (
            None
            if (
                challenger_expectancy is None
                or reference_expectancy is None
            )
            else challenger_expectancy
            - reference_expectancy
        )

    return {
        "candidate_id": candidate_id,
        "reference_arm_id": REFERENCE_ARM_ID,
        "challenger_arm_id": CHALLENGER_ARM_ID,
        "completed_trades_delta": (
            int(challenger["completed_trades"])
            - int(reference["completed_trades"])
        ),
        "net_pnl_after_costs_delta_quote": (
            _plain(net_delta)
        ),
        "expectancy_delta_quote": _plain(
            expectancy_delta
        ),
        "maximum_drawdown_delta_fraction": (
            _plain(dd_delta)
        ),
        "status": (
            "QUALIFIED_FOR_FURTHER_HSL_RESEARCH"
            if not failures
            else "NOT_QUALIFIED_FOR_FURTHER_HSL_RESEARCH"
        ),
        "failure_reasons": failures,
        "automatic_promotion": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
        "live_authorized": False,
    }


def run_risk_overlay(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    protocol, protocol_sha = load_protocol(protocol_path)
    parent, parent_sha = hsl1.load_protocol()
    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=(
                quality_manifest_relative_path
            ),
            quality_manifest_file_sha256=(
                quality_manifest_file_sha256
            ),
        )
    except controls.ControlError as exc:
        raise HSLRiskOverlayError(str(exc)) from None

    all_cells: list[dict[str, object]] = []
    arm_summaries: list[dict[str, object]] = []
    summary_index: dict[
        tuple[str, str], dict[str, object]
    ] = {}

    for arm in protocol["arms"]:
        for candidate in parent["candidates"]:
            candidate_cells: list[dict[str, object]] = []
            for fold in parent["folds"]:
                for symbol in acq.ALLOWED_SYMBOLS:
                    scoped = dict(candidate)
                    scoped["_symbol"] = symbol
                    cell = _run_cell(
                        corpus=corpus,
                        fold=fold,
                        candidate_record=scoped,
                        arm=arm,
                    )
                    candidate_cells.append(cell)
                    all_cells.append(cell)
            summary = _aggregate_arm_candidate(
                candidate_record=candidate,
                arm=arm,
                cells=candidate_cells,
                parent_gate=parent[
                    "qualification_gate"
                ],
            )
            arm_summaries.append(summary)
            summary_index[
                (
                    str(candidate["candidate_id"]),
                    str(arm["arm_id"]),
                )
            ] = summary

    comparisons = []
    for candidate in parent["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        comparisons.append(
            _comparison(
                candidate_id=candidate_id,
                reference=summary_index[
                    (candidate_id, REFERENCE_ARM_ID)
                ],
                challenger=summary_index[
                    (candidate_id, CHALLENGER_ARM_ID)
                ],
                gate=protocol["comparison_gate"],
            )
        )

    result: dict[str, object] = {
        "schema": "YATL_HSL_RISK_OVERLAY_RESULT",
        "schema_version": SCHEMA_VERSION,
        "implementation_id": IMPLEMENTATION_ID,
        "protocol_relative_path": protocol_path.as_posix(),
        "protocol_sha256": protocol_sha,
        "parent_protocol_sha256": parent_sha,
        "source_corpus_id": corpus.event_id,
        "input_quality_manifest_relative_path": (
            corpus.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "arms": protocol["arms"],
        "invariants": protocol["invariants"],
        "comparison_gate": protocol["comparison_gate"],
        "cells": all_cells,
        "arm_candidate_summaries": arm_summaries,
        "comparisons": comparisons,
        "historical_outcomes_used_for_strategy_selection": False,
        "parameter_search_performed": False,
        "research_only": True,
        "paper_only": True,
        "p4_policy_mutated": False,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    result["result_sha256"] = _sha256(
        _canonical_json(result)
    )
    return result


def _relative_path(digest: str) -> Path:
    return (
        Path("historical-strategy-lab")
        / "risk-overlay-v0.1.0"
        / f"hsl-002-{digest[:24]}.json"
    )


def run_and_write_risk_overlay(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, object]:
    result = run_risk_overlay(
        runtime_root=runtime_root,
        quality_manifest_relative_path=(
            quality_manifest_relative_path
        ),
        quality_manifest_file_sha256=(
            quality_manifest_file_sha256
        ),
        protocol_path=protocol_path,
    )
    payload = _canonical_json(result)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise HSLRiskOverlayError(
            "HSL-002 artifact exceeds bounded size"
        )
    digest = _sha256(payload)
    try:
        relative = acq._write_immutable(
            runtime_root,
            _relative_path(digest),
            payload,
        )
    except acq.AcquisitionError as exc:
        raise HSLRiskOverlayError(str(exc)) from None
    return {
        "manifest_relative_path": relative,
        "manifest_file_sha256": digest,
        "result_sha256": result["result_sha256"],
        "comparisons": result["comparisons"],
        "research_only": True,
        "p4_policy_mutated": False,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=(
            "python -m "
            "research.historical_strategy_lab.risk_overlay"
        ),
        description=(
            "YATL HSL-002 research-only risk overlay challenger"
        ),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--quality-manifest",
        required=True,
    )
    parser.add_argument(
        "--quality-manifest-sha256",
        required=True,
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=DEFAULT_PROTOCOL_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_and_write_risk_overlay(
            runtime_root=args.runtime_root,
            quality_manifest_relative_path=(
                args.quality_manifest
            ),
            quality_manifest_file_sha256=(
                args.quality_manifest_sha256
            ),
            protocol_path=args.protocol,
        )
    except HSLRiskOverlayError as exc:
        print(
            json.dumps(
                {
                    "code": "HSL002_RISK_OVERLAY_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p4_policy_mutated": False,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
