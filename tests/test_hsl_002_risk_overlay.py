import inspect
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from yatl.risk import RiskPolicy
from yatl.validation.paper_runner import _RiskTracker

from research.historical_strategy_lab import risk_overlay as hsl2


HOUR = 3_600_000


def snapshot(
    *,
    equity="10000",
    realized="0",
    closed_trades=0,
    cash=None,
    asset="0",
):
    if cash is None:
        cash = equity
    return SimpleNamespace(
        equity_quote=Decimal(equity),
        realized_pnl_quote=Decimal(realized),
        closed_trades=closed_trades,
        cash=Decimal(cash),
        asset_quantity=Decimal(asset),
    )


class HSL002RiskOverlayTests(unittest.TestCase):
    def test_protocol_is_preregistered_and_does_not_mutate_p4(self):
        protocol, digest = hsl2.load_protocol()
        self.assertEqual(len(digest), 64)
        self.assertTrue(protocol["research_only"])
        self.assertTrue(protocol["paper_only"])
        self.assertTrue(protocol["p10_untouched"])
        self.assertTrue(protocol["p11_locked"])
        self.assertFalse(protocol["trade_permission"])
        self.assertEqual(protocol["live_master_lock"], "OFF")

        arms = {
            item["arm_id"]: item
            for item in protocol["arms"]
        }
        self.assertEqual(
            set(arms),
            {
                hsl2.REFERENCE_ARM_ID,
                hsl2.CHALLENGER_ARM_ID,
            },
        )
        challenger = arms[hsl2.CHALLENGER_ARM_ID]
        self.assertEqual(
            challenger["cooldown_primary_decisions"], 24
        )
        self.assertEqual(
            challenger["hard_latch_breakers"],
            ["DRAWDOWN_LIMIT"],
        )
        self.assertEqual(
            challenger["recoverable_breakers"],
            [
                "SESSION_LOSS_LIMIT",
                "CONSECUTIVE_LOSS_LIMIT",
            ],
        )
        self.assertFalse(
            protocol["invariants"][
                "strategy_selection_from_hsl001_outcomes"
            ]
        )
        self.assertFalse(
            protocol["invariants"][
                "drawdown_hard_latch_auto_reset"
            ]
        )
        self.assertFalse(
            protocol["invariants"]["p4_policy_mutated"]
        )

        policy = RiskPolicy()
        self.assertEqual(
            policy.max_session_loss_fraction, "0.02"
        )
        self.assertEqual(
            policy.max_drawdown_fraction, "0.10"
        )
        self.assertEqual(policy.max_consecutive_losses, 3)

    def test_reference_wrapper_matches_accepted_latched_tracker(self):
        wrapped = hsl2._ReferenceRiskTracker(
            "BTCUSDT", "10000"
        )
        accepted = _RiskTracker("BTCUSDT", "10000")
        observations = [
            (0, snapshot(), "100"),
            (
                HOUR,
                snapshot(
                    equity="9990",
                    realized="-10",
                    closed_trades=1,
                ),
                "100",
            ),
            (
                2 * HOUR,
                snapshot(
                    equity="9980",
                    realized="-20",
                    closed_trades=2,
                ),
                "100",
            ),
            (
                3 * HOUR,
                snapshot(
                    equity="9970",
                    realized="-30",
                    closed_trades=3,
                ),
                "100",
            ),
            (
                4 * HOUR,
                snapshot(
                    equity="9970",
                    realized="-30",
                    closed_trades=3,
                ),
                "100",
            ),
        ]
        for event_time, snap, mark in observations:
            with self.subTest(event_time=event_time):
                expected = accepted.observe(
                    event_time, snap, mark
                )
                actual = wrapped.observe(
                    event_time, snap, mark
                )
                self.assertEqual(
                    actual.as_record(),
                    expected.as_record(),
                )

    def test_loss_streak_cooldown_releases_after_24_blocked_decisions(self):
        tracker = hsl2._RecoveryCooldownRiskTracker(
            "BTCUSDT",
            "10000",
            cooldown_primary_decisions=24,
        )
        tracker.observe(0, snapshot(), "100")
        for index in range(1, 4):
            state = tracker.observe(
                index * HOUR,
                snapshot(
                    equity=str(10000 - index * 10),
                    realized=str(-index * 10),
                    closed_trades=index,
                ),
                "100",
            )
        self.assertTrue(state.kill_switch_active)
        self.assertEqual(
            state.consecutive_losses, 3
        )
        self.assertEqual(
            tracker.loss_streak_trigger_count, 1
        )

        for offset in range(1, 25):
            state = tracker.observe(
                (3 + offset) * HOUR,
                snapshot(
                    equity="9970",
                    realized="-30",
                    closed_trades=3,
                ),
                "100",
            )
            self.assertTrue(
                state.kill_switch_active,
                msg=f"cooldown released too early at {offset}",
            )

        released = tracker.observe(
            28 * HOUR,
            snapshot(
                equity="9970",
                realized="-30",
                closed_trades=3,
            ),
            "100",
        )
        self.assertFalse(released.kill_switch_active)
        self.assertEqual(released.consecutive_losses, 0)
        self.assertEqual(tracker.cooldown_release_count, 1)
        self.assertEqual(
            tracker.cooldown_blocked_decision_count, 24
        )
        self.assertEqual(
            tracker.observed_consecutive_losses_peak, 3
        )

    def test_drawdown_is_hard_latched_and_never_auto_resets(self):
        tracker = hsl2._RecoveryCooldownRiskTracker(
            "ETHUSDT",
            "10000",
            cooldown_primary_decisions=24,
        )
        tracker.observe(0, snapshot(), "100")
        triggered = tracker.observe(
            HOUR,
            snapshot(equity="8900"),
            "100",
        )
        self.assertTrue(triggered.kill_switch_active)
        self.assertTrue(tracker.hard_latched)
        self.assertEqual(
            tracker.hard_latch_trigger_count, 1
        )

        for index in range(2, 40):
            state = tracker.observe(
                index * HOUR,
                snapshot(equity="10000"),
                "100",
            )
            self.assertTrue(state.kill_switch_active)
        self.assertTrue(tracker.hard_latched)
        self.assertEqual(
            tracker.summary()["hard_latch_bypass_count"], 0
        )

    def test_session_loss_releases_only_on_later_utc_session(self):
        tracker = hsl2._RecoveryCooldownRiskTracker(
            "BTCUSDT",
            "10000",
            cooldown_primary_decisions=24,
        )
        tracker.observe(0, snapshot(), "100")
        breached = tracker.observe(
            HOUR,
            snapshot(
                equity="9790",
                realized="-210",
                closed_trades=1,
            ),
            "100",
        )
        self.assertTrue(breached.kill_switch_active)
        self.assertTrue(tracker.session_block_active)

        same_day = tracker.observe(
            23 * HOUR,
            snapshot(
                equity="9790",
                realized="-210",
                closed_trades=1,
            ),
            "100",
        )
        self.assertTrue(same_day.kill_switch_active)

        next_day = tracker.observe(
            24 * HOUR,
            snapshot(
                equity="9790",
                realized="-210",
                closed_trades=1,
            ),
            "100",
        )
        self.assertFalse(next_day.kill_switch_active)
        self.assertFalse(tracker.session_block_active)
        self.assertEqual(tracker.session_release_count, 1)

    def test_comparison_gate_cannot_promote_to_p10_or_live(self):
        gate = hsl2.load_protocol()[0]["comparison_gate"]
        reference = {
            "completed_trades": 30,
            "total_net_pnl_after_costs_quote": "10",
            "expectancy_quote": "1",
            "profit_factor": "1.1",
            "profit_factor_infinite": False,
            "maximum_drawdown_fraction": "0.04",
            "hard_latch_bypass_count": 0,
        }
        challenger = {
            "completed_trades": 40,
            "total_net_pnl_after_costs_quote": "15",
            "expectancy_quote": "1.2",
            "profit_factor": "1.2",
            "profit_factor_infinite": False,
            "maximum_drawdown_fraction": "0.05",
            "hard_latch_bypass_count": 0,
        }
        result = hsl2._comparison(
            candidate_id="TEST",
            reference=reference,
            challenger=challenger,
            gate=gate,
        )
        self.assertEqual(
            result["status"],
            "QUALIFIED_FOR_FURTHER_HSL_RESEARCH",
        )
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(result["p10_evidence_effect"], "NONE")
        self.assertTrue(result["p11_locked"])
        self.assertFalse(result["live_authorized"])

    def test_p10_runtime_is_protected(self):
        with self.assertRaises(hsl2.HSLRiskOverlayError):
            hsl2.run_risk_overlay(
                runtime_root=Path("/var/lib/yatl/p10"),
                quality_manifest_relative_path=(
                    "quality/event-quality-" + "0" * 24 + ".json"
                ),
                quality_manifest_file_sha256="0" * 64,
            )

    def test_source_has_no_network_credentials_or_order_authority(self):
        source = inspect.getsource(hsl2)
        for forbidden in (
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
