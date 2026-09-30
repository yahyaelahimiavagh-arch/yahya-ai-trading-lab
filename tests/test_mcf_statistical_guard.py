import unittest

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_generator import freeze_executable_generation
from research.mass_candidate_factory.production_rules import BLOCKED_FAMILIES
from research.mass_candidate_factory.statistical_guard_cli import build_manifest
from research.mass_candidate_factory.statistical_guard import (
    build_preoutcome_multiplicity_manifest,
    deflated_sharpe_probability,
    expected_maximum_sharpe,
    fdr_adjust,
    one_sided_sharpe_p_value,
    pbo_cscv,
    periodic_sharpe,
    probabilistic_sharpe_ratio,
)


class StatisticalMultiplicityGuardTest(unittest.TestCase):
    def test_by_is_not_less_conservative_than_bh(self):
        p = {
            "A": 0.001,
            "B": 0.012,
            "C": 0.018,
            "D": 0.040,
            "E": 0.300,
        }
        bh = {x.candidate_id: x for x in fdr_adjust(p, alpha=0.05, method="BH")}
        by = {x.candidate_id: x for x in fdr_adjust(p, alpha=0.05, method="BY")}
        for candidate_id in p:
            self.assertGreaterEqual(
                by[candidate_id].adjusted_p_value,
                bh[candidate_id].adjusted_p_value,
            )
            if by[candidate_id].rejected:
                self.assertTrue(bh[candidate_id].rejected)

    def test_fdr_is_deterministic_under_input_order(self):
        first = fdr_adjust({"Z": 0.02, "A": 0.02, "M": 0.001}, method="BY")
        second = fdr_adjust({"M": 0.001, "A": 0.02, "Z": 0.02}, method="BY")
        self.assertEqual(first, second)

    def test_fdr_rejects_invalid_probability(self):
        with self.assertRaises(MCFError):
            fdr_adjust({"A": -0.1})
        with self.assertRaises(MCFError):
            fdr_adjust({})

    def test_probabilistic_sharpe_separates_positive_and_negative_series(self):
        positive = (0.012, 0.010, 0.011, 0.009, 0.013, 0.008, 0.012, 0.010)
        negative = tuple(-x for x in positive)
        self.assertGreater(periodic_sharpe(positive), 0)
        self.assertLess(periodic_sharpe(negative), 0)
        self.assertGreater(probabilistic_sharpe_ratio(positive), 0.95)
        self.assertLess(probabilistic_sharpe_ratio(negative), 0.05)
        self.assertLess(one_sided_sharpe_p_value(positive), 0.05)

    def test_zero_variance_sharpe_fails_closed(self):
        with self.assertRaises(MCFError):
            periodic_sharpe((0.01,) * 8)

    def test_expected_maximum_sharpe_rises_with_trial_count(self):
        trial_sharpes = (-0.3, -0.1, 0.0, 0.2, 0.4, 0.6)
        small = expected_maximum_sharpe(
            trial_sharpes,
            conservative_trial_count=len(trial_sharpes),
        )
        large = expected_maximum_sharpe(
            trial_sharpes,
            conservative_trial_count=6852,
        )
        self.assertGreater(large, small)

    def test_dsr_records_conservative_trial_count(self):
        values = (
            0.020, 0.010, -0.004, 0.013, 0.008, -0.002,
            0.015, 0.006, 0.011, -0.003, 0.014, 0.009,
        )
        trial_sharpes = (-0.2, -0.1, 0.0, 0.1, 0.2, 0.3)
        result = deflated_sharpe_probability(
            values,
            trial_sharpes=trial_sharpes,
            conservative_trial_count=6852,
        )
        self.assertEqual(result["conservative_trial_count"], 6852)
        self.assertGreaterEqual(result["dsr_probability"], 0.0)
        self.assertLessEqual(result["dsr_probability"], 1.0)
        self.assertGreater(result["deflated_null_sharpe"], 0.0)

    def test_trial_count_cannot_be_shrunk_below_observed_trials(self):
        with self.assertRaises(MCFError):
            expected_maximum_sharpe(
                (-0.2, 0.0, 0.2, 0.4),
                conservative_trial_count=3,
            )

    def test_cscv_pbo_stable_winner_is_zero(self):
        panel = {
            "A": (0.020, 0.010, 0.020, 0.010, 0.020, 0.010, 0.020, 0.010),
            "B": (0.010, 0.000, 0.010, 0.000, 0.010, 0.000, 0.010, 0.000),
            "C": (0.030, -0.030, 0.030, -0.030, 0.030, -0.030, 0.030, -0.030),
        }
        result = pbo_cscv(panel, block_count=4)
        self.assertEqual(result["split_count"], 6)
        self.assertEqual(result["pbo"], 0.0)
        self.assertEqual(result["selected_candidate_counts"], (("A", 6),))

    def test_cscv_requires_rectangular_pre_registered_blocks(self):
        with self.assertRaises(MCFError):
            pbo_cscv(
                {
                    "A": (0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01),
                    "B": (0.01, 0.00, 0.01, 0.00, 0.01, 0.00),
                },
                block_count=4,
            )
        with self.assertRaises(MCFError):
            pbo_cscv(
                {
                    "A": (0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01),
                    "B": (0.01, 0.00, 0.01, 0.00, 0.01, 0.00, 0.01, 0.00, 0.01, 0.00),
                },
                block_count=4,
            )

    def test_preoutcome_manifest_reads_metadata_only(self):
        executable = (
            {
                "candidate_id": "MCF-PROD-001-000001",
                "family": "TREND",
                "economic_mechanism_id": "MOMENTUM",
                "timeframe": "15m",
                "free_parameter_dimensions": 2,
                "parameter_neighbor_ids": ("MCF-PROD-001-000002",),
            },
            {
                "candidate_id": "MCF-PROD-001-000002",
                "family": "TREND",
                "economic_mechanism_id": "MOMENTUM",
                "timeframe": "1h",
                "free_parameter_dimensions": 2,
                "parameter_neighbor_ids": ("MCF-PROD-001-000001",),
            },
            {
                "candidate_id": "MCF-PROD-001-000003",
                "family": "MEAN_REVERSION",
                "economic_mechanism_id": "REVERSION",
                "timeframe": "4h",
                "free_parameter_dimensions": 3,
                "parameter_neighbor_ids": (),
            },
        )
        graph = {
            "MCF-PROD-001-000001": ("MCF-PROD-001-000002",),
            "MCF-PROD-001-000002": ("MCF-PROD-001-000001",),
            "MCF-PROD-001-000003": (),
        }
        result = build_preoutcome_multiplicity_manifest(
            executable,
            neighbor_graph=graph,
            expected_candidate_count=3,
        )
        self.assertEqual(result["state"], "PRE_OUTCOME_MULTIPLICITY_FROZEN")
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["conservative_trial_count"], 3)
        self.assertEqual(result["default_fdr_method"], "BY")
        self.assertEqual(result["directed_parameter_neighbor_edge_count"], 2)
        self.assertFalse(result["performance_read"])
        self.assertFalse(result["fresh_oos_read"])
        self.assertFalse(result["p10_read"])
        self.assertEqual(len(result["manifest_sha256"]), 64)

    def test_preoutcome_manifest_rejects_duplicate_candidate(self):
        row = {
            "candidate_id": "X",
            "family": "TREND",
            "economic_mechanism_id": "MOMENTUM",
            "timeframe": "15m",
            "free_parameter_dimensions": 1,
            "parameter_neighbor_ids": (),
        }
        with self.assertRaises(MCFError):
            build_preoutcome_multiplicity_manifest(
                (row, dict(row)),
                neighbor_graph={"X": ()},
            )


    def test_real_frozen_generation_builds_exact_preoutcome_manifest(self):
        frozen = freeze_executable_generation(BLOCKED_FAMILIES)
        self.assertEqual(frozen["summary"]["executable_candidate_count"], 6852)
        manifest = build_manifest()
        self.assertEqual(manifest["candidate_count"], 6852)
        self.assertEqual(manifest["conservative_trial_count"], 6852)
        self.assertEqual(
            manifest["candidate_ledger_sha256"],
            frozen["summary"]["candidate_ledger_sha256"],
        )
        self.assertEqual(
            manifest["neighbor_graph_sha256"],
            frozen["summary"]["neighbor_graph_sha256"],
        )
        self.assertGreater(manifest["directed_parameter_neighbor_edge_count"], 0)
        self.assertFalse(manifest["performance_read"])
        self.assertFalse(manifest["fresh_oos_read"])
        self.assertFalse(manifest["p10_read"])
        self.assertFalse(manifest["live_authorized"])


if __name__ == "__main__":
    unittest.main()
