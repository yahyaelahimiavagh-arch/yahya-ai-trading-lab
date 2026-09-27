import hashlib
import tempfile
import unittest
from pathlib import Path
from mcf_fixtures import family,bars
from research.mass_candidate_factory.models import EvidenceBinding,MCFError,safe_path
from research.mass_candidate_factory.feature_cache import FeatureCache
from research.mass_candidate_factory.manifest import validate
from research.mass_candidate_factory.screening import screen
from research.mass_candidate_factory.generator import write_batch
from research.mass_candidate_factory.shards import finalize
class SafetyTest(unittest.TestCase):
    def test_sealed_paths_and_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);good=root/"quality.json";good.write_text("{}")
            sha=hashlib.sha256(good.read_bytes()).hexdigest()
            self.assertEqual(EvidenceBinding(root,"quality.json",sha,"SYNTHETIC").validate(),good)
            for name in ("../escape","p10/state.json","fresh_oos/data","recent-reserve/data","/tmp/x"):
                with self.assertRaises(MCFError):safe_path(root,name)
            (root/"link").symlink_to(good)
            with self.assertRaises(MCFError):safe_path(root,"link")
            with self.assertRaises(MCFError):EvidenceBinding(root,"quality.json","0"*64,"SYNTHETIC").validate()
    def test_no_capabilities(self):
        for key,value in (("futures",True),("leverage",True),("short",True),("live_execution",True),("order_endpoint",True),("ai_direct_execution",True),("p10_write_allowed",True)):
            m=family();m["safety"][key]=value
            with self.assertRaises(MCFError):validate(m)
        b=bars();b=type(b)(**{**vars(b),"partition":"FRESH_OOS"})
        with self.assertRaises(MCFError):FeatureCache(b)
    def test_p10_write_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"p10";root.mkdir()
            with self.assertRaises(MCFError):write_batch(root,{},[],[])
            with self.assertRaises(MCFError):finalize(root,{"start":0,"end":0,"shard_id":"x"},[])
    def test_unbound_screening_and_cost_rejected(self):
        args=((False,False,False),(10,11,12),(10,11,12),__import__("mcf_fixtures").policy())
        with self.assertRaises(MCFError):screen(*args,cost_policy_ref="COST/v1",thresholds={},folds=((0,3),))
        with self.assertRaises(MCFError):screen(*args,cost_policy_ref="OPTIMISTIC/v1",thresholds={},folds=((0,3),),fixture_id="SYNTHETIC-001")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"quality.json";p.write_text("{}")
            binding=EvidenceBinding(Path(d),"quality.json",hashlib.sha256(p.read_bytes()).hexdigest(),"DEV-001")
            with self.assertRaises(MCFError):screen(*args,cost_policy_ref="COST/v1",thresholds={},folds=((0,3),),evidence=binding)
