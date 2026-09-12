"""Immutable P4 risk contracts with no exchange execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

from yatl.data import INTERVAL_MILLISECONDS, SYMBOLS
from yatl.strategy import EvidenceLabel, StrategyAction, StrategyDecision


POLICY_ID = "P4_RISK_V1"
UNSIGNED_DECIMAL_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?"
)
SIGNED_DECIMAL_PATTERN = re.compile(
    r"-?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,40})?"
)


class RiskContractError(ValueError):
    """A P4 request, policy, state or decision violates the safety boundary."""


def _decimal(value, field_name, *, positive=False, signed=False):
    pattern = SIGNED_DECIMAL_PATTERN if signed else UNSIGNED_DECIMAL_PATTERN
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RiskContractError(f"{field_name} must be a plain decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise RiskContractError(f"{field_name} is invalid") from None
    if not number.is_finite() or (positive and number <= 0):
        raise RiskContractError(f"{field_name} is outside the allowed range")
    return number


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Pre-registered conservative limits for deterministic P4 research."""

    policy_id: str = POLICY_ID
    risk_per_trade_fraction: str = "0.01"
    max_position_fraction: str = "0.25"
    max_gross_exposure_fraction: str = "0.25"
    max_session_loss_fraction: str = "0.02"
    max_drawdown_fraction: str = "0.10"
    max_consecutive_losses: int = 3
    max_open_positions: int = 1
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    long_only: bool = True
    allow_leverage: bool = False
    allow_withdrawal: bool = False
    allow_order_endpoint: bool = False
    allow_ai_direct_execution: bool = False

    def __post_init__(self):
        fixed = (
            self.policy_id == POLICY_ID
            and self.risk_per_trade_fraction == "0.01"
            and self.max_position_fraction == "0.25"
            and self.max_gross_exposure_fraction == "0.25"
            and self.max_session_loss_fraction == "0.02"
            and self.max_drawdown_fraction == "0.10"
            and type(self.max_consecutive_losses) is int
            and self.max_consecutive_losses == 3
            and type(self.max_open_positions) is int
            and self.max_open_positions == 1
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.long_only is True
            and self.allow_leverage is False
            and self.allow_withdrawal is False
            and self.allow_order_endpoint is False
            and self.allow_ai_direct_execution is False
        )
        if not fixed:
            raise RiskContractError("Risk policy differs from the frozen P4 policy")


@dataclass(frozen=True, slots=True)
class PortfolioRiskState:
    """Point-in-time paper portfolio facts supplied to the independent manager."""

    symbol: str
    decision_time_ms: int
    equity_quote: str
    cash_quote: str
    position_quantity: str
    mark_price: str
    peak_equity_quote: str
    session_realized_pnl_quote: str = "0"
    consecutive_losses: int = 0
    open_positions: int = 0
    kill_switch_active: bool = False

    def __post_init__(self):
        if self.symbol not in SYMBOLS:
            raise RiskContractError("Risk state symbol is not approved")
        if (
            type(self.decision_time_ms) is not int
            or self.decision_time_ms < 0
            or self.decision_time_ms % INTERVAL_MILLISECONDS["1h"]
        ):
            raise RiskContractError("Risk state time must be an aligned 1h boundary")
        equity = _decimal(self.equity_quote, "equity_quote", positive=True)
        _decimal(self.cash_quote, "cash_quote")
        quantity = _decimal(self.position_quantity, "position_quantity")
        _decimal(self.mark_price, "mark_price", positive=True)
        peak = _decimal(self.peak_equity_quote, "peak_equity_quote", positive=True)
        _decimal(self.session_realized_pnl_quote, "session_realized_pnl_quote", signed=True)
        if peak < equity:
            raise RiskContractError("peak_equity_quote cannot be below current equity")
        if (
            type(self.consecutive_losses) is not int
            or not 0 <= self.consecutive_losses <= 1_000_000
            or type(self.open_positions) is not int
            or not 0 <= self.open_positions <= 1_000_000
            or type(self.kill_switch_active) is not bool
        ):
            raise RiskContractError("Risk state counters are invalid")
        if (quantity == 0) != (self.open_positions == 0):
            raise RiskContractError("Position quantity and open-position count disagree")


@dataclass(frozen=True, slots=True)
class RiskRequest:
    """A strategy decision bound to evidence, portfolio state and frozen policy."""

    strategy_decision: StrategyDecision
    evidence_label: EvidenceLabel
    portfolio: PortfolioRiskState
    policy: RiskPolicy = field(default_factory=RiskPolicy)

    def __post_init__(self):
        if (
            not isinstance(self.strategy_decision, StrategyDecision)
            or not isinstance(self.evidence_label, EvidenceLabel)
            or not isinstance(self.portfolio, PortfolioRiskState)
            or not isinstance(self.policy, RiskPolicy)
        ):
            raise RiskContractError("Risk request identity is invalid")
        if (
            self.strategy_decision.symbol != self.portfolio.symbol
            or self.strategy_decision.decision_time_ms != self.portfolio.decision_time_ms
        ):
            raise RiskContractError("Strategy decision and portfolio state do not match")
        action = self.strategy_decision.action
        if action is StrategyAction.ENTER_LONG and self.portfolio.open_positions != 0:
            raise RiskContractError("Entry request cannot overlap an open position")
        if action is StrategyAction.EXIT_LONG and self.portfolio.open_positions == 0:
            raise RiskContractError("Exit request requires an open position")

    @property
    def request_sha256(self):
        setup = self.strategy_decision.setup
        payload = {
            "schema_version": 1,
            "strategy": {
                "id": self.strategy_decision.strategy_id,
                "version": self.strategy_decision.strategy_version,
                "action": self.strategy_decision.action.value,
                "reason": self.strategy_decision.reason.value,
                "context_sha256": self.strategy_decision.context_sha256,
                "setup": None if setup is None else {
                    "reference_price": setup.reference_price,
                    "invalidation_price": setup.invalidation_price,
                    "target_price": setup.target_price,
                },
            },
            "evidence_label": self.evidence_label.value,
            "portfolio": {
                name: getattr(self.portfolio, name)
                for name in self.portfolio.__dataclass_fields__
            },
            "policy": {
                name: getattr(self.policy, name)
                for name in self.policy.__dataclass_fields__
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RiskDisposition(str, Enum):
    NO_ACTION = "NO_ACTION"
    REJECT = "REJECT"
    APPROVE_PAPER = "APPROVE_PAPER"


class RiskReason(str, Enum):
    NO_STRATEGY_ACTION = "NO_STRATEGY_ACTION"
    PENDING_RISK_EVALUATION = "PENDING_RISK_EVALUATION"
    EVIDENCE_NOT_QUALIFIED = "EVIDENCE_NOT_QUALIFIED"
    RISK_CHECKS_PASSED = "RISK_CHECKS_PASSED"
    EXIT_REDUCES_RISK = "EXIT_REDUCES_RISK"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Fail-closed P4 result; approval is paper-only and never submits an order."""

    request: RiskRequest
    disposition: RiskDisposition
    reason: RiskReason
    approved_quantity: str | None = None

    def __post_init__(self):
        if (
            not isinstance(self.request, RiskRequest)
            or not isinstance(self.disposition, RiskDisposition)
            or not isinstance(self.reason, RiskReason)
        ):
            raise RiskContractError("Risk decision identity is invalid")
        action = self.request.strategy_decision.action
        quantity = None
        if self.approved_quantity is not None:
            quantity = _decimal(self.approved_quantity, "approved_quantity", positive=True)

        if self.disposition is RiskDisposition.NO_ACTION:
            valid = (
                action is StrategyAction.NO_TRADE
                and self.reason is RiskReason.NO_STRATEGY_ACTION
                and quantity is None
            )
        elif self.disposition is RiskDisposition.REJECT:
            valid = (
                action is StrategyAction.ENTER_LONG
                and self.reason in {
                    RiskReason.PENDING_RISK_EVALUATION,
                    RiskReason.EVIDENCE_NOT_QUALIFIED,
                    RiskReason.KILL_SWITCH_ACTIVE,
                }
                and quantity is None
            )
        elif action is StrategyAction.ENTER_LONG:
            valid = (
                self.reason is RiskReason.RISK_CHECKS_PASSED
                and quantity is not None
                and self.request.evidence_label
                is EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH
                and self.request.portfolio.kill_switch_active is False
            )
        else:
            valid = (
                action is StrategyAction.EXIT_LONG
                and self.reason is RiskReason.EXIT_REDUCES_RISK
                and quantity == Decimal(self.request.portfolio.position_quantity)
            )
        if not valid:
            raise RiskContractError("Risk disposition, reason and quantity are inconsistent")

    @property
    def request_sha256(self):
        return self.request.request_sha256
