import json
import tempfile
import unittest
from pathlib import Path

from research.historical_strategy_search import survivor_freeze as freeze


ROOT = Path(__file__).resolve().parents[1]
FREEZE = (
    ROOT
    / "docs"
    / "research"
    / "historical-strategy-search"
    / "HSSE-004A-SURVIVOR-FREEZE-v0.1.0.json"
)


class HSSE004ASurvivorFreezeTests(unittest.TestCase):
    def test_exact_six_survivors_are_frozen_before_blind_oos(self):
        result = freeze.validate_freeze(FREEZE)
        self.assertEqual(result["survivor_count"], 6)
        self.assertEqual(result["families"]["TREND_MA_EMA"], 3)
        self.assertEqual(result["families"]["TREND_MA_DEMA"], 3)
        self.assertEqual(
            result["blind_oos_start_utc"], "2023-01-01T00:00:00Z"
        )
        self.assertEqual(
            result["blind_oos_end_exclusive_utc"], "2025-01-01T00:00:00Z"
        )
        self.assertFalse(result["blind_oos_accessed"])
        self.assertFalse(result["p10_write_allowed"])
        self.assertTrue(result["p11_locked"])

    def test_parameter_mutation_fails_closed(self):
        record = json.loads(FREEZE.read_text(encoding="utf-8"))
        record["survivors"][0]["parameters"]["n2"] = 501
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "freeze.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(freeze.HSSEFreezeError):
                freeze.validate_freeze(path)

    def test_survivor_count_mutation_fails_closed(self):
        record = json.loads(FREEZE.read_text(encoding="utf-8"))
        record["survivors"].pop()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "freeze.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(freeze.HSSEFreezeError):
                freeze.validate_freeze(path)

    def test_blind_window_mutation_fails_closed(self):
        record = json.loads(FREEZE.read_text(encoding="utf-8"))
        record["blind_oos"]["analysis_start_utc"] = "2022-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "freeze.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(freeze.HSSEFreezeError):
                freeze.validate_freeze(path)


if __name__ == "__main__":
    unittest.main()
