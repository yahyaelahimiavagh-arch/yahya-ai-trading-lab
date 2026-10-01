import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_distributed import build_execution_plan
from research.mass_candidate_factory import production_worker_bundle as bundle


class FakeReader:
    def __init__(self, root, relative, expected):
        datasets = []
        for i in range(175):
            symbol = f"ASSET{i:03d}USDT"
            for timeframe in ("15m", "1h", "4h"):
                datasets.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "data_ref": f"runtime-data/{symbol}/{timeframe}/data.csv",
                    "gap_ref": f"runtime-data/{symbol}/{timeframe}/gaps.json",
                })
        self._doc = {
            "runtime_index": {
                "index_sha256": "c" * 64,
                "dataset_count": 525,
                "datasets": datasets,
            },
            "membership": {"freeze_sha256": "d" * 64},
        }


class WorkerBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_execution_plan()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runner = "runner-input/input-test.json"
        p = self.root / self.runner
        p.parent.mkdir(parents=True)
        p.write_bytes(b"runner\n")
        for i in range(175):
            symbol = f"ASSET{i:03d}USDT"
            for timeframe in ("15m", "1h", "4h"):
                base = self.root / "runtime-data" / symbol / timeframe
                base.mkdir(parents=True)
                (base / "data.csv").write_bytes(f"{symbol},{timeframe},data\n".encode())
                (base / "gaps.json").write_bytes(f"{symbol},{timeframe},gap\n".encode())

    def test_freeze_and_verify_exact_portable_inventory(self):
        with patch.object(bundle, "FrozenRunnerInput", FakeReader):
            manifest = bundle.build_bundle_manifest(
                self.root,
                runner_input_relative=self.runner,
                expected_runner_input_sha256="b" * 64,
                distributed_plan=self.plan,
                git_sha="a" * 40,
            )
            self.assertEqual(manifest["dataset_count"], 525)
            self.assertEqual(manifest["object_count"], 1051)
            self.assertFalse(manifest["safety"]["fresh_oos_included"])
            self.assertFalse(manifest["safety"]["p10_included"])
            result = bundle.verify_bundle(self.root, manifest, self.plan)
        self.assertEqual(result["status"], "WORKER_BUNDLE_VERIFIED_NO_PERFORMANCE")
        self.assertFalse(result["performance_execution_authorized"])

    def test_changed_worker_byte_is_rejected(self):
        with patch.object(bundle, "FrozenRunnerInput", FakeReader):
            manifest = bundle.build_bundle_manifest(
                self.root,
                runner_input_relative=self.runner,
                expected_runner_input_sha256="b" * 64,
                distributed_plan=self.plan,
                git_sha="a" * 40,
            )
        target = self.root / manifest["objects"][1]["relative"]
        target.write_bytes(target.read_bytes() + b"tamper")
        with patch.object(bundle, "FrozenRunnerInput", FakeReader):
            with self.assertRaises(MCFError):
                bundle.verify_bundle(self.root, manifest, self.plan)

    def test_manifest_tamper_rejected_before_file_scan(self):
        with patch.object(bundle, "FrozenRunnerInput", FakeReader):
            manifest = bundle.build_bundle_manifest(
                self.root,
                runner_input_relative=self.runner,
                expected_runner_input_sha256="b" * 64,
                distributed_plan=self.plan,
                git_sha="a" * 40,
            )
        manifest["objects"][0]["relative"] = "p10/forbidden"
        with self.assertRaises(MCFError):
            bundle.validate_bundle_manifest(manifest, self.plan)


if __name__ == "__main__":
    unittest.main()
