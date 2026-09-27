import unittest
from mcf_fixtures import bars,policy
from research.mass_candidate_factory.feature_cache import FeatureCache
from research.mass_candidate_factory.operators import evaluate
from research.mass_candidate_factory.screening import screen,float_account
class ScreeningTest(unittest.TestCase):
    def test_cache_and_no_lookahead(self):
        b=bars();c=FeatureCache(b);a=c.get("MOVING_AVERAGE",window=2);self.assertEqual(a[0],None);self.assertEqual(a[1],10.5)
        self.assertIs(a,c.get("MOVING_AVERAGE",window=2));self.assertEqual(c.builds,1)
        s=evaluate({"operator":"GT","left":{"feature":"MOVING_AVERAGE","window":2},"right":11},c,{})
        self.assertFalse(s[0]);self.assertTrue(s[3])
        x=screen(s,b.opens,b.closes,policy(),cost_policy_ref="COST/v1",thresholds={"minimum_signals":1},folds=((0,4),(4,8)),fixture_id="SYNTHETIC-001")
        self.assertEqual(x,screen(s,b.opens,b.closes,policy(),cost_policy_ref="COST/v1",thresholds={"minimum_signals":1},folds=((0,4),(4,8)),fixture_id="SYNTHETIC-001"))
        self.assertIn(x["result_state"],("DEVELOPMENT_GATE_PASS","DEVELOPMENT_FAIL"))
        self.assertLess(float_account((True,False,False), (10,11,12),(10,11,12),policy())["net"],2)
