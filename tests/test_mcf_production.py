import unittest

from research.mass_candidate_factory.models import MCFError, digest
from research.mass_candidate_factory.production import (
    DEVELOPMENT_START_MS,
    FrozenCandidateBinding,
    MembershipSnapshot,
    PreOutcomeFreeze,
    ProductionCostPolicy,
    ProductionSeries,
    ProductionUniverseBinding,
    freeze_digest,
    run_candidate,
    _simulate,
)


H = "a" * 64
S = "b" * 64
F = "c" * 64


def binding(*snapshots):
    return ProductionUniverseBinding(
        universe_evidence_id="MCF-PROD-001-UNIVERSE-EVIDENCE",
        population_manifest_sha256=H,
        quality_index_sha256=S,
        universe_policy_sha256=F,
        membership_snapshots=tuple(snapshots),
    )


def candidate_binding():
    return FrozenCandidateBinding(
        candidate_id="MCF-TEST-000001",
        candidate_spec_sha256=H,
        family_id="FAM-TEST",
        economic_mechanism_id="MECH-TEST",
        family_spec_sha256=S,
        parameter_neighbor_ids=(),
        neighbor_graph_sha256=F,
        free_parameter_dimensions=2,
    )


def freeze_for(b):
    cost = ProductionCostPolicy()
    binding_sha, cost_sha = freeze_digest(b, cost)
    registered = (("MCF-TEST-000001", H),)
    return PreOutcomeFreeze(
        batch_id="MCF-PROD-001",
        registered_candidates=registered,
        candidate_ledger_sha256=digest([
            {"candidate_id": "MCF-TEST-000001", "candidate_spec_sha256": H}
        ]),
        family_manifest_sha256s=(S,),
        neighbor_graph_sha256=F,
        evidence_binding_sha256=binding_sha,
        cost_policy_sha256=cost_sha,
    )


class ProductionRunnerTest(unittest.TestCase):
    def test_next_bar_only_and_gap_cancellation(self):
        snap = MembershipSnapshot(DEVELOPMENT_START_MS, ("BTCUSDT",), H)
        b = binding(snap)
        day = 86_400_000
        series = ProductionSeries(
            "BTCUSDT", "1d",
            (DEVELOPMENT_START_MS, DEVELOPMENT_START_MS + 2 * day),
            ("100", "110"), ("101", "111"),
            (True, False), (True, True),
        )
        result = _simulate(series, b, ProductionCostPolicy(), stress=False)
        self.assertEqual(result["fills"], 0)
        self.assertEqual(result["source_gap_cancellations"], 1)

    def test_membership_loss_forces_next_observed_exit(self):
        mar = DEVELOPMENT_START_MS
        apr = 1585699200000
        b = binding(
            MembershipSnapshot(mar, ("BTCUSDT",), H),
            MembershipSnapshot(apr, ("ETHUSDT",), S),
        )
        day = 86_400_000
        times = (apr - 2 * day, apr - day, apr, apr + day)
        series = ProductionSeries(
            "BTCUSDT", "1d", times,
            ("100", "101", "102", "103"), ("100", "101", "102", "103"),
            (True, True, True, False), (True, True, True, True),
        )
        result = _simulate(series, b, ProductionCostPolicy(), stress=False)
        self.assertEqual(result["fills"], 2)
        self.assertEqual(result["completed_trades"], 1)
        self.assertEqual(result["forced_membership_exits"], 1)

    def test_membership_leave_and_reentry_across_gap_forces_exit(self):
        mar = DEVELOPMENT_START_MS
        apr = 1585699200000
        may = 1588291200000
        b = binding(
            MembershipSnapshot(mar, ("BTCUSDT",), H),
            MembershipSnapshot(apr, ("ETHUSDT",), S),
            MembershipSnapshot(may, ("BTCUSDT",), F),
        )
        day = 86_400_000
        times = (apr - 2 * day, apr - day, may, may + day)
        series = ProductionSeries(
            "BTCUSDT", "1d", times,
            ("100", "101", "120", "121"), ("100", "101", "120", "121"),
            (True, True, True, False), (True, True, True, True),
        )
        result = _simulate(series, b, ProductionCostPolicy(), stress=False)
        self.assertEqual(result["completed_trades"], 1)
        self.assertEqual(result["forced_membership_exits"], 1)
        self.assertIn(may // day, result["forced_exit_days"])

    def test_daily_return_mask_does_not_bridge_missing_source_day(self):
        snap = MembershipSnapshot(DEVELOPMENT_START_MS, ("BTCUSDT",), H)
        b = binding(snap)
        f = freeze_for(b)
        day = 86_400_000
        series = ProductionSeries(
            "BTCUSDT", "1d",
            (
                DEVELOPMENT_START_MS,
                DEVELOPMENT_START_MS + 2 * day,
                DEVELOPMENT_START_MS + 3 * day,
            ),
            ("100", "100", "100"), ("100", "100", "100"),
            (False, False, False), (True, True, True),
        )
        result = run_candidate(
            candidate=candidate_binding(),
            freeze=f,
            binding=b,
            series_by_symbol={"BTCUSDT": series},
        )
        mask = result["daily_return_series"]["valid_mask"]
        self.assertEqual(mask[:4], (True, False, False, True))

    def test_public_runner_requires_pre_outcome_freeze(self):
        snap = MembershipSnapshot(DEVELOPMENT_START_MS, ("BTCUSDT",), H)
        b = binding(snap)
        f = freeze_for(b)
        day = 86_400_000
        series = ProductionSeries(
            "BTCUSDT", "1d",
            (DEVELOPMENT_START_MS, DEVELOPMENT_START_MS + day, DEVELOPMENT_START_MS + 2 * day),
            ("100", "101", "102"), ("100", "101", "102"),
            (True, False, False), (True, True, True),
        )
        result = run_candidate(
            candidate=candidate_binding(),
            freeze=f,
            binding=b,
            series_by_symbol={"BTCUSDT": series},
        )
        self.assertEqual(result["candidate_id"], "MCF-TEST-000001")
        self.assertEqual(result["evidence_partition"], "DEVELOPMENT")
        self.assertEqual(result["f0_f3_state"], "DEVELOPMENT_FAIL")
        self.assertFalse(result["safety"]["fresh_oos_read"])
        self.assertFalse(result["safety"]["p10_read"])
        self.assertEqual(result, run_candidate(
            candidate=candidate_binding(),
            freeze=f,
            binding=b,
            series_by_symbol={"BTCUSDT": series},
        ))
        with self.assertRaises(MCFError):
            run_candidate(
                candidate=FrozenCandidateBinding(
                    candidate_id="MCF-TEST-999999",
                    candidate_spec_sha256=H,
                    family_id="FAM-TEST",
                    economic_mechanism_id="MECH-TEST",
                    family_spec_sha256=S,
                    parameter_neighbor_ids=(),
                    neighbor_graph_sha256=F,
                    free_parameter_dimensions=2,
                ),
                freeze=f,
                binding=b,
                series_by_symbol={"BTCUSDT": series},
            )

    def test_runtime_binding_change_fails_closed(self):
        b = binding(MembershipSnapshot(DEVELOPMENT_START_MS, ("BTCUSDT",), H))
        f = freeze_for(b)
        changed = ProductionUniverseBinding(
            universe_evidence_id=b.universe_evidence_id,
            population_manifest_sha256=b.population_manifest_sha256,
            quality_index_sha256=b.quality_index_sha256,
            universe_policy_sha256="d" * 64,
            membership_snapshots=b.membership_snapshots,
        )
        day = 86_400_000
        series = ProductionSeries(
            "BTCUSDT", "1d",
            (DEVELOPMENT_START_MS, DEVELOPMENT_START_MS + day),
            ("100", "101"), ("100", "101"),
            (False, False), (True, True),
        )
        with self.assertRaises(MCFError):
            run_candidate(
                candidate=candidate_binding(),
                freeze=f,
                binding=changed,
                series_by_symbol={"BTCUSDT": series},
            )


if __name__ == "__main__":
    unittest.main()
