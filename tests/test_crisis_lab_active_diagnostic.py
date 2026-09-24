import inspect
import unittest
from pathlib import Path

from research.crisis_lab import active_diagnostic as diagnostic
from research.crisis_lab import controls


def candidate(time_ms, symbol):
    return {
        "decision_time_ms": time_ms,
        "fill_time_ms": time_ms,
        "symbol": symbol,
        "context_sha256": "a" * 64,
        "regime": "TREND_UP",
        "strategy_reason": "TREND_PULLBACK_ENTRY",
        "active_setup": {
            "reference_price": "100",
            "invalidation_price": "95",
            "target_price": "110",
        },
        "risk_state_before_entry": {},
        "portfolio_before_entry": {},
        "portfolio_after_entry": {},
        "entry_fill": {},
    }


class CrisisLabStrategyActiveDiagnosticTests(unittest.TestCase):
    def test_protocol_freezes_confirmed_open_entry_definition(self):
        protocol, _ = controls.load_protocol()
        active = protocol["strategy_active_diagnostic"]

        self.assertEqual(
            active["selection_scope"],
            "BTCUSDT_AND_ETHUSDT_COMBINED",
        )
        self.assertTrue(active["confirmed_open_position_required"])
        self.assertTrue(active["deterministic_tie_break"])
        self.assertEqual(active["maximum_episodes"], 10)
        self.assertEqual(active["minimum_separation_ms"], 604800000)
        self.assertFalse(active["unbiased_performance_evidence"])
        self.assertTrue(active["diagnostic_only"])
        self.assertIn(
            "actual Paper NEXT_PRIMARY_OPEN entry fill",
            active["entry_definition"],
        )
        self.assertIn(
            "later_pnl", active["forbidden_selection_fields"]
        )
        self.assertIn(
            "active_setup", active["required_source_state_fields"]
        )
        self.assertIn(
            "portfolio_after_entry",
            active["required_source_state_fields"],
        )

    def test_selection_is_chronological_with_lexical_tie_break(self):
        day = 86_400_000
        values = [
            candidate(10 * day, "ETHUSDT"),
            candidate(2 * day, "ETHUSDT"),
            candidate(2 * day, "BTCUSDT"),
            candidate(20 * day, "BTCUSDT"),
        ]
        selected = diagnostic._select_episodes(
            values,
            maximum_episodes=10,
            minimum_separation_ms=7 * day,
        )
        self.assertEqual(
            [
                (item["decision_time_ms"], item["symbol"])
                for item in selected
            ],
            [
                (2 * day, "BTCUSDT"),
                (10 * day, "ETHUSDT"),
                (20 * day, "BTCUSDT"),
            ],
        )

    def test_selection_never_uses_future_outcome_fields(self):
        item = candidate(1_000_000_000, "BTCUSDT")
        item["later_pnl"] = "999"
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic._select_episodes(
                [item],
                maximum_episodes=10,
                minimum_separation_ms=604800000,
            )

    def test_separation_is_measured_from_last_selected_episode(self):
        day = 86_400_000
        values = [
            candidate(1 * day, "BTCUSDT"),
            candidate(2 * day, "ETHUSDT"),
            candidate(7 * day, "BTCUSDT"),
            candidate(8 * day, "ETHUSDT"),
            candidate(15 * day, "BTCUSDT"),
        ]
        selected = diagnostic._select_episodes(
            values,
            maximum_episodes=10,
            minimum_separation_ms=7 * day,
        )
        self.assertEqual(
            [item["decision_time_ms"] for item in selected],
            [1 * day, 8 * day, 15 * day],
        )

    def test_crisis_exclusions_are_registered_and_guarded(self):
        protocol, _ = controls.load_protocol()
        guard = protocol["strategy_active_diagnostic"][
            "crisis_exclusion_guard_days"
        ]
        ranges = diagnostic._load_crisis_exclusions(
            event_catalog_path=diagnostic.DEFAULT_EVENT_CATALOG_PATH,
            guard_days=guard,
        )
        self.assertGreater(len(ranges), 0)
        for start, end, event_id in ranges:
            self.assertLess(start, end)
            self.assertTrue(event_id.startswith("CRL-E"))
            midpoint = start + (end - start) // 2
            self.assertTrue(diagnostic._excluded(midpoint, ranges))

    def test_p10_runtime_root_is_forbidden(self):
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.run_strategy_active_diagnostic(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_or_execution_capability(self):
        source = inspect.getsource(diagnostic)
        for forbidden in (
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
