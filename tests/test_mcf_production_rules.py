import unittest

from research.mass_candidate_factory.production_features import ProductionBars, ProductionFeatureCache
from research.mass_candidate_factory.production_generator import generate, freeze_executable_generation
from research.mass_candidate_factory.production_rules import (
    BLOCKED_FAMILIES,
    ProductionRuleBlocked,
    compile_candidate,
    implementation_audit,
)

START = 1577836800000
HOUR = 3_600_000


def cache(symbol="AAAUSDT", rows=300):
    times = tuple(START + i * HOUR for i in range(rows))
    closes = tuple(100.0 + (i % 20) * 0.1 + i * 0.01 for i in range(rows))
    b = ProductionBars(
        dataset_id="SYNTHETIC-" + symbol,
        symbol=symbol,
        timeframe="1h",
        times=times,
        opens=closes,
        highs=tuple(x + 1 for x in closes),
        lows=tuple(x - 1 for x in closes),
        closes=closes,
        base_volume=tuple(100.0 + (i % 7) * 10 for i in range(rows)),
        quote_volume=tuple(10_000.0 + (i % 11) * 100 for i in range(rows)),
        trade_count=tuple(100.0 + (i % 5) * 5 for i in range(rows)),
    )
    return ProductionFeatureCache(b)


def candidate(family, params, timeframe="1h"):
    return {
        "candidate_id": "TEST-" + family,
        "candidate_spec_sha256": "a" * 64,
        "family": family,
        "family_id": "FAM-" + family,
        "economic_mechanism_id": family,
        "timeframe": timeframe,
        "parameter_vector": params,
        "free_parameter_dimensions": len(params),
        "state": "PRE_OUTCOME_REGISTERED",
    }


class ProductionRulesTest(unittest.TestCase):
    def test_exact_trend_rule_compiles_deterministically(self):
        c = cache()
        row = candidate("TREND_CROSSOVER", {"fast_window": 4, "slow_window": 24})
        a = compile_candidate(row, c)
        b = compile_candidate(row, c)
        self.assertEqual(a, b)
        self.assertEqual(len(a.desired_state), len(c.bars.times))
        self.assertEqual(a.timeframe, "1h")

    def test_blocked_families_fail_before_performance(self):
        c = cache()
        for family in BLOCKED_FAMILIES:
            with self.assertRaises(ProductionRuleBlocked):
                compile_candidate(candidate(family, {}), c)

    def test_full_implementation_audit_and_executable_freeze(self):
        generated = generate()
        audit = implementation_audit(generated["valid"])
        self.assertEqual(audit["status"], "PASS_WITH_IMPLEMENTATION_BLOCKERS")
        self.assertEqual(dict(audit["blocked_families"]), BLOCKED_FAMILIES)
        self.assertEqual(audit["executable_candidate_count"], 6852)
        self.assertEqual(len(dict(audit["executable_family_counts"])), 10)
        self.assertFalse(audit["performance_read"])

        frozen = freeze_executable_generation(BLOCKED_FAMILIES)
        self.assertEqual(frozen["summary"]["pre_block_structurally_valid_count"], 8640)
        self.assertEqual(frozen["summary"]["blocked_implementation_count"], 1788)
        self.assertEqual(frozen["summary"]["executable_candidate_count"], 6852)
        self.assertEqual(len(frozen["registered_candidates"]), 6852)
        self.assertEqual(len(frozen["neighbor_graph"]["graph"]), 6852)
        self.assertFalse(frozen["summary"]["safety"]["performance_read"])

    def test_lead_lag_peer_target_is_not_silently_same_asset(self):
        c = cache("BTCUSDT")
        row = candidate(
            "LEAD_LAG",
            {
                "peer": "BTCUSDT",
                "lag_bars": 1,
                "peer_return_threshold": "0.0025",
                "response_mode": "MOMENTUM",
            },
        )
        result = compile_candidate(row, c)
        self.assertFalse(any(result.feature_available))
        self.assertFalse(any(result.desired_state))


if __name__ == "__main__":
    unittest.main()
