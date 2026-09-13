"""Deterministic P4 loss, drawdown and loss-streak circuit breakers."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from yatl.strategy import StrategyAction

from .contracts import RiskRequest, UNSIGNED_DECIMAL_PATTERN
from .state import ManagedPortfolioState


class CircuitBreakerError(ValueError):
    """Circuit-breaker input or evidence is invalid or inconsistent."""


class CircuitBreaker(str, Enum):
    SESSION_LOSS_LIMIT = "SESSION_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    CONSECUTIVE_LOSS_LIMIT = "CONSECUTIVE_LOSS_LIMIT"


class CircuitDisposition(str, Enum):
    CLEAR = "CLEAR"
    BLOCK_ENTRY = "BLOCK_ENTRY"
    ALLOW_RISK_REDUCING_EXIT = "ALLOW_RISK_REDUCING_EXIT"
    NO_ACTION = "NO_ACTION"


class CircuitReason(str, Enum):
    WITHIN_LIMITS = "WITHIN_LIMITS"
    SESSION_LOSS_LIMIT = "SESSION_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    CONSECUTIVE_LOSS_LIMIT = "CONSECUTIVE_LOSS_LIMIT"
    MULTIPLE_LIMITS = "MULTIPLE_LIMITS"
    EXIT_REDUCES_RISK = "EXIT_REDUCES_RISK"
    NO_STRATEGY_ACTION = "NO_STRATEGY_ACTION"


_SINGLE_REASON = {
    CircuitBreaker.SESSION_LOSS_LIMIT: CircuitReason.SESSION_LOSS_LIMIT,
    CircuitBreaker.DRAWDOWN_LIMIT: CircuitReason.DRAWDOWN_LIMIT,
    CircuitBreaker.CONSECUTIVE_LOSS_LIMIT: CircuitReason.CONSECUTIVE_LOSS_LIMIT,
}


def _canonical(number):
    return format(number, "f")


def _values(request, managed_state):
    if not isinstance(request, RiskRequest):
        raise CircuitBreakerError("Circuit assessment requires a valid risk request")
    if not isinstance(managed_state, ManagedPortfolioState):
        raise CircuitBreakerError("Circuit assessment requires valid managed state")
    projected = managed_state.to_risk_state(
        kill_switch_active=request.portfolio.kill_switch_active,
    )
    if request.portfolio != projected:
        raise CircuitBreakerError("Risk request does not match managed portfolio state")

    with localcontext() as context:
        context.prec = 256
        session_pnl = Decimal(managed_state.session_realized_pnl_quote)
        session_loss = max(-session_pnl, Decimal(0))
        session_limit = (
            Decimal(managed_state.session_start_equity_quote)
            * Decimal(request.policy.max_session_loss_fraction)
        )
        drawdown = (
            Decimal(managed_state.peak_equity_quote)
            - Decimal(managed_state.equity_quote)
        )
        drawdown_limit = (
            Decimal(managed_state.peak_equity_quote)
            * Decimal(request.policy.max_drawdown_fraction)
        )

    triggered = tuple(
        breaker
        for breaker, active in (
            (CircuitBreaker.SESSION_LOSS_LIMIT, session_loss >= session_limit),
            (CircuitBreaker.DRAWDOWN_LIMIT, drawdown >= drawdown_limit),
            (
                CircuitBreaker.CONSECUTIVE_LOSS_LIMIT,
                managed_state.consecutive_losses
                >= request.policy.max_consecutive_losses,
            ),
        )
        if active
    )
    action = request.strategy_decision.action
    if action is StrategyAction.NO_TRADE:
        disposition = CircuitDisposition.NO_ACTION
        reason = CircuitReason.NO_STRATEGY_ACTION
    elif action is StrategyAction.EXIT_LONG:
        disposition = CircuitDisposition.ALLOW_RISK_REDUCING_EXIT
        reason = CircuitReason.EXIT_REDUCES_RISK
    elif triggered:
        disposition = CircuitDisposition.BLOCK_ENTRY
        reason = (
            _SINGLE_REASON[triggered[0]]
            if len(triggered) == 1
            else CircuitReason.MULTIPLE_LIMITS
        )
    else:
        disposition = CircuitDisposition.CLEAR
        reason = CircuitReason.WITHIN_LIMITS

    return {
        "disposition": disposition,
        "reason": reason,
        "triggered_breakers": triggered,
        "session_loss_quote": session_loss,
        "session_loss_limit_quote": session_limit,
        "drawdown_quote": drawdown,
        "drawdown_limit_quote": drawdown_limit,
        "consecutive_losses": managed_state.consecutive_losses,
        "consecutive_loss_limit": request.policy.max_consecutive_losses,
    }


@dataclass(frozen=True, slots=True)
class CircuitAssessment:
    """Tamper-checked breaker evidence; never an approval or execution command."""

    request: RiskRequest
    managed_state: ManagedPortfolioState
    disposition: CircuitDisposition
    reason: CircuitReason
    triggered_breakers: tuple[CircuitBreaker, ...]
    session_loss_quote: str
    session_loss_limit_quote: str
    drawdown_quote: str
    drawdown_limit_quote: str
    consecutive_losses: int
    consecutive_loss_limit: int

    def __post_init__(self):
        expected = _values(self.request, self.managed_state)
        if (
            self.disposition is not expected["disposition"]
            or self.reason is not expected["reason"]
            or self.triggered_breakers != expected["triggered_breakers"]
            or type(self.triggered_breakers) is not tuple
            or not all(
                isinstance(item, CircuitBreaker) for item in self.triggered_breakers
            )
        ):
            raise CircuitBreakerError("Circuit disposition or reason is inconsistent")
        for name in (
            "session_loss_quote",
            "session_loss_limit_quote",
            "drawdown_quote",
            "drawdown_limit_quote",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or UNSIGNED_DECIMAL_PATTERN.fullmatch(value) is None
                or value != _canonical(expected[name])
            ):
                raise CircuitBreakerError(
                    "Circuit assessment is noncanonical or inconsistent"
                )
        for name in ("consecutive_losses", "consecutive_loss_limit"):
            value = getattr(self, name)
            if type(value) is not int or value != expected[name]:
                raise CircuitBreakerError("Circuit counters are inconsistent")

    @property
    def request_sha256(self):
        return self.request.request_sha256

    @property
    def state_sha256(self):
        return self.managed_state.state_sha256

    @property
    def circuit_sha256(self):
        payload = {
            "schema_version": 1,
            "request_sha256": self.request_sha256,
            "state_sha256": self.state_sha256,
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "triggered_breakers": [item.value for item in self.triggered_breakers],
            "session_loss_quote": self.session_loss_quote,
            "session_loss_limit_quote": self.session_loss_limit_quote,
            "drawdown_quote": self.drawdown_quote,
            "drawdown_limit_quote": self.drawdown_limit_quote,
            "consecutive_losses": self.consecutive_losses,
            "consecutive_loss_limit": self.consecutive_loss_limit,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assess_circuit_breakers(request, managed_state):
    """Assess frozen P4 breaker limits without latching state or approving entry."""
    values = _values(request, managed_state)
    return CircuitAssessment(
        request=request,
        managed_state=managed_state,
        disposition=values["disposition"],
        reason=values["reason"],
        triggered_breakers=values["triggered_breakers"],
        session_loss_quote=_canonical(values["session_loss_quote"]),
        session_loss_limit_quote=_canonical(values["session_loss_limit_quote"]),
        drawdown_quote=_canonical(values["drawdown_quote"]),
        drawdown_limit_quote=_canonical(values["drawdown_limit_quote"]),
        consecutive_losses=values["consecutive_losses"],
        consecutive_loss_limit=values["consecutive_loss_limit"],
    )
