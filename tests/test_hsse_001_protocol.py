import json
import tempfile
import unittest
from pathlib import Path

from research.historical_strategy_search import protocol as hsse


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = (
    ROOT
    / "docs"
    / "research"
    / "historical-strategy-search"
    / "HSSE-001-SEARCH-PROTOCOL-v0.1.0.json"
)


class HSSE001ProtocolTests(unittest.TestCase):
    def test_protocol_is_valid_and_holdouts_are_sealed(self):
        result = hsse.validate_protocol(PROTOCOL)
        self.assertEqual(result["development_end_exclusive_utc"], "2023-01-01T00:00:00Z")
        self.assertEqual(result["blind_oos_start_utc"], "2023-01-01T00:00:00Z")
        self.assertEqual(result["blind_oos_end_exclusive_utc"], "2025-01-01T00:00:00Z")
        self.assertEqual(result["audit_start_utc"], "2025-01-01T00:00:00Z")
        self.assertEqual(result["audit_end_exclusive_utc"], "2026-07-01T00:00:00Z")
        self.assertEqual(result["maximum_total_trials"], 20000)
        self.assertEqual(result["maximum_survivors"], 12)
        self.assertTrue(result["blind_oos_sealed"])
        self.assertTrue(result["audit_holdout_sealed"])
        self.assertFalse(result["p10_write_allowed"])
        self.assertTrue(result["p11_locked"])

    def _mutate(self, callback):
        record = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        callback(record)
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "protocol.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return temp, path

    def test_overlap_between_development_and_blind_fails_closed(self):
        temp, path = self._mutate(
            lambda record: record["data_boundaries"]["blind_oos"].__setitem__(
                "analysis_start_utc", "2022-12-01T00:00:00Z"
            )
        )
        with temp, self.assertRaises(hsse.HSSEProtocolError):
            hsse.validate_protocol(path)

    def test_unsealing_blind_oos_fails_closed(self):
        temp, path = self._mutate(
            lambda record: record["data_boundaries"]["blind_oos"].__setitem__(
                "inspection_status", "OPEN"
            )
        )
        with temp, self.assertRaises(hsse.HSSEProtocolError):
            hsse.validate_protocol(path)

    def test_search_budget_cannot_be_unbounded(self):
        temp, path = self._mutate(
            lambda record: record["search_budget"].__setitem__(
                "maximum_total_trials", 1000000
            )
        )
        with temp, self.assertRaises(hsse.HSSEProtocolError):
            hsse.validate_protocol(path)

    def test_raw_pnl_only_ranking_cannot_be_enabled(self):
        temp, path = self._mutate(
            lambda record: record["ranking"].__setitem__(
                "raw_pnl_only_ranking_forbidden", False
            )
        )
        with temp, self.assertRaises(hsse.HSSEProtocolError):
            hsse.validate_protocol(path)

    def test_blind_outcome_cannot_become_selection_input(self):
        temp, path = self._mutate(
            lambda record: record["anti_overfitting"].__setitem__(
                "blind_oos_outcomes_may_inform_selection", True
            )
        )
        with temp, self.assertRaises(hsse.HSSEProtocolError):
            hsse.validate_protocol(path)


if __name__ == "__main__":
    unittest.main()
