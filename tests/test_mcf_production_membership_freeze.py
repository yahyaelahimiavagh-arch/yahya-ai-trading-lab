import json
import tempfile
import unittest
from pathlib import Path

from research.mass_candidate_factory.models import MCFError, canonical, digest
from research.mass_candidate_factory.production_binding_preflight import (
    EXPECTED_POPULATION_RECONCILIATION_SHA256,
    VERSION as PREFLIGHT_SCHEMA,
    _month_starts,
)
from research.mass_candidate_factory.production_generator import UNIVERSE_POLICY_SHA256
from research.mass_candidate_factory.production_membership_freeze import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_SAFETY,
    build_freeze,
    materialize,
)


def ready_preflight():
    monthly = []
    for index, effective_ms in enumerate(_month_starts()):
        symbols = [] if index == 0 else ["BTCUSDT", "ETHUSDT"]
        monthly.append({
            "effective_ms": effective_ms,
            "eligible_count": len(symbols),
            "selected_count": len(symbols),
            "selected_symbols": symbols,
            "ranking_sha256": digest({
                "month": effective_ms,
                "symbols": tuple(symbols),
            }),
        })

    base = {
        "schema": PREFLIGHT_SCHEMA,
        "generation_id": "MCF-PROD-001",
        "state": "READY_FOR_PRODUCTION_BINDING",
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "population_reconciliation_sha256":
            EXPECTED_POPULATION_RECONCILIATION_SHA256,
        "population_reconciliation_state":
            "POPULATION_COMPLETE_WITH_SOURCE_GAPS",
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "classification_map_sha256": "a" * 64,
        "symbol_count": 413,
        "month_count": len(monthly),
        "classification_complete": False,
        "membership_resolved": True,
        "unresolved_data_eligible_symbol_count": 206,
        "unresolved_data_eligible_symbols": ["LOWERUSDT"],
        "unresolved_month_counts": [],
        "data_eligible_month_counts": [],
        "classification_neutral_rankings": [],
        "frontier_month_counts": [],
        "next_classification_frontier_symbol_count": 0,
        "next_classification_frontier_symbols": [],
        "initial_classification_frontier_symbol_count": 0,
        "initial_classification_frontier_symbols": [],
        "monthly_rankings": monthly,
        "symbol_audit": [],
        "safety": EXPECTED_SAFETY,
    }
    return {**base, "preflight_sha256": digest(base)}


class ProductionMembershipFreezeTest(unittest.TestCase):
    def test_ready_preflight_freezes_exact_months_and_union(self):
        doc = ready_preflight()
        freeze = build_freeze(doc)

        self.assertEqual(freeze["month_count"], 34)
        self.assertEqual(freeze["selected_union_count"], 2)
        self.assertEqual(
            freeze["selected_union_symbols"],
            ("BTCUSDT", "ETHUSDT"),
        )
        self.assertFalse(freeze["classification_complete"])
        self.assertEqual(
            freeze["unresolved_data_eligible_symbol_count"],
            206,
        )
        self.assertEqual(
            freeze["monthly_memberships"][0]["selected_symbols"],
            (),
        )
        self.assertEqual(len(freeze["freeze_sha256"]), 64)

    def test_materialization_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preflight_root = root / "preflight"
            output_root = root / "output"
            preflight_root.mkdir()
            output_root.mkdir()

            doc = ready_preflight()
            relative = f"preflight-{doc['preflight_sha256']}.json"
            (preflight_root / relative).write_bytes(canonical(doc))

            first = materialize(
                preflight_root=preflight_root,
                preflight_artifact=relative,
                expected_preflight_sha256=doc["preflight_sha256"],
                output_root=output_root,
            )
            second = materialize(
                preflight_root=preflight_root,
                preflight_artifact=relative,
                expected_preflight_sha256=doc["preflight_sha256"],
                output_root=output_root,
            )

            self.assertEqual(first, second)
            artifact = output_root / first["artifact"]
            frozen = json.loads(artifact.read_text())
            self.assertEqual(
                frozen["source_preflight_sha256"],
                doc["preflight_sha256"],
            )
            self.assertEqual(first["selected_union_count"], 2)
            self.assertFalse(first["performance_read"])
            self.assertFalse(first["p10_read"])
            self.assertTrue(first["p11_locked"])

    def test_membership_unresolved_is_rejected(self):
        doc = ready_preflight()
        doc["membership_resolved"] = False
        doc["state"] = "CLASSIFICATION_INCOMPLETE"
        doc["next_classification_frontier_symbol_count"] = 1
        doc["next_classification_frontier_symbols"] = ["NEXTUSDT"]
        base = dict(doc)
        base.pop("preflight_sha256")
        doc["preflight_sha256"] = digest(base)
        with self.assertRaises(MCFError):
            build_freeze(doc)

    def test_expected_preflight_identity_and_canonical_bytes_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preflight_root = root / "preflight"
            output_root = root / "output"
            preflight_root.mkdir()
            output_root.mkdir()

            doc = ready_preflight()
            relative = f"preflight-{doc['preflight_sha256']}.json"
            (preflight_root / relative).write_bytes(canonical(doc))

            with self.assertRaises(MCFError):
                materialize(
                    preflight_root=preflight_root,
                    preflight_artifact=relative,
                    expected_preflight_sha256="b" * 64,
                    output_root=output_root,
                )

            (preflight_root / relative).write_text(
                json.dumps(doc, indent=2),
                encoding="utf-8",
            )
            with self.assertRaises(MCFError):
                materialize(
                    preflight_root=preflight_root,
                    preflight_artifact=relative,
                    expected_preflight_sha256=doc["preflight_sha256"],
                    output_root=output_root,
                )

    def test_monthly_membership_tamper_breaks_preflight_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preflight_root = root / "preflight"
            output_root = root / "output"
            preflight_root.mkdir()
            output_root.mkdir()

            doc = ready_preflight()
            claimed = doc["preflight_sha256"]
            doc["monthly_rankings"][1]["selected_symbols"] = ["BTCUSDT"]
            relative = f"preflight-{claimed}.json"
            (preflight_root / relative).write_bytes(canonical(doc))

            with self.assertRaises(MCFError):
                materialize(
                    preflight_root=preflight_root,
                    preflight_artifact=relative,
                    expected_preflight_sha256=claimed,
                    output_root=output_root,
                )


if __name__ == "__main__":
    unittest.main()
