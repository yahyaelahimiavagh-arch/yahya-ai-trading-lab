"""Independent fresh-process synthetic memory measurements for Issue #187.

Each worker is separately resource-limited and its stdout contains ONLY
memory/fixture metadata, not financial or strategy outputs. The comparison is
observational: do not label a regression as PASS or pretend noise is a win.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "mcf_replay_marks_memory_probe.py"


@unittest.skipUnless(platform.system() == "Linux", "requires Linux VmRSS/ru_maxrss")
class SyntheticReplayMemoryMeasurementTest(unittest.TestCase):
    def test_two_fresh_processes_each_exact_same_fixture(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "tests")))
        runs = {}
        for mode in ("legacy", "proposed"):
            proc = subprocess.run(
                [sys.executable, "-B", str(PROBE), mode],
                cwd=ROOT, env=env, capture_output=True, text=True,
                timeout=95, check=False,
            )
            self.assertEqual(proc.returncode, 0, "synthetic probe worker failed")
            rows = proc.stdout.splitlines()
            self.assertEqual(len(rows), 1, "only one memory-only JSON row allowed")
            row = json.loads(rows[0])
            self.assertEqual(row["schema"], "MCF_SYNTHETIC_REPLAY_MEMORY_PROBE/1.0.0")
            self.assertEqual(row["mode"], mode)
            self.assertEqual((row["symbols"], row["bars_per_symbol"], row["scenarios"]),
                             (6, 12000, 2))
            for flag in ("candidate_executed", "real_data_read",
                         "performance_exposed", "source_input_modified"):
                self.assertIs(row[flag], False)
            for key in ("rss_after_fixture_kib", "rss_after_results_kib",
                        "peak_rss_kib"):
                self.assertIs(type(row[key]), int)
                self.assertGreater(row[key], 0)
            self.assertGreaterEqual(row["peak_rss_kib"], row["rss_after_results_kib"])
            self.assertGreaterEqual(row["peak_rss_kib"], row["rss_after_fixture_kib"])
            runs[mode] = row

        old, new = runs["legacy"], runs["proposed"]
        # No output values or digest hashes from actual candidate results.
        report = {
            "schema": "MCF_SYNTHETIC_REPLAY_MEMORY_COMPARISON/1.0.0",
            "fixture": "six_invented_symbols_12000_15m_bars_base_and_stress",
            "legacy_peak_mib": round(old["peak_rss_kib"] / 1024, 3),
            "proposed_peak_mib": round(new["peak_rss_kib"] / 1024, 3),
            "peak_delta_mib": round(
                (new["peak_rss_kib"] - old["peak_rss_kib"]) / 1024, 3),
            "legacy_fixture_rss_mib": round(old["rss_after_fixture_kib"] / 1024, 3),
            "proposed_fixture_rss_mib": round(new["rss_after_fixture_kib"] / 1024, 3),
            "legacy_retained_rss_mib": round(old["rss_after_results_kib"] / 1024, 3),
            "proposed_retained_rss_mib": round(new["rss_after_results_kib"] / 1024, 3),
            "runtime_candidate_executed": False,
            "real_data_read": False,
            "memory_improvement_proven": False,
            "status": "OBSERVATION_ONLY_REQUIRES_INDEPENDENT_REVIEW",
        }
        print("MCF_REPLAY_MEMORY_AUDIT=" + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    unittest.main()
