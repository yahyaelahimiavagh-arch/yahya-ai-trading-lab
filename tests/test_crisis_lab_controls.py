import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.crisis_lab import acquisition as acq


ROOT = Path("docs/research/crisis-lab")
PROTOCOL = ROOT / "CONTROL-WINDOW-PROTOCOL-v0.1.0.json"
CONTROL_REGISTER = ROOT / "CONTROL-DATA-ACQUISITION-REGISTER-v0.1.0.json"
EVENT_CATALOG = ROOT / "EVENT-CATALOG-v0.1.0.json"
CONTROL_EVENT_ID = "CRL-CONTROL-DEV-POOL-001"


def iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class CrisisLabControlProtocolTests(unittest.TestCase):
    def test_control_register_plans_continuous_six_dataset_pool(self):
        registration = acq.load_acquisition_register(CONTROL_REGISTER)
        plan = acq.plan_event(registration, CONTROL_EVENT_ID)

        self.assertEqual(plan["event_id"], CONTROL_EVENT_ID)
        self.assertEqual(plan["designation"], "DEVELOPMENT")
        self.assertTrue(plan["replay_eligible"])
        self.assertEqual(len(plan["datasets"]), 6)
        self.assertFalse(plan["market_data_downloaded"])
        self.assertFalse(plan["p10_write_allowed"])
        self.assertTrue(plan["p11_locked"])

        pairs = {
            (item["symbol"], item["interval"])
            for item in plan["datasets"]
        }
        self.assertEqual(
            pairs,
            {
                (symbol, interval)
                for symbol in acq.ALLOWED_SYMBOLS
                for interval in acq.ALLOWED_INTERVALS
            },
        )
        for item in plan["datasets"]:
            self.assertEqual(
                item["semantic_start_utc"],
                "2019-12-18T00:00:00Z",
            )
            self.assertEqual(
                item["semantic_end_utc"],
                "2023-01-01T00:00:00Z",
            )
            self.assertGreater(item["expected_row_count"], 0)

    def test_ordinary_windows_are_frozen_without_outcome_selection(self):
        protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        ordinary = protocol["unbiased_ordinary_windows"]
        rule = ordinary["selection_rule"]
        windows = ordinary["windows"]

        self.assertEqual(protocol["version"], "0.1.0")
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(rule["selection_uses_market_outcomes"])
        self.assertFalse(rule["selection_uses_strategy_results"])
        self.assertTrue(
            rule["selected_windows_may_not_be_discarded_for_no_trade_or_bad_performance"]
        )
        self.assertEqual(len(windows), 8)
        self.assertEqual(
            len({item["control_id"] for item in windows}),
            len(windows),
        )

    def test_registered_ordinary_windows_do_not_touch_crisis_guard_bands(self):
        protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        catalog = json.loads(EVENT_CATALOG.read_text(encoding="utf-8"))
        guard = timedelta(days=7)

        crisis_ranges = []
        for event in catalog["events"]:
            start = iso(event["windows"]["pre_event"]["start_utc"]) - guard
            end = iso(event["windows"]["aftermath_recovery"]["end_utc"]) + guard
            crisis_ranges.append((event["event_id"], start, end))

        for control in protocol["unbiased_ordinary_windows"]["windows"]:
            start = iso(control["acquisition_start_utc"])
            end = iso(control["analysis_end_utc"])
            with self.subTest(control=control["control_id"]):
                overlaps = [
                    event_id
                    for event_id, crisis_start, crisis_end in crisis_ranges
                    if start < crisis_end and end > crisis_start
                ]
                self.assertEqual(overlaps, [])

    def test_strategy_active_cohort_is_diagnostic_not_unbiased(self):
        protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        active = protocol["strategy_active_diagnostic"]
        transition = protocol["historical_crisis_transition"]

        self.assertTrue(active["diagnostic_only"])
        self.assertFalse(active["unbiased_performance_evidence"])
        self.assertTrue(transition["no_forced_entry"])
        self.assertIn("position_at_event_anchor", transition["required_fields"])
        self.assertIn("time_to_zero_exposure_ms", transition["required_fields"])


if __name__ == "__main__":
    unittest.main()
