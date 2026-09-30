import unittest

from research.mass_candidate_factory.models import digest
from research.mass_candidate_factory.production import (
    DEVELOPMENT_START_MS,
    MembershipSnapshot,
    ProductionUniverseBinding,
)
from research.mass_candidate_factory.production_features import ProductionBars
from research.mass_candidate_factory.production_runtime import ProductionRuntime

H = "a" * 64
S = "b" * 64
HOUR = 3_600_000


def binding():
    return ProductionUniverseBinding(
        universe_evidence_id="MCF-PROD-001-UNIVERSE-EVIDENCE",
        population_manifest_sha256=H,
        quality_index_sha256=S,
        universe_policy_sha256=H,
        membership_snapshots=(
            MembershipSnapshot(DEVELOPMENT_START_MS, ("AAAUSDT", "BBBUSDT"), S),
        ),
    )


def bars(symbol):
    times = tuple(DEVELOPMENT_START_MS + i * HOUR for i in range(40))
    closes = tuple(100.0 + i * 0.1 for i in range(40))
    return ProductionBars(
        dataset_id="SYNTHETIC-" + symbol,
        symbol=symbol,
        timeframe="1h",
        times=times,
        opens=closes,
        highs=tuple(x + 1 for x in closes),
        lows=tuple(x - 1 for x in closes),
        closes=closes,
        base_volume=(100.0,) * 40,
        quote_volume=(10_000.0,) * 40,
        trade_count=(100.0,) * 40,
    )


def freeze_artifact():
    candidate = {
        "ordinal": 0,
        "candidate_id": "MCF-PROD-001-000000",
        "candidate_spec_sha256": H,
        "family_id": "MCF-P1-F01",
        "family": "TREND_CROSSOVER",
        "economic_mechanism_id": "TREND_CROSSOVER",
        "family_spec_sha256": S,
        "timeframe": "1h",
        "parameter_vector": {"fast_window": 4, "slow_window": 24},
        "free_parameter_dimensions": 2,
        "state": "PRE_OUTCOME_REGISTERED",
    }
    graph_body = {
        "schema": "MCF_PRODUCTION_NEIGHBOR_GRAPH/1.0.0",
        "graph": {candidate["candidate_id"]: ()},
    }
    graph = {**graph_body, "neighbor_graph_sha256": digest(graph_body)}
    registered = ((candidate["candidate_id"], candidate["candidate_spec_sha256"]),)
    ledger_sha = digest([
        {"candidate_id": candidate["candidate_id"], "candidate_spec_sha256": candidate["candidate_spec_sha256"]}
    ])
    return {
        "summary": {
            "state": "PRE_OUTCOME_EXECUTABLE_SET_FROZEN",
            "candidate_ledger_sha256": ledger_sha,
            "neighbor_graph_sha256": graph["neighbor_graph_sha256"],
            "family_spec_sha256s": (S,),
        },
        "registered_candidates": registered,
        "neighbor_graph": graph,
        "executable": (candidate,),
        "blocked": (),
    }


class ProductionRuntimeTest(unittest.TestCase):
    def test_canonical_runtime_wires_rule_universe_and_decimal_accounting(self):
        runtime = ProductionRuntime(
            synthetic_fixture=True,
            executable_freeze=freeze_artifact(),
            binding=binding(),
            bars_by_timeframe={
                "1h": {
                    "AAAUSDT": bars("AAAUSDT"),
                    "BBBUSDT": bars("BBBUSDT"),
                }
            },
        )
        result = runtime.run("MCF-PROD-001-000000")
        self.assertEqual(result["candidate_id"], "MCF-PROD-001-000000")
        self.assertTrue(result["exact_accounting"])
        self.assertEqual(result["accounting_engine"], "MCF_PRODUCTION_DECIMAL/1.0.0")
        self.assertEqual(result["neighbor_graph_sha256"], freeze_artifact()["summary"]["neighbor_graph_sha256"])
        self.assertFalse(result["safety"]["fresh_oos_read"])
        self.assertFalse(result["safety"]["p10_read"])


if __name__ == "__main__":
    unittest.main()
