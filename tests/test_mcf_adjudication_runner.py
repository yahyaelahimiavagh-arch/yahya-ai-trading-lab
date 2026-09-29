import unittest

from research.mass_candidate_factory.adjudication_runner import adjudicate
from research.mass_candidate_factory.models import digest


def candidate(i):
    return {
        "candidate_id": f"C{i}",
        "candidate_spec_sha256": (str(i + 1) * 64)[:64],
        "family_id": "FAM",
        "family": "FAM",
        "economic_mechanism_id": "MECH",
        "free_parameter_dimensions": 2,
    }


def result(c, state, returns=None):
    daily = returns if returns is not None else [0.0] * 80
    body = {
        "candidate_id": c["candidate_id"],
        "candidate_spec_sha256": c["candidate_spec_sha256"],
        "family_id": c["family_id"],
        "economic_mechanism_id": c["economic_mechanism_id"],
        "evidence_partition": "DEVELOPMENT",
        "f0_f3_state": state,
        "aggregate_stress_net_return": "0.10" if state == "F0_F3_PASS" else "-0.01",
        "median_symbol_stress_net_return": "0.02",
        "fold_stress_returns": ("0.01",) * 6,
        "maximum_normalized_drawdown": "0.05",
        "mean_turnover": "1.0",
        "exact_accounting": True,
        "daily_return_series": {
            "calendar_days": tuple(range(len(daily))),
            "returns": tuple(str(x) for x in daily),
            "valid_mask": (True,) * len(daily),
        },
    }
    return {**body, "result_sha256": digest(body)}


def graph(candidates):
    ids = tuple(c["candidate_id"] for c in candidates)
    mapping = {
        cid: tuple(other for other in ids if other != cid)
        for cid in ids
    }
    body = {"schema": "MCF_PRODUCTION_NEIGHBOR_GRAPH/1.0.0", "graph": mapping}
    return {**body, "neighbor_graph_sha256": digest(body)}


class AdjudicationRunnerTest(unittest.TestCase):
    def test_zero_f0_f3_passers_is_valid_terminal_outcome(self):
        candidates = tuple(candidate(i) for i in range(4))
        results = tuple(result(c, "DEVELOPMENT_FAIL") for c in candidates)
        out = adjudicate(
            production_results=results,
            executable_candidates=candidates,
            neighbor_graph_artifact=graph(candidates),
        )
        self.assertEqual(out["state"], "ZERO_SURVIVOR_VALID")
        self.assertEqual(out["development_survivor_count"], 0)
        self.assertIsNotNone(out["trial_accounting"])
        self.assertEqual(out["trial_accounting"]["raw_generation_trials"], 4)
        self.assertEqual(out["trial_accounting"]["raw_family_trials"], (("FAM", 4),))
        self.assertEqual(out["trial_accounting"]["raw_mechanism_trials"], (("MECH", 4),))
        self.assertFalse(out["safety"]["fresh_oos_read"])
        self.assertFalse(out["safety"]["p10_read"])

    def test_f4_failure_cannot_be_rescued_by_statistics(self):
        candidates = tuple(candidate(i) for i in range(4))
        positive = [0.01 + ((i % 5) - 2) * 0.0002 for i in range(80)]
        results = (
            result(candidates[0], "F0_F3_PASS", positive),
            result(candidates[1], "DEVELOPMENT_FAIL"),
            result(candidates[2], "DEVELOPMENT_FAIL"),
            result(candidates[3], "DEVELOPMENT_FAIL"),
        )
        out = adjudicate(
            production_results=results,
            executable_candidates=candidates,
            neighbor_graph_artifact=graph(candidates),
        )
        self.assertEqual(out["state"], "ZERO_SURVIVOR_VALID")
        self.assertFalse(out["f4"][0]["f4_pass"])
        self.assertEqual(out["f5"], ())
        self.assertEqual(out["representatives_pending_reality_review"], ())


if __name__ == "__main__":
    unittest.main()
