"""Paper-only bridge from P3 decisions to the accepted P2 fill engine."""

from dataclasses import dataclass, replace

from yatl.backtest import (DecisionEvent, FillModelError, FillReference,
                           IntentAction, PaperFillEngine, PaperIntent)
from yatl.backtest.models import BacktestContractError
from yatl.data import Candle, SYMBOLS

from .breakout import IDENTITY as BREAKOUT_IDENTITY
from .contracts import (DecisionReason, LongSetup, StrategyAction,
                        StrategyContractError, StrategyDecision,
                        StrategyIdentity)
from .trend import IDENTITY as TREND_PULLBACK_IDENTITY


FIXED_RESEARCH_QUANTITY = "0.001"
SUPPORTED_IDENTITIES = (TREND_PULLBACK_IDENTITY, BREAKOUT_IDENTITY)


class SignalAdapterError(Exception):
    """A strategy decision cannot enter the deterministic paper lifecycle."""


@dataclass(frozen=True, slots=True)
class AdapterStep:
    decision: StrategyDecision
    intent: PaperIntent
    fills: tuple[FillReference, ...]

    def __post_init__(self):
        if (type(self.decision) is not StrategyDecision
                or type(self.intent) is not PaperIntent
                or type(self.fills) is not tuple
                or len(self.fills) > 2
                or any(type(item) is not FillReference for item in self.fills)
                or self.intent.decision_time_ms != self.decision.decision_time_ms):
            raise SignalAdapterError("Adapter step identity is invalid")
        expected = {
            StrategyAction.NO_TRADE: IntentAction.HOLD,
            StrategyAction.ENTER_LONG: IntentAction.ENTER_LONG,
            StrategyAction.EXIT_LONG: IntentAction.EXIT_LONG,
        }[self.decision.action]
        if self.intent.action is not expected:
            raise SignalAdapterError("Decision and paper intent actions differ")
        if any(item.symbol != self.decision.symbol
               or item.decision_time_ms != self.decision.decision_time_ms
               for item in self.fills):
            raise SignalAdapterError("Adapter fill identity is invalid")


class ResearchSignalAdapter:
    """Tracks one candidate/symbol and delegates fills to P2 atomically."""

    def __init__(self, identity, symbol):
        if type(identity) is not StrategyIdentity or identity not in SUPPORTED_IDENTITIES:
            raise SignalAdapterError("Adapter strategy identity is not supported")
        if symbol not in SYMBOLS:
            raise SignalAdapterError("Adapter symbol is not approved")
        self.identity = identity
        self.symbol = symbol
        self._fill_engine = PaperFillEngine(symbol)
        self._active_setup = None
        self._last_sequence = None
        self._last_decision_time_ms = None

    @property
    def has_position(self):
        return self._active_setup is not None

    @property
    def active_setup(self):
        return self._active_setup

    def _validate(self, event, decision, fill_candle):
        if (type(event) is not DecisionEvent
                or type(decision) is not StrategyDecision
                or type(fill_candle) is not Candle
                or decision.context.identity != self.identity
                or decision.symbol != self.symbol
                or event.snapshot.symbol != self.symbol
                or decision.decision_time_ms != event.decision_time_ms
                or decision.context.snapshot != event.snapshot):
            raise SignalAdapterError("Event, decision or fill identity is inconsistent")
        try:
            replace(decision.context.identity)
            replace(decision.context.snapshot)
            replace(decision.context)
            replace(decision)
        except (BacktestContractError, StrategyContractError, TypeError, ValueError):
            raise SignalAdapterError("Strategy decision failed reconstruction") from None
        expected_sequence = 0 if self._last_sequence is None else self._last_sequence + 1
        if (event.sequence != expected_sequence
                or (self._last_decision_time_ms is not None
                    and event.decision_time_ms <= self._last_decision_time_ms)):
            raise SignalAdapterError("Duplicate or out-of-order decision")

    def _intent(self, decision):
        if self.has_position:
            if decision.action is StrategyAction.EXIT_LONG:
                return PaperIntent(IntentAction.EXIT_LONG, decision.decision_time_ms)
            if (decision.action is StrategyAction.NO_TRADE
                    and decision.reason is DecisionReason.HOLD_POSITION):
                return PaperIntent(IntentAction.HOLD, decision.decision_time_ms)
            raise SignalAdapterError("Open strategy state requires HOLD or EXIT_LONG")
        if decision.action is StrategyAction.ENTER_LONG:
            return PaperIntent(
                IntentAction.ENTER_LONG, decision.decision_time_ms,
                FIXED_RESEARCH_QUANTITY, decision.setup.invalidation_price,
                decision.setup.target_price,
            )
        if (decision.action is StrategyAction.NO_TRADE
                and decision.reason is not DecisionReason.HOLD_POSITION):
            return PaperIntent(IntentAction.HOLD, decision.decision_time_ms)
        raise SignalAdapterError("Flat strategy state cannot hold or exit a position")

    def process(self, event, decision, fill_candle):
        """Translate and process exactly one next-open paper event."""
        self._validate(event, decision, fill_candle)
        intent = self._intent(decision)
        try:
            fills = self._fill_engine.process(event, intent, fill_candle)
        except FillModelError:
            raise SignalAdapterError("P2 rejected the strategy paper intent") from None

        step = AdapterStep(decision, intent, fills)
        if intent.action is IntentAction.ENTER_LONG and self._fill_engine.has_position:
            self._active_setup = decision.setup
        elif not self._fill_engine.has_position:
            self._active_setup = None
        if self.has_position != self._fill_engine.has_position:
            raise SignalAdapterError("Strategy and fill-engine position states diverged")
        self._last_sequence = event.sequence
        self._last_decision_time_ms = event.decision_time_ms
        return step
