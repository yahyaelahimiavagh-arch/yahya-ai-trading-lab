"""Immutable point-in-time signal contracts with no execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from yatl.backtest.config import DECIMAL_PATTERN
from yatl.backtest.models import MarketSnapshot


STRATEGY_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{2,31}")
VERSION_PATTERN = re.compile(r"[1-9][0-9]*\.[0-9]+\.[0-9]+")


class StrategyContractError(Exception):
    """A strategy identity, context or decision violates the P3 boundary."""


class StrategyAction(str, Enum):
    NO_TRADE = "NO_TRADE"
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"


class DecisionReason(str, Enum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    REGIME_UNKNOWN = "REGIME_UNKNOWN"
    REGIME_BLOCKED = "REGIME_BLOCKED"
    SETUP_ABSENT = "SETUP_ABSENT"
    CONFIRMATION_FAILED = "CONFIRMATION_FAILED"
    HOLD_POSITION = "HOLD_POSITION"
    TREND_PULLBACK_ENTRY = "TREND_PULLBACK_ENTRY"
    BREAKOUT_ENTRY = "BREAKOUT_ENTRY"
    STRATEGY_EXIT = "STRATEGY_EXIT"


ENTRY_REASONS = {DecisionReason.TREND_PULLBACK_ENTRY, DecisionReason.BREAKOUT_ENTRY}
NO_TRADE_REASONS = {
    DecisionReason.INSUFFICIENT_HISTORY,
    DecisionReason.REGIME_UNKNOWN,
    DecisionReason.REGIME_BLOCKED,
    DecisionReason.SETUP_ABSENT,
    DecisionReason.CONFIRMATION_FAILED,
    DecisionReason.HOLD_POSITION,
}


def _positive(value, field):
    if not isinstance(value, str) or DECIMAL_PATTERN.fullmatch(value) is None:
        raise StrategyContractError(f"{field} must be a plain positive decimal string")
    number = Decimal(value)
    if not number.is_finite() or number <= 0:
        raise StrategyContractError(f"{field} must be positive")
    return number


@dataclass(frozen=True, slots=True)
class StrategyIdentity:
    strategy_id: str
    version: str

    def __post_init__(self):
        if (not isinstance(self.strategy_id, str)
                or STRATEGY_ID_PATTERN.fullmatch(self.strategy_id) is None
                or not isinstance(self.version, str)
                or VERSION_PATTERN.fullmatch(self.version) is None):
            raise StrategyContractError("Strategy identity is invalid")


@dataclass(frozen=True, slots=True)
class StrategyContext:
    identity: StrategyIdentity
    snapshot: MarketSnapshot
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_leverage: bool = False

    def __post_init__(self):
        if (not isinstance(self.identity, StrategyIdentity)
                or not isinstance(self.snapshot, MarketSnapshot)
                or self.paper_only is not True
                or self.live_master_lock != "OFF"
                or self.spot_only is not True
                or self.allow_short is not False
                or self.allow_leverage is not False):
            raise StrategyContractError("Strategy context or safety policy is invalid")

    @property
    def symbol(self):
        return self.snapshot.symbol

    @property
    def decision_time_ms(self):
        return self.snapshot.decision_time_ms

    @property
    def context_sha256(self):
        payload = {
            "strategy_id": self.identity.strategy_id,
            "strategy_version": self.identity.version,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "primary": [item.as_record() for item in self.snapshot.primary],
            "context": [item.as_record() for item in self.snapshot.context],
            "regime": [item.as_record() for item in self.snapshot.regime],
            "safety": {
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "spot_only": self.spot_only,
                "allow_short": self.allow_short,
                "allow_leverage": self.allow_leverage,
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LongSetup:
    reference_price: str
    invalidation_price: str
    target_price: str

    def __post_init__(self):
        reference = _positive(self.reference_price, "reference_price")
        invalidation = _positive(self.invalidation_price, "invalidation_price")
        target = _positive(self.target_price, "target_price")
        if not invalidation < reference < target:
            raise StrategyContractError("Long setup levels are invalid")


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    context: StrategyContext
    action: StrategyAction
    reason: DecisionReason
    setup: LongSetup | None = None

    def __post_init__(self):
        if (not isinstance(self.context, StrategyContext)
                or not isinstance(self.action, StrategyAction)
                or not isinstance(self.reason, DecisionReason)):
            raise StrategyContractError("Strategy decision identity is invalid")
        if self.action is StrategyAction.ENTER_LONG:
            valid = isinstance(self.setup, LongSetup) and self.reason in ENTRY_REASONS
        elif self.action is StrategyAction.EXIT_LONG:
            valid = self.setup is None and self.reason is DecisionReason.STRATEGY_EXIT
        else:
            valid = self.setup is None and self.reason in NO_TRADE_REASONS
        if not valid:
            raise StrategyContractError("Strategy action, reason and setup are inconsistent")

    @property
    def strategy_id(self):
        return self.context.identity.strategy_id

    @property
    def strategy_version(self):
        return self.context.identity.version

    @property
    def symbol(self):
        return self.context.symbol

    @property
    def decision_time_ms(self):
        return self.context.decision_time_ms

    @property
    def context_sha256(self):
        return self.context.context_sha256
