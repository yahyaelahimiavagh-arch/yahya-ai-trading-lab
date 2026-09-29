import json
import tempfile
import unittest
from pathlib import Path

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_freeze import (
    ARTIFACT_DIR,
    build_payloads,
    materialize,
    verify,
)


class ProductionVpsFreezeTest(unittest.TestCase):
    def test_build_payloads_is_exact_and_pre_outcome(self):
        manifest_a, payloads_a = build_payloads()
        manifest_b, payloads_b = build_payloads()
        self.assertEqual(manifest_a, manifest_b)
        self.assertEqual(payloads_a, payloads_b)
        self.assertEqual(manifest_a["executable_candidate_count"], 6852)
        self.assertEqual(manifest_a["blocked_implementation_count"], 1788)
        self.assertEqual(
            manifest_a["freeze_sha256"],
            "84d4f8ec6234ffb5afccf44ea044661d72af8b4de525b111118ae087907d1dc6",
        )
        self.assertEqual(
            manifest_a["candidate_ledger_sha256"],
            "084150778f2270c2ce96dac631f2e0fb1e6f84fed3325a197a80aa3d59db8e73",
        )
        self.assertEqual(
            manifest_a["neighbor_graph_sha256"],
            "4eb36ca827b5b458147e6ba2a74308353dfa047cd368d72e106f568b1f4fc4bb",
        )
        self.assertFalse(manifest_a["safety"]["performance_read"])
        self.assertFalse(manifest_a["safety"]["fresh_oos_read"])
        self.assertFalse(manifest_a["safety"]["recent_reserve_read"])
        self.assertFalse(manifest_a["safety"]["p10_read"])
        self.assertFalse(manifest_a["safety"]["p10_write"])
        self.assertFalse(manifest_a["safety"]["live"])
        self.assertTrue(manifest_a["safety"]["p11_locked"])

    def test_materialize_verify_and_idempotent_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = materialize(root)
            second = materialize(root)
            checked = verify(root)
            self.assertEqual(first, second)
            self.assertEqual(first, checked)
            self.assertEqual(first["status"], "VERIFIED")
            self.assertEqual(first["executable_candidate_count"], 6852)

            artifact_dir = root / ARTIFACT_DIR
            names = sorted(path.name for path in artifact_dir.iterdir())
            self.assertEqual(
                names,
                [
                    "blocked-candidates.jsonl",
                    "freeze-summary.json",
                    "manifest.json",
                    "neighbor-graph.json",
                    "registered-candidates.jsonl",
                ],
            )

            manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "PRE_OUTCOME_VPS_FREEZE_MATERIALIZED")

    def test_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materialize(root)
            target = root / ARTIFACT_DIR / "registered-candidates.jsonl"
            target.write_bytes(target.read_bytes() + b"tamper\n")
            with self.assertRaises(MCFError):
                verify(root)
            with self.assertRaises(MCFError):
                materialize(root)

    def test_missing_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaises(MCFError):
                materialize(missing)
            with self.assertRaises(MCFError):
                verify(missing)


if __name__ == "__main__":
    unittest.main()
