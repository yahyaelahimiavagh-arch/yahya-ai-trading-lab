"""Guarded P3-to-P2 Paper bridge requiring complete P4 authorization."""

import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum

from yatl.backtest import (
    DecisionEvent,
    FillModelError,
    FillReference,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
)
from yatl.backtest.models import BacktestContractError
from yatl.data import Candle, SYMBOLS
from yatl.strategy import (
    BREAKOUT_IDENTITY,
    TREND_PULLBACK_IDENTITY,
    DecisionReason,
    EvidenceLabel,
    StrategyAction,
    StrategyContractError,
    StrategyDecision,
    StrategyIdentity,
)

from .circuit import CircuitAssessment
from .contracts import (
    RiskDecision,
    RiskDisposition,
    RiskReason,
    RiskRequest,
)
from .kill_switch import KillSwitchState
from .protective import ProtectiveAssessment, ProtectiveStatus
from .state import ManagedPortfolioState


SUPPORTED_IDENTITIES = (TREND_PULLBACK_IDENTITY, BREAKOUT_IDENTITY)


class RiskAdapterError(ValueError):
    """P4 authorization cannot safely enter the P2 Paper lifecycle."""


def _decision_for(request, managed_state, kill_switch_state,
                  circuit_assessment, protective_assessment):
    if not isinstance(request, RiskRequest):
        raise RiskAdapterError("Authorization requires a valid risk request")
    if not isinstance(managed_state, ManagedPortfolioState):
        raise RiskAdapterError("Authorization requires valid managed state")
    if not isinstance(kill_switch_state, KillSwitchState):
        raise RiskAdapterError("Authorization requires valid Kill Switch state")
    if not isinstance(circuit_assessment, CircuitAssessment):
        raise RiskAdapterError("Authorization requires valid circuit evidence")
    if (
        circuit_assessment.request != request
        or circuit_assessment.managed_state != managed_state
    ):
        raise RiskAdapterError("Circuit evidence does not match the risk request")
    if request.portfolio.kill_switch_active is not kill_switch_state.active:
        raise RiskAdapterError("Risk request and Kill Switch state disagree")
    if protective_assessment is not None:
        if (
            not isinstance(protective_assessment, ProtectiveAssessment)
            or protective_assessment.limit_assessment.position_size.request != request
        ):
            raise RiskAdapterError("Protective evidence does not match the request")

    action = request.strategy_decision.action
    if action is StrategyAction.ENTER_LONG:
        if (
            kill_switch_state.last_circuit_sha256
            != circuit_assessment.circuit_sha256
            or kill_switch_state.last_circuit_time_ms
            != managed_state.decision_time_ms
        ):
            raise RiskAdapterError("Entry requires the latest consumed circuit evidence")
        if circuit_assessment.triggered_breakers and not kill_switch_state.active:
            raise RiskAdapterError("Active circuit breakers are not latched")
        if kill_switch_state.active:
            return RiskDecision(
                request, RiskDisposition.REJECT, RiskReason.KILL_SWITCH_ACTIVE,
            )
        if request.evidence_label is not EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH:
            return RiskDecision(
                request, RiskDisposition.REJECT, RiskReason.EVIDENCE_NOT_QUALIFIED,
            )
        if (
            circuit_assessment.triggered_breakers
            or protective_assessment is None
            or protective_assessment.status is not ProtectiveStatus.PASS
        ):
            return RiskDecision(
                request, RiskDisposition.REJECT, RiskReason.PENDING_RISK_EVALUATION,
            )
        return RiskDecision(
            request,
            RiskDisposition.APPROVE_PAPER,
            RiskReason.RISK_CHECKS_PASSED,
            protective_assessment.quantity,
        )
    if protective_assessment is not None:
        raise RiskAdapterError("Non-entry authorization cannot carry protective evidence")
    if action is StrategyAction.EXIT_LONG:
        return RiskDecision(
            request,
            RiskDisposition.APPROVE_PAPER,
            RiskReason.EXIT_REDUCES_RISK,
            request.portfolio.position_quantity,
        )
    return RiskDecision(
        request, RiskDisposition.NO_ACTION, RiskReason.NO_STRATEGY_ACTION,
    )


@dataclass(frozen=True, slots=True)
class RiskAuthorization:
    """Tamper-checked P4 result binding every input needed by the Paper bridge."""

    request: RiskRequest
    managed_state: ManagedPortfolioState
    kill_switch_state: KillSwitchState
    circuit_assessment: CircuitAssessment
    protective_assessment: ProtectiveAssessment | None
    decision: RiskDecision

    def __post_init__(self):
        expected = _decision_for(
            self.request,
            self.managed_state,
            self.kill_switch_state,
            self.circuit_assessment,
            self.protective_assessment,
        )
        if self.decision != expected or self.decision.request != self.request:
            raise RiskAdapterError("Risk authorization decision is inconsistent")

    @property
    def authorization_sha256(self):
        payload = {
            "schema_version": 1,
            "request_sha256": self.request.request_sha256,
            "managed_state_sha256": self.managed_state.state_sha256,
            "kill_switch_state_sha256": self.kill_switch_state.state_sha256,
            "circuit_sha256": self.circuit_assessment.circuit_sha256,
            "protective_sha256": (
                None
                if self.protective_assessment is None
                else self.protective_assessment.gate_sha256
            ),
            "disposition": self.decision.disposition.value,
            "reason": self.decision.reason.value,
            "approved_quantity": self.decision.approved_quantity,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def authorize_paper_request(request, managed_state, kill_switch_state,
                            circuit_assessment, protective_assessment=None):
    """Create a complete P4 Paper authorization without submitting an order."""
    decision = _decision_for(
        request,
        managed_state,
        kill_switch_state,
        circuit_assessment,
        protective_assessment,
    )
    return RiskAuthorization(
        request,
        managed_state,
        kill_switch_state,
        circuit_assessment,
        protective_assessment,
        decision,
    )


class RiskAdapterOutcome(str, Enum):
    ENTRY_APPROVED = "ENTRY_APPROVED"
    ENTRY_BLOCKED = "ENTRY_BLOCKED"
    NO_ACTION = "NO_ACTION"
    EXIT_APPROVED = "EXIT_APPROVED"


@dataclass(frozen=True, slots=True)
class RiskAdapterStep:
    """One atomic P4-authorized translation into the local P2 Paper engine."""

    authorization: RiskAuthorization
    outcome: RiskAdapterOutcome
    intent: PaperIntent
    fills: tuple[FillReference, ...]

    def __post_init__(self):
        if (
            not isinstance(self.authorization, RiskAuthorization)
            or not isinstance(self.outcome, RiskAdapterOutcome)
            or not isinstance(self.intent, PaperIntent)
            or type(self.fills) is not tuple
            or len(self.fills) > 2
            or any(not isinstance(item, FillReference) for item in self.fills)
        ):
            raise RiskAdapterError("Risk adapter step identity is invalid")
        decision = self.authorization.decision
        action = decision.request.strategy_decision.action
        expected = {
            (StrategyAction.ENTER_LONG, RiskDisposition.APPROVE_PAPER): (
                RiskAdapterOutcome.ENTRY_APPROVED, IntentAction.ENTER_LONG,
            ),
            (StrategyAction.ENTER_LONG, RiskDisposition.REJECT): (
                RiskAdapterOutcome.ENTRY_BLOCKED, IntentAction.HOLD,
            ),
            (StrategyAction.NO_TRADE, RiskDisposition.NO_ACTION): (
                RiskAdapterOutcome.NO_ACTION, IntentAction.HOLD,
            ),
            (StrategyAction.EXIT_LONG, RiskDisposition.APPROVE_PAPER): (
                RiskAdapterOutcome.EXIT_APPROVED, IntentAction.EXIT_LONG,
            ),
        }.get((action, decision.disposition))
        if expected != (self.outcome, self.intent.action):
            raise RiskAdapterError("Authorization and Paper intent actions differ")
        if self.intent.decision_time_ms != decision.request.portfolio.decision_time_ms:
            raise RiskAdapterError("Authorization and Paper intent times differ")
        if self.outcome is RiskAdapterOutcome.ENTRY_APPROVED:
            if self.intent.quantity != decision.approved_quantity:
                raise RiskAdapterError("P2 entry quantity differs from P4 approval")
            if (
                not self.fills
                or self.fills[0].action is not IntentAction.ENTER_LONG
                or self.fills[0].quantity != decision.approved_quantity
            ):
                raise RiskAdapterError("P2 entry fill differs from P4 approval")
        elif self.outcome is RiskAdapterOutcome.ENTRY_BLOCKED and self.fills:
            raise RiskAdapterError("Rejected entry produced a Paper fill")

    @property
    def authorization_sha256(self):
        return self.authorization.authorization_sha256


class RiskManagedPaperAdapter:
    """Stateful P4-only gateway into the accepted local P2 fill engine."""

    def __init__(self, identity, symbol):
        if not isinstance(identity, StrategyIdentity) or identity not in SUPPORTED_IDENTITIES:
            raise RiskAdapterError("Risk adapter strategy identity is not supported")
        if symbol not in SYMBOLS:
            raise RiskAdapterError("Risk adapter symbol is not approved")
        self.identity = identity
        self.symbol = symbol
        self._fill_engine = PaperFillEngine(symbol)
        self._active_setup = None
        self._active_quantity = None
        self._last_sequence = None
        self._last_decision_time_ms = None

    @property
    def has_position(self):
        return self._fill_engine.has_position

    @property
    def active_quantity(self):
        return self._active_quantity

    def _validate(self, event, authorization, fill_candle):
        if (
            not isinstance(event, DecisionEvent)
            or not isinstance(authorization, RiskAuthorization)
            or not isinstance(fill_candle, Candle)
        ):
            raise RiskAdapterError("Event, authorization or fill candle is invalid")
        decision = authorization.request.strategy_decision
        if (
            decision.context.identity != self.identity
            or decision.symbol != self.symbol
            or event.snapshot.symbol != self.symbol
            or decision.decision_time_ms != event.decision_time_ms
            or decision.context.snapshot != event.snapshot
        ):
            raise RiskAdapterError("Event and authorized strategy decision differ")
        try:
            replace(decision.context.identity)
            replace(decision.context.snapshot)
            replace(decision.context)
            replace(decision)
            replace(authorization.decision)
            replace(authorization)
        except (BacktestContractError, StrategyContractError, TypeError, ValueError):
            raise RiskAdapterError("P4 authorization failed reconstruction") from None
        expected_sequence = 0 if self._last_sequence is None else self._last_sequence + 1
        if (
            event.sequence != expected_sequence
            or (
                self._last_decision_time_ms is not None
                and event.decision_time_ms <= self._last_decision_time_ms
            )
        ):
            raise RiskAdapterError("Duplicate or out-of-order authorized decision")

    def _intent(self, authorization):
        risk_decision = authorization.decision
        strategy_decision = authorization.request.strategy_decision
        action = strategy_decision.action
        if self.has_position:
            if action is StrategyAction.EXIT_LONG:
                if risk_decision.disposition is not RiskDisposition.APPROVE_PAPER:
                    raise RiskAdapterError("Risk-reducing exit lacks P4 authorization")
                if risk_decision.approved_quantity != self._active_quantity:
                    raise RiskAdapterError("Exit portfolio quantity differs from P2 state")
                return (
                    RiskAdapterOutcome.EXIT_APPROVED,
                    PaperIntent(IntentAction.EXIT_LONG, strategy_decision.decision_time_ms),
                )
            if (
                action is StrategyAction.NO_TRADE
                and strategy_decision.reason is DecisionReason.HOLD_POSITION
                and risk_decision.disposition is RiskDisposition.NO_ACTION
                and authorization.request.portfolio.position_quantity
                == self._active_quantity
            ):
                return (
                    RiskAdapterOutcome.NO_ACTION,
                    PaperIntent(IntentAction.HOLD, strategy_decision.decision_time_ms),
                )
            raise RiskAdapterError("Open Paper state requires matching HOLD or EXIT")

        if action is StrategyAction.ENTER_LONG:
            if risk_decision.disposition is RiskDisposition.APPROVE_PAPER:
                setup = strategy_decision.setup
                return (
                    RiskAdapterOutcome.ENTRY_APPROVED,
                    PaperIntent(
                        IntentAction.ENTER_LONG,
                        strategy_decision.decision_time_ms,
                        risk_decision.approved_quantity,
                        setup.invalidation_price,
                        setup.target_price,
                    ),
                )
            if risk_decision.disposition is RiskDisposition.REJECT:
                return (
                    RiskAdapterOutcome.ENTRY_BLOCKED,
                    PaperIntent(IntentAction.HOLD, strategy_decision.decision_time_ms),
                )
        if (
            action is StrategyAction.NO_TRADE
            and strategy_decision.reason is not DecisionReason.HOLD_POSITION
            and risk_decision.disposition is RiskDisposition.NO_ACTION
        ):
            return (
                RiskAdapterOutcome.NO_ACTION,
                PaperIntent(IntentAction.HOLD, strategy_decision.decision_time_ms),
            )
        raise RiskAdapterError("Flat Paper state cannot process this authorization")

    def process(self, event, authorization, fill_candle):
        """Atomically translate complete P4 evidence into one local P2 step."""
        self._validate(event, authorization, fill_candle)
        outcome, intent = self._intent(authorization)
        try:
            fills = self._fill_engine.process(event, intent, fill_candle)
        except FillModelError:
            raise RiskAdapterError("P2 rejected the P4-authorized Paper intent") from None

        step = RiskAdapterStep(authorization, outcome, intent, fills)
        if self._fill_engine.has_position:
            if outcome is RiskAdapterOutcome.ENTRY_APPROVED:
                self._active_setup = authorization.request.strategy_decision.setup
                self._active_quantity = authorization.decision.approved_quantity
        else:
            self._active_setup = None
            self._active_quantity = None
        if self.has_position != (self._active_quantity is not None):
            raise RiskAdapterError("P4 and P2 Paper position states diverged")
        self._last_sequence = event.sequence
        self._last_decision_time_ms = event.decision_time_ms
        return step
