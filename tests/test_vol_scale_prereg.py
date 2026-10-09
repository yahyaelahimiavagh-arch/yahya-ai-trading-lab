"""Synthetic-only tests for YATL-PREREG-VOL-SCALE-001 protocol implementation.

No market data is read. No protected holdout, VPS, or P10 state is accessed.
"""
from __future__ import annotations

import math
import unittest
from array import array
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from research.generation_2 import vol_scale_prereg as vsp
from research.generation_2 import downside_vol_scaling as g
from research.generation_2 import vol_scaling as shared
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2

D = Decimal
HOUR_MS = shared.HOUR_MS


class VolScalePreregSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "base_quantity": "0.001",
            "initial_equity_quote": "10000",
            "base_fee_bps": 10,
            "base_adverse_slippage_bps": 5,
            "stress_fee_bps": 20,
            "stress_adverse_slippage_bps": 10,
        }

    def _build_synthetic_series(
        self, symbol: str = "BTCUSDT", n_bars: int = 750, start_ms: int = 1577836800000
    ) -> tuple[hsse3.ExactSeries, hsse2.SearchSeries]:
        """Build synthetic deterministic 1h series with warmup and two crossovers."""
        times = tuple(start_ms + i * HOUR_MS for i in range(n_bars))
        opens = []
        closes = []
        for i in range(n_bars):
            if i < 500:
                p = 100.0
            elif i < 550:
                p = 150.0  # triggers fast EMA > slow EMA crossover (long entry)
            elif i < 600:
                p = 80.0   # triggers fast EMA < slow EMA crossover (long exit)
            elif i < 650:
                p = 130.0  # second entry
            else:
                p = 85.0   # second exit
            opens.append(str(p))
            closes.append(str(p))

        exact = hsse3.ExactSeries(symbol, times, tuple(opens), tuple(closes))
        signal = hsse2.SearchSeries(
            symbol,
            times,
            tuple(float(x) for x in opens),
            tuple(float(x) for x in closes),
        )
        return exact, signal

    def _build_multimonth_synthetic_series(
        self,
        symbol: str = "BTCUSDT",
        start_ms: int = 1577836800000,  # 2020-01-01T00:00:00Z
        end_ms: int = 1604188800000,    # 2020-11-01T00:00:00Z (10 full months)
    ) -> tuple[hsse3.ExactSeries, hsse2.SearchSeries]:
        """Build 10-month continuous synthetic hourly series with oscillating price.

        Permits full 6-month warmup and training (Feb-Jul 2020), followed by scored
        months (Aug-Oct 2020) where fresh scales below 1.0 are computed.
        """
        n_hours = (end_ms - start_ms) // HOUR_MS
        times = tuple(start_ms + i * HOUR_MS for i in range(n_hours))
        prices = []
        for i in range(n_hours):
            p = 100.0 + 30.0 * math.sin(2 * math.pi * i / 400.0) + 10.0 * math.sin(2 * math.pi * i / 80.0)
            prices.append(round(p, 4))

        exact = hsse3.ExactSeries(
            symbol,
            times,
            tuple(str(p) for p in prices),
            tuple(str(p) for p in prices),
        )
        signal = hsse2.SearchSeries(
            symbol,
            times,
            tuple(prices),
            tuple(prices),
        )
        return exact, signal

    def test_protocol_validation_and_safety_invariants(self):
        p, digest, freeze = vsp.validate_protocol()
        self.assertEqual(digest, vsp.PROTOCOL_SHA256)
        self.assertEqual(p["protocol_id"], "YATL-PREREG-VOL-SCALE-001")
        self.assertEqual(p["candidate_id"], vsp.CANDIDATE_ID)
        self.assertEqual(p["trial_matrix"]["conditions"], list(vsp.CONDITIONS))
        self.assertTrue(p["safety_boundary"]["paper_research_only"])
        self.assertFalse(p["safety_boundary"]["p10_read"])
        self.assertFalse(p["safety_boundary"]["p10_write_allowed"])
        self.assertTrue(p["safety_boundary"]["p11_locked"])
        self.assertEqual(p["safety_boundary"]["live_master_lock"], "OFF")

        survivors = {s["frozen_id"]: s for s in freeze["survivors"]}
        self.assertIn(vsp.FROZEN_ID, survivors)
        surv = survivors[vsp.FROZEN_ID]
        self.assertEqual(surv["family"], "TREND_MA_EMA")
        self.assertEqual(surv["parameters"]["n1"], 11)
        self.assertEqual(surv["parameters"]["n2"], 491)

    def test_protocol_tampering_fails_validation(self):
        with patch.object(vsp, "_read_normalized", return_value=b'{"mutated": true}'):
            with self.assertRaisesRegex(vsp.VolScalePreregError, "SHA-256 mismatch"):
                vsp.validate_protocol()

    def test_mandatory_prerequisites_and_market_data_lock(self):
        """Scope checks must pass for synthetic/paper and strictly block market data."""
        p, sha, freeze = vsp.check_execution_prerequisites(allow_market_data=False)
        self.assertEqual(p["protocol_id"], "YATL-PREREG-VOL-SCALE-001")

        # Attempting market data execution via prerequisite check must fail closed
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Market data execution path is currently disabled"):
            vsp.check_execution_prerequisites(allow_market_data=True)

        # Calling load_market_data must raise explicitly
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Market data loading is disabled and locked"):
            vsp.load_market_data("any_path")

    def test_multimonth_synthetic_integration_computes_fresh_scales_below_one(self):
        """Point 1: Demonstrate multi-month training computes fresh scale < 1.0,

        changes exposure, preserves directional signals, and charges rebalance costs.
        """
        jan = 1577836800000  # 2020-01-01T00:00:00Z
        feb = int(datetime(2020, 2, 1, tzinfo=timezone.utc).timestamp() * 1000)
        aug = int(datetime(2020, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
        nov = int(datetime(2020, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)

        exact, signal = self._build_multimonth_synthetic_series("BTCUSDT", start_ms=jan, end_ms=nov)

        res = vsp.run_two_arm_single_symbol(
            signal=signal,
            exact=exact,
            warmup_start_ms=jan,
            first_managed_ms=feb,
            scored_start_ms=aug,
            end_ms=nov,
            policy=self.policy,
        )

        arm_a = res["arm_a_control"]
        arm_b = res["arm_b_scaled"]
        counts = res["decision_counts"]

        # 1. Six-month training requirement satisfied: fresh decisions computed
        self.assertGreaterEqual(counts["valid_new_scale_decisions"], 2)
        valid_frac = Decimal(counts["valid_new_scale_decisions"]) / Decimal(
            counts["valid_new_scale_decisions"] + counts["carried_scale_decisions"]
        )
        self.assertGreaterEqual(valid_frac, Decimal("0.50"))

        # 2. Scaler actually computes scale below 1.0
        self.assertLess(arm_b["minimum_scale"], Decimal("1.0"))
        self.assertLess(arm_b["mean_scale"], Decimal("1.0"))

        # 3. Changes exposure: scaled notional is reduced vs control
        self.assertLess(arm_b["notional_exposure"], arm_a["notional_exposure"])
        self.assertGreaterEqual(arm_b["notional_exposure_ratio_vs_control"], Decimal("0.25"))

        # 4. Preserves directional signals
        self.assertEqual(arm_b["entry_signals"], arm_a["entry_signals"])
        self.assertEqual(arm_b["completed_trades"], arm_a["completed_trades"])
        self.assertEqual(arm_b["active_hours"], arm_a["active_hours"])
        self.assertEqual(arm_b["active_exposure_hours_fraction_vs_control"], Decimal("1.0"))

        # 5. Month boundary rebalance executed and charged
        self.assertGreaterEqual(arm_b["rebalances"], 1)
        self.assertGreater(arm_b["rebalance_notional"], Decimal("0"))

        # 6. Relabeled transparent exposure metrics present
        self.assertIn("average_active_notional_quote", arm_b)
        self.assertIn("pnl_over_average_active_notional_base", arm_b)
        self.assertIn("unimplemented_evaluations", arm_b)

    def test_directional_signals_and_opportunity_preservation_identical(self):
        start_ms = 1577836800000
        exact, signal = self._build_synthetic_series("BTCUSDT", n_bars=750, start_ms=start_ms)

        res = vsp.run_two_arm_single_symbol(
            signal=signal,
            exact=exact,
            warmup_start_ms=start_ms,
            first_managed_ms=start_ms + 31 * 24 * HOUR_MS,
            scored_start_ms=start_ms,
            end_ms=start_ms + 750 * HOUR_MS,
            policy=self.policy,
        )

        arm_a = res["arm_a_control"]
        arm_b = res["arm_b_scaled"]

        # Opportunity preservation: signals and completed trades must match exactly
        self.assertEqual(arm_a["entry_signals"], arm_b["entry_signals"])
        self.assertEqual(arm_a["completed_trades"], arm_b["completed_trades"])
        self.assertEqual(arm_a["entry_signals"], 2)
        self.assertEqual(arm_a["completed_trades"], 2)

        # Active hours fraction must be 1.0 (no starved trade duration)
        self.assertEqual(arm_a["active_hours"], arm_b["active_hours"])
        self.assertEqual(
            arm_b["active_exposure_hours_fraction_vs_control"], D(1)
        )

        # Notional exposure ratio must be >= 0.25 and <= 1.0
        ratio = arm_b["notional_exposure_ratio_vs_control"]
        self.assertGreaterEqual(ratio, D("0.25"))
        self.assertLessEqual(ratio, D(1))

    def test_no_leverage_and_long_only_bounds(self):
        start_ms = 1577836800000
        exact, signal = self._build_synthetic_series("BTCUSDT", n_bars=750, start_ms=start_ms)

        res = vsp.run_two_arm_single_symbol(
            signal=signal,
            exact=exact,
            warmup_start_ms=start_ms,
            first_managed_ms=start_ms + 31 * 24 * HOUR_MS,
            scored_start_ms=start_ms,
            end_ms=start_ms + 750 * HOUR_MS,
            policy=self.policy,
        )
        arm_b = res["arm_b_scaled"]

        # Scale is capped at 1.0 and strictly positive
        self.assertLessEqual(arm_b["mean_scale"], D(1))
        self.assertLessEqual(arm_b["median_scale"], D(1))
        self.assertGreater(arm_b["minimum_scale"], D(0))

    def test_month_boundary_rebalance_delta_and_costs(self):
        h = HOUR_MS
        ts = tuple(i * h for i in range(-4, 5))
        exact = hsse3.ExactSeries("BTCUSDT", ts, ("100",) * len(ts), ("100",) * len(ts))
        signal = hsse2.SearchSeries("BTCUSDT", ts, (100.0,) * len(ts), (100.0,) * len(ts))
        short = array("d", [math.nan, 1, 2, 2, 2, 2, 2, 2, 2])
        long = array("d", [math.nan, 2, 1, 1, 1, 1, 1, 1, 1])

        # At t=0, scale changes from 1.0 to 0.5 with active long position
        decisions = {
            -2678400000: {"scale": D(1), "new": False},
            0: {"scale": D("0.5"), "new": True},
        }
        cell = g._simulate_cell(
            signal=signal,
            exact=exact,
            short_values=short,
            long_values=long,
            start_ms=-4 * h,
            end_ms=5 * h,
            policy=self.policy,
            decisions=decisions,
            condition=vsp.CONDITIONS[1],
        )

        self.assertEqual(cell["entry_fills"], 1)
        self.assertEqual(cell["rebalances"], 1)
        # Delta = 0.001 * 0.5 - 0.001 = -0.0005 BTC at $100 => $0.05 delta notional
        self.assertEqual(cell["rebalance_notional"], D("0.05"))
        # Trading costs must be incurred on rebalance
        self.assertLess(cell["base_net"], D(0))
        self.assertLess(cell["stress_net"], cell["base_net"])

    def test_zero_lookahead_execution(self):
        """Signal on bar i fill occurs strictly at bar i+1 open."""
        h = HOUR_MS
        ts = tuple(i * h for i in range(5))
        # Entry signal on bar 2 fills at bar 3. Exit signal on bar 3 fills at bar 4.
        exact = hsse3.ExactSeries(
            "BTCUSDT", ts, ("100", "100", "110", "110", "120"), ("100", "100", "110", "110", "120")
        )
        signal = hsse2.SearchSeries(
            "BTCUSDT", ts, (100.0, 100.0, 110.0, 110.0, 120.0), (100.0, 100.0, 110.0, 110.0, 120.0)
        )
        short = array("d", [math.nan, 1.0, 2.0, 1.0, 1.0])
        long = array("d", [math.nan, 2.0, 1.0, 2.0, 2.0])

        res = g._simulate_cell(
            signal=signal,
            exact=exact,
            short_values=short,
            long_values=long,
            start_ms=0,
            end_ms=5 * h,
            policy=self.policy,
            decisions={},
            condition=vsp.CONDITIONS[0],
        )
        self.assertEqual(res["entry_signals"], 1)
        self.assertEqual(res["entry_fills"], 1)
        self.assertEqual(res["completed_trades"], 1)

    def test_missing_fill_bar_fails_closed(self):
        h = HOUR_MS
        ts = (0, h, 2 * h, 4 * h)  # Missing bar at 3*h where fill is expected
        exact = hsse3.ExactSeries("BTCUSDT", ts, ("100",) * 4, ("100",) * 4)
        signal = hsse2.SearchSeries("BTCUSDT", ts, (100.0,) * 4, (100.0,) * 4)

        with self.assertRaisesRegex(g.Gen2DownsideError, "fill bar missing"):
            g._simulate_cell(
                signal=signal,
                exact=exact,
                short_values=array("d", [math.nan, 1, 2, 2]),
                long_values=array("d", [math.nan, 2, 1, 1]),
                start_ms=0,
                end_ms=5 * h,
                policy=self.policy,
                decisions={},
                condition=vsp.CONDITIONS[0],
            )

    def test_exposed_gap_poisons_month_and_carries_scale(self):
        jan = 1577836800000
        feb = g._next_month(jan)
        # Gap between jan+1h and jan+4h while position is 1
        ts = (jan, jan + HOUR_MS, jan + 4 * HOUR_MS)
        exact = hsse3.ExactSeries("BTCUSDT", ts, ("100",) * 3, ("100",) * 3)

        months, exposed = g._monthly_inputs(
            exact=exact, positions=(0, 1, 1), start_ms=jan, end_ms=feb
        )
        self.assertEqual(exposed, 1)
        self.assertIsNone(months[jan])

    def _make_eval_cell(self, trades: int, base_net: Decimal, stress_net: Decimal, dd: Decimal, min_scale: Decimal = D("0.8")):
        cell_a = {
            "completed_trades": trades, "entry_signals": trades,
            "base_net": base_net, "stress_net": stress_net,
            "maximum_drawdown": dd, "drawdown": dd,
            "rebalances": 0, "rebalance_notional": D(0),
            "scaled_entries": 0, "active_hours": 100, "notional_exposure": D(1000),
            "average_active_notional_quote": D(10),
            "pnl_over_average_active_notional_base": base_net / D(10),
            "pnl_over_average_active_notional_stress": stress_net / D(10),
            "expectancy_base": D("0.1"), "profit_factor_base": D("1.2"),
            "minimum_scale": D(1),
        }
        cell_b = {
            "completed_trades": trades, "entry_signals": trades,
            "base_net": base_net + D("5"), "stress_net": stress_net + D("3"),
            "maximum_drawdown": dd - D("0.01"), "drawdown": dd - D("0.01"),
            "rebalances": 1, "rebalance_notional": D(10),
            "scaled_entries": 1, "active_hours": 100, "notional_exposure": D(800),
            "average_active_notional_quote": D(8),
            "pnl_over_average_active_notional_base": (base_net + D("5")) / D(8),
            "pnl_over_average_active_notional_stress": (stress_net + D("3")) / D(8),
            "expectancy_base": D("0.12"), "profit_factor_base": D("1.25"),
            "minimum_scale": min_scale,
        }
        return {
            "arm_a_control": cell_a,
            "arm_b_scaled": cell_b,
            "decision_counts": {"valid_new_scale_decisions": 4, "carried_scale_decisions": 1},
        }

    def test_pass_with_unresolved_blockers_is_impossible(self):
        """Focused Test 1: Even if all economic gates pass, presence of blockers forces BLOCKED and proposal_count=0."""
        protocol, _, _ = vsp.validate_protocol()
        evals = {
            "BTCUSDT": self._make_eval_cell(trades=35, base_net=D(20), stress_net=D(10), dd=D("0.05")),
            "ETHUSDT": self._make_eval_cell(trades=40, base_net=D(25), stress_net=D(12), dd=D("0.04")),
        }
        res = vsp.adjudicate_universe(evals, protocol)

        # Must NOT be PASS! Must be BLOCKED with proposal_count = 0
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["proposal_count"], 0)
        self.assertGreater(len(res["blockers"]), 0)
        self.assertTrue(any("UNRESOLVED_EVALUATION_BLOCKER" in b for b in res["blockers"]))

    def test_zero_scale_decisions_cannot_pass(self):
        """Focused Test 2: If valid + carried scale decisions = 0, status must be INSUFFICIENT_EVIDENCE and proposal_count=0."""
        protocol, _, _ = vsp.validate_protocol()
        evals = {
            "BTCUSDT": self._make_eval_cell(trades=35, base_net=D(20), stress_net=D(10), dd=D("0.05")),
            "ETHUSDT": self._make_eval_cell(trades=40, base_net=D(25), stress_net=D(12), dd=D("0.04")),
        }
        # Zero scale decisions
        evals["BTCUSDT"]["decision_counts"] = {"valid_new_scale_decisions": 0, "carried_scale_decisions": 0}
        evals["ETHUSDT"]["decision_counts"] = {"valid_new_scale_decisions": 0, "carried_scale_decisions": 0}

        res = vsp.adjudicate_universe(evals, protocol)
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res["proposal_count"], 0)
        self.assertTrue(any("ZERO_SCALE_DECISIONS_EVALUATED" in r for r in res["verdict_reasons"]))

    def test_protocol_mismatch_must_fail_closed(self):
        """Focused Test 3: Passing mismatched or invalid protocol to adjudication must raise VolScalePreregError."""
        evals = {
            "BTCUSDT": self._make_eval_cell(trades=35, base_net=D(20), stress_net=D(10), dd=D("0.05")),
            "ETHUSDT": self._make_eval_cell(trades=40, base_net=D(25), stress_net=D(12), dd=D("0.04")),
        }
        # Not a dict
        with self.assertRaisesRegex(vsp.VolScalePreregError, "protocol must be a dictionary"):
            vsp.adjudicate_universe(evals, "not_a_protocol")

        # Wrong protocol_id or altered protocol
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Altered in-memory protocol rejected"):
            vsp.adjudicate_universe(evals, {"schema": "YATL_VOL_SCALE_PREREG_PROTOCOL", "protocol_id": "WRONG_ID"})

        # Wrong candidate_id or altered protocol
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Altered in-memory protocol rejected"):
            vsp.adjudicate_universe(evals, {
                "schema": "YATL_VOL_SCALE_PREREG_PROTOCOL",
                "protocol_id": "YATL-PREREG-VOL-SCALE-001",
                "candidate_id": "WRONG_CANDIDATE",
            })

    def test_missing_mandatory_metrics_cannot_pass(self):
        """Focused Test 4: Missing mandatory metrics (e.g. expectancy or profit_factor) must cause FAIL and proposal_count=0."""
        protocol, _, _ = vsp.validate_protocol()
        evals = {
            "BTCUSDT": self._make_eval_cell(trades=35, base_net=D(20), stress_net=D(10), dd=D("0.05")),
            "ETHUSDT": self._make_eval_cell(trades=40, base_net=D(25), stress_net=D(12), dd=D("0.04")),
        }
        # Delete mandatory expectancy metric from BTC Arm B
        del evals["BTCUSDT"]["arm_b_scaled"]["expectancy_base"]

        res = vsp.adjudicate_universe(evals, protocol)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["proposal_count"], 0)
        self.assertTrue(any("MISSING_MANDATORY_METRIC:BTCUSDT:arm_b_scaled:expectancy_base" in r for r in res["verdict_reasons"]))

    def test_end_to_end_simulator_output_reaches_adjudication_without_schema_mismatch(self):
        """Task A: End-to-end synthetic test using actual run_two_arm_single_symbol output.

        Confirms genuine simulator output reaches adjudication without naming/schema mismatch
        (expectancy_base, profit_factor_base, maximum_drawdown correctly mapped).
        """
        start_ms = 1577836800000
        exact_btc, signal_btc = self._build_synthetic_series("BTCUSDT", n_bars=750, start_ms=start_ms)
        exact_eth, signal_eth = self._build_synthetic_series("ETHUSDT", n_bars=750, start_ms=start_ms)

        res_btc = vsp.run_two_arm_single_symbol(
            signal=signal_btc,
            exact=exact_btc,
            warmup_start_ms=start_ms,
            first_managed_ms=start_ms + 31 * 24 * HOUR_MS,
            scored_start_ms=start_ms,
            end_ms=start_ms + 750 * HOUR_MS,
            policy=self.policy,
        )
        res_eth = vsp.run_two_arm_single_symbol(
            signal=signal_eth,
            exact=exact_eth,
            warmup_start_ms=start_ms,
            first_managed_ms=start_ms + 31 * 24 * HOUR_MS,
            scored_start_ms=start_ms,
            end_ms=start_ms + 750 * HOUR_MS,
            policy=self.policy,
        )

        protocol, _, _ = vsp.validate_protocol()
        evals = {"BTCUSDT": res_btc, "ETHUSDT": res_eth}
        adjudication = vsp.adjudicate_universe(evals, protocol)

        # Confirm that NO MISSING_MANDATORY_METRIC error exists
        missing_metric_errors = [
            r for r in adjudication["verdict_reasons"] if "MISSING_MANDATORY_METRIC" in r
        ]
        self.assertEqual(missing_metric_errors, [])

        # In this synthetic run with 2 trades, status is INSUFFICIENT_EVIDENCE purely due to trade count
        self.assertEqual(adjudication["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(adjudication["proposal_count"], 0)
        self.assertTrue(any("INSUFFICIENT_TRADES" in r for r in adjudication["verdict_reasons"]))

    def test_removing_unresolved_blockers_from_copied_protocol_fails_closed(self):
        """Task B: Removing unresolved blockers from an in-memory copied protocol must fail closed

        and can never produce PASS.
        """
        import copy
        canonical_protocol, _, _ = vsp.validate_protocol()

        # Copy protocol and mutate it by deleting all blockers
        tampered_protocol = copy.deepcopy(canonical_protocol)
        tampered_protocol["evidence_and_gates"]["unimplemented_benchmarks_and_risk_metrics"] = {}

        evals = {
            "BTCUSDT": self._make_eval_cell(trades=35, base_net=D(20), stress_net=D(10), dd=D("0.05")),
            "ETHUSDT": self._make_eval_cell(trades=40, base_net=D(25), stress_net=D(12), dd=D("0.04")),
        }

        # Passing the altered in-memory protocol MUST raise VolScalePreregError
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Altered in-memory protocol rejected"):
            vsp.adjudicate_universe(evals, tampered_protocol)

    def test_cli_and_direct_execution_cannot_load_market_data(self):
        """Focused Test 5: Neither CLI nor direct helper invocation can load historical market data."""
        # CLI validate-only works
        self.assertEqual(vsp.main(["--validate-protocol-only"]), 0)

        # CLI without validate-only refuses market data execution
        self.assertEqual(vsp.main([]), 1)

        # Direct helper check blocks market data
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Market data execution path is currently disabled"):
            vsp.check_execution_prerequisites(allow_market_data=True)

        # Direct market data loader raises
        with self.assertRaisesRegex(vsp.VolScalePreregError, "Market data loading is disabled and locked"):
            vsp.load_market_data()

    def test_enrich_arm_does_not_fabricate_zero_when_metrics_missing(self):
        """Final 3-field safety check: enrich_arm must NOT fabricate ZERO when expectancy,

        profit_factor, or drawdown are absent from the cell. Missing metrics must cause FAIL.
        """
        start_ms = 1577836800000
        exact, signal = self._build_synthetic_series("BTCUSDT", n_bars=750, start_ms=start_ms)

        # Mock g._simulate_cell to return cells without expectancy, profit_factor, or drawdown
        def mock_simulate(*args, **kwargs):
            return {
                "completed_trades": 35, "entry_signals": 35,
                "base_net": D(20), "stress_net": D(10),
                "rebalances": 0, "rebalance_notional": D(0),
                "scaled_entries": 0, "active_hours": 100, "notional_exposure": D(1000),
                "minimum_scale": D(1), "mean_scale": D(1), "median_scale": D(1),
                # Note: expectancy, profit_factor, drawdown deliberately omitted
            }

        with patch.object(vsp.g, "_simulate_cell", side_effect=mock_simulate):
            res_btc = vsp.run_two_arm_single_symbol(
                signal=signal,
                exact=exact,
                warmup_start_ms=start_ms,
                first_managed_ms=start_ms + 31 * 24 * HOUR_MS,
                scored_start_ms=start_ms,
                end_ms=start_ms + 750 * HOUR_MS,
                policy=self.policy,
            )

        # Confirm that enrich_arm did NOT fabricate numeric ZERO values
        self.assertNotIn("expectancy_base", res_btc["arm_a_control"])
        self.assertNotIn("profit_factor_base", res_btc["arm_a_control"])
        self.assertNotIn("maximum_drawdown", res_btc["arm_a_control"])

        # When passed to adjudicate_universe, missing metrics must be detected and prevent qualification
        evals = {
            "BTCUSDT": res_btc,
            "ETHUSDT": res_btc,
        }
        protocol, _, _ = vsp.validate_protocol()
        adj = vsp.adjudicate_universe(evals, protocol)
        self.assertEqual(adj["status"], "FAIL")
        self.assertEqual(adj["proposal_count"], 0)
        reasons = adj["verdict_reasons"]
        self.assertTrue(any("MISSING_MANDATORY_METRIC:BTCUSDT:arm_a_control:expectancy_base" in r for r in reasons))
        self.assertTrue(any("MISSING_MANDATORY_METRIC:BTCUSDT:arm_a_control:profit_factor_base" in r for r in reasons))
        self.assertTrue(any("MISSING_MANDATORY_METRIC:BTCUSDT:arm_a_control:maximum_drawdown" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
