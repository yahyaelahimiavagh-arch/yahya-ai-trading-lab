import unittest

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_generator import (
    DOMAIN_PLAN_SHA256,
    SEARCH_BUDGET_SHA256,
    UNIVERSE_POLICY_SHA256,
    build_neighbor_graph,
    generate,
    structural_pass,
)


class ProductionGeneratorTest(unittest.TestCase):
    def test_frozen_domain_reconciles_before_performance(self):
        a = generate()
        b = generate()
        self.assertEqual(a, b)
        summary = a["summary"]
        self.assertEqual(summary["raw_candidate_count"], 9176)
        self.assertEqual(summary["structurally_valid_count"], 8640)
        self.assertEqual(summary["structurally_invalid_count"], 536)
        self.assertEqual(summary["domain_plan_sha256"], DOMAIN_PLAN_SHA256)
        self.assertEqual(summary["search_budget_sha256"], SEARCH_BUDGET_SHA256)
        self.assertEqual(summary["universe_policy_sha256"], UNIVERSE_POLICY_SHA256)
        self.assertEqual(len(a["registered_candidates"]), 8640)
        self.assertFalse(summary["safety"]["performance_read"])
        counts = dict(summary["family_valid_counts"])
        self.assertEqual(counts["CRASH_REBOUND"], 1536)
        self.assertEqual(counts["TREND_CROSSOVER"], 116)
        self.assertEqual(counts["BREAKOUT_CHANNEL"], 416)

    def test_neighbor_graph_is_deterministic_and_pre_outcome(self):
        generated = generate()
        a = build_neighbor_graph(generated["valid"])
        b = build_neighbor_graph(generated["valid"])
        self.assertEqual(a, b)
        self.assertEqual(len(a["graph"]), 8640)
        by_id = {x["candidate_id"]: x for x in generated["valid"]}
        for cid, neighbors in list(a["graph"].items())[:100]:
            for neighbor in neighbors:
                self.assertEqual(by_id[cid]["family"], by_id[neighbor]["family"])
                self.assertEqual(by_id[cid]["timeframe"], by_id[neighbor]["timeframe"])

    def test_constraint_parser_is_closed(self):
        self.assertTrue(structural_pass("fast_window < slow_window", {"fast_window": 4, "slow_window": 24}))
        self.assertTrue(structural_pass(
            "session_start_utc + session_length_hours <= 24",
            {"session_start_utc": 12, "session_length_hours": 8},
        ))
        with self.assertRaises(MCFError):
            structural_pass("__import__('os').system('true') == 0", {})


if __name__ == "__main__":
    unittest.main()
