import contextlib
import io
import json
import unittest
from unittest.mock import patch
from dataclasses import FrozenInstanceError, replace
from decimal import localcontext

from yatl.__main__ import main
from yatl.strategy import (ParameterRule, RegistryError, StrategyConfiguration,
                           StrategyDefinition, StrategyIdentity, StrategyRegistry)


def definition(version="1.0.0"):
    return StrategyDefinition(StrategyIdentity("RESEARCH_FIXTURE", version), (
        ParameterRule("lookback", "integer", 2, 200),
        ParameterRule("threshold", "decimal", "0", "1"),
    ))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.definition = definition()
        self.registry = StrategyRegistry((self.definition,))
        self.values = {"lookback": 20, "threshold": "0.0020"}

    def config(self, values=None):
        return self.registry.configure(self.definition.identity, self.values if values is None else values)

    def test_canonical_order_decimal_and_precision(self):
        first = self.config()
        other = replace(self.definition, parameters=tuple(reversed(self.definition.parameters)))
        replay = StrategyRegistry((other,)).configure(other.identity, {"threshold": "0.002", "lookback": 20})
        self.assertEqual(first.to_json(), replay.to_json())
        self.assertEqual(first.sha256, replay.sha256)
        with localcontext() as ctx:
            ctx.prec = 2
            exact = self.config({"lookback": 20, "threshold": "0.123456789012345678900"})
            self.assertEqual(dict(exact.values)["threshold"], "0.1234567890123456789")
        self.assertEqual(len(first.sha256), 64)

    def test_material_changes_change_hash(self):
        original = self.config().sha256
        self.assertNotEqual(original, self.config({"lookback": 21, "threshold": "0.002"}).sha256)
        for updated in (definition("1.0.1"), replace(self.definition, parameters=(
                ParameterRule("lookback", "integer", 2, 201),
                ParameterRule("threshold", "decimal", "0", "1")))):
            self.assertNotEqual(original, StrategyRegistry((updated,)).configure(updated.identity, self.values).sha256)

    def test_exact_types_and_ranges(self):
        for value in (True, 20.0, "20", -1, 1, 201, None):
            with self.subTest(value=value), self.assertRaises(RegistryError):
                self.config({"lookback": value, "threshold": "0.002"})
        for value in (True, 0.2, 0, "NaN", "Infinity", "1e-3", "-0.2", "1.01", "00.2", None):
            with self.subTest(value=value), self.assertRaises(RegistryError):
                self.config({"lookback": 20, "threshold": value})
        for value in ("0.00", "1.00"):
            self.config({"lookback": 2, "threshold": value})

    def test_unknown_missing_duplicate_parameters(self):
        for values in ({}, {"lookback": 20}, {**self.values, "extra": 1},
                       {**self.values, "live_master_lock": "ON"}):
            with self.assertRaises(RegistryError):
                self.config(values)
        with self.assertRaises(RegistryError):
            StrategyConfiguration(self.definition, (("lookback", 20), ("lookback", 20), ("threshold", "0")))

    def test_registration_identity_and_versions(self):
        with self.assertRaises(RegistryError):
            StrategyRegistry((self.definition, self.definition))
        other = definition("2.0.0")
        registry = StrategyRegistry((other, self.definition))
        self.assertNotEqual(registry.configure(other.identity, self.values).sha256, self.config().sha256)
        for identity in (StrategyIdentity("UNKNOWN", "1.0.0"), StrategyIdentity("RESEARCH_FIXTURE", "3.0.0"), None):
            with self.assertRaises(RegistryError):
                registry.configure(identity, self.values)

    def test_invalid_definitions_and_reserved_fields(self):
        for name in ("quantity", "broker", "api_secret", "order", "live_master_lock", "bad name"):
            with self.assertRaises(RegistryError):
                ParameterRule(name, "integer", 0, 1)
        for kind, low, high in (("integer", True, 10), ("integer", 2, 1),
                                ("integer", 0, 10001), ("decimal", "NaN", "1"),
                                ("decimal", "-1", "1"), ("text", 0, 1)):
            with self.assertRaises(RegistryError):
                ParameterRule("value", kind, low, high)
        with self.assertRaises(RegistryError):
            replace(self.definition, parameters=(self.definition.parameters[0],)*2)
        with self.assertRaises(RegistryError):
            StrategyRegistry([self.definition])

    def test_immutable_input_snapshot_and_fixed_policy(self):
        config = self.config()
        digest = config.sha256
        self.values["lookback"] = 30
        self.assertEqual(config.sha256, digest)
        with self.assertRaises(FrozenInstanceError):
            config.values = ()
        with self.assertRaises(FrozenInstanceError):
            self.definition.parameters[0].maximum = 300
        self.assertEqual(json.loads(config.to_json())["policy"], {
            "paper_only": True, "live_master_lock": "OFF", "spot_only": True,
            "allow_short": False, "allow_leverage": False})

    def test_tampered_invalid_config_fails_closed(self):
        config = self.config()
        object.__setattr__(config, "values", (("lookback", 9999), ("threshold", "0")))
        with self.assertRaises(RegistryError):
            config.to_json()

    def test_runtime_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("sys.argv", ["yatl", "strategy-registry-check"]):
            result = main()
        self.assertEqual(result, 0)
        self.assertIn("replay_equal=true changed_digest=true rejected=2", output.getvalue())
        self.assertIn("LIVE_MASTER_LOCK=OFF", output.getvalue())


if __name__ == "__main__":
    unittest.main()
