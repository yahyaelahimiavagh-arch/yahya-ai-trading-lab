import unittest

from research.mass_candidate_factory.models import MCFError, digest
from research.mass_candidate_factory.production_result_projection import (
    OMITTED_FIELDS,
    project_result,
    storage_result,
    validate_projection,
)


def full_result():
    body = {
        "schema": "MCF_PRODUCTION_ACCOUNTING/1.0.0",
        "candidate_id": "MCF-PROD-001-000001",
        "candidate_spec_sha256": "a" * 64,
        "family_id": "FAM",
        "economic_mechanism_id": "MECH",
        "family_spec_sha256": "b" * 64,
        "neighbor_graph_sha256": "c" * 64,
        "evidence_partition": "DEVELOPMENT",
        "exact_accounting": True,
        "aggregate_stress_net_return": "0.01",
        "median_symbol_stress_net_return": "0.01",
        "fold_stress_returns": ("0.01",) * 6,
        "maximum_normalized_drawdown": "0.02",
        "mean_turnover": "1.0",
        "f0_f3_state": "F0_F3_PASS",
        "daily_return_series": {
            "calendar_days": (1, 2, 3),
            "returns": ("0.01", "0.00", "-0.01"),
            "valid_mask": (True, True, True),
        },
        "per_symbol_base": ({"marks": tuple(range(100))},),
        "per_symbol_stress": ({"marks": tuple(range(100))},),
        "per_symbol_daily_return_series": ({"returns": tuple(range(100))},),
        "completed_trades": 300,
        "failure_reasons": (),
    }
    return {**body, "result_sha256": digest(body)}


class ProductionResultProjectionTest(unittest.TestCase):
    def test_projection_drops_only_declared_heavy_fields_and_rehashes(self):
        source = full_result()
        projected = project_result(source)
        validate_projection(projected)
        self.assertEqual(projected["source_full_result_sha256"], source["result_sha256"])
        for field in OMITTED_FIELDS:
            self.assertNotIn(field, projected)
        self.assertEqual(projected["candidate_id"], source["candidate_id"])
        self.assertEqual(projected["completed_trades"], 300)
        self.assertEqual(projected["daily_return_series"], source["daily_return_series"])
        self.assertNotEqual(projected["result_sha256"], source["result_sha256"])

    def test_projection_is_storage_idempotent(self):
        projected = project_result(full_result())
        self.assertEqual(storage_result(projected), projected)

    def test_invalid_source_digest_rejected(self):
        source = full_result()
        source["completed_trades"] = 301
        with self.assertRaises(MCFError):
            project_result(source)

    def test_missing_adjudication_surface_rejected(self):
        source = full_result()
        body = {k: v for k, v in source.items() if k != "result_sha256"}
        del body["daily_return_series"]
        source = {**body, "result_sha256": digest(body)}
        with self.assertRaises(MCFError):
            project_result(source)


if __name__ == "__main__":
    unittest.main()
