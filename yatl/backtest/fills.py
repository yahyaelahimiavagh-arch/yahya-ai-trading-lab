"""Local long-only intent lifecycle and uncosted fill references for P2."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from yatl.data import Candle, INTERVAL_MILLISECONDS, SYMBOLS

from .clock import DecisionEvent
from .config import DECIMAL_PATTERN, PRIMARY_INTERVAL


class FillModelError(Exception):
    """A paper intent or fill violates the deterministic Spot model."""


class IntentAction(str, Enum):
    HOLD = "HOLD"
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"


class FillReason(str, Enum):
    NEXT_PRIMARY_OPEN = "NEXT_PRIMARY_OPEN"
    SCRIPTED_EXIT = "SCRIPTED_EXIT"
    STOP = "STOP"
    TARGET = "TARGET"
    AMBIGUOUS_STOP_PRIORITY = "AMBIGUOUS_STOP_PRIORITY"


def _positive_decimal(value, field):
    if not isinstance(value, str) or DECIMAL_PATTERN.fullmatch(value) is None:
        raise FillModelError(f"{field} must be a plain decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise FillModelError(f"{field} is invalid") from None
    if not number.is_finite() or number <= 0:
        raise FillModelError(f"{field} must be positive")
    return number


@dataclass(frozen=True, slots=True)
class PaperIntent:
    action: IntentAction
    decision_time_ms: int
    quantity: str | None = None
    stop_price: str | None = None
    target_price: str | None = None

    def __post_init__(self):
        duration = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
        if (not isinstance(self.action, IntentAction)
                or type(self.decision_time_ms) is not int
                or self.decision_time_ms <= 0
                or self.decision_time_ms % duration):
            raise FillModelError("Paper intent identity is invalid")
        if self.action is IntentAction.ENTER_LONG:
            quantity = _positive_decimal(self.quantity, "quantity")
            stop = _positive_decimal(self.stop_price, "stop_price")
            target = _positive_decimal(self.target_price, "target_price")
            if quantity <= 0 or stop >= target:
                raise FillModelError("Long entry bracket is invalid")
        elif any(value is not None for value in
                 (self.quantity, self.stop_price, self.target_price)):
            raise FillModelError("HOLD and EXIT_LONG cannot carry entry fields")


@dataclass(frozen=True, slots=True)
class FillReference:
    action: IntentAction
    symbol: str
    decision_time_ms: int
    fill_time_ms: int
    quantity: str
    reference_price: str
    reason: FillReason

    def __post_init__(self):
        if (self.action not in (IntentAction.ENTER_LONG, IntentAction.EXIT_LONG)
                or self.symbol not in SYMBOLS
                or type(self.decision_time_ms) is not int
                or self.fill_time_ms != self.decision_time_ms
                or self.fill_time_ms <= 0
                or self.fill_time_ms % INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
                or not isinstance(self.reason, FillReason)
                or (self.action is IntentAction.ENTER_LONG
                    and self.reason is not FillReason.NEXT_PRIMARY_OPEN)
                or (self.action is IntentAction.EXIT_LONG
                    and self.reason is FillReason.NEXT_PRIMARY_OPEN)):
            raise FillModelError("Fill reference identity is invalid")
        _positive_decimal(self.quantity, "quantity")
        _positive_decimal(self.reference_price, "reference_price")


@dataclass(frozen=True, slots=True)
class _OpenPosition:
    quantity: str
    stop_price: str
    target_price: str


class PaperFillEngine:
    """Stateful local lifecycle; produces references for the P2-005 cost model."""

    def __init__(self, symbol):
        if symbol not in SYMBOLS:
            raise FillModelError("Fill engine symbol is not approved")
        self.symbol = symbol
        self._position = None

    @property
    def has_position(self):
        return self._position is not None

    def _reference(self, action, event, quantity, price, reason):
        return FillReference(action, self.symbol, event.decision_time_ms,
                             event.eligible_fill_open_time_ms, quantity, price, reason)

    def _protective_exit(self, event, bar):
        if self._position is None:
            return None
        opened, low, high = map(Decimal, (bar.open, bar.low, bar.high))
        stop = Decimal(self._position.stop_price)
        target = Decimal(self._position.target_price)
        if opened <= stop:
            price, reason = bar.open, FillReason.STOP
        elif opened >= target:
            price, reason = self._position.target_price, FillReason.TARGET
        elif low <= stop and high >= target:
            price, reason = self._position.stop_price, FillReason.AMBIGUOUS_STOP_PRIORITY
        elif low <= stop:
            price, reason = self._position.stop_price, FillReason.STOP
        elif high >= target:
            price, reason = self._position.target_price, FillReason.TARGET
        else:
            return None
        result = self._reference(IntentAction.EXIT_LONG, event,
                                 self._position.quantity, price, reason)
        self._position = None
        return result

    def process(self, event, intent, fill_candle):
        if (not isinstance(event, DecisionEvent) or not isinstance(intent, PaperIntent)
                or intent.decision_time_ms != event.decision_time_ms
                or event.snapshot.symbol != self.symbol
                or not isinstance(fill_candle, Candle)
                or fill_candle.symbol != self.symbol
                or fill_candle.interval != PRIMARY_INTERVAL
                or not fill_candle.is_closed
                or fill_candle.open_time_ms != event.eligible_fill_open_time_ms):
            raise FillModelError("Intent, event or next-open candle is invalid")
        original = self._position
        fills = []
        try:
            if intent.action is IntentAction.EXIT_LONG:
                if self._position is None:
                    raise FillModelError("Cannot exit without an open long position")
                fills.append(self._reference(IntentAction.EXIT_LONG, event,
                                             self._position.quantity, fill_candle.open,
                                             FillReason.SCRIPTED_EXIT))
                self._position = None
            elif intent.action is IntentAction.ENTER_LONG:
                if self._position is not None:
                    raise FillModelError("Overlapping long positions are forbidden")
                opened = Decimal(fill_candle.open)
                if not Decimal(intent.stop_price) < opened < Decimal(intent.target_price):
                    raise FillModelError("Next-open price is outside the long bracket")
                self._position = _OpenPosition(intent.quantity, intent.stop_price,
                                               intent.target_price)
                fills.append(self._reference(IntentAction.ENTER_LONG, event,
                                             intent.quantity, fill_candle.open,
                                             FillReason.NEXT_PRIMARY_OPEN))
                protective = self._protective_exit(event, fill_candle)
                if protective is not None:
                    fills.append(protective)
            else:
                protective = self._protective_exit(event, fill_candle)
                if protective is not None:
                    fills.append(protective)
            if sum(Decimal(item.quantity) for item in fills) > Decimal(fill_candle.base_volume):
                raise FillModelError("Paper fills exceed the candle base volume")
        except FillModelError:
            self._position = original
            raise
        return tuple(fills)
