"""Synthetic-only exact parity for the isolated MCF replay-mark lifetime change.

No real market input, FrozenRunnerInput, benchmark candidate or VPS is used.
The oracle is the preserved PR186 _simulate source at the prechange merge commit.
"""
import unittest
from unittest.mock import patch

from mcf_replay_marks_baseline import baseline_simulate
from research.mass_candidate_factory.models import canonical, digest
from research.mass_candidate_factory import production as prod


H = "a" * 64
S = "b" * 64
F = "c" * 64
DAY = prod.DAY_MS
MAR = prod.DEVELOPMENT_START_MS
APR = 1585699200000
MAY = 1588291200000


def synthetic_binding():
    return prod.ProductionUniverseBinding(
        universe_evidence_id=prod.UNIVERSE_EVIDENCE_ID,
        population_manifest_sha256=H,
        quality_index_sha256=S,
        universe_policy_sha256=F,
        membership_snapshots=(
            prod.MembershipSnapshot(MAR, ("AAAUSDT", "BBBUSDT"), H),
            prod.MembershipSnapshot(APR, ("BBBUSDT",), S),
            prod.MembershipSnapshot(MAY, ("AAAUSDT", "BBBUSDT"), F),
        ),
    )


def synthetic_series(symbol, *, variant=0):
    # Gap over a signalled next bar; member->nonmember on APR and reentry on MAY.
    times = (MAR, MAR + DAY, MAR + 3 * DAY, APR - DAY, APR,
             APR + DAY, MAY, MAY + DAY, MAY + 2 * DAY, MAY + 3 * DAY)
    n = len(times)
    opens = tuple(str(100 + variant * 13 + i * 3) for i in range(n))
    closes = tuple(str(101 + variant * 13 + i * 3 + (i % 3)) for i in range(n))
    desired = (True, True, False, True, True, False, True, True, False, False)
    available = (True, True, True, True, True, False, True, True, True, True)
    return prod.ProductionSeries(
        symbol, "1d", times, opens, closes, desired, available
    )


def synthetic_contract(binding, policy):
    candidate = prod.FrozenCandidateBinding(
        candidate_id="MCF-TEST-REPLAY",
        candidate_spec_sha256=H,
        family_id="FAM-SYNTHETIC",
        economic_mechanism_id="SYNTHETIC-REPLAY",
        family_spec_sha256=S,
        parameter_neighbor_ids=(),
        neighbor_graph_sha256=F,
        free_parameter_dimensions=0,
    )
    binding_sha, cost_sha = prod.freeze_digest(binding, policy)
    freeze = prod.PreOutcomeFreeze(
        batch_id="MCF-PROD-001",
        registered_candidates=((candidate.candidate_id, candidate.candidate_spec_sha256),),
        candidate_ledger_sha256=digest([
            {"candidate_id": candidate.candidate_id, "candidate_spec_sha256": candidate.candidate_spec_sha256}
        ]),
        family_manifest_sha256s=(S,),
        neighbor_graph_sha256=F,
        evidence_binding_sha256=binding_sha,
        cost_policy_sha256=cost_sha,
    )
    return candidate, freeze


class ReplayMarksLifetimeParityTest(unittest.TestCase):
    def test_exact_legacy_parity_of_simulated_marks_and_economics(self):
        binding = synthetic_binding()
        prices = [
            synthetic_series("AAAUSDT"),
            synthetic_series("BBBUSDT", variant=1),
            prod.ProductionSeries(
                "AAAUSDT", "1d", (MAR - 2 * DAY, MAR - DAY),
                ("100", "100"), ("100", "100"),
                (False, False), (True, True),
            ),
        ]
        policies = (
            prod.ProductionCostPolicy(),
            prod.ProductionCostPolicy(
                base_fee_bps="13", base_slippage_bps="7",
                stress_fee_bps="27", stress_slippage_bps="15",
            ),
        )
        for series in prices:
            for policy in policies:
                for stress in (False, True):
                    with self.subTest(symbol=series.symbol, n=len(series.times),
                                      fees=policy.base_fee_bps, stress=stress):
                        old = baseline_simulate(series, binding, policy, stress=stress)
                        new = prod._simulate(series, binding, policy, stress=stress)
                        self.assertEqual(old, new)
                        self.assertEqual(canonical(old), canonical(new))
                        self.assertEqual(digest(old), digest(new))

    def test_exact_complete_candidate_result_digest_under_synthetic_contract(self):
        binding = synthetic_binding()
        policy = prod.ProductionCostPolicy()
        candidate, freeze = synthetic_contract(binding, policy)
        series = {
            "AAAUSDT": synthetic_series("AAAUSDT"),
            "BBBUSDT": synthetic_series("BBBUSDT", variant=2),
        }
        args = dict(candidate=candidate, freeze=freeze, binding=binding,
                    series_by_symbol=series, cost_policy=policy)
        with patch.object(prod, "_simulate", baseline_simulate):
            old = prod.run_candidate(**args)
        new = prod.run_candidate(**args)
        self.assertEqual(old, new)
        self.assertEqual(canonical(old), canonical(new))
        self.assertEqual(old["result_sha256"], new["result_sha256"])
        self.assertTrue(new["safety"]["paper_research_only"])
        self.assertFalse(new["safety"]["p10_read"])
        self.assertFalse(new["safety"]["p10_write"])
        self.assertTrue(new["safety"]["p11_locked"])


if __name__ == "__main__":
    unittest.main()
