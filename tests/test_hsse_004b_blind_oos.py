import inspect, json, tempfile, unittest
from pathlib import Path
from research.crisis_lab import acquisition as acq
from research.historical_strategy_search import blind_protocol
from research.historical_strategy_search import blind_oos

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"docs/research/historical-strategy-search/HSSE-004B-BLIND-OOS-PROTOCOL-v0.1.0.json"
REGISTER=ROOT/"docs/research/historical-strategy-search/HSSE-004B-DATA-ACQUISITION-REGISTER-v0.1.0.json"
CRL_REGISTER=ROOT/"docs/research/crisis-lab/DATA-ACQUISITION-REGISTER-v0.1.0.json"

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

    def test_hsse_register_does_not_mutate_canonical_crl_catalog(self):
        crl=acq.load_acquisition_register(CRL_REGISTER)
        hsse=acq.load_acquisition_register(REGISTER)
        self.assertEqual(len(crl["events"]),16)
        self.assertEqual(len(hsse["events"]),1)
        self.assertEqual(hsse["events"][0]["event_id"],"HSSE-BLIND-OOS-001")
        self.assertNotIn("HSSE-BLIND-OOS-001",{e["event_id"] for e in crl["events"]})

    def test_protocol_rejects_parameter_change_permission(self):
        p=json.loads(PROTOCOL.read_text(encoding="utf-8"))
        p["decision"]["no_parameter_change"]=False
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"p.json"; path.write_text(json.dumps(p),encoding="utf-8")
            with self.assertRaises(blind_protocol.HSSEBlindError): blind_protocol.load_protocol(path)

    def test_blind_corpus_binding_is_exact_and_pre_replay(self):
        path=ROOT/"docs/research/historical-strategy-search/HSSE-004B-BLIND-CORPUS-BINDING-v0.1.0.json"
        record=json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["acquisition"]["manifest_file_sha256"],"978d8f51e6feeba7a313d9f4a9be1061ca8848e3bd709ae33ede4bc186b41c04")
        self.assertEqual(record["quality"]["manifest_file_sha256"],"e466c8249f8d9d70e0664b839093ffd9b564405427a3698dfdf7e6f9c6a0f8fd")
        self.assertTrue(record["quality"]["replay_admitted"])
        self.assertFalse(record["quality"]["market_outcomes_exposed"])
        self.assertEqual(record["allowed_next_action"],"ONE_TIME_HSSE004B_FROZEN_SURVIVOR_REPLAY")

    def test_runner_has_no_network_or_live_execution_authority(self):
        src=inspect.getsource(blind_oos)
        for forbidden in ("requests","httpx","aiohttp","websockets","urllib.request","/api/v3/order","/fapi","/dapi","API_KEY","API_SECRET","os.environ","os.getenv","RiskAuthorization"):
            with self.subTest(forbidden=forbidden): self.assertNotIn(forbidden,src)

if __name__=="__main__": unittest.main()
