"""Deterministic, hash-chained P4 portfolio and session state transitions."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from yatl.data import INTERVAL_MILLISECONDS, SYMBOLS

from .contracts import PortfolioRiskState, SIGNED_DECIMAL_PATTERN, UNSIGNED_DECIMAL_PATTERN


UTC_DAY_MILLISECONDS = 86_400_000
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RiskStateError(ValueError):
    """A state observation or transition is incomplete or inconsistent."""


class CloseOutcome(str, Enum):
    NO_CLOSE = "NO_CLOSE"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


def _number(value, name, *, positive=False, signed=False):
    pattern = SIGNED_DECIMAL_PATTERN if signed else UNSIGNED_DECIMAL_PATTERN
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RiskStateError(f"{name} must be a plain decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise RiskStateError(f"{name} is invalid") from None
    if not number.is_finite() or (positive and number <= 0):
        raise RiskStateError(f"{name} is outside the allowed range")
    return number


def _canonical(number):
    return format(number, "f")


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PortfolioObservation:
    """Complete point-in-time facts for one ordered paper-ledger observation."""

    symbol: str
    sequence: int
    decision_time_ms: int
    equity_quote: str
    cash_quote: str
    position_quantity: str
    mark_price: str
    realized_pnl_delta_quote: str = "0"
    close_outcome: CloseOutcome = CloseOutcome.NO_CLOSE
    start_new_session: bool = False

    def __post_init__(self):
        if self.symbol not in SYMBOLS:
            raise RiskStateError("Observation symbol is not approved")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise RiskStateError("Observation sequence is invalid")
        if (
            type(self.decision_time_ms) is not int
            or self.decision_time_ms < 0
            or self.decision_time_ms % INTERVAL_MILLISECONDS["1h"]
        ):
            raise RiskStateError("Observation time must be an aligned 1h boundary")
        _number(self.equity_quote, "equity_quote", positive=True)
        _number(self.cash_quote, "cash_quote")
        _number(self.position_quantity, "position_quantity")
        _number(self.mark_price, "mark_price", positive=True)
        pnl = _number(
            self.realized_pnl_delta_quote, "realized_pnl_delta_quote", signed=True,
        )
        if not isinstance(self.close_outcome, CloseOutcome):
            raise RiskStateError("Close outcome is invalid")
        if type(self.start_new_session) is not bool:
            raise RiskStateError("Session reset flag is invalid")
        signs_match = {
            CloseOutcome.NO_CLOSE: pnl == 0,
            CloseOutcome.WIN: pnl > 0,
            CloseOutcome.LOSS: pnl < 0,
            CloseOutcome.BREAKEVEN: pnl == 0,
        }
        if not signs_match[self.close_outcome]:
            raise RiskStateError("Close outcome and realized PnL disagree")

    @property
    def observation_sha256(self):
        return _digest({
            "schema_version": 1,
            **{
                name: (
                    getattr(self, name).value
                    if isinstance(getattr(self, name), Enum)
                    else getattr(self, name)
                )
                for name in self.__dataclass_fields__
            },
        })


@dataclass(frozen=True, slots=True)
class ManagedPortfolioState:
    """Canonical state resulting from an accepted hash-chained observation."""

    symbol: str
    sequence: int
    decision_time_ms: int
    session_start_time_ms: int
    session_start_equity_quote: str
    equity_quote: str
    cash_quote: str
    position_quantity: str
    mark_price: str
    peak_equity_quote: str
    session_realized_pnl_quote: str
    consecutive_losses: int
    open_positions: int
    gross_exposure_quote: str
    previous_state_sha256: str | None
    observation_sha256: str

    def __post_init__(self):
        if self.symbol not in SYMBOLS:
            raise RiskStateError("Managed-state symbol is not approved")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 1_000_000_000:
            raise RiskStateError("Managed-state sequence is invalid")
        for name in ("decision_time_ms", "session_start_time_ms"):
            value = getattr(self, name)
            if type(value) is not int or value < 0 or value % INTERVAL_MILLISECONDS["1h"]:
                raise RiskStateError(f"{name} must be an aligned 1h boundary")
        if self.session_start_time_ms > self.decision_time_ms:
            raise RiskStateError("Session cannot start after the managed state")
        session_start = _number(
            self.session_start_equity_quote, "session_start_equity_quote", positive=True,
        )
        equity = _number(self.equity_quote, "equity_quote", positive=True)
        _number(self.cash_quote, "cash_quote")
        quantity = _number(self.position_quantity, "position_quantity")
        mark = _number(self.mark_price, "mark_price", positive=True)
        peak = _number(self.peak_equity_quote, "peak_equity_quote", positive=True)
        _number(self.session_realized_pnl_quote, "session_realized_pnl_quote", signed=True)
        exposure = _number(self.gross_exposure_quote, "gross_exposure_quote")
        if session_start <= 0 or peak < equity:
            raise RiskStateError("Managed-state equity values are inconsistent")
        if (
            type(self.consecutive_losses) is not int
            or not 0 <= self.consecutive_losses <= 1_000_000
            or type(self.open_positions) is not int
            or self.open_positions not in (0, 1)
        ):
            raise RiskStateError("Managed-state counters are invalid")
        if (quantity == 0) != (self.open_positions == 0):
            raise RiskStateError("Position quantity and open-position count disagree")
        with localcontext() as context:
            context.prec = 256
            if self.gross_exposure_quote != _canonical(quantity * mark) or exposure != quantity * mark:
                raise RiskStateError("Gross exposure is noncanonical or inconsistent")
        if self.sequence == 0:
            if self.previous_state_sha256 is not None:
                raise RiskStateError("Initial state cannot have a predecessor")
        elif (
            not isinstance(self.previous_state_sha256, str)
            or SHA256_PATTERN.fullmatch(self.previous_state_sha256) is None
        ):
            raise RiskStateError("Managed state is missing its predecessor digest")
        if (
            not isinstance(self.observation_sha256, str)
            or SHA256_PATTERN.fullmatch(self.observation_sha256) is None
        ):
            raise RiskStateError("Managed state observation digest is invalid")

    @property
    def state_sha256(self):
        return _digest({
            "schema_version": 1,
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
        })

    def to_risk_state(self, *, kill_switch_active=False):
        """Project managed facts into the accepted P4-001 request contract."""
        if type(kill_switch_active) is not bool:
            raise RiskStateError("Kill-switch flag must be boolean")
        return PortfolioRiskState(
            symbol=self.symbol,
            decision_time_ms=self.decision_time_ms,
            equity_quote=self.equity_quote,
            cash_quote=self.cash_quote,
            position_quantity=self.position_quantity,
            mark_price=self.mark_price,
            peak_equity_quote=self.peak_equity_quote,
            session_realized_pnl_quote=self.session_realized_pnl_quote,
            consecutive_losses=self.consecutive_losses,
            open_positions=self.open_positions,
            kill_switch_active=kill_switch_active,
        )


def _next_state(previous, observation):
    if not isinstance(observation, PortfolioObservation):
        raise RiskStateError("A complete portfolio observation is required")
    pnl_delta = Decimal(observation.realized_pnl_delta_quote)
    equity = Decimal(observation.equity_quote)
    quantity = Decimal(observation.position_quantity)
    mark = Decimal(observation.mark_price)

    if previous is None:
        if observation.sequence != 0 or observation.start_new_session is not True:
            raise RiskStateError("Initial state requires sequence zero and a session start")
        if observation.close_outcome is not CloseOutcome.NO_CLOSE or quantity != 0:
            raise RiskStateError("Initial state must be flat with no close outcome")
        session_start_time = observation.decision_time_ms
        session_start_equity = equity
        session_pnl = Decimal("0")
        peak = equity
        consecutive_losses = 0
        previous_sha = None
    else:
        if not isinstance(previous, ManagedPortfolioState):
            raise RiskStateError("Previous managed state is invalid")
        if observation.symbol != previous.symbol:
            raise RiskStateError("State symbol cannot change")
        if observation.sequence != previous.sequence + 1:
            raise RiskStateError("State sequence is duplicate or missing")
        if observation.decision_time_ms <= previous.decision_time_ms:
            raise RiskStateError("State observation is stale or out of order")

        prior_quantity = Decimal(previous.position_quantity)
        if observation.close_outcome is CloseOutcome.NO_CLOSE:
            if prior_quantity > 0 and quantity != prior_quantity:
                raise RiskStateError("An open position changed without a close outcome")
        elif prior_quantity <= 0 or quantity != 0:
            raise RiskStateError("A close outcome must close the complete open position")

        if observation.start_new_session:
            if observation.decision_time_ms % UTC_DAY_MILLISECONDS:
                raise RiskStateError("A new session must start at 00:00 UTC")
            if observation.close_outcome is not CloseOutcome.NO_CLOSE:
                raise RiskStateError("Session reset and close outcome require separate observations")
            session_start_time = observation.decision_time_ms
            session_start_equity = equity
            session_pnl = Decimal("0")
        else:
            session_start_time = previous.session_start_time_ms
            session_start_equity = Decimal(previous.session_start_equity_quote)
            with localcontext() as context:
                context.prec = 256
                session_pnl = Decimal(previous.session_realized_pnl_quote) + pnl_delta

        peak = max(Decimal(previous.peak_equity_quote), equity)
        if observation.close_outcome is CloseOutcome.LOSS:
            consecutive_losses = previous.consecutive_losses + 1
        elif observation.close_outcome in (CloseOutcome.WIN, CloseOutcome.BREAKEVEN):
            consecutive_losses = 0
        else:
            consecutive_losses = previous.consecutive_losses
        previous_sha = previous.state_sha256

    with localcontext() as context:
        context.prec = 256
        gross_exposure = quantity * mark
    return ManagedPortfolioState(
        symbol=observation.symbol,
        sequence=observation.sequence,
        decision_time_ms=observation.decision_time_ms,
        session_start_time_ms=session_start_time,
        session_start_equity_quote=_canonical(session_start_equity),
        equity_quote=_canonical(equity),
        cash_quote=_canonical(Decimal(observation.cash_quote)),
        position_quantity=_canonical(quantity),
        mark_price=_canonical(mark),
        peak_equity_quote=_canonical(peak),
        session_realized_pnl_quote=_canonical(session_pnl),
        consecutive_losses=consecutive_losses,
        open_positions=0 if quantity == 0 else 1,
        gross_exposure_quote=_canonical(gross_exposure),
        previous_state_sha256=previous_sha,
        observation_sha256=observation.observation_sha256,
    )


@dataclass(frozen=True, slots=True)
class PortfolioStateTransition:
    """Tamper-evident proof of one deterministic state transition."""

    previous: ManagedPortfolioState | None
    observation: PortfolioObservation
    current: ManagedPortfolioState

    def __post_init__(self):
        if self.current != _next_state(self.previous, self.observation):
            raise RiskStateError("Current managed state does not match its transition")


def apply_portfolio_observation(previous, observation):
    """Apply one complete, strictly ordered observation without side effects."""
    current = _next_state(previous, observation)
    return PortfolioStateTransition(previous, observation, current)
