import unittest

from research.mass_candidate_factory.production_generator import (
    freeze_executable_generation,
    generate,
)
from research.mass_candidate_factory.production_rules import BLOCKED_FAMILIES


class MCFProd001PreOutcomeFreezeTest(unittest.TestCase):
    def test_generation_and_executable_identity_freeze(self):
        generated = generate()
        summary = generated["summary"]

        self.assertEqual(summary["raw_candidate_count"], 9176)
        self.assertEqual(summary["structurally_valid_count"], 8640)
        self.assertEqual(summary["structurally_invalid_count"], 536)
        self.assertEqual(
            summary["registered_candidate_ledger_sha256"],
            "ea53e211f7bce3ed5c3421c15a8538b4abd6a7b2151182443363a95d8c6b5505",
        )
        self.assertEqual(
            summary["summary_sha256"],
            "6b89457087d03f796802e1e6f71bb3b38129163d4bdce50dc0254cfd6baefaf6",
        )
        self.assertFalse(summary["safety"]["performance_read"])
        self.assertFalse(summary["safety"]["fresh_oos_read"])
        self.assertFalse(summary["safety"]["recent_reserve_read"])
        self.assertFalse(summary["safety"]["p10_read"])
        self.assertFalse(summary["safety"]["p10_write"])
        self.assertFalse(summary["safety"]["live"])

        frozen = freeze_executable_generation(BLOCKED_FAMILIES)
        fs = frozen["summary"]

        self.assertEqual(fs["pre_block_structurally_valid_count"], 8640)
        self.assertEqual(fs["blocked_implementation_count"], 1788)
        self.assertEqual(fs["executable_candidate_count"], 6852)
        self.assertEqual(
            fs["candidate_ledger_sha256"],
            "084150778f2270c2ce96dac631f2e0fb1e6f84fed3325a197a80aa3d59db8e73",
        )
        self.assertEqual(
            fs["neighbor_graph_sha256"],
            "4eb36ca827b5b458147e6ba2a74308353dfa047cd368d72e106f568b1f4fc4bb",
        )
        self.assertEqual(
            fs["freeze_sha256"],
            "364696a021d7d9371423cfed7fe832fc3d45886990f548f20317b882023ca634",
        )
        self.assertEqual(
            fs["executable_family_counts"],
            (
                ("BREAKOUT_CHANNEL", 416),
                ("LEAD_LAG", 288),
                ("LIQUIDITY_CONDITIONED_ENTRY", 240),
                ("PRICE_VOLUME_INTERACTION", 1200),
                ("SESSION_TIME_EFFECT", 600),
                ("SHORT_HORIZON_MEAN_REVERSION", 1240),
                ("SIMPLE_STATISTICAL_DEVIATION", 352),
                ("TRADE_COUNT_CONFIRMED_DIRECTION", 1200),
                ("TREND_CROSSOVER", 116),
                ("VOLUME_CONFIRMED_DIRECTION", 1200),
            ),
        )
        self.assertEqual(
            fs["blocked_families"],
            tuple(sorted(BLOCKED_FAMILIES.items())),
        )
        self.assertEqual(
            frozen["registered_candidates"][0],
            (
                "MCF-PROD-001-000000",
                "1e278262d3abf0809a8e269a460ee43136f06eab6744a2313e19087e352727b9",
            ),
        )
        self.assertEqual(
            frozen["registered_candidates"][-1],
            (
                "MCF-PROD-001-008815",
                "aa55a978bf91c8a16bf4cf95542a4bc327d4563067c8f937c61b9be50d569c0a",
            ),
        )
        self.assertFalse(fs["safety"]["performance_read"])
        self.assertFalse(fs["safety"]["fresh_oos_read"])
        self.assertFalse(fs["safety"]["recent_reserve_read"])
        self.assertFalse(fs["safety"]["p10_read"])
        self.assertFalse(fs["safety"]["p10_write"])
        self.assertFalse(fs["safety"]["live"])


if __name__ == "__main__":
    unittest.main()
