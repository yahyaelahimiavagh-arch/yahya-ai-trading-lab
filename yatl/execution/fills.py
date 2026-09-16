"""Fail-closed P5 adapter into the accepted P2 fill and cost contracts."""

import copy
import hashlib
import json
from dataclasses import dataclass

from yatl.backtest import (
    BacktestSpec,
    CostedFill,
    CostModelError,
    DecisionEvent,
    FillModelError,
    FillReference,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    apply_costs,
)
from yatl.data import Candle, SYMBOLS

from .contracts import (
    ExecutionContractError,
    ExecutionDisposition,
    LocalPaperExecutionDecision,
)
from .journal import ExecutionJournalError, LocalPaperIntentRecord
from .state import LocalOrderError, LocalOrderStatus, LocalPaperOrderState


class LocalPaperFillError(Exception):
    """Accepted local evidence cannot safely enter the P2 fill model."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _validate_decision(decision):
    if not isinstance(decision, LocalPaperExecutionDecision):
        raise LocalPaperFillError("A complete accepted execution decision is required")
    try:
        reconstructed = LocalPaperExecutionDecision(
            decision.authorization,
            decision.readiness,
            decision.disposition,
            decision.reason,
            decision.action,
            decision.approved_quantity,
            decision.policy,
        )
    except (ExecutionContractError, TypeError, ValueError):
        raise LocalPaperFillError(
            "Execution decision failed deterministic reconstruction"
        ) from None
    if (
        reconstructed != decision
        or reconstructed.decision_sha256 != decision.decision_sha256
        or decision.disposition is not ExecutionDisposition.ACCEPT_LOCAL_PAPER
        or decision.approved_quantity is None
    ):
        raise LocalPaperFillError("Execution decision is not accepted local Paper")


def _validate_intent(decision, intent):
    if not isinstance(intent, LocalPaperIntentRecord):
        raise LocalPaperFillError("A canonical accepted local intent is required")
    try:
        expected = LocalPaperIntentRecord.from_decision(decision)
    except ExecutionJournalError:
        raise LocalPaperFillError("Accepted local intent failed reconstruction") from None
    if intent != expected:
        raise LocalPaperFillError("Accepted local intent and decision disagree")


def _validate_order(intent, order):
    if not isinstance(order, LocalPaperOrderState):
        raise LocalPaperFillError("An active local order state is required")
    try:
        reconstructed = LocalPaperOrderState(
            order.authorization_sha256,
            order.intent_sha256,
            order.sequence,
            order.updated_time_ms,
            order.status,
            order.reason,
            order.previous_state_sha256,
            order.event_sha256,
        )
    except (LocalOrderError, TypeError, ValueError):
        raise LocalPaperFillError("Local order state failed reconstruction") from None
    if (
        reconstructed != order
        or order.authorization_sha256 != intent.authorization_sha256
        or order.intent_sha256 != intent.intent_sha256
        or order.status is not LocalOrderStatus.ACTIVE_LOCAL
        or order.sequence != 1
    ):
        raise LocalPaperFillError("Local order is not the active accepted intent")


def _fill_record(fill):
    reference = fill.reference
    return {
        "action": reference.action.value,
        "symbol": reference.symbol,
        "decision_time_ms": reference.decision_time_ms,
        "fill_time_ms": reference.fill_time_ms,
        "quantity": reference.quantity,
        "reference_price": reference.reference_price,
        "reason": reference.reason.value,
        "fee_bps": format(fill.fee_bps, "f"),
        "slippage_bps": format(fill.slippage_bps, "f"),
        "execution_price": format(fill.execution_price, "f"),
        "gross_quote": format(fill.gross_quote, "f"),
        "fee_quote": format(fill.fee_quote, "f"),
        "slippage_quote": format(fill.slippage_quote, "f"),
        "cash_delta": format(fill.cash_delta, "f"),
        "asset_delta": format(fill.asset_delta, "f"),
    }


@dataclass(frozen=True, slots=True)
class LocalPaperFillStep:
    """One deterministic in-memory P5-to-P2 fill and cost result."""

    authorization_sha256: str
    intent_sha256: str
    order_state_sha256: str
    p2_intent: PaperIntent
    references: tuple[FillReference, ...]
    fills: tuple[CostedFill, ...]

    def __post_init__(self):
        if (
            not isinstance(self.p2_intent, PaperIntent)
            or type(self.references) is not tuple
            or type(self.fills) is not tuple
            or not self.references
            or len(self.references) != len(self.fills)
            or any(not isinstance(item, FillReference) for item in self.references)
            or any(not isinstance(item, CostedFill) for item in self.fills)
            or tuple(item.reference for item in self.fills) != self.references
        ):
            raise LocalPaperFillError("P2 fill step identity is invalid")
        digests = (
            self.authorization_sha256,
            self.intent_sha256,
            self.order_state_sha256,
        )
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in digests
        ):
            raise LocalPaperFillError("P2 fill step evidence digest is invalid")
        if self.references[0].action is not self.p2_intent.action:
            raise LocalPaperFillError("P2 fill step action or quantity changed")

    def as_record(self):
        return {
            "schema_version": 1,
            "authorization_sha256": self.authorization_sha256,
            "intent_sha256": self.intent_sha256,
            "order_state_sha256": self.order_state_sha256,
            "p2_intent": {
                "action": self.p2_intent.action.value,
                "decision_time_ms": self.p2_intent.decision_time_ms,
                "quantity": self.p2_intent.quantity,
                "stop_price": self.p2_intent.stop_price,
                "target_price": self.p2_intent.target_price,
            },
            "fills": [_fill_record(fill) for fill in self.fills],
        }

    @property
    def fill_step_sha256(self):
        return hashlib.sha256(
            _canonical_json(self.as_record()).encode("utf-8")
        ).hexdigest()


class LocalPaperFillCostAdapter:
    """Atomic local-only bridge that delegates all economics to accepted P2."""

    def __init__(self, symbol, accepted_spec):
        if symbol not in SYMBOLS or not isinstance(accepted_spec, BacktestSpec):
            raise LocalPaperFillError("Accepted P2 identity is invalid")
        if accepted_spec.symbol != symbol:
            raise LocalPaperFillError("Accepted P2 symbol differs from the adapter")
        self.symbol = symbol
        self.spec = accepted_spec
        self._engine = PaperFillEngine(symbol)
        self._active_quantity = None
        self._last_sequence = None
        self._last_decision_time_ms = None

    @property
    def has_position(self):
        return self._engine.has_position

    @property
    def active_quantity(self):
        return self._active_quantity

    def _validate(self, event, decision, intent, order, fill_candle, cost_spec):
        _validate_decision(decision)
        _validate_intent(decision, intent)
        _validate_order(intent, order)
        if (
            not isinstance(event, DecisionEvent)
            or not isinstance(fill_candle, Candle)
            or not isinstance(cost_spec, BacktestSpec)
            or cost_spec != self.spec
        ):
            raise LocalPaperFillError("P2 event, candle or cost policy is invalid")
        strategy = decision.authorization.request.strategy_decision
        if (
            strategy.symbol != self.symbol
            or event.snapshot.symbol != self.symbol
            or strategy.decision_time_ms != event.decision_time_ms
            or strategy.context.snapshot != event.snapshot
            or not self.spec.start_time_ms <= event.decision_time_ms < self.spec.end_time_ms
        ):
            raise LocalPaperFillError("Accepted intent and P2 event disagree")
        expected_sequence = 0 if self._last_sequence is None else self._last_sequence + 1
        if (
            event.sequence != expected_sequence
            or (
                self._last_decision_time_ms is not None
                and event.decision_time_ms <= self._last_decision_time_ms
            )
        ):
            raise LocalPaperFillError("P2 event is duplicate or out of order")

    def _p2_intent(self, decision):
        strategy = decision.authorization.request.strategy_decision
        if decision.action is IntentAction.ENTER_LONG:
            if self.has_position or strategy.setup is None:
                raise LocalPaperFillError("Local entry conflicts with Paper state")
            return PaperIntent(
                IntentAction.ENTER_LONG,
                strategy.decision_time_ms,
                decision.approved_quantity,
                strategy.setup.invalidation_price,
                strategy.setup.target_price,
            )
        if decision.action is IntentAction.EXIT_LONG:
            if not self.has_position or self._active_quantity != decision.approved_quantity:
                raise LocalPaperFillError("Local exit conflicts with Paper state")
            return PaperIntent(IntentAction.EXIT_LONG, strategy.decision_time_ms)
        raise LocalPaperFillError("Accepted local intent has no fill action")

    def process(self, event, decision, intent, order, fill_candle, cost_spec):
        """Apply accepted P2 fill and cost rules without a partial state change."""
        self._validate(event, decision, intent, order, fill_candle, cost_spec)
        p2_intent = self._p2_intent(decision)
        candidate = copy.deepcopy(self._engine)
        try:
            references = candidate.process(event, p2_intent, fill_candle)
            fills = tuple(apply_costs(reference, cost_spec) for reference in references)
        except (FillModelError, CostModelError):
            raise LocalPaperFillError(
                "Accepted P2 fill or cost contract rejected the local intent"
            ) from None
        if not references:
            raise LocalPaperFillError("Accepted local intent produced no P2 fill")
        step = LocalPaperFillStep(
            intent.authorization_sha256,
            intent.intent_sha256,
            order.state_sha256,
            p2_intent,
            references,
            fills,
        )
        self._engine = candidate
        self._active_quantity = (
            decision.approved_quantity if candidate.has_position else None
        )
        self._last_sequence = event.sequence
        self._last_decision_time_ms = event.decision_time_ms
        return step
