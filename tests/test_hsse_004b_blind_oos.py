import inspect, json, tempfile, unittest
from pathlib import Path
from research.crisis_lab import acquisition as acq
from research.historical_strategy_search import blind_protocol
from research.historical_strategy_search import blind_oos

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/research/historical-strategy-search/HSSE-004B-BLIND-OOS-PROTOCOL-v0.1.0.json"
REGISTER=ROOT/"docs/research/crisis-lab/DATA-ACQUISITION-REGISTER-v0.1.0.json"

class HSSE004BTests(unittest.TestCase):
    def test_protocol_binds_six_frozen_survivors_before_blind(self):
        p,d,f=blind_protocol.load_protocol(PROTOCOL)
        self.assertEqual(f["survivor_count"],6)
        self.assertEqual(p["data"]["event_id"],"HSSE-BLIND-OOS-001")
        self.assertEqual(p["execution"]["execution_count_per_frozen_survivor"],1)
        self.assertFalse(p["execution"]["reset_at_calendar_quarter_boundary"])
        self.assertEqual(len(d),64)

    def test_blind_acquisition_plan_has_warmup_and_exact_end(self):
        r=acq.load_acquisition_register(REGISTER)
        plan=acq.plan_event(r,"HSSE-BLIND-OOS-001")
        self.assertEqual(plan["designation"],"BLIND_HOLDOUT")
        self.assertTrue(plan["replay_eligible"])
        self.assertEqual(len(plan["datasets"]),6)
        for d in plan["datasets"]:
            self.assertEqual(d["semantic_start_utc"],"2022-11-01T00:00:00Z")
            self.assertEqual(d["semantic_end_utc"],"2025-01-01T00:00:00Z")

    def test_protocol_rejects_parameter_change_permission(self):
        p=json.loads(PROTOCOL.read_text(encoding="utf-8"))
        p["decision"]["no_parameter_change"]=False
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"p.json"; path.write_text(json.dumps(p),encoding="utf-8")
            with self.assertRaises(blind_protocol.HSSEBlindError): blind_protocol.load_protocol(path)

    def test_runner_has_no_network_or_live_execution_authority(self):
        src=inspect.getsource(blind_oos)
        for forbidden in ("requests","httpx","aiohttp","websockets","urllib.request","/api/v3/order","/fapi","/dapi","API_KEY","API_SECRET","os.environ","os.getenv","RiskAuthorization"):
            with self.subTest(forbidden=forbidden): self.assertNotIn(forbidden,src)

if __name__=="__main__": unittest.main()
