import inspect, json, unittest
from pathlib import Path
from research.historical_strategy_search import crisis_regime_certification as h5

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/research/historical-strategy-search/HSSE-005-CRISIS-REGIME-CERTIFICATION-PROTOCOL-v0.1.0.json"

class HSSE005Tests(unittest.TestCase):
    def test_protocol_is_frozen_before_outcome_access(self):
        p,d,a,f=h5.load_protocol(PROTOCOL)
        self.assertEqual(len(p["certification_units"]),8)
        self.assertEqual(len(f["survivors"]),6)
        self.assertEqual(a["result"]["pass_count"],6)
        self.assertFalse(p["exclusions"]["audit_holdout_read"])
        self.assertEqual(len(d),64)

    def test_audit_holdout_and_quarantined_events_are_excluded(self):
        p,_,_,_=h5.load_protocol(PROTOCOL)
        used={e for u in p["certification_units"] for e in u["event_ids"]}
        for eid in ("CRL-E010","CRL-E012","CRL-E013","CRL-E014","CRL-E015"):
            self.assertNotIn(eid,used)

    def test_units_end_before_audit_holdout(self):
        p,_,_,_=h5.load_protocol(PROTOCOL)
        self.assertTrue(all(u["semantic_end_exclusive_utc"]<="2025-01-01T00:00:00Z" for u in p["certification_units"]))

    def test_runner_has_no_network_or_live_authority(self):
        src=inspect.getsource(h5)
        for forbidden in ("urllib.request","requests","httpx","aiohttp","websockets","/api/v3/order","/fapi","/dapi","API_KEY","API_SECRET","os.environ","os.getenv","RiskAuthorization"):
            with self.subTest(forbidden=forbidden): self.assertNotIn(forbidden,src)

if __name__=="__main__": unittest.main()
