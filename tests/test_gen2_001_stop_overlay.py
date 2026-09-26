import json
import math
import unittest
from array import array
from pathlib import Path

from research.generation_2 import stop_overlay as g2
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs"/"research"/"generation-2"/"GEN2-001-STOP-OVERLAY-PROTOCOL-v0.1.0.json"

class Gen2StopOverlayTests(unittest.TestCase):
    def test_protocol_is_fully_bound_and_safe(self):
        p, sha, freeze, hsse = g2.validate_protocol(PROTOCOL)
        self.assertEqual(len(sha),64)
        self.assertEqual(len(freeze["survivors"]),6)
        self.assertEqual(len(hsse["development_cross_validation"]["folds"]),5)
        self.assertEqual(p["trial_matrix"]["total_conditions"],36)
        self.assertFalse(p["development_scope"]["fresh_oos_read_allowed"])
        self.assertTrue(p["evidence_attribution"]["source_candidate_is_not_claimed_reproduced"])
        self.assertEqual(p["evidence_attribution"]["tested_object_id"],"GEN2-ADAPT-0001-STOP-OVERLAY")
        self.assertFalse(p["p10_write_allowed"])
        self.assertTrue(p["p11_locked"])

    def test_synthetic_stop_triggers_next_open_and_closes_trade(self):
        times=tuple(i*g2.HOUR_MS for i in range(8))
        opens=("100","100","100","100","100","84","84","84")
        closes=("100","100","100","100","85","84","84","84")
        signal=hsse2.SearchSeries("BTCUSDT",times,tuple(map(float,opens)),tuple(map(float,closes)))
        exact=hsse3.ExactSeries("BTCUSDT",times,opens,closes)
        short=array("d",[math.nan,1,2,2,2,2,2,2])
        long=array("d",[math.nan,2,1,1,1,1,1,1])
        policy={
            "quantity":"0.001","initial_equity_quote":"10000",
            "base_fee_bps":10,"base_adverse_slippage_bps":5,
            "stress_fee_bps":20,"stress_adverse_slippage_bps":10,
        }
        r=g2._simulate_cell(
            signal=signal,exact=exact,short_values=short,long_values=long,
            start_ms=0,end_ms=8*g2.HOUR_MS,threshold_percent=10,policy=policy
        )
        self.assertEqual(r["entry_fills"],1)
        self.assertEqual(r["stop_exit_fills"],1)
        self.assertEqual(r["completed_trades"],1)
        self.assertFalse(r["open_position_at_end"])

    def test_control_has_no_stop_exit(self):
        times=tuple(i*g2.HOUR_MS for i in range(8))
        opens=("100","100","100","100","100","84","84","84")
        closes=("100","100","100","100","85","84","84","84")
        signal=hsse2.SearchSeries("BTCUSDT",times,tuple(map(float,opens)),tuple(map(float,closes)))
        exact=hsse3.ExactSeries("BTCUSDT",times,opens,closes)
        short=array("d",[math.nan,1,2,2,2,2,2,2])
        long=array("d",[math.nan,2,1,1,1,1,1,1])
        policy={
            "quantity":"0.001","initial_equity_quote":"10000",
            "base_fee_bps":10,"base_adverse_slippage_bps":5,
            "stress_fee_bps":20,"stress_adverse_slippage_bps":10,
        }
        r=g2._simulate_cell(
            signal=signal,exact=exact,short_values=short,long_values=long,
            start_ms=0,end_ms=8*g2.HOUR_MS,threshold_percent=None,policy=policy
        )
        self.assertEqual(r["stop_exit_fills"],0)
        self.assertEqual(r["completed_trades"],0)
        self.assertTrue(r["open_position_at_end"])

    def test_source_has_no_network_live_or_secret_capability(self):
        source=(ROOT/"research"/"generation_2"/"stop_overlay.py").read_text(encoding="utf-8")
        for forbidden in ("requests","httpx","aiohttp","websockets","api_key","api_secret","/api/v3/order","/fapi","/dapi"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
