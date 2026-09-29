import unittest

from mcf_fixtures import family
from research.mass_candidate_factory.adjudication import (
    DailySeries,
    TrialAccounting,
    build_neighbor_graph,
    common_factor_clusters,
    cscv_pbo,
    deflated_sharpe,
    effective_trial_count,
    freeze_survivor,
    neighbor_stability,
    reality_check,
    select_representative,
    statistical_gate,
)
from research.mass_candidate_factory.generator import generate
from research.mass_candidate_factory.manifest import validate


def series(cid, values, family_id="FAM-1"):
    return DailySeries(
        candidate_id=cid,
        family_id=family_id,
        mechanism_id="MECH-1",
        calendar_days=tuple(range(len(values))),
        returns=tuple(values),
        valid_mask=(True,) * len(values),
    )


class AdjudicationTest(unittest.TestCase):
    def test_neighbor_graph_is_pre_outcome_and_deterministic(self):
        manifest = family()
        sha = validate(manifest)
        _, candidates, _ = generate([manifest], batch_id="CAL-001")
        a = build_neighbor_graph(candidates, {sha: manifest})
        b = build_neighbor_graph(candidates, {sha: manifest})
        self.assertEqual(a, b)
        self.assertEqual(set(a["graph"]), {c["candidate_id"] for c in candidates})
        cid = candidates[0]["candidate_id"]
        outcome = neighbor_stability(
            cid,
            a["graph"],
            set(a["graph"]),
            {x: 0.01 for x in a["graph"]},
        )
        self.assertIn("f4_pass", outcome)

    def test_neighbor_stability_median_uses_all_valid_neighbors(self):
        graph = {"A": ("B", "C", "D", "E")}
        outcome = neighbor_stability(
            "A",
            graph,
            {"B", "C"},
            {"B": 0.01, "C": 0.02, "D": -0.50, "E": -1.00},
        )
        self.assertEqual(outcome["passing_neighbor_fraction"], 0.5)
        self.assertLess(outcome["median_neighbor_stress_return"], 0.0)
        self.assertFalse(outcome["f4_pass"])

    def test_effective_trials_and_deflated_sharpe(self):
        values = [0.01 + ((i % 5) - 2) * 0.0005 for i in range(80)]
        a = series("A", values)
        b = series("B", [2.0 * x for x in values])
        eff = effective_trial_count([a, b])
        self.assertAlmostEqual(eff["effective_trials"], 1.0, places=9)
        dsr = deflated_sharpe(a, 1.0)
        self.assertEqual(dsr["state"], "PASS")
        self.assertGreaterEqual(dsr["confidence"], 0.95)

    def test_cscv_and_reality_check_are_deterministic(self):
        a = series("A", [0.004 + ((i % 7) - 3) * 0.0004 for i in range(80)])
        b = series("B", [0.002 * (1 if (i // 10) % 2 == 0 else -1) + (i % 3) * 0.0001 for i in range(80)])
        p1 = cscv_pbo([a, b])
        p2 = cscv_pbo([a, b])
        self.assertEqual(p1, p2)
        self.assertGreater(p1["split_count"], 0)
        self.assertGreaterEqual(p1["pbo"], 0.0)
        self.assertLessEqual(p1["pbo"], 1.0)

        r1 = reality_check([a, b], replications=64)
        r2 = reality_check([a, b], replications=64)
        self.assertEqual(r1, r2)
        self.assertEqual(r1["replications"], 64)

    def test_common_factor_cluster_and_representative_order(self):
        values = [0.001 + ((i % 5) - 2) * 0.0002 for i in range(50)]
        a = series("A", values)
        b = series("B", [3 * x for x in values])
        clusters = common_factor_clusters([a, b])
        self.assertEqual(clusters["clusters"], (("A", "B"),))
        metrics = {
            "A": {
                "median_symbol_stress_net_return": "0.02",
                "fold_stress_returns": ("0.01", "0.02"),
                "maximum_normalized_drawdown": "0.10",
                "mean_turnover": "1.0",
                "free_parameter_dimensions": 2,
            },
            "B": {
                "median_symbol_stress_net_return": "0.03",
                "fold_stress_returns": ("0.005", "0.02"),
                "maximum_normalized_drawdown": "0.09",
                "mean_turnover": "1.2",
                "free_parameter_dimensions": 2,
            },
        }
        self.assertEqual(select_representative(("A", "B"), metrics), "B")

    def test_statistical_gate_and_f7_freeze(self):
        values = [0.01 + ((i % 5) - 2) * 0.0005 for i in range(80)]
        a = series("A", values)
        accounting = TrialAccounting(
            raw_generation_trials=10,
            effective_generation_trials=2.0,
            raw_family_trials={"FAM-1": 5},
            effective_family_trials={"FAM-1": 1.5},
            raw_mechanism_trials={"MECH-1": 10},
            effective_mechanism_trials={"MECH-1": 2.0},
        )
        gate = statistical_gate(
            a,
            accounting,
            {"schema": "MCF_CSCV_PBO/1.0.0", "pbo": 0.10, "state": "PASS"},
        )
        self.assertTrue(gate["f5_pass"])

        hold = freeze_survivor(
            candidate_id="A",
            candidate_spec_sha256="a" * 64,
            universe_sha256="b" * 64,
            evidence_sha256="c" * 64,
            cost_sha256="d" * 64,
            statistical_artifact_sha256="e" * 64,
            exact_recomputed=True,
            reality_review_clear=False,
        )
        self.assertEqual(hold["state"], "HELD_FOR_DIRECTOR_REVIEW")

        frozen = freeze_survivor(
            candidate_id="A",
            candidate_spec_sha256="a" * 64,
            universe_sha256="b" * 64,
            evidence_sha256="c" * 64,
            cost_sha256="d" * 64,
            statistical_artifact_sha256="e" * 64,
            exact_recomputed=True,
            reality_review_clear=True,
        )
        self.assertEqual(frozen["state"], "DEVELOPMENT_SURVIVOR_FROZEN")
        self.assertFalse(frozen["safety"]["fresh_oos_opened"])


if __name__ == "__main__":
    unittest.main()
