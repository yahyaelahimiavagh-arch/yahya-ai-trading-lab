import json
import math
import unittest
from array import array
from decimal import Decimal, localcontext
from pathlib import Path

from research.generation_2 import vol_scaling as g2
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs"/"research"/"generation-2"/"GEN2-002-VOL-SCALING-PROTOCOL-v0.1.0.json"

class Gen2VolScalingTests(unittest.TestCase):
    def test_protocol_is_bound_safe_and_still_pre_performance(self):
        p,sha,freeze,hsse=g2.validate_protocol(PROTOCOL)
        self.assertEqual(len(sha),64)
        self.assertEqual(len(freeze["survivors"]),6)
        self.assertEqual(hsse["protocol_id"],"HSSE-001-SEARCH-PROTOCOL")
        self.assertEqual(p["trial_matrix"]["total_conditions"],12)
        self.assertEqual(len(p["development_scope"]["development_folds"]),5)
        self.assertFalse(p["development_scope"]["fresh_oos_read_allowed"])
        self.assertFalse(p["pre_performance_binding_amendment"]["outcome_accessed"])
        self.assertFalse(p["pre_performance_binding_amendment"]["parameter_changes"])
        self.assertFalse(p["p10_write_allowed"])
        self.assertTrue(p["p11_locked"])

    def test_scale_uses_exact_prior_183_days_and_caps_at_one(self):
        boundary=20000*g2.DAY_MS
        daily={boundary-i*g2.DAY_MS:Decimal("0.01") for i in range(1,184)}
        scale=g2._scale_from_returns(daily,boundary_ms=boundary)
        with localcontext() as ctx:
            ctx.prec=hsse3.DECIMAL_PRECISION
            expected=Decimal("0.12")/(Decimal(365)*Decimal("0.0001")).sqrt()
        self.assertEqual(scale,expected)
        low={boundary-i*g2.DAY_MS:Decimal("0.0001") for i in range(1,184)}
        self.assertEqual(g2._scale_from_returns(low,boundary_ms=boundary),Decimal(1))

    def test_scale_fails_closed_on_missing_day(self):
        boundary=20000*g2.DAY_MS
        daily={boundary-i*g2.DAY_MS:Decimal("0.01") for i in range(1,184) if i!=17}
        with self.assertRaises(g2.Gen2VolError):
            g2._scale_from_returns(daily,boundary_ms=boundary)

    def test_required_fill_gap_fails_closed(self):
        times=(0,g2.HOUR_MS,2*g2.HOUR_MS,4*g2.HOUR_MS)
        opens=("100","100","100","100")
        closes=("100","100","101","102")
        signal=hsse2.SearchSeries("BTCUSDT",times,tuple(map(float,opens)),tuple(map(float,closes)))
        exact=hsse3.ExactSeries("BTCUSDT",times,opens,closes)
        short=array("d",[math.nan,1,2,2])
        long=array("d",[math.nan,2,1,1])
        policy={
            "base_quantity":"0.001","initial_equity_quote":"10000",
            "base_fee_bps":10,"base_adverse_slippage_bps":5,
            "stress_fee_bps":20,"stress_adverse_slippage_bps":10,
        }
        with self.assertRaises(g2.Gen2VolError):
            g2._simulate_cell(
                signal=signal,exact=exact,short_values=short,long_values=long,
                start_ms=0,end_ms=5*g2.HOUR_MS,policy=policy,scaled=True,
                scale_schedule={0:Decimal("0.5")},
            )

    def test_variable_quantity_accounting_keeps_one_directional_cycle(self):
        a=g2._new_account(Decimal("10000"))
        g2._buy(a,reference=Decimal("100"),quantity=Decimal("0.001"),fee_bps=Decimal("10"),slippage_bps=Decimal("5"),start_cycle=True)
        g2._sell(a,reference=Decimal("110"),quantity=Decimal("0.0005"),fee_bps=Decimal("10"),slippage_bps=Decimal("5"),close_cycle=False)
        self.assertEqual(len(a.realized),0)
        self.assertEqual(a.quantity,Decimal("0.0005"))
        g2._sell(a,reference=Decimal("120"),quantity=a.quantity,fee_bps=Decimal("10"),slippage_bps=Decimal("5"),close_cycle=True)
        self.assertEqual(len(a.realized),1)
        self.assertEqual(a.quantity,Decimal(0))
        self.assertIsNone(a.cycle_cashflow)

    def test_scaled_signal_path_does_not_create_new_directional_signal(self):
        times=tuple(i*g2.HOUR_MS for i in range(8))
        opens=("100","100","100","100","100","100","100","100")
        closes=("100","100","101","102","103","104","103","102")
        signal=hsse2.SearchSeries("BTCUSDT",times,tuple(map(float,opens)),tuple(map(float,closes)))
        exact=hsse3.ExactSeries("BTCUSDT",times,opens,closes)
        short=array("d",[math.nan,1,2,2,2,2,1,1])
        long=array("d",[math.nan,2,1,1,1,1,2,2])
        policy={
            "base_quantity":"0.001","initial_equity_quote":"10000",
            "base_fee_bps":10,"base_adverse_slippage_bps":5,
            "stress_fee_bps":20,"stress_adverse_slippage_bps":10,
        }
        schedule={0:Decimal("0.5")}
        r=g2._simulate_cell(
            signal=signal,exact=exact,short_values=short,long_values=long,
            start_ms=0,end_ms=8*g2.HOUR_MS,policy=policy,scaled=True,
            scale_schedule=schedule,
        )
        self.assertEqual(r["underlying_entry_signals"],1)
        self.assertEqual(r["entry_fills"],1)
        self.assertEqual(r["completed_trades"],1)
        self.assertEqual(r["scaled_entry_count"],1)
        self.assertFalse(r["open_position_at_end"])

    def test_source_has_no_network_live_secret_or_order_capability(self):
        source=(ROOT/"research"/"generation_2"/"vol_scaling.py").read_text(encoding="utf-8")
        for forbidden in (
            "requests","httpx","aiohttp","websockets","api_key","api_secret",
            "/api/v3/order","/fapi","/dapi","os.environ","os.getenv"
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
