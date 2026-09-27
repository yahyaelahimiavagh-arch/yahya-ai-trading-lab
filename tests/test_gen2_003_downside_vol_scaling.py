import math
import tempfile
import unittest
from array import array
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from research.generation_2 import downside_vol_scaling as g
from research.generation_2 import vol_scaling as shared
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2

D = Decimal


class Gen2DownsideTests(unittest.TestCase):
    def test_frozen_identity_and_no_market_read_on_validation(self):
        with patch.object(g.controls, "_load_control_corpus", side_effect=AssertionError("market read")):
            p, sha, freeze = g.validate_protocol()
        self.assertEqual(sha, g.PROTOCOL_SHA256)
        self.assertEqual(len(freeze["survivors"]), 6)
        self.assertEqual(p["trial_matrix"]["conditions"], list(g.CONDITIONS))
        self.assertFalse(p["development_scope"]["fresh_oos_read_allowed"])
        self.assertFalse(p["development_scope"]["recent_reserve_read_allowed"])
        self.assertFalse(p["p10_read"])
        self.assertEqual(g.main(["--validate-protocol-only"]), 0)

    def test_protocol_mutation_rejected_before_bound_data(self):
        with patch.object(Path, "read_bytes", return_value=b'{}'):
            with self.assertRaisesRegex(g.Gen2DownsideError, "SHA-256"):
                g.validate_protocol()

    def test_total_and_sparse_downside_exact(self):
        # Three negatives uses current month. Two negatives uses prior month too.
        jan = 1577836800000
        feb = g._next_month(jan)
        mar = g._next_month(feb)
        months = {jan:(D("0"), [D("-0.1"),D("0.2"),D("-0.3")]),
                  feb:(D("0"), [D("-0.2"),D("0.1")]),
                  mar:None}
        est = g._estimators(months)
        self.assertAlmostEqual(est["total"][jan], D("0.14").sqrt())
        self.assertAlmostEqual(est["downside"][feb], D("0.14").sqrt())
        self.assertIsNone(est["total"][mar])
        self.assertIsNone(est["downside"][mar])

    def test_expanding_prior_only_and_carry_without_new_pair(self):
        start = 1577836800000
        keys = [start]
        for _ in range(9): keys.append(g._next_month(keys[-1]))
        months = {t:(D(i+1)/100,[D("-0.01")]*3) for i,t in enumerate(keys[:-1])}
        e = {v:{t:D("0.1") + D(i)/100 for i,t in enumerate(keys[:-1])} for v in ("total","downside")}
        schedules, counters = g._schedule(months=months,estimators=e,first_managed_ms=keys[1],
                                           scored_start_ms=keys[7],end_ms=keys[-1],minimum_pairs=6)
        self.assertEqual(counters["total"]["valid_new_scale_decisions"], 2)
        self.assertEqual(counters["total"]["carried_scale_decisions"], 0)
        self.assertTrue(schedules["total"][keys[7]]["new"])
        self.assertTrue(schedules["total"][keys[8]]["new"])
        e["total"][keys[8]] = None
        # No t-month sigma may affect t decision; missing sigma for t+1 carries.
        later, _ = g._schedule(months=months,estimators=e,first_managed_ms=keys[1],
                               scored_start_ms=keys[7],end_ms=keys[-1],minimum_pairs=6)
        self.assertEqual(later["total"], schedules["total"])

    def test_exposed_gap_poison_month_without_price_fill(self):
        jan = 1577836800000
        feb = g._next_month(jan)
        # Deliberately sparse synthetic series; exposed gap counted, no daily return invented.
        ts = (jan,jan+g.shared.HOUR_MS,jan+4*g.shared.HOUR_MS)
        exact = hsse3.ExactSeries("BTCUSDT",ts,("100",)*3,("100",)*3)
        months, exposed = g._monthly_inputs(exact=exact,positions=(0,1,1),start_ms=jan,end_ms=feb)
        self.assertEqual(exposed,1)
        self.assertIsNone(months[jan])

    def test_boundary_rebalance_only_delta_and_costs(self):
        h = shared.HOUR_MS
        ts = tuple(i*h for i in range(-4,5))
        exact = hsse3.ExactSeries("BTCUSDT",ts,("100",)*len(ts),("100",)*len(ts))
        signal = hsse2.SearchSeries("BTCUSDT",ts,(100.0,)*len(ts),(100.0,)*len(ts))
        short = array("d",[math.nan,1,2,2,2,2,2,2,2])
        long = array("d",[math.nan,2,1,1,1,1,1,1,1])
        policy = {"base_quantity":"0.001","initial_equity_quote":"10000",
                  "base_fee_bps":10,"base_adverse_slippage_bps":5,
                  "stress_fee_bps":20,"stress_adverse_slippage_bps":10}
        decisions = {-2678400000:{"scale":D(1),"new":False}, 0:{"scale":D("0.5"),"new":True}}
        cell = g._simulate_cell(signal=signal,exact=exact,short_values=short,long_values=long,
                                start_ms=-4*h,end_ms=5*h,policy=policy,decisions=decisions,condition=g.CONDITIONS[2])
        control = g._simulate_cell(signal=signal,exact=exact,short_values=short,long_values=long,
                                   start_ms=-4*h,end_ms=5*h,policy=policy,decisions={},condition=g.CONDITIONS[0])
        self.assertEqual(cell["entry_signals"], control["entry_signals"])
        self.assertEqual(cell["entry_fills"], 1)
        self.assertEqual(cell["rebalances"], 1)
        self.assertEqual(cell["rebalance_notional"], D("0.05"))
        self.assertLess(cell["base_net"], D(0))
        self.assertLess(cell["stress_net"], cell["base_net"])

    def test_missing_execution_fill_fails_closed(self):
        h = shared.HOUR_MS
        ts = (0,h,2*h,4*h)
        exact = hsse3.ExactSeries("BTCUSDT",ts,("100",)*4,("100",)*4)
        signal = hsse2.SearchSeries("BTCUSDT",ts,(100.0,)*4,(100.0,)*4)
        policy = {"base_quantity":"0.001","initial_equity_quote":"10000",
                  "base_fee_bps":10,"base_adverse_slippage_bps":5,
                  "stress_fee_bps":20,"stress_adverse_slippage_bps":10}
        with self.assertRaisesRegex(g.Gen2DownsideError,"fill bar missing"):
            g._simulate_cell(signal=signal,exact=exact,short_values=array("d",[math.nan,1,2,2]),
                             long_values=array("d",[math.nan,2,1,1]),start_ms=0,end_ms=5*h,
                             policy=policy,decisions={},condition=g.CONDITIONS[0])

    def test_all_18_registered_conditions_and_proposal_gates_synthetic(self):
        protocol, _, freeze = g.validate_protocol()
        rows = []
        for survivor in freeze["survivors"]:
            for index, condition in enumerate(g.CONDITIONS):
                rows.append({"frozen_id":survivor["frozen_id"],"condition":condition,
                    "base_net":D(index+1),"stress_net":D(index+1),
                    "maximum_drawdown":D("0.03")-D(index)/100,
                    "minimum_active_scale":D("0.5") if index else D(1),
                    "scaled_entry_count":1 if index else 0,
                    "monthly_rebalance_count":0,"active_hours":10,
                    "notional_exposure":D(5) if index else D(10),
                    "entry_signals":2,"completed_trades":2,
                    "valid_new_scale_decision_fraction":D(1),
                    "cells":[{"profit_factor_infinite":False}]})
        result = g._adjudicate(rows,protocol)
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(len(result["comparisons"]),12)
        rows[2]["notional_exposure"] = D(1)
        fail = g._adjudicate(rows,protocol)
        self.assertEqual(fail["status"],"FAIL")
        self.assertTrue(any(x.startswith("OPPORTUNITY_PRESERVATION_FAILED") for x in fail["failure_reasons"]))

    def test_run_is_bound_to_only_registered_development_manifest(self):
        protocol, _, _ = g.validate_protocol()
        binding = protocol["bindings"]["development_quality_manifest"]
        def reject(**kwargs):
            self.assertEqual(kwargs["quality_manifest_relative_path"],binding["relative_path"])
            self.assertEqual(kwargs["quality_manifest_file_sha256"],binding["file_sha256"])
            raise g.controls.ControlError("synthetic stop before market read")
        with patch.object(g.controls,"_load_control_corpus",side_effect=reject):
            with self.assertRaisesRegex(g.Gen2DownsideError,"synthetic stop"):
                g.run(runtime_root=Path("/tmp/nonexistent-gen2-003"))

    def test_no_run_reads_p10_fresh_or_recent(self):
        with patch.object(g.controls,"_load_control_corpus",side_effect=AssertionError("market access")):
            g.validate_protocol()
            g._estimators({0:(D("0.1"),[D("-0.01")]*3)})


if __name__ == "__main__": unittest.main()
