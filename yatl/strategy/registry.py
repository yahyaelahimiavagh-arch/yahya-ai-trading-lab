"""Immutable strategy metadata and bounded numeric configuration; no execution."""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal

from yatl.backtest.config import DECIMAL_PATTERN
from .contracts import StrategyIdentity, StrategyContractError


class RegistryError(Exception):
    """Strategy registration or configuration failed validation."""


NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
RESERVED = frozenset({
    "quantity", "position_size", "broker", "api_key", "api_secret", "credential",
    "account", "order", "leverage", "paper_only", "live_master_lock",
    "spot_only", "allow_short", "allow_leverage",
})


def _number(value, kind):
    if kind == "integer" and type(value) is int:
        return value
    if (kind == "decimal" and type(value) is str
            and DECIMAL_PATTERN.fullmatch(value)):
        return Decimal(value)
    raise RegistryError("Parameter must match its exact declared numeric type")


def _canonical_value(value, kind):
    number = _number(value, kind)
    if kind == "integer":
        return number
    # String trimming is lossless and independent of ambient Decimal precision.
    return value.rstrip("0").rstrip(".") if "." in value else value


@dataclass(frozen=True, slots=True)
class ParameterRule:
    name: str
    kind: str
    minimum: int | str
    maximum: int | str

    def __post_init__(self):
        if (type(self.name) is not str or NAME.fullmatch(self.name) is None
                or self.name in RESERVED or self.kind not in ("integer", "decimal")):
            raise RegistryError("Parameter rule identity is invalid")
        low, high = _number(self.minimum, self.kind), _number(self.maximum, self.kind)
        if not 0 <= low <= high <= 10_000:
            raise RegistryError("Parameter rule bounds are invalid")
        object.__setattr__(self, "minimum", _canonical_value(self.minimum, self.kind))
        object.__setattr__(self, "maximum", _canonical_value(self.maximum, self.kind))

    def validate(self, value):
        number = _number(value, self.kind)
        if not _number(self.minimum, self.kind) <= number <= _number(self.maximum, self.kind):
            raise RegistryError("Parameter is outside its declared range")
        return _canonical_value(value, self.kind)


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    identity: StrategyIdentity
    parameters: tuple[ParameterRule, ...]

    def __post_init__(self):
        if type(self.identity) is not StrategyIdentity:
            raise RegistryError("Definition requires a strategy identity")
        try:
            replace(self.identity)
        except (StrategyContractError, TypeError, ValueError):
            raise RegistryError("Definition identity is invalid") from None
        if (type(self.parameters) is not tuple or len(self.parameters) > 32
                or any(type(rule) is not ParameterRule for rule in self.parameters)):
            raise RegistryError("Definition rules must be an immutable bounded tuple")
        for rule in self.parameters:
            replace(rule)
        if len({rule.name for rule in self.parameters}) != len(self.parameters):
            raise RegistryError("Duplicate parameter name")
        object.__setattr__(self, "parameters",
                           tuple(sorted(self.parameters, key=lambda rule: rule.name)))


@dataclass(frozen=True, slots=True)
class StrategyConfiguration:
    definition: StrategyDefinition
    values: tuple[tuple[str, int | str], ...]

    def __post_init__(self):
        if type(self.definition) is not StrategyDefinition:
            raise RegistryError("Configuration requires a validated definition")
        replace(self.definition)
        if (type(self.values) is not tuple
                or any(type(pair) is not tuple or len(pair) != 2
                       or type(pair[0]) is not str for pair in self.values)):
            raise RegistryError("Configuration values must be immutable pairs")
        names = [name for name, _ in self.values]
        rules = {rule.name: rule for rule in self.definition.parameters}
        if len(set(names)) != len(names) or set(names) != set(rules):
            raise RegistryError("Unknown, duplicate or missing parameter")
        normalized = tuple(sorted((name, rules[name].validate(value))
                                  for name, value in self.values))
        object.__setattr__(self, "values", normalized)

    def to_json(self):
        replace(self)
        payload = {
            "schema_version": 1,
            "strategy_id": self.definition.identity.strategy_id,
            "strategy_version": self.definition.identity.version,
            "rules": [
                {"name": rule.name, "kind": rule.kind,
                 "minimum": rule.minimum, "maximum": rule.maximum}
                for rule in self.definition.parameters
            ],
            "parameters": dict(self.values),
            "policy": {"paper_only": True, "live_master_lock": "OFF",
                       "spot_only": True, "allow_short": False, "allow_leverage": False},
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"

    @property
    def sha256(self):
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StrategyRegistry:
    definitions: tuple[StrategyDefinition, ...]

    def __post_init__(self):
        if (type(self.definitions) is not tuple or len(self.definitions) > 128
                or any(type(item) is not StrategyDefinition for item in self.definitions)):
            raise RegistryError("Registry requires an immutable bounded definition tuple")
        seen = set()
        for definition in self.definitions:
            replace(definition)
            key = (definition.identity.strategy_id, definition.identity.version)
            if key in seen:
                raise RegistryError("Duplicate strategy ID/version")
            seen.add(key)
        object.__setattr__(self, "definitions", tuple(sorted(
            self.definitions, key=lambda item: (item.identity.strategy_id, item.identity.version))))

    def configure(self, identity, parameters):
        replace(self)
        if type(identity) is not StrategyIdentity or type(parameters) is not dict:
            raise RegistryError("Configuration request is invalid")
        for definition in self.definitions:
            if definition.identity == identity:
                return StrategyConfiguration(definition, tuple(parameters.items()))
        raise RegistryError("Strategy ID/version is not registered")
